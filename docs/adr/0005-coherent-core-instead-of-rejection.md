# ADR-0005: Keep the coherent core of an answer; drop the two-equation rule from acceptance

**Status:** accepted (2026-10-06, after the runs and before the final analysis)

## Context

The analysis plan written before the runs (Paper 0, Section 5) accepts an answer when it
is complete and coherent: exactly one objective function, at least one variable and one
constraint, every variable in at least two equations (objective or constraints), and a
connected variable-equation graph. The interim data (three of five models, 720 runs,
2026-10-06) showed two problems with that rule.

1. **The two-equation rule rejects sound models.** It removed 405 of the 720 runs, more
   than every other check together. The same rule rejects four of the six published
   formulations of the input papers (`studies/paper0_2026/references/README.md`, written
   on 2026-10-04, before the first production run). In all four, the reason is a variable
   that appears in exactly one constraint and not in the objective: a quantity the model
   defines and reports, an auxiliary variable bounded by its domain, or a linearisation
   written as one numbered equation. Such a variable does not change what the model
   optimises.
2. **Rejecting an answer that is not connected discards a working model.** In 169 of the
   720 runs the graph was not connected, but the part connected to the objective was a
   complete model: cutting the rest removed a median of one variable and no constraint,
   typically a symbol that the answer declared and never used.

Joern, 2026-10-06: "I'd completely cross it off, maybe argument why. The variable in two
equations made sense for coherence, and it still does, so we can analyze coherence. But
maybe we should instead extract the coherent core model after a run rather than discarding
everything as a strategy."

## Decision

- **The coherent core.** Every parsed answer with exactly one objective function is
  reduced to the connected component of its objective (`metrics.core_model`). A block
  that shares no variable with the objective cannot change its optimum; it can only make
  the whole model infeasible. The core is what the answer optimises. What is cut away
  (variables, constraints) and whether the whole answer was connected are recorded per
  run (`metrics.core_metrics`) and analysed as the coherence of the answer.
- **The yield of usable MILPs** replaces acceptance as the main outcome: a run yields a
  usable MILP when its answer is not empty, passes the notation gate, is parsed with a
  formulation and exactly one objective, has a core with at least one variable and one
  constraint, and the core is linear and contains an integer variable
  (`analyze.STAGES`, `analyze.yield_stage`). Linearity, so far a reported share, becomes
  a stage: a nonlinear model is not a MILP.
- **The two-equation rule is no longer an acceptance criterion.** The degree of every
  variable stays in the records and in the analysis of coherence.
- **The pre-registered classification is still computed and reported** (`analyze.classify`,
  macros `resAccept*`): the plan named it, and it is the only basis for comparing with
  the 2025 pilot, whose numbers use it.

## Consequences

- The paper states both outcomes, the reason for the change and that it was decided after
  the runs. The evidence for the first point (the published models) predates the runs.
- Interim (846 graphed runs): pre-registered acceptance 37 %, usable MILPs 67 %; the
  nonlinear cores (28 %) are now the largest loss.
- A core can still contain a variable that appears only in the objective; whether such
  answers differ is open to the analysis, not to a filter.
