# ADR-0008: A two-sided audit of the parser, labelled by hand on paper forms

**Status:** accepted (2026-10-07, after the runs)

## Context

Every yield in the paper is a joint property of the generating model and the parser (an
LLM). The parser was validated on test cases of known structure (54 cases, each parsed
twice: 107 of 108 parses fully right), but on the published formulations it got every verdict right in only 6 of 12 parses,
and the linearity audit (`scripts/audit_nonlinear.py`) found 8 parser errors among 40
nonlinear verdicts. That audit covers one direction only: false rejections. A referee-style
review (2026-10-07) pointed out that nothing measures false acceptances (an answer counted
as usable that is not), so the yield is uncalibrated in both directions. The 40 classes of
the linearity audit were also proposed by the analysis assistant and not yet checked by a
person.

## Decision

- **Sample** (`scripts/audit_forms.py draw`, seed 2026, drawn once): 40 usable MILPs as
  written (of 758), 20 usable MILPs with a warning (of 81, ADR-0007) and the 40 runs of the
  linearity audit, shuffled into 5 batches of 20 with blind codes. The labeller does not see
  the model, workflow, temperature or paper behind an answer.
- **Questions.** Usable: one objective function, linear as printed, an integer variable, no
  detached block, and what the parser's lists miss; for a warning, whether the cut block is
  detached in the answer or the parser lost the link. Nonlinear: are the equations the parser
  marked nonlinear nonlinear as printed, and of which kind (the classes of the linearity
  audit). The nonlinear runs are labelled again without the proposed classes.
- **Labeller and medium.** Joern labels by hand, on paper forms on his reMarkable tablet:
  per item the answer as printed (pandoc and LuaLaTeX; an answer that does not typeset is
  shown as its source) and a check page whose boxes stand at the same place on every page.
  The labels are a person's, not another LLM's, and the forms keep the task focused.
  `read` decides each box by the ink inside it and leaves notes and doubtful boxes to a look
  by eye.

## Consequences

- From the labels: the precision of "usable" (with a Wilson interval), the share of
  warnings whose block is detached in the answer, what the parser misses, and the final
  classes of the linearity audit. The paper then reports a confusion matrix of the parser's
  verdicts with intervals, in both directions.
- The rendering is a second instrument between the answer and the labeller; the source
  fallback and the note field exist so that a rendering problem does not become a label.
