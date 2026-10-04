# ADR-0003: Minimal reasoning for every model, and GLM-5.3 replaced

**Status:** accepted (2026-10-04); the fifth model is chosen by the pilot in
`studies/pilot_2026_fifth/` (see "The fifth model").

## Context

The first production run (`exp1.P1.glm.CFC.t10.r05`, 2026-10-04 20:33 UTC) used
GLM-5.3 in its default reasoning mode with `max_tokens = 16000`. In each of its four
coder calls the model spent all 16,000 tokens on reasoning (`finish_reason = length`,
16,000 reasoning tokens, no content), the orchestrator asked again until the tool-round
limit, and the final answer was empty: 9 requests, 38 minutes, 66,597 tokens. The block
was stopped and the record moved to `studies/paper0_2026/abandoned/`, outside the
runner's view, so that the cell is run again under the corrected settings. It stays in
the repository as the record of the failure.

Replaying exactly that coder request at temperature 0.6 (request and results in
`studies/paper0_2026/probes/reasoning_2026-10-04.*`) gave:

| Model | Thinking switched off | Reasoning effort "low" |
|---|---|---|
| GLM-5.3 | reasons inside the answer instead, cut off at 16,000 tokens (412 s) | 2,924 tokens, 78 s, no reasoning |
| GLM-5.3-Flash | the same, cut off at 16,000 tokens | 2,936 tokens, 20 s |
| DeepSeek-V4.1-Flash | 5,275 tokens, 124 s | 10,167 tokens, 141 s (6,236 reasoning) |
| gpt-oss-120b | not offered | 5,572 tokens, 28 s |
| Qwen3.8-27B | 6,603 tokens, 68 s | 13,031 tokens, 132 s |
| MiniMax-M3 | switch ignored: 15,410 reasoning tokens, cut off | 7,058 tokens, 75 s (3,528 reasoning) |
| Kimi K3 (OpenRouter, DeepInfra) | 6,350 tokens, 207 s, US$ 0.09 | 4,880 tokens, 149 s (23 reasoning) |

At default reasoning, two of the five models could not answer a single coder call within
the limit, and the reasoning of the others would have made the study take weeks of the
shared service.

## Decision

1. **Every model reasons as little as it allows** (Joern, 2026-10-04: "the thinking part
   is fine for now. I mean, we can go higher on thinking, but I like the raw approach").
   Thinking is switched off where the model honours the switch and then answers normally
   (DeepSeek-V4.1-Flash, Qwen3.8-27B, Kimi K3); otherwise the lowest reasoning effort is
   used (gpt-oss-120b, MiniMax-M3, and GLM, whose thinking-off mode moves the reasoning
   into the answer). The settings are each model's `extra` in `study.toml`, sent with
   every request and stored in every record.
2. **GLM-5.3 is replaced** (Joern: "Replace glm"), first by Kimi K3, which ScaDS does not
   serve: through OpenRouter, provider pinned to DeepInfra without fallback, because
   Moonshot's own endpoint there accepts neither temperature nor seed, and temperature is
   a factor of the design. A model on another endpoint has its own request counter, so it
   never uses the ScaDS budget. The pilot below then chose GLM-5.3-Flash.

## The fifth model

Joern was open to GLM-5.3-Flash (MIT, served by ScaDS) instead of Kimi K3 "if it works
better". Both ran every workflow at temperatures 0.2 and 1.0 on one production input
(`studies/pilot_2026_fifth/`). The criteria, written into that spec before the runs, are
operational only: complete answers, tool calls answered by the sub-agents, answers that
pass the notation gate and parse, time and cost per run. Acceptance is the study's
outcome and was not used.

Result (2026-10-04, 16 runs, `runs/` and `graphs/` in that directory):

| | GLM-5.3-Flash (ScaDS) | Kimi K3 (OpenRouter, DeepInfra) |
|---|---|---|
| runs complete (finish stop, answer not empty) | 8/8 | 8/8 |
| tool calls answered by the sub-agents | all | all |
| answers passing the notation gate | 8/8 | 7/8 |
| gated answers parsed | 8/8 | 7/7 (6/7 before the quoted-label repair) |
| time per run | 22-137 s | 81-446 s |
| cost | none (ScaDS) | about US$ 0.19 per run, about US$ 45 per block |

The Kimi answer without a formulation is an Operator-Expert orchestrator that ended with
"Let me request a final revision" instead of calling its tool; the parse failure was the
parser's (a constraint numbered "5'", repaired since). On the stated criteria
GLM-5.3-Flash works better: as reliable, about 3.6 times faster, and free. **GLM-5.3-Flash
is the fifth model**; Kimi K3 is the larger model, which was the argument for it.

## Consequences

- The models run without extended reasoning, unlike the pilot's Gemini 2.5 and o4-mini;
  the paper says so where it describes the models.
- Temperature acts on the answer directly; vendors of thinking modes recommend fixed
  sampling settings, and low temperatures can make long reasoning loop.
- The spec changed before any production record: no study_id change is needed.
