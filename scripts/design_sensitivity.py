"""What the design can detect: minimum detectable differences in acceptance.

    python3 scripts/design_sensitivity.py [studies/paper0_2026/study.toml]

For each comparison the paper makes, the group sizes follow from the study
specification, and the minimum detectable difference (MDD) between two acceptance
shares is computed for a two-sided test at the 5 % level with 80 % power, around an
acceptance of 50 % (the least favourable value), with Cohen's arcsine effect size h:
h = (z_0.975 + z_0.8) * sqrt(1/n1 + 1/n2), MDD = sin^2(asin(sqrt(.5)) + h/4) -
sin^2(asin(sqrt(.5)) - h/4). This is a sensitivity statement about the fixed design,
not an a-priori power analysis: the number of replicates continues the 2025 pilot
(at least 14 per cell) within the request budget of the shared service.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from statistics import NormalDist

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from genstudy.config import load_study

Z = NormalDist().inv_cdf(0.975) + NormalDist().inv_cdf(0.8)


def mdd(n1: int, n2: int, p: float = 0.5) -> float:
    """h = 2 asin(sqrt(p1)) - 2 asin(sqrt(p2)), so each share lies h/4 from p on the asin scale."""
    h = Z * math.sqrt(1 / n1 + 1 / n2)
    base = math.asin(math.sqrt(p))
    return math.sin(base + h / 4) ** 2 - math.sin(base - h / 4) ** 2


def main() -> int:
    spec = load_study(sys.argv[1] if len(sys.argv) > 1 else "studies/paper0_2026/study.toml")
    e1 = spec.experiment("exp1")
    e2 = spec.experiment("exp2")
    runs1 = len(e1.models) * len(e1.workflows) * len(e1.temperatures) * e1.replicates
    per_wf = runs1 // len(e1.workflows)
    per_t = runs1 // len(e1.temperatures)
    per_m = runs1 // len(e1.models)
    per_m_wf = per_m // len(e1.workflows)
    per_paper = len(e2.models) * e2.replicates
    rows = [
        ("zero-shot vs the three coordinated workflows", per_wf, runs1 - per_wf),
        ("two workflows", per_wf, per_wf),
        ("two temperatures", per_t, per_t),
        ("two models", per_m, per_m),
        ("two workflows within one model", per_m_wf, per_m_wf),
        ("two input papers (Zero-Shot, T = 0.6)", per_paper, per_paper),
        ("one cell against another", e1.replicates, e1.replicates),
    ]
    print(f"experiment 1: {runs1} runs; experiment 2: {per_paper} runs per paper")
    for name, n1, n2 in rows:
        print(f"  {name:48s} n = {n1:3d} vs {n2:3d}: MDD = {100 * mdd(n1, n2):4.1f} points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
