# ADR-004: OpenRouter and Model Strategy

**Status:** Accepted for implementation; model performance hypotheses await live validation.
**Date:** 2026-11-02.

## Context

Timbre needs a standalone streaming conversation layer and a controlled comparison
between response quality and latency. A unified endpoint can expose different
models/providers without coupling conversation state to their SDK objects.

## Decision

Use the official `openrouter==1.3.107` Python SDK, isolated behind normalized
`LLMEvent`/`Usage` records and safe `LLMError` categories. Use plain message mappings
to permit future message extensions without introducing tools now. Pin the SDK;
retain its implementation rather than adding a second OpenAI SDK adapter.

The initial Standard model is `deepseek/deepseek-v4.1-flash-1017`, with default
balanced routing. Fast uses `openai/gpt-oss-120b` and `provider.sort="latency"`.
These choices express the project's quality and latency hypotheses, not measured
Timbre results. Open-weight models are prioritized to preserve a potential future
path to local deployment; actual hardware, license, operational cost, and serving
requirements must be evaluated separately.

TOML controls modes, output budget, history, routing, and optional reasoning.
`OPENROUTER_API_KEY` comes only from an explicit local dotenv file or the shell;
the shell wins. No sampling or reasoning parameter is sent by default. Fast's
verified effort allowlist permits opt-in settings; Standard's effort controls
remain unset until their exact contract is verified. Require providers to support
requested parameters instead of silently dropping them.

Keep three choices distinct: manual mode selection, provider fallback for a model,
and optional cross-model fallback using OpenRouter's ordered `models` list.
Disable SDK/application retries. Never replay a partially displayed answer.
Record requested/actual model separately and announce cross-model fallback.
Comparative benchmarks disable it and exclude unattributed results.

## Alternatives considered

- Direct individual-provider SDKs: more control, but repeated routing/client work.
- OpenAI-compatible SDK: acceptable if the official SDK has a concrete blocker;
  offline transport tests found no blocker for this implementation's interfaces.
- Agent frameworks: unnecessary dependencies for this synchronous, tool-free scope.
- Local inference now: stronger infrastructure control, but no evaluated serving
  environment or hardware commitment exists.

## Rationale

One provider adapter keeps streaming/error translation small, testable, and
replaceable. Supported routing controls avoid custom failover loops and expose
provider variability for evaluation. SDK source and public documentation were
inspected; the obsolete supplied Chat reference URL was replaced by the current
[Chat reference](https://openrouter.ai/docs/client-sdks/python/sdks/chat/README).

## Consequences and trade-offs

Availability, latency, costs, caching, and supported parameters depend on external
providers and account preferences. A latency sort is not a guaranteed response
deadline; throughput alone does not measure customer wait time. Default routing
can also be influenced by account settings. Open-weight inference through a
third party is external data processing, not local inference or automatic privacy.
The defaults request `data_collection="deny"`; ZDR is independently configurable,
and either constraint can reduce provider availability. Neither setting is a
complete privacy/compliance guarantee.

## Validation strategy

Offline tests run the pinned SDK against `httpx.MockTransport`, exercising actual
serialization, SSE parsing, routing/usage shapes, safe errors, timeouts, and zero
SDK retries. Official model pages confirm the requested IDs, but no inference
request has been executed. Follow the [private live-test guide](../phase2.md) to
validate credentials, account routing, actual model/provider, behavior, and costs.

Sources: [SDK overview](https://openrouter.ai/docs/client-sdks/python/overview),
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[model fallback](https://openrouter.ai/docs/guides/routing/model-fallbacks),
[DeepSeek model](https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017),
[GPT-OSS model](https://openrouter.ai/openai/gpt-oss-120b).
