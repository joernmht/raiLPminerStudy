# ADR-0009: A small check on public benchmarks, scored against original and cleaned labels

**Status:** accepted (2026-11-07, after the freeze of 2026-10-27; exploratory)

## Context

Paper 0 has no reference answer and reports no benchmark accuracy. Readers from the
LLM-for-OR literature ask how the five generators compare on the usual benchmarks
(NL4Opt, MAMO, IndustryOR). Those benchmarks score a single objective value against a label,
and an expert audit (Xiao et al., IJCAI 2025, doi 10.24963/ijcai.2025/1192) found at least
26 % of the NL4Opt and 54 % of the IndustryOR labels or problems faulty and published cleaned
versions (repo LLM4OR/LLM4OR).

Joern, 2026-11-07: "Do a small one for Paper 0, but also add the paper being sceptical towards
those benchmarks".

## Decision

- `scripts/benchmark_check.py`, outputs in `studies/benchmark_2026/`. The five study models
  with their study settings (`studies/paper0_2026/study.toml`), temperature 0, one attempt,
  no repair: problem text in, one PuLP script out, CBC solves, the printed objective is
  compared with the label (relative tolerance 1e-4; 1e-2 as sensitivity).
- Sample (seed 20261107): all 100 IndustryOR problems (42 the audit kept, 58 it removed) and
  50 NL4Opt problems (the 23 matched problems whose label the audit corrected, 27 drawn from
  those it kept). Every answer is scored against the original label (ORLM test sets) and the
  cleaned one; a consensus of at least three models against the label is reported.
- Benchmark texts are not committed (the cleaned sets carry no licence, the HF originals are
  CC BY-NC): `fetch` downloads them at pinned commits (LLM4OR 75962df, ORLM 33bc47d) into the
  gitignored `data/`; records keep item ids, question hashes, the generated code and outcomes,
  and drop the request messages.
- Paper numbers: `report` writes `benchmark_macros.tex` and `tab_benchmark.tex`, copied by
  `scripts/export_paper.sh`.

## Consequences

The check tests the generators, not Paper 0's workflows or its structural instrument, and the
paper says so. It is small (150 problems per model) and descriptive; it enters no test.
