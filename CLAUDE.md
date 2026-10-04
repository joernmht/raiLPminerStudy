# CLAUDE.md: raiLPminerStudy

The **2026 rerun of Paper 0's experiment** (raiLPminer: LLMs generate railway-rescheduling
MILPs from a paper's abstract + introduction; LP2Graph turns each answer into a
variable-equation graph; structural metrics filter and select). Paper 0's LaTeX lives in
`~/6a7cb7f3670577d85a762b35` (`Main.tex` = frozen 2025 version, the rerun manuscript is the
distributed `Main_v2.tex`). Read `docs/adr/0001-*.md` first: it records why this harness
exists (the 2025 harness sent neither system prompts nor temperatures).

## Hard rules

- **Do NOT use the lp2graph library, the lab's `railpminer` package or raiLParchitect.**
  Those are the successor approach (Papers 1 and 2). This repo reproduces Paper 0's own
  instrument: an LLM fills the LP2Graph schema (`genstudy/graphing.py`).
- **ScaDS is a shared academic service; Joern asked to use it mindfully.** One runner process
  at a time (never two processes against the endpoint), the pacing in `study.toml` (one request
  in flight, >= 3 s gap, daily cap persisted in `studies/<id>/state/`). Run **model after
  model**. Do not raise the cap or lower the gap without asking.
- Input papers must be **open access under a Creative Commons licence** (CC BY, BY-SA, BY-NC,
  BY-NC-ND) and **not from MDPI journals** (ADR-0002, Joern). Texts and run records are published
  with the repo (public, non-commercial). Never add a paper without such a licence.
- Production runs need a **clean, committed tree** (`run` refuses otherwise): every record
  stamps the commit that produced it.
- Do not edit `study.toml` after the first production run of a study without a new `study_id`.

## Layout

- `genstudy/` the package: `config` (TOML spec), `prompts` (verbatim, fingerprinted), `llm`
  (paced/retried requests, bodies on the record), `workflows` (ZS/CFC/OE/PS, first tool call
  forced), `runner` (design, model-by-model shuffled order, resumable), `store` (append-only
  JSONL), `notation` (the gate), `graphing` (LP2Graph v2), `metrics`, `instrument` (parser
  test cases with known structure), `cli`.
- `studies/paper0_2026/` the study: `study.toml`, `inputs/` (paper texts, CC BY, with
  attribution), `references/` (annotated reference formulations), `runs/<model>.jsonl`,
  `graphs/<model>.jsonl`, `instrument/<grapher>.jsonl`, `probe.jsonl`; `state/` is local only.
- `docs/adr/` decisions. `tests/` pytest, no network.

## Commands

```bash
set -a; . ~/.config/raiLP/secrets.env; set +a          # SCADS_API_KEY
python -m genstudy plan
python -m genstudy probe                                 # 4 requests per model
python -m genstudy validate-grapher --served-id google/gemma-4-26B-A4B-it --repeats 2
python -m genstudy run --model glm [--experiment exp1] [--limit N]
python -m genstudy status
python -m genstudy graph --model glm
python -m pytest -q && ruff check . && ruff format --check .
```

Long runs: detach (`setsid nohup python -m genstudy run --model glm > studies/paper0_2026/logs/glm.log 2>&1 &`)
and watch the log; a stop on a transient fault is resumed by running the same command again.
Commit `runs/<model>.jsonl` when a model block is complete.

## Conventions

- Python 3.11+, `from __future__ import annotations`, frozen dataclasses for specs/results.
- Every text `open`/`read_text`/`write_text` passes `encoding="utf-8"`; writes in `genstudy/`
  also `newline="\n"` (`tests/test_text_io_encoding.py`).
- ruff (`pyproject.toml`), CI runs lint + tests on 3.11 to 3.13 + a C-locale job.
- Legacy 2025 code: `raiLPminerExperimentation`, branch `legacy/raiLPminer-2025`,
  tag `raiLPminer-v1-2025` (= commit 64b3b36 cited by the 2025 paper).
