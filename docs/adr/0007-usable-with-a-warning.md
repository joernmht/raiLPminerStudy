# ADR-0007: Three levels of the outcome: usable as written, usable with a warning, not usable

**Status:** accepted (2026-10-07, after the runs and after an external review of the manuscript)

## Context

ADR-0005 keeps the coherent core of every answer (the connected component of its objective)
instead of rejecting an answer whose graph is not connected. A referee-style review of the
manuscript (2026-10-07) called this a silent repair: a block of constraints that shares no
variable with the objective, such as a headway rule, usually means that the answer misses a
link (an order variable, an event time), and counting its core as usable hides the failure
that the paper warns about.

The records separate two cases. Of the 839 usable MILPs, 185 come from answers that are not
connected. In 104 of them the core cuts only variables that no equation uses, symbols the
answer declares and never uses. In 81 it cuts at least one constraint, and in 40 of these a
constraint named after a headway, separation, ordering, conflict, occupation or capacity
rule (examples: "Headway", "Train Ordering", "Bidirectional Segment Conflict").

Joern, 2026-10-07: "I see the coherent core issue, but rather than rejecting, in reality it
would be a warning or feedback loop".

## Decision

- **Three levels.** A run is *usable as written* when it yields a usable MILP (ADR-0005) and
  its core cut no constraint; *usable with a warning* when it yields a usable MILP and its core
  cut at least one constraint; otherwise *not usable*. The yield, the share of usable MILPs,
  is unchanged and is the sum of the first two levels.
- **A warning is feedback, not a verdict.** In assisted modeling, such an answer is neither
  discarded nor accepted silently: the detached block goes back to the modeler, or to the
  generating model in a feedback loop.
- **The rule fixed before the runs, restricted to MILPs,** is reported next to the levels:
  runs that the 2025 acceptance rule accepts and whose model is linear with an integer
  variable (`resUsablePrereg`).
- The railway words in the names of the cut constraints (`RULE_WORDS` in
  `scripts/paper_numbers.py`) describe the detached blocks. They decide nothing.

## Consequences

- Macros `usAsWritten`, `usWarning`, `usWarningRule`, `usUnusedOnly`, `usConnected`,
  `usPrereg` and their shares; `tab_yield.tex` gets a Warning column; the yield Sankey splits
  the usable band and the per-model bars. At the time of this ADR: 758 (63 %) usable as
  written, 81 (7 %) with a warning, 379 (32 %) under the rule fixed before the runs, 654
  (54 %) usable and connected as a whole.
- A detached block can also come from the parser losing a link. Without an audit of usable
  answers, the two causes are not separated (open).
