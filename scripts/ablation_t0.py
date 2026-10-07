"""The temperature-0 ablation against the main study: yield and how far greedy decoding repeats.

    python3 -m genstudy --study studies/ablation_t0_2026/study.toml analyze
    ~/.venvs/genstudy-analysis/bin/python scripts/ablation_t0.py

The ablation (studies/ablation_t0_2026, decided after the production runs) ran every model
and workflow twice at temperature 0 on the anchor paper. It is descriptive, without tests:

* **yield** at temperature 0 against the anchor paper's yield at 0.2 in Experiment 1;
* **repetition**: the share of the 20 pairs (model x workflow) whose two answers are
  identical, the median similarity of the two answers of a pair (share of matching words,
  ``difflib`` on word lists) against the same for the replicates 1 and 2 of the
  corresponding cells at temperature 0.2, and how many leading words two different
  answers share before they diverge.

Writes ``studies/paper0_2026/analysis/ablation_macros.tex`` and ``ablation.json``.
Deterministic; no requests.
"""

from __future__ import annotations

import difflib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import load_study
from genstudy.store import RunStore

MAIN = "studies/paper0_2026/study.toml"
#: 5 models x 4 workflows x 2 runs (studies/ablation_t0_2026/study.toml).
EXPECTED_RUNS = 40
ABLATION = "studies/ablation_t0_2026/study.toml"
NAMES = {"glmflash": "GLM-5.3-Flash", "deepseek": "DeepSeek-V4.1-Flash",
         "gptoss": "gpt-oss-120b", "qwen": "Qwen3.8-27B", "minimax": "MiniMax-M3"}  # fmt: skip


def pairs(spec, temperature: float, experiment: str) -> dict[tuple[str, str], list[str]]:
    """Final answers of replicates 1 and 2 per (model, workflow) on the anchor paper."""
    out: dict[tuple[str, str], dict[int, str]] = defaultdict(dict)
    for model in spec.models:
        for r in RunStore(spec.root / "runs" / f"{model}.jsonl").records():
            if (r["experiment"] == experiment and r["paper"] == "P1"
                    and r["temperature"] == temperature and r["replicate"] in (1, 2)):  # fmt: skip
                out[(model, r["workflow"])][r["replicate"]] = r.get("final_answer") or ""
    return {k: [v[1], v[2]] for k, v in sorted(out.items()) if len(v) == 2}


def similarity(a: str, b: str) -> float:
    """Share of matching words of two answers (difflib on word lists, no junk heuristic)."""
    return difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()


def divergence(a: str, b: str) -> int:
    """Number of leading words two answers share before they first differ."""
    n = 0
    for x, y in zip(a.split(), b.split(), strict=False):
        if x != y:
            break
        n += 1
    return n


def main() -> int:
    main_spec, abl = load_study(MAIN), load_study(ABLATION)
    rows = json.loads((abl.root / "analysis" / "summary.json").read_text(encoding="utf-8"))["rows"]
    ref_rows = json.loads(
        (main_spec.root / "analysis" / "summary.json").read_text(encoding="utf-8")
    )["rows"]
    ref = [r for r in ref_rows if r["experiment"] == "exp1" and r["temperature"] == 0.2]

    def share(rs: list[dict]) -> float:
        return sum(r["stage"] == "usable" for r in rs) / len(rs)

    t0 = pairs(abl, 0.0, rows[0]["experiment"])
    t2 = pairs(main_spec, 0.2, "exp1")
    identical = {k: a == b for k, (a, b) in t0.items()}
    sim0 = [similarity(a, b) for a, b in t0.values()]
    sim2 = [similarity(a, b) for k, (a, b) in t2.items() if k in t0]
    first = [divergence(a, b) for a, b in t0.values() if a != b]
    first_zs = [divergence(a, b) for (_, wf), (a, b) in t0.items() if wf == "ZS" and a != b]
    by_model = {m: sum(v for (mm, _), v in identical.items() if mm == m) for m in abl.models}
    result = {
        "runs": len(rows),
        "yield_t0": round(share(rows), 3),
        "yield_t0_by_model": {
            m: round(share([r for r in rows if r["model"] == m]), 3) for m in abl.models
        },
        "yield_t02_exp1": round(share(ref), 3),
        "pairs": len(t0),
        "identical_pairs": sum(identical.values()),
        "identical_by_model": by_model,
        "similarity_t0_median": round(median(sim0), 3),
        "similarity_t02_median": round(median(sim2), 3),
        "shared_leading_words_median": median(first) if first else None,
        "shared_leading_words_zs": sorted(first_zs),
        "stages": dict(sorted(Counter(r["stage"] for r in rows).items())),
    }
    out = main_spec.root / "analysis"
    (out / "ablation.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8",
                                       newline="\n")  # fmt: skip
    repeating = [NAMES[m] for m, k in by_model.items() if k > 0]
    # Wilson 95 % interval of the yield at temperature 0 (descriptive)
    k, n, z = sum(r["stage"] == "usable" for r in rows), len(rows), 1.959964
    centre, half = (
        (k + z * z / 2) / (n + z * z),
        z * math.sqrt(k * (n - k) / n + z * z / 4) / (n + z * z),
    )
    low, high = centre - half, centre + half
    macros = {
        "abRuns": str(result["runs"]),
        "abYield": f"{100 * result['yield_t0']:.0f}\\,\\%",
        "abYieldRef": f"{100 * result['yield_t02_exp1']:.0f}\\,\\%",
        "abYieldLow": f"{100 * low:.0f}",
        "abYieldHigh": f"{100 * high:.0f}",
        "abPairs": str(result["pairs"]),
        "abIdentical": str(result["identical_pairs"]) if result["identical_pairs"] else "none",
        "abIdenticalModels": ", ".join(repeating) if repeating else "none",
        "abSimilarity": f"{result['similarity_t0_median']:.2f}",
        "abSimilarityRef": f"{result['similarity_t02_median']:.2f}",
        "abLeadingWords": f"{result['shared_leading_words_median']:g}",
        "abLeadingWordsZS": f"{median(first_zs):g}" if first_zs else "--",
    }
    complete = len(rows) == EXPECTED_RUNS and "pending" not in result["stages"]
    if not complete:
        # never report a partial ablation in the paper: placeholders until every run is graphed
        print(f"ablation incomplete ({len(rows)} of {EXPECTED_RUNS} runs, stages "
              f"{result['stages']}): macros written as [tbd]", file=sys.stderr)  # fmt: skip
        macros = dict.fromkeys(macros, "\\TBD{}")
    text = ["%% Generated by scripts/ablation_t0.py; do not edit."]
    text += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    (out / "ablation_macros.tex").write_text("\n".join(text) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
