# ADR-0002: Input papers are chosen by a rule, and all five are new

**Status:** proposed (2026-10-04); the selected papers are confirmed by Joern before the
production runs.

## Context

The 2025 pilot read five papers (Zhan et al. 2016 TR-E; D'Ariano et al. 2008 Transp.
Sci.; Koniorczyk et al. 2025 JRTPM; Pellegrini et al. 2014 TR-B; Zhang et al. 2023 TR-B).
Four were published by Elsevier and one by INFORMS, so their abstracts and introductions
could not be published with the run records; the pilot's Zenodo record contained them
and its access is now restricted. One paper (D'Ariano et al. 2008) contains no MILP, so
it had no reference formulation. Most were older and well cited, so the models may have
seen them, including their formulations, during training.

## Decision

All five input papers are replaced (Joern, 2026-10-04: "public access, similar to the
other papers, relevant authors but low citation so adaptation risk is lower, only papers
with models"). A paper qualifies if it

1. is open access under a licence that permits redistribution of its text (CC BY or
   CC BY-SA), so that the inputs and the generated answers, which quote them, are
   published with the data;
2. addresses real-time or operational train rescheduling or dispatching under
   disruptions or perturbations, the problem family of the pilot;
3. has at least one author with an established record in railway rescheduling;
4. has few citations and a recent publication date (lower risk that the models
   memorized it);
5. writes out an explicit MILP or ILP formulation (objective function and constraints),
   separate from an introduction that contains no formulation.

Papers co-authored by the study's authors are excluded. Among qualifying papers we
prefer a spread over the pilot's sub-problems (blocked line segments, real-time
reordering and rerouting, urban networks, station and junction routing, network-wide
disruptions). One paper is the anchor of experiment 1.

## The input text

`inputs/Pn.md` holds exactly the text that is sent: the abstract, a blank line, the word
"Introduction" and the introduction, with citation markers kept as in the pilot and
extraction artifacts removed. Title and authors are not part of the input (they would cue
recall); the attribution lives in `study.toml` and `inputs/README.md`. The reference
formulation is kept in `references/Pn.md` with its annotated structure in
`references/Pn.json` (the LP2Graph v2 schema), which also serve as realistic parser test
cases.

## Search and selection

[To be filled from the search: queries, filters, candidates with licence, citations,
problem family and the location of the formulation; the five selected papers.]
