# Routing Policy: mapping task tiers to actually active routes

This table is a proposed mapping from task tiers to the variant names in `core/spec/variant-specs.json`. It is not registration evidence. Routes registered in the current delegation tool and its runtime config take priority. Never auto-substitute an old alias with the names below.

| Policy | Task | Preferred proposed routes |
|---|---|---|
| L1 | Narrow extraction / classification / transformation | L-GLM-Extract; long simple input: M-Qwen-Lite |
| L2 | Small edit with clear scope and tests | M-Haiku-Quick; M-DeepSeekPro-Plain |
| M1 | General multi-step research / implementation | M-Haiku-Balanced (input <100K); M-Terra-Quick; M-Terra-Balanced |
| M2 | Deep logic / code analysis | M-DeepSeekPro-Reason; M-Terra-Deep |
| F1 | Specialist design / code implementation / cross-check | F-Sol-Standard; F-Sonnet-Code; open-weight (value): F-GLM-Standard; F-DeepSeek-Standard; F-Qwen-Standard |
| F2 | Hard problems / high-risk review | F-Sol-Deep; F-Sonnet-Debug; open-weight (value): F-GLM-Deep; F-DeepSeek-Deep; F-Qwen-Deep |
| F3 | Highest-difficulty exception | Unregistered reserve. Do not call Opus/Kimi by name alone |
| E0 | Free experiments tolerant of latency/failure | Free-Nemotron-Visual |
| V1 | Visual reading | MM-MiMo-Inspect; if insufficient, MM-Gemini-Inspect |
| V2 | Visual relation / contradiction reasoning | MM-Gemini-Reason |

## Model variant mapping

- Sol Standard=medium / Deep=high.
- Sonnet Code=medium / Debug=high.
- Terra Quick=low / Balanced=medium / Deep=high.
- DeepSeek V4 Pro Plain=none / Reason=high. Never set low/medium arbitrarily.
- Open-weight frontier routes (added for value per cost; text input only, so image tasks go to V1/V2 or a closed F route): DeepSeek V4 Pro 0813 Standard=high / Deep=max; GLM 5.3 Standard=high / Deep=max; Qwen3.8 2.4T-A95B Standard=medium / Deep=xhigh. GLM and Qwen cannot run with reasoning off. Quality against the closed F routes is unmeasured: compare on the same task (success rate, rework, total cost per successful task) before treating them as equivalents.
- Haiku Quick=low / Balanced=medium. Do not assign unconditionally to inputs in the 100K+ surcharge band.
- Qwen Lite=none; GLM Extract=low; free VL=none; MiMo Inspect=none.
- Gemini Inspect=low / Reason=high.
- All current proposals use service_tier=normal. Do not confuse a low-latency goal with fast-service support.
- Live calls of reasoning-off routes and new model variants need separate validation. The table does not replace live validation.

## Selection checklist

1. First choose: direct tool / single child / independent parallel / sequential.
2. Pick the tier from task type, change risk, input size, and latency/cost constraints.
3. Match the exact names in the currently registered route list against the actual model, reasoning effort, and speed.
4. If the proposed name is missing or settings differ, stop with activation_required. Continue with the parts the parent can do directly.
5. In frameworks that freeze the route list at session start, re-check in a new session after applying new settings.

Do not copy current model prices or measured speeds into this file. Check original prices, endpoints, and validation records when needed to avoid stale data.
