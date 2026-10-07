"""Audit of the parser's linearity verdicts: what makes a "nonlinear" core nonlinear.

    ~/.venvs/genstudy-analysis/bin/python scripts/audit_nonlinear.py draw   [study.toml]
    ~/.venvs/genstudy-analysis/bin/python scripts/audit_nonlinear.py report [study.toml]

Nonlinearity is the most frequent reason why an answer is not a usable MILP, and the
verdict comes from the parser (an LLM). ``draw`` takes a seeded random sample of the runs
that leave the yield pipeline at the linearity check and writes, for each, every equation
of the core that the parser marked nonlinear together with the symbols of the variables
the parser found in it (``audit/nonlinear_sample.md``). A person classifies each run in
``audit/nonlinear_labels.json`` by what the answer, as printed, does (parameters and
variables as the answer declares them):

* ``continuous``: a product, quotient or power of continuous decision variables, or a
  continuous variable inside a nonlinear function (not linear, no exact linear form);
* ``binary``: a product in which every factor but one is a binary or integer variable
  (exactly linearizable by the standard reformulation);
* ``logic``: an indicator, implication or case distinction on the variables written as
  such (linearizable with big-M constraints);
* ``piecewise``: an absolute value, maximum, minimum or positive part of an expression
  in the variables (piecewise linear, linearizable by standard means);
* ``parser``: none of the above; every equation marked nonlinear is linear as printed
  (an error of the instrument).

A run gets the first class in this order that applies to one of its marked equations.
``report`` counts the classes into ``audit/nonlinear_report.json`` with a Wilson 95 %
interval for the parser's share. Deterministic.
"""

from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import load_study
from genstudy.graphing import parse_reply
from genstudy.metrics import core_model
from genstudy.store import RunStore

SAMPLE = 40
SEED = 2026
CLASSES = ("continuous", "binary", "logic", "piecewise", "parser")


def draw(root: Path, models: list[str]) -> None:
    rows = json.loads((root / "analysis" / "summary.json").read_text(encoding="utf-8"))["rows"]
    nonlinear = {r["run_id"] for r in rows if r["stage"] == "nonlinear"}
    graphs = {}
    for model in models:
        for g in RunStore(root / "graphs" / f"{model}.jsonl").records():
            if g["run_id"] in nonlinear:
                graphs[g["run_id"]] = g
    sample = random.Random(SEED).sample(sorted(graphs), SAMPLE)
    md = [f"# Nonlinear cores: random sample of {SAMPLE} of {len(graphs)} (seed {SEED})", ""]
    for run_id in sample:
        core = core_model(parse_reply(graphs[run_id]["call"]["response"]["content"]))
        symbols = {v.Number: f"{v.Abbreviation} ({v.Domain})" for v in core.variablesInModel}
        marked = [e for e in (*core.objective_functions, *core.constraints) if not e.Linear]
        md += [f"## {run_id}: {len(marked)} of "
               f"{len(core.objective_functions) + len(core.constraints)} equations marked", ""]  # fmt: skip
        for e in marked:
            md.append(f"- **{e.Name}**: `{e.equation}`")
            md.append(
                f"  variables: {', '.join(symbols.get(n, f'#{n}') for n in e.VariablesIncluded)}"
            )
        md.append("")
    out = root / "audit"
    out.mkdir(exist_ok=True)
    (out / "nonlinear_sample.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    print(f"wrote {out / 'nonlinear_sample.md'}")


def report(root: Path) -> None:
    out = root / "audit"
    labels = json.loads((out / "nonlinear_labels.json").read_text(encoding="utf-8"))
    runs = labels["runs"]
    bad = [k for k, v in runs.items() if v["class"] not in CLASSES]
    if bad:
        sys.exit(f"unknown class in {bad}")
    counts = Counter(v["class"] for v in runs.values())
    n, k, z = len(runs), counts.get("parser", 0), 1.959964
    centre = (k + z * z / 2) / (n + z * z)
    half = z * math.sqrt(k * (n - k) / n + z * z / 4) / (n + z * z)
    result = {
        "sample": n,
        "seed": SEED,
        "annotation": labels["annotation"],
        "counts": {c: counts.get(c, 0) for c in CLASSES},
        "parser_share_wilson95": [round(centre - half, 3), round(centre + half, 3)],
    }
    (out / "nonlinear_report.json").write_text(json.dumps(result, indent=1) + "\n",
                                               encoding="utf-8", newline="\n")  # fmt: skip
    print(json.dumps(result, indent=1))


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("draw", "report"):
        sys.exit(__doc__)
    spec = load_study(sys.argv[2] if len(sys.argv) > 2 else "studies/paper0_2026/study.toml")
    if sys.argv[1] == "draw":
        draw(spec.root, list(spec.models))
    else:
        report(spec.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
