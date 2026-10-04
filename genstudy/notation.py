"""The notation gate: does an answer contain the notation a written MILP needs?

Paper 0 (Section 3.3.1) found that the parsing model turned prose into complete
graphs, and added an operator check: five operator groups that written MILPs
use, and an answer passes when more than half of them are present. In 2025 the
check ran *after* parsing, as a correction of the completeness score; the audit
of the 2025 data found 233 answers without a formulation that the parser had
graphed as complete and coherent.

Here the gate runs *before* graphing: an answer that fails it is recorded as
"no formulation" and never reaches the parsing model, so that model cannot
invent structure for it. The groups are the 2025 groups; the patterns also
cover ``\\le``/``\\ge`` (unmatched in 2025), ``\\leqslant``, Unicode variants
and "for every".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Operator groups (Paper 0, Section 3.3.1) and the patterns that evidence each.
OPERATOR_GROUPS: dict[str, tuple[str, ...]] = {
    "le": (r"<=", r"\\le(?:q|qslant)?(?![A-Za-z])", "≤", "⩽"),
    "ge": (r">=", r"\\ge(?:q|qslant)?(?![A-Za-z])", "≥", "⩾"),
    "sum": (r"\\sum(?![A-Za-z])", r"\bsum_", "∑"),
    "forall": (r"\\forall(?![A-Za-z])", r"\bfor\s+(?:all|each|every|any)\b", "∀"),
    "st": (r"\bs\.\s?t\.", r"\bsubject\s+to\b", r"\bsuch\s+that\b"),
}

#: An answer passes when strictly more than half of the groups are present (>= 3 of 5).
THRESHOLD = 0.5

_COMPILED = {
    g: tuple(re.compile(p, re.IGNORECASE) for p in pats) for g, pats in OPERATOR_GROUPS.items()
}


@dataclass(frozen=True)
class NotationResult:
    groups: tuple[str, ...]
    coverage: float

    @property
    def passed(self) -> bool:
        return self.coverage > THRESHOLD


def notation(text: str) -> NotationResult:
    """Which operator groups ``text`` contains, and the coverage share."""
    present = tuple(g for g, pats in _COMPILED.items() if any(p.search(text) for p in pats))
    return NotationResult(groups=present, coverage=len(present) / len(OPERATOR_GROUPS))
