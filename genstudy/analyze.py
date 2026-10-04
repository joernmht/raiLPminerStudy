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

Everything here is deterministic: the same records produce the same rows,
tables and macros, byte for byte.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from genstudy.config import StudySpec
from genstudy.store import RunStore

CLASSES = ("accepted", "incomplete", "incoherent", "both", "no_formulation", "unparsed", "pending")


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


def rows(
    records: Iterable[Mapping[str, Any]], graphs: Mapping[str, Mapping[str, Any]]
) -> list[Row]:
    out = []
    for rec in records:
        g = graphs.get(rec["run_id"])
        m = (g or {}).get("metrics") or {}
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
            g["run_id"]: g for g in RunStore(spec.root / "graphs" / f"{model}.jsonl").records()
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


def macros(data: list[Row]) -> dict[str, str]:
    """The result macros of study_macros.tex (design and pilot macros are fixed there)."""
    total: Counter[str] = Counter(r.outcome for r in data)
    zs: Counter[str] = Counter(r.outcome for r in data if r.workflow == "ZS")
    multi: Counter[str] = Counter(r.outcome for r in data if r.workflow != "ZS")
    return {
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
