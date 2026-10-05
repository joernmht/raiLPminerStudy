# ADR-0004: gpt-oss-120b and Qwen3.8-27B are served via OpenRouter

**Status:** accepted (2026-10-05)

## Context

The study keeps one request in flight on ScaDS and stops at a daily budget of 1,500
requests (`[pacing]`, ADR-0001), a fair-use limit for a shared academic service. On
2026-10-05 06:30 UTC two of the five model blocks were done (GLM-5.3-Flash run and
graphed, DeepSeek-V4.1-Flash run), and the remaining work of about 3,100 ScaDS requests
would have taken until about 8 October at that budget. Joern offered his OpenRouter
account: "To speed things up, you could use my open router account for a cheap model or
two in parallel."

## Decision

The two cheapest remaining models, gpt-oss-120b and Qwen3.8-27B, are served by DeepInfra
through OpenRouter (`deepinfra/bf16`, no fallback), each as a whole block and before any
of its runs: no model is served by two providers. DeepInfra supports every parameter the
harness sends (temperature, seed, tools, a named tool choice, reasoning). The reasoning
settings are the same as on ScaDS, written in OpenRouter's notation: gpt-oss
`reasoning = { effort = "low" }`, Qwen `reasoning = { enabled = false }`. Replaying the
coder request of ADR-0003 confirmed both (`probes/reasoning_2026-10-04.jsonl`, last two
rows): gpt-oss 4,709 tokens, 23 of them reasoning, 63 s, US$ 0.0008; Qwen 8,718 tokens,
no reasoning, 155 s, US$ 0.016. The parser stays on ScaDS, so that every answer is parsed
by the validated configuration.

`study.toml` was amended accordingly (the two `[models]` entries only); the records of
these two models carry the amended spec hash, those of GLM-5.3-Flash and DeepSeek the
original. Cells, seeds and run order do not depend on the endpoint and are unchanged. Each
model on another endpoint has its own daily request counter.

## Consequences

- Two models run in parallel with the ScaDS queue; the data are complete about a day
  earlier. Expected OpenRouter cost: under US$ 10 for both blocks.
- The paper names the provider of every model. Each model is served by one provider
  throughout its block, so the comparisons within a model (workflow, temperature) are
  unaffected; differences between models already include differences of serving.
- The served model identifier changes for Qwen (`qwen/qwen3.8-27b` on OpenRouter instead of
  `Qwen/Qwen3.8-27B` on ScaDS); the analysis groups by the model key.
