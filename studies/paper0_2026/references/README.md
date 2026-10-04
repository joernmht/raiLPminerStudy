# Reference formulations: the input papers' own models

`Pn.md` is the formulation of input paper Pn as the paper writes it; it is the text the
parser reads in the check. `Pn.json` is its hand annotation in the LP2Graph v2 schema
(`genstudy.graphing.Model`), the ground truth. Zhu et al. (P3) state two models: `P3` is
the rolling-stock MILP of Sect. 4.1 and `P3b` the timetable MILP of Sect. 4.2.

| Key | Text source | How |
|---|---|---|
| P1 | CC BY accepted manuscript (University of Bath repository) | transcribed by hand from 400-600 dpi crops: Tables A.1-A.2, model (13) of Appendix D, Sections 4.1-4.4 and Section 4.5 from (6g) to (6q) with their prose; objective (1), which (13) restates linearly, and the dynamics (6a)-(6f) left out; checked by compiling and against the PDF's text layer |
| P2 | CC BY PDF (authors' HAL deposit of the article) | transcribed by hand: Sect. 4.2.1 notation, objective (2), constraints (3)-(18) with their explanations; every equation checked against the page |
| P3, P3b | Elsevier XML (CC BY 4.0) | `scripts/extract_reference.py --section 4.1` (and `4.2`) |
| P4 | Elsevier XML (CC BY 4.0) | `scripts/extract_reference.py`: notation Tables 2-4 and the formulas of the MILP-based MPC, numbered as in the paper |
| P5 | Elsevier XML (CC BY-NC 4.0) | `scripts/extract_reference.py`: notation Tables 1-2, Sect. 2 constraints (1)-(26), objective (72) |

`extract_reference.py` converts MathML to LaTeX deterministically; what it does not know
it keeps as characters. Printed oddities are kept as printed and noted in the annotation's
descriptions (for example P2 (8) and (10)).

## Annotation conventions

- Decision variables only; parameters, sets and indices are not variables. An indexed
  family counts once; a symbol the paper defines as its own variable counts on its own
  (P3: `I_m^t`, `I_{m,0}^s`, `I_{m,end}^s`, `I_{m,off}^s` are four variables).
- One numbered equation is one constraint or objective, also when it is written for all
  members of a set or spans several lines. Domain declarations alone are not constraints.
- `Linear` is false when the expression as printed multiplies decision variables or uses
  another nonlinear function of them, whatever the paper calls the model.

## What the annotations show

The structural rules of the study, applied to the published models:

| Key | Variables | Objectives | Constraints | Complete | Coherent | Linear |
|---|---|---|---|---|---|---|
| P1 | 22 | 1 | 38 | no: `delta`, `z` occur only in (6j) | yes | yes |
| P2 | 10 | 1 | 16 | yes | yes | yes |
| P3 | 11 | 1 | 14 | no: `I_m^t` occurs only in (7) | yes | yes |
| P3b | 5 | 1 | 10 | yes | yes | yes |
| P4 | 20 | 1 | 24 | no: `gamma` occurs only in (27) | yes | no: (15), (29) |
| P5 | 12 | 1 | 26 | no: `d` occurs only in (5) | yes | yes |

Four of the six annotated models (P1, P3, P4, P5) fail the completeness rule (every
variable in at least two equations), each for a reason that lies in how the model is
written rather than in what it models. In P1 the variables of the piecewise-affine time
approximation (`delta`, `z`) enter only (6j), through the definition (6h) of G, because the
constraints that tie them to the kinetic energy, (12d)-(12g), sit in Appendix C outside the
constraint list of model (13); in P3 the inventory `I_m^t` is defined by (7) and constrained by its non-negative domain,
which is not an equation; in P4 the sign selector `gamma` belongs to a linearisation that
the paper numbers as one equation; in P5 the delay `d` is defined by (5) and reported but
not used. P4 is labelled an MILP but, as printed, multiplies the binary `xi` with `y` in
(15) and with `a` in (29); P1 states its objective (1) with absolute values and a maximum
and gives the linear model (13) only in an appendix. The completeness rule therefore measures how a formulation is
written, not whether it is correct.

## The parser check

`python -m genstudy validate-references --mode <mode> --repeats 2` parses every `Pn.md`
and stores the replies in `validation.<grapher>.<mode>.jsonl`; `python -m genstudy
grapher-report` re-scores the stored replies with the current parser into `report.json`
(no requests).
