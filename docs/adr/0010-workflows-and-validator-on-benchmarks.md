# ADR-0010: Paper 0's workflows and validator on public benchmarks, with an explicit and a code level

**Status:** accepted (2026-11-11, after the freeze of 2026-10-27; exploratory). Supersedes the
paper-facing part of ADR-0009 (the model-only check stays in `studies/benchmark_2026/`).

## Context

ADR-0009 scored the five generators on benchmark problems, which tests the models, not the
study. Joern, 2026-11-07: "I wanted to have the workflow implemented into this rather, maybe as a
Validator ... Just testing the model wouldn't seem relevant to the paper." Decided with him: 4
workflows x 5 models x 30 problems, prompts verbatim, the model-only table is replaced.

The first results (GLM, DeepSeek) showed the frozen validator rejecting many correct answers as
"no formulation". Joern, 2026-11-11: "we should add a code detector level as well ... Rejecting
perfectly good formulas, just because they're not in the form we want them to be, seems very
academic. Can we add and validate a code formulation detector, and also explain that?"
Inspection showed that the rejected answers were not code but small *explicit* formulations
(`max 15x_A + ... s.t. ... <= 6000`): the notation gate wants three of five operator groups
(<=, >=, sum, for-all, subject-to), which an indexed railway model shows and a scalar model does not.

## Decision

- `scripts/benchmark_workflows.py` (outputs `studies/benchmark_workflows_2026/`): 30 problems
  drawn (seed 20261108) from the ADR-0009 sample (IndustryOR kept 8 / removed 7, NL4Opt kept 8 /
  corrected 7); each model runs each workflow at temperature 0.6 with the study prompts.
- Ground truth: a translator that is none of the generators (`mistralai/devstral-2512`,
  OpenRouter, provider mistral/eu) implements the answer in PuLP as written, with the numbers the
  text states (it never sees the problem; missing data raises instead of being invented), up to
  two repairs; CBC solves; the objective is scored against the original and the cleaned label.
- The validator in three variants, all reported:
  1. **gate** = Paper 0's instrument as frozen (`yield_stage`);
  2. **explicit** level (`genstudy.codeform.explicit_formulation`): an answer the gate turns away
     goes to the parser when it has an objective keyword and at least two (in)equalities with a
     symbol on the left, and is not an unfinished tool call;
  3. **code** level (`genstudy.codeform.read_code`): solver code in an answer still without a
     written formulation is executed in the solver sandbox with `LpProblem.solve` stopped, and the
     model it built is read (objective terms, constraints, integer variables; PuLP refuses
     products of variables, so a nonlinear model fails). Nothing is solved, no LLM is involved.
     Only PuLP is read; other libraries are detected and reported.
- Accepted = `usable` (Paper 0's definition). The pre-registered benchmark rule (2026-11-07,
  `usable` or `no_integer`) is reported alongside, since it was fixed before the results.
- Validation of the levels: the code level against the 750 executed answers of ADR-0009 (does
  it find a model exactly when the script runs up to `solve()`; how do its stages relate to the
  scored outcome); the explicit level by hand on a sample of its admissions and all its
  rejections, and by how often it applies in the main study (14 of 1,183 answers fail the gate,
  2 of them explicit formulations), so Paper 0's main numbers are unaffected.
- A credit stop on OpenRouter (HTTP 402) is an infrastructure failure: such records are dropped
  and retried, never counted as model failures.
- Texts stay out of git (ADR-0009); records replace the benchmark text by a placeholder.

## Consequences

The paper can say what the validator is good for on a task with a known answer, and that its
verdict is about form unless the explicit and code levels are added. It stays small and
descriptive; it enters no test. The explicit level was designed after seeing the first results
and is reported as such.
