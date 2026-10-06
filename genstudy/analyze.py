"""From records to the paper's numbers: one row per run, tables, and study_macros.tex.

The analysis joins each run record (``runs/<model>.jsonl``) with its graphing
row (``graphs/<model>.jsonl``) and classifies the answer:

* ``no_formulation``: the notation gate failed, or the parser reported that the
  text states no formulation;
* ``accepted``: complete (Equation 3 of the paper) and coherent;
* ``incomplete``, ``incoherent``, ``both``: the structural failure classes;
* ``unparsed``: the parser's reply did not validate (an instrument failure,
  reported separately, never counted as a model failure);
* ``pending``: not graphed yet.

That is the classification fixed before the runs (pre-registered). The study
reports it, and since 2026-10-06 (docs/adr/0005) the **yield stage** of each run
next to it: the first check a run fails on the way to a usable MILP, with the
answer reduced to its coherent core (:func:`genstudy.metrics.core_model`) instead
of being rejected when it is not connected, and without the rule that every
variable must appear in two equations (:data:`STAGES`).

The parser's stored reply is parsed again with the current parser
(:func:`reparsed`), so a repair of the parsing step applies to every answer
already graphed without a new request; the metrics stored at graphing time are
only a cache. Everything here is deterministic: the same records produce the
same rows, tables and macros, byte for byte.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from genstudy.config import StudySpec
from genstudy.graphing import parse_reply
from genstudy.metrics import core_metrics, graph_metrics
from genstudy.store import RunStore

CLASSES = ("accepted", "incomplete", "incoherent", "both", "no_formulation", "unparsed", "pending")

#: The yield pipeline, in order; a run's stage is the first check it fails ("usable" if none).
STAGES = (
    "request_error",
    "empty_answer",
    "no_formulation",
    "unparsed",
    "objective_count",
    "no_core",
    "nonlinear",
    "no_integer",
    "usable",
    "pending",
)


@dataclass(frozen=True)
class Row:
    run_id: str
    experiment: str
    paper: str
    model: str
    workflow: str
    temperature: float
    status: str
    outcome: str
    stage: str
    coherent_whole: bool | None
    cut_variables: int | None
    cut_constraints: int | None
    core_minimal_size: int | None
    core_cv_ratio: float | None
    core_diameter: int | None
    linear: bool | None
    integral: bool | None
    minimal_size: int | None
    cv_ratio: float | None
    diameter: int | None
    requests: int
    prompt_tokens: int
    completion_tokens: int
    wall_s: float
    tool_rounds: int


def classify(graph: Mapping[str, Any] | None) -> str:
    if graph is None:
        return "pending"
    if not graph.get("gate_passed"):
        return "no_formulation"
    metrics = graph.get("metrics")
    if metrics is None:
        return "unparsed"
    if not metrics["contains_formulation"]:
        return "no_formulation"
    complete, coherent = metrics["complete_struct"], metrics["coherent"]
    if complete and coherent:
        return "accepted"
    if not complete and not coherent:
        return "both"
    return "incomplete" if not complete else "incoherent"


def reparsed(graph: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """The graphing row with its metrics (and its core's) recomputed from the stored reply."""
    call = (graph or {}).get("call")
    if graph is None or not graph.get("gate_passed") or not call:
        return graph
    try:
        model = parse_reply(call["response"]["content"])
    except ValueError as exc:
        return {**graph, "metrics": None, "core": None, "error": str(exc)}
    return {
        **graph,
        "metrics": asdict(graph_metrics(model)),
        "core": asdict(core_metrics(model)),
        "error": None,
    }


def yield_stage(record: Mapping[str, Any], graph: Mapping[str, Any] | None) -> str:
    """The first check of :data:`STAGES` the run fails, or ``usable``."""
    if record.get("status", "ok") != "ok":
        return "request_error"
    if not (record.get("final_answer") or "").strip():
        return "empty_answer"
    if graph is None:
        return "pending"
    if not graph.get("gate_passed"):
        return "no_formulation"
    metrics = graph.get("metrics")
    if metrics is None:
        return "unparsed"
    if not metrics["contains_formulation"]:
        return "no_formulation"
    if metrics["n_objectives"] != 1:
        return "objective_count"
    core = graph.get("core") or {}
    if not core.get("has_core"):
        return "no_core"
    if not core["linear"]:
        return "nonlinear"
    if not core["integral"]:
        return "no_integer"
    return "usable"


def rows(
    records: Iterable[Mapping[str, Any]], graphs: Mapping[str, Mapping[str, Any]]
) -> list[Row]:
    out = []
    for rec in records:
        g = graphs.get(rec["run_id"])
        m = (g or {}).get("metrics") or {}
        core = (g or {}).get("core") or {}
        calls = rec.get("calls", [])
        usage = [c["response"].get("usage", {}) for c in calls]
        outcome = "request_error" if rec.get("status") != "ok" else classify(g)
        out.append(
            Row(
                run_id=rec["run_id"],
                experiment=rec["experiment"],
                paper=rec["paper"],
                model=rec["model"],
                workflow=rec["workflow"],
                temperature=rec["temperature"],
                status=rec.get("status", "ok"),
                outcome=outcome,
                stage=yield_stage(rec, g),
                coherent_whole=core.get("coherent_whole"),
                cut_variables=core.get("cut_variables"),
                cut_constraints=core.get("cut_constraints"),
                core_minimal_size=core.get("minimal_size") if core.get("has_core") else None,
                core_cv_ratio=core.get("cv_ratio") if core.get("has_core") else None,
                core_diameter=core.get("diameter") if core.get("has_core") else None,
                linear=m.get("linear"),
                integral=m.get("integral"),
                minimal_size=m.get("minimal_size"),
                cv_ratio=m.get("cv_ratio"),
                diameter=m.get("diameter"),
                requests=len(calls),
                prompt_tokens=sum(int(u.get("prompt_tokens") or 0) for u in usage),
                completion_tokens=sum(int(u.get("completion_tokens") or 0) for u in usage),
                wall_s=float(rec.get("wall_s") or 0.0),
                tool_rounds=int(rec.get("rounds") or 0),
            )
        )
    return sorted(out, key=lambda r: r.run_id)


def load_rows(spec: StudySpec) -> list[Row]:
    out: list[Row] = []
    for model in spec.models:
        graphs = {
            g["run_id"]: reparsed(g)
            for g in RunStore(spec.root / "graphs" / f"{model}.jsonl").records()
        }
        out += rows(RunStore(spec.runs_dir / f"{model}.jsonl").records(), graphs)
    return sorted(out, key=lambda r: r.run_id)


def acceptance_table(data: Iterable[Row], by: tuple[str, ...]) -> dict[tuple, dict[str, int]]:
    """Outcome counts per group (``by`` names Row fields)."""
    table: dict[tuple, Counter[str]] = defaultdict(Counter)
    for r in data:
        table[tuple(getattr(r, f) for f in by)][r.outcome] += 1
    return {k: dict(sorted(v.items())) for k, v in sorted(table.items())}


def share(counts: Mapping[str, int], outcome: str) -> float | None:
    """Share of ``outcome`` among graphed runs (pending and request errors excluded)."""
    n = sum(v for k, v in counts.items() if k not in ("pending", "request_error"))
    return counts.get(outcome, 0) / n if n else None


def _pct(x: float | None) -> str:
    return r"\TBD" if x is None else f"{100 * x:.0f}\\,\\%"


def stage_share(data: Iterable[Row], stage: str = "usable") -> float | None:
    """Share of runs at ``stage`` among runs with a result (pending and request errors excluded)."""
    counts = Counter(r.stage for r in data)
    n = sum(v for k, v in counts.items() if k not in ("pending", "request_error"))
    return counts.get(stage, 0) / n if n else None


def macros(data: list[Row]) -> dict[str, str]:
    """The result macros of study_macros.tex (design and pilot macros are fixed there)."""
    total: Counter[str] = Counter(r.outcome for r in data)
    zs: Counter[str] = Counter(r.outcome for r in data if r.workflow == "ZS")
    multi: Counter[str] = Counter(r.outcome for r in data if r.workflow != "ZS")
    cores = [r for r in data if r.stage in ("nonlinear", "no_integer", "usable")]
    extracted = [r for r in cores if r.coherent_whole is False]
    cut = sorted(r.cut_variables for r in extracted if r.cut_variables is not None)
    return {
        "resUsableOverall": _pct(stage_share(data)),
        "resUsableZS": _pct(stage_share([r for r in data if r.workflow == "ZS"])),
        "resUsableMultiStep": _pct(stage_share([r for r in data if r.workflow != "ZS"])),
        "resCores": str(len(cores)),
        "resCoresExtracted": str(len(extracted)),
        "resCoreCutVariablesMedian": str(cut[len(cut) // 2]) if cut else r"\TBD",
        "resNonlinearCoreShare": _pct(
            sum(r.stage == "nonlinear" for r in cores) / len(cores) if cores else None
        ),
        "resAcceptOverall": _pct(share(total, "accepted")),
        "resAcceptZS": _pct(share(zs, "accepted")),
        "resAcceptMultiStep": _pct(share(multi, "accepted")),
        "resNoFormulationShare": _pct(share(total, "no_formulation")),
        "resRunsGraphed": str(
            sum(v for k, v in total.items() if k not in ("pending", "request_error"))
        ),
    }


def write_summary(spec: StudySpec, out_dir: Path) -> dict[str, Any]:
    data = load_rows(spec)
    summary = {
        "runs": len(data),
        "by_model_workflow": {
            "|".join(map(str, k)): v
            for k, v in acceptance_table(data, ("model", "workflow")).items()
        },
        "stages": dict(sorted(Counter(r.stage for r in data).items())),
        "stages_by_model": {
            m: dict(sorted(Counter(r.stage for r in data if r.model == m).items()))
            for m in sorted({r.model for r in data})
        },
        "macros": macros(data),
        "rows": [asdict(r) for r in data],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary
