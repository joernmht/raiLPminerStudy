# ADR-0006: Domain relevance and diversity from the names in the graphs

**Status:** accepted (2026-10-07, after the runs)

## Context

The analysis plan named a keyword analysis of constraint categories (Paper 0, Section 3.5,
carried over from 2025) and complexity metrics (minimal size, constraint-variable ratio,
diameter) for selecting a diverse subset. Joern asked to condense the paper (2026-10-07) and
to keep a measure of domain relevance; a first attempt with hand-made keyword categories
matched incidental words ("per mass unit", "at platform p") and needed patterns tuned on
the reference models. Joern: "Couldn't we do something with feature vectors based on the
names instead?"

## Decision

- Every usable MILP (its coherent core) and every input paper's own formulation becomes a
  TF-IDF vector of the words in its variable, objective and constraint names
  (`genstudy.domain.names`, `scripts/domain_vectors.py`). **Domain relevance**: the mean
  cosine similarity of the models generated from a paper to each paper's formulation, and
  the share whose most similar reference is their own paper's. **Diversity**: one minus the
  mean pairwise similarity within a cell of Experiment 1, modelled over the cells.
- The keyword categories are dropped. The complexity metrics are reduced to **size**
  (variable and constraint families against the paper's own formulation); the subset
  selection by extreme complexity and the complexity regressions leave the paper (Joern:
  "This makes our complexity metrics unnecessary as well, right?").

## Consequences

- First results (839 usable MILPs): the nearest of the five references is the model's own
  paper for 64 % (chance 20 %; 59-97 % by paper); diversity within a cell grows with
  temperature (0.72, 0.75, 0.80; Wald chi2_2 = 32.0, p < 0.001) although temperature does
  not change the yield; generated models are about half the size of the expert models
  (median 9 variable and 14 constraint families against 10-22 and 16-38).
- A data-driven clustering of constraint names into railway constraint types is under
  discussion as the domain-interpretable part.
