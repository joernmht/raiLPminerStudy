# raiLPminerStudy

The 2026 rerun of the **raiLPminer** experiment: large language models generate
mixed-integer linear programming (MILP) formulations for railway rescheduling from
the introduction of a research paper (the 2025 pilot also sent the abstract), in four
workflows
(Zero-Shot, Code-First-Chain, Operator-Expert, Parallelization-Selection) and at
three temperatures. Each answer is turned into a variable-equation graph
(LP2Graph), filtered on completeness and coherence, and measured on size,
constraint-variable ratio and graph diameter.

The first run of this experiment (2025) is reported in Maurischat and Bešinović,
*raiLPminer: LLM-driven optimization model mining for railway rescheduling and the
case for deterministic structural validation*. Its code is preserved in
[raiLPminerExperimentation](https://github.com/joernmht/raiLPminerExperimentation)
(branch `legacy/raiLPminer-2025`) and its records on Zenodo
([10.5281/zenodo.19165428](https://doi.org/10.5281/zenodo.19165428); restricted access,
because the logged conversations contain the copyrighted input papers). An audit of
that run found that its harness sent neither the system prompts nor the
temperatures it reported; [ADR-0001](docs/adr/0001-an-explicit-logged-harness.md)
lists the findings and the design that answers them.

## What makes this run checkable

- The **design is one file** (`studies/paper0_2026/study.toml`), hashed into every record.
- **Every request body is on the record**, next to the response (content, reasoning,
  tool calls, token usage, served model).
- The **prompts are the published texts**, fingerprinted per record.
- The **workflows are explicit code paths**; the orchestrator's first tool call is forced, and
  every deviation (a clamped count, a round limit) is noted.
- **Open-weight models** with pinned identities, served by the ScaDS.AI LLM service; a probe
  documents that temperature and seed are honoured.
- The **parser is validated** on test cases of known structure before it is used, and its
  error rates are reported.

## Reproduce

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
export SCADS_API_KEY=...            # or any OpenAI-compatible endpoint: edit base_url
python -m genstudy plan
python -m genstudy run --model glm
python -m genstudy graph --model glm
```

## Licence

Code: Apache-2.0 (see `LICENSE` and `NOTICE`). Input texts: the papers' own Creative Commons licences (attribution in
`studies/paper0_2026/inputs/README.md`). Run records and derived data: CC BY-NC 4.0, because
some inputs carry non-commercial licences.
