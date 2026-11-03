# Fast Model Selection — 2026-11-03

## Decision

Replace `openai/gpt-oss-120b` with `reflection/beam-1.0-501b-a23b`.
Keep latency-prioritized provider routing, required tool-parameter support,
collection-denial preferences, and provider failover. Leave optional reasoning
effort unset until supported values are validated for the configured route.

This is a task-specific engineering choice, not a claim that any model is universally
the most stable. Our previous Fast sample showed language violations, overconfident
stock wording, provider fallback, and variable end-to-end latency. A high output
token rate alone did not make it a reliable customer-service configuration.

## Public evidence checked

OpenRouter's [usage rankings](https://openrouter.ai/rankings) used data through
2026-11-02. They measure traffic, not task accuracy or reliability. Its
[speed table](https://openrouter.ai/discover) placed GPT-OSS first, followed by
Beam and Qwen3.8 27B among the relevant alternatives. The displayed figures were
approximately 740, 483, and 425 tokens/s respectively; these aggregate values are
different from performance on a tools-compatible endpoint under our privacy filters.

| Candidate | Release listed by OpenRouter | Relevant evidence and tradeoff |
|---|---|---|
| [Beam 1.0](https://openrouter.ai/reflection/beam-1.0-501b-a23b) | 2026-10-16 | Recent alternative; 99.96% reported 72-hour inference availability. Together showed 0.24 s latency and 233 tokens/s; CoreWeave 0.55 s and 228 tokens/s |
| [Qwen3.8 27B](https://openrouter.ai/qwen/qwen3.8-27b) | 2026-08-14 | Fast, broader provider coverage, but older than Beam; retained as a considered alternative |
| [GLM 5.3 Flash](https://openrouter.ai/z-ai/glm-5.3-flash) | 2026-08-26 | Strong value/usage and tool-task benchmark evidence; considered for balance rather than leading the speed shortlist |

The public Endpoints API was also checked without credentials or inference.
Beam had five provider endpoints; four accepted both `tools` and `tool_choice`.
Baseten's advertised 482 tokens/s endpoint did **not** expose those parameters,
so that number is not a defensible promise for Timbre's tool-calling turns.
`require_parameters=true` keeps incompatible endpoints out of these requests.
The API's recent latency/throughput fields were null; the table above uses the
provider page, not invented API measurements. Detailed fetched metadata stays local.

OpenRouter documents that explicit [latency sorting](https://openrouter.ai/docs/guides/routing/provider-selection)
prioritizes first-token delay rather than using its default price/speed/reliability
balance. Our collection filters and tool requirements can change the available
route. Public measurements are moving observations; they do not establish a
service-level guarantee or predict multi-step customer-perceived latency.

Live application findings are recorded in the [refinement validation](phase3b-refinement.md).
No large comparative benchmark or Phase 4 evaluation is implied.
