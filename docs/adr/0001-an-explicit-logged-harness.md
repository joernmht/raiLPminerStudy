# ADR-0001: Rebuild the Paper 0 experiment as an explicit, logged harness

**Status:** accepted (2026-10-04)

## Context

Paper 0 (*raiLPminer: LLM-driven optimization model mining for railway
rescheduling and the case for deterministic structural validation*) reports an
experiment run 15 to 26 May 2025 with four proprietary or hosted models
(DeepSeek-V3, Gemini 2.5 Flash/Pro previews, o4-mini), four workflows (ZS, CFC,
OE, PS) and three temperatures. A review on 2026-10-04 checked the paper
against the code that produced the runs (`raiLPminerExperimentation@64b3b36`,
`legacy/raiLPminer_submitted.ipynb`) and the public data (Zenodo
10.5281/zenodo.19165428, 823 rows):

1. **No system prompt was sent.** Every agent was built as
   `Agent(model, systemprompt=..., temperature=...)`. PydanticAI 0.1.x to 0.2.x
   collects unknown keywords in `**_deprecated_kwargs` and ignores them. None of
   the 823 logged conversations contains a system prompt. The models received
   one user message, "Develop an optimization model, that tackles all the
   specific issues in the following scientific paper:", followed by the paper's
   abstract and introduction, plus one tool definition in CFC, OE and PS.
2. **No temperature was sent**, by the same mechanism. o4-mini, which rejects
   any temperature but 1, completed its runs labelled 0.2 and 0.6 without an
   error. The three temperature groups are replicates.
3. **The multi-step workflows mostly did not run.** Share of runs with a tool
   call (CFC/OE/PS): o4-mini 2/0/0 %, DeepSeek 100/0/0 %, Gemini Flash
   77/14/14 %, Gemini Pro 98/50/66 %.
4. **The parser invented structure.** 378 of the 536 rejections were answers
   without a formulation (fewer than three of five operator groups). The
   LLM-based LP2Graph had turned 233 of them into complete, coherent graphs. Its
   schema required exactly one objective, so a missing objective could not be
   observed (0 such cases in the data).
5. The paper's counts did not match the data (836 outputs reported, 823 in the
   data; 822 valid, since one Paper-2 run had no task instruction).

The names *lp2graph* and *raiLPminer* now belong to the successor approach:
the deterministic lp2graph library (Paper 1) and the generation loop in
raiLParchitect (Paper 2). The rerun must reproduce **Paper 0's** instrument, not
borrow the successors'.

## Decision

1. **A separate repository** (`raiLPminerStudy`) with no code dependency on
   lp2graph, the lab's mining pipeline or raiLParchitect. The one shared helper
   (HTTP retry) is vendored. The 2025 code stays citable as branch
   `legacy/raiLPminer-2025` / tag `raiLPminer-v1-2025` in
   raiLPminerExperimentation.
2. **The design is data.** `studies/<id>/study.toml` names the models, papers,
   experiments and pacing; its SHA-256 is stamped into every record.
3. **What is sent is what is logged.** Requests are plain dicts built by our
   code; each record stores every request body verbatim (no API key) and every
   response (content, reasoning, tool calls, usage, served model). Tests assert
   that each request carries the system prompt, the temperature and the seed
   (`tests/test_workflows.py`, the regression test for finding 1).
4. **Workflows are explicit code paths.** The orchestrator keeps its autonomy
   but its first turn is a forced call of its tool; our code executes the tool
   with the sub-agent's own prompts. PS starts the orchestrator's `count`
   (clamped to 2..5) of independent factory instances, as the paper describes,
   not one call asking for a list as the 2025 code did. Every deviation from the
   plain path is noted in the record.
5. **Prompts are the published texts**, fingerprinted per record; departures are
   listed in `genstudy.prompts.DEPARTURES`.
6. **Each request has its own seed**, derived from the run seed, so independent
   instances are independent samples and a replay sends the same seeds.
7. **Model by model, shuffled.** Runs execute one model's block at a time
   (the endpoint is shared), in a reproducible random order, so drift and
   outages do not pile onto one factor as they piled onto temperature in 2025.
8. **A transient fault is not a result.** Exhausted retries stop the block
   without a record; a non-retryable refusal is recorded; three refusals in a
   row stop the block; whatever the model answers is a result.
9. **ScaDS is used gently:** one request in flight, at least 3 s between
   requests, a daily budget persisted across processes, `Retry-After` honoured.
   `genstudy probe` documents that each model honours temperature and seed.
10. **The notation gate runs before parsing.** An answer below the threshold is
    recorded as "no formulation" and never reaches the parser.
11. **LP2Graph v2 keeps Paper 0's design and field names and fixes the schema:**
    an exit (`ContainsFormulation`), a list of objectives (0, 1 or more),
    `Domain` per variable and `Linear` per equation. The reply is constrained
    by a JSON schema and validated with pydantic; nothing is `exec`-ed.
12. **The parser is validated before it is used** (`genstudy.instrument`):
    six railway MILPs of known structure, five mutations with known effects,
    and two renderings without a formulation (prose, refusal). Candidates come
    from families that do not generate (Gemma-4, Llama-3.3); the better one is
    fixed in the spec and its error rates are reported in the paper.
13. **Completeness is defined as the 2025 code computed it** (exactly one
    objective, a variable and a constraint, and every variable in at least two
    equations), not as the 2025 manuscript's Equation (3) stated it.

## Consequences

- The rerun is comparable with 2025 in its factors, prompt texts and metrics,
  and different in what the 2025 run never did: temperatures and system prompts
  now reach the models, and the workflows now run. The paper reports the 2025
  run as a pilot whose audit motivated this design.
- Estimated volume (spec of 2026-10-04): about 1,200 runs, about 3,500
  generation requests, and about 1,300 parsing and validation requests, over
  several days at the paced rate.
- Records are large (reasoning text). They are committed per model block; the
  input texts are open access under CC BY (ADR-0002), so the data can be
  published with the code.
