"""The numbers and tables of Paper 0's results that the other analysis scripts do not write.

    ~/.venvs/genstudy-analysis/bin/python scripts/paper_numbers.py [studies/paper0_2026/study.toml]

Reads ``analysis/summary.json`` (``python -m genstudy analyze``), ``analysis/domain.json``
(scripts/domain_vectors.py), ``audit/nonlinear_report.json`` (scripts/audit_nonlinear.py),
the run records and the graph records, and writes

* ``analysis/paper_macros.tex``: the stages of the yield pipeline, the coherent cores,
  Experiment 1 per workflow, Experiment 2 per paper, the execution of the workflows, the
  parser's repairs, the audit of the nonlinear verdicts and the cost;
* ``analysis/tab_yield.tex``: yield per model and workflow (Experiment 1), with each
  model's yield over all its runs and its two main failures;
* ``analysis/tab_fingerprint.tex``: one row per model with the size, diameter, coherence,
  diversity and domain relevance of its usable MILPs, and the published formulations for
  comparison.

Shares count every run in the denominator, as the yield does (Section "From answer to
usable MILP"). Deterministic; no requests.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.analyze import reparsed
from genstudy.config import load_study
from genstudy.graphing import Model, parse_reply
from genstudy.metrics import core_metrics
from genstudy.store import RunStore

NAMES = {
    "glmflash": "GLM-5.3-Flash",
    "deepseek": "DeepSeek-V4.1-Flash",
    "gptoss": "gpt-oss-120b",
    "qwen": "Qwen3.8-27B",
    "minimax": "MiniMax-M3",
}
AUTHORS = {"P1": "Shi", "P2": "Versluis", "P3": "Zhu", "P4": "Liu", "P5": "Lovetei"}
WORKFLOWS = ("ZS", "CFC", "OE", "PS")


def pct(part: float, whole: float, digits: int = 0) -> str:
    return f"{100 * part / whole:.{digits}f}\\,\\%" if whole else "--"


def num(x: float) -> str:
    """A count with a thin-space thousands separator as the paper writes it."""
    s = f"{x:,.0f}" if isinstance(x, int) or float(x).is_integer() else f"{x:,.1f}"
    return s.replace(",", "{,}")


def main() -> int:
    spec = load_study(sys.argv[1] if len(sys.argv) > 1 else "studies/paper0_2026/study.toml")
    root, out = spec.root, spec.root / "analysis"
    rows = json.loads((out / "summary.json").read_text(encoding="utf-8"))["rows"]
    domain = json.loads((out / "domain.json").read_text(encoding="utf-8"))
    audit = json.loads((root / "audit" / "nonlinear_report.json").read_text(encoding="utf-8"))
    by_id = {r["run_id"]: r for r in rows}
    models = list(spec.models)

    runs, graphs = {}, {}
    for m in models:
        for r in RunStore(root / "runs" / f"{m}.jsonl").records():
            runs[r["run_id"]] = r
        for g in RunStore(root / "graphs" / f"{m}.jsonl").records():
            graphs[g["run_id"]] = g
    stage = Counter(r["stage"] for r in rows)
    n_runs = len(rows)
    mac: dict[str, str] = {}

    # ---- the yield pipeline ---------------------------------------------------------
    gate = sum(1 for r in rows if r["stage"] == "no_formulation"
               and not graphs[r["run_id"]]["gate_passed"])  # fmt: skip
    n_obj = Counter()
    repaired, repair_kinds = 0, Counter()
    cores = {}
    for run_id, g in graphs.items():
        row = reparsed(g)
        if row and row.get("metrics") and by_id[run_id]["stage"] == "objective_count":
            n_obj["none" if row["metrics"]["n_objectives"] == 0 else "several"] += 1
        if row and row.get("core") and row["core"].get("has_core"):
            cores[run_id] = row["core"]
        if g.get("gate_passed") and g.get("call"):
            log: list[str] = []
            with contextlib.suppress(ValueError):
                parse_reply(g["call"]["response"]["content"], log)
            if log:
                repaired += 1
                repair_kinds.update({re.sub(r" [a-z_]+\.\w+$", "", x) for x in log})
    failures = n_runs - stage["usable"] - stage["unparsed"]
    usable = [r for r in rows if r["stage"] == "usable"]
    extracted_usable = sum(1 for r in usable if not r["coherent_whole"])
    parser_low, parser_high = audit["parser_share_wilson95"]
    nl = audit["counts"]
    parser_share = nl["parser"] / audit["sample"]
    mac |= {
        "stEmpty": str(stage["empty_answer"]),
        "stGate": str(gate),
        "stNoFormulation": str(stage["no_formulation"] - gate),
        "stUnparsed": str(stage["unparsed"]),
        "stUnparsedShare": pct(stage["unparsed"], n_runs, 1),
        "stObjectives": str(stage["objective_count"]),
        "stNoObjective": str(n_obj["none"]),
        "stSeveralObjectives": str(n_obj["several"]),
        "stNoCore": str(stage["no_core"]),
        "stNonlinear": str(stage["nonlinear"]),
        "stNoInteger": str(stage["no_integer"]),
        "stUsable": str(stage["usable"]),
        "stFailures": str(failures),
        "stNonlinearOfFailures": pct(stage["nonlinear"], failures),
        "coreUsableExtracted": str(extracted_usable),
        "coreUsableConnected": pct(len(usable) - extracted_usable, len(usable)),
        "repRuns": str(repaired),
        "repShare": pct(repaired, len([g for g in graphs.values() if g.get("gate_passed")])),
        "nlSample": str(audit["sample"]),
        "nlContinuous": str(nl["continuous"]),
        "nlBinary": str(nl["binary"]),
        "nlLogic": str(nl["logic"]),
        "nlPiecewise": str(nl["piecewise"]),
        "nlParser": str(nl["parser"]),
        "nlLinearizable": str(nl["binary"] + nl["logic"] + nl["piecewise"]),
        "nlParserLow": f"{100 * parser_low:.0f}",
        "nlParserHigh": f"{100 * parser_high:.0f}",
        "yieldCorrected": pct(stage["usable"] + parser_share * stage["nonlinear"], n_runs),
    }

    # ---- Experiment 1: workflows; Experiment 2: papers -------------------------------
    exp1 = [r for r in rows if r["experiment"] == "exp1"]

    def yield_of(rs: list[dict]) -> str:
        return pct(sum(r["stage"] == "usable" for r in rs), len(rs))

    def accept_of(rs: list[dict]) -> str:
        return pct(sum(r["outcome"] == "accepted" for r in rs), len(rs))

    mac["yOneAll"] = yield_of(exp1)
    mac["yOneMulti"] = yield_of([r for r in exp1 if r["workflow"] != "ZS"])
    for wf in WORKFLOWS:
        mac[f"yOne{wf}"] = yield_of([r for r in exp1 if r["workflow"] == wf])
    mac["aOneZS"] = accept_of([r for r in exp1 if r["workflow"] == "ZS"])
    mac["aOneMulti"] = accept_of([r for r in exp1 if r["workflow"] != "ZS"])
    papers = defaultdict(list)
    for r in rows:
        if r["workflow"] == "ZS" and r["temperature"] == 0.6:
            papers[r["paper"]].append(r)
    paper_yield = {p: sum(r["stage"] == "usable" for r in rs) / len(rs) for p, rs in papers.items()}
    for p, y in paper_yield.items():
        mac[f"yPaper{AUTHORS[p]}"] = pct(y, 1)
    mac["yPaperMin"] = pct(min(paper_yield.values()), 1)
    mac["yPaperMax"] = pct(max(paper_yield.values()), 1)
    mac["yPaperRuns"] = str(len(papers["P1"]))

    # ---- execution ---------------------------------------------------------------------
    notes = Counter()
    notes_by = Counter()
    sub_calls, sub_empty = Counter(), Counter()
    for rec in runs.values():
        for x in rec.get("notes", []):
            kind = re.sub(r"\d+", "N", x)
            notes[kind] += 1
            notes_by[(rec["model"], rec["workflow"], kind)] += 1
            if "returned empty content" in x:
                sub_empty[rec["model"]] += 1
        sub_calls[rec["model"]] += rec.get("subcalls", 0)
    coordinated = [r for r in exp1 if r["workflow"] != "ZS"]
    ps_counts = [runs[r["run_id"]]["subcalls"] for r in exp1 if r["workflow"] == "PS"]
    mac |= {
        "exCoordinated": str(len(coordinated)),
        "exForcedMissed": str(notes["forced first tool call not honoured"]),
        "exRoundLimit": str(notes["tool round limit (N) reached"]),
        "exRoundLimitQwenOE": str(notes_by[("qwen", "OE", "tool round limit (N) reached")]),
        "exClampedGptoss": str(notes_by[("gptoss", "PS", "or_factory count N clamped to N")]),
        "exNoDescription": str(sum(v for k, v in notes.items() if "without a description" in k)),
        "exEmptySubMinimax": str(sub_empty["minimax"]),
        "exSubMinimax": str(sub_calls["minimax"]),
        "exPSInstancesMedian": f"{median(ps_counts):g}",
    }

    # ---- cost --------------------------------------------------------------------------
    usd = 0.0
    paid_runs = set()
    for run_id, rec in runs.items():
        for c in rec["calls"]:
            cost = ((c.get("response") or {}).get("usage") or {}).get("cost")
            if cost is not None:
                usd += cost
                paid_runs.add(run_id)
    tokens = sum((r["prompt_tokens"] or 0) + (r["completion_tokens"] or 0) for r in rows)
    multi = [r for r in rows if r["workflow"] != "ZS"]
    mac |= {
        "costRequests": num(sum(r["requests"] for r in rows)),
        "costRequestsMultiMedian": f"{median(r['requests'] for r in multi):g}",
        "costTokensMillions": f"{tokens / 1e6:.0f}",
        "costWallZS": f"{median(r['wall_s'] for r in rows if r['workflow'] == 'ZS'):.0f}",
        "costWallMulti": f"{median(r['wall_s'] for r in multi):.0f}",
        "costUSD": f"{usd:.2f}",
        "costUSDRuns": str(len(paid_runs)),
    }

    # ---- table: yield per model and workflow -------------------------------------------
    lines = [
        "%% Generated by scripts/paper_numbers.py; do not edit.",
        "\\begin{tabular}{@{}lccccccc@{}}",
        "\\toprule",
        " & \\multicolumn{5}{c}{Experiment 1 (anchor paper)} & \\multicolumn{2}{c}{All runs} \\\\",
        "\\cmidrule(lr){2-6}\\cmidrule(l){7-8}",
        "Model & ZS & CFC & OE & PS & All & Yield & Nonlinear \\\\",
        "\\midrule",
    ]  # fmt: skip
    for m in models:
        mine = [r for r in exp1 if r["model"] == m]
        cells = [yield_of([r for r in mine if r["workflow"] == wf]) for wf in WORKFLOWS]
        allm = [r for r in rows if r["model"] == m]
        lines.append(f"{NAMES[m]} & {' & '.join(cells)} & {yield_of(mine)} & {yield_of(allm)} & "
                     f"{pct(sum(r['stage'] == 'nonlinear' for r in allm), len(allm))} \\\\")  # fmt: skip
    lines += ["\\midrule",
              f"All models & {' & '.join(mac[f'yOne{wf}'] for wf in WORKFLOWS)} & {mac['yOneAll']} & "
              f"{pct(stage['usable'], n_runs)} & {pct(stage['nonlinear'], n_runs)} \\\\",
              "\\bottomrule", "\\end{tabular}"]  # fmt: skip
    (out / "tab_yield.tex").write_text("\n".join(lines).replace("\\,\\%", "") + "\n",
                                       encoding="utf-8", newline="\n")  # fmt: skip

    # ---- table: fingerprints of the usable MILPs ---------------------------------------
    def size_cells(cs: list[dict]) -> list[str]:
        return [f"{median(c['core_variables'] for c in cs):g}",
                f"{median(c['core_constraints'] for c in cs):g}",
                f"{median(c['diameter'] for c in cs if c['diameter'] is not None):g}"]  # fmt: skip

    lines = [
        "%% Generated by scripts/paper_numbers.py; do not edit.",
        "\\begin{tabular}{@{}lccccccc@{}}",
        "\\toprule",
        " & & \\multicolumn{3}{c}{Core, median} & Connected & Diversity & Nearest \\\\",
        "\\cmidrule(lr){3-5}",
        "Model & MILPs & variables & constraints & diameter & graph & within a cell & is own paper \\\\",
        "\\midrule",
    ]  # fmt: skip
    for m in models:
        mine = [r for r in usable if r["model"] == m]
        cs = [cores[r["run_id"]] for r in mine]
        lines.append(f"{NAMES[m]} & {len(mine)} & {' & '.join(size_cells(cs))} & "
                     f"{pct(sum(r['coherent_whole'] for r in mine), len(mine))} & "
                     f"{domain['diversity_by_model'][m]:.2f} & "
                     f"{pct(domain['nearest_reference_is_own_by_model'][m], 1)} \\\\")  # fmt: skip
    refs = []
    for path in sorted((root / "references").glob("P*.json")):
        refs.append(core_metrics(Model.model_validate_json(path.read_text(encoding="utf-8"))))
    rv = [r.core_variables for r in refs]
    rc = [r.core_constraints for r in refs]
    rd = [r.diameter for r in refs if r.diameter is not None]
    lines += ["\\midrule",
              f"Published formulations & {len(refs)} & {min(rv)}--{max(rv)} & {min(rc)}--{max(rc)} & "
              f"{min(rd)}--{max(rd)} & {sum(r.coherent_whole for r in refs)} of {len(refs)} & -- & -- \\\\",
              "\\bottomrule", "\\end{tabular}"]  # fmt: skip
    (out / "tab_fingerprint.tex").write_text("\n".join(lines).replace("\\,\\%", "") + "\n",
                                             encoding="utf-8", newline="\n")  # fmt: skip
    mac["refDiameter"] = f"{min(rd)}--{max(rd)}"
    allcores = [cores[r["run_id"]] for r in usable]
    mac["genDiameter"] = f"{median(c['diameter'] for c in allcores if c['diameter'] is not None):g}"

    text = ["%% Generated by scripts/paper_numbers.py; do not edit."]
    text += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in mac.items()]
    (out / "paper_macros.tex").write_text("\n".join(text) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(text))
    print("repairs:", dict(repair_kinds.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
