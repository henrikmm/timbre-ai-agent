# Request observability contract

Phase 3A extends the existing observer with one `event_type="conversation_turn"`
schema-version-2 metrics record per interaction and schema-version-1 typed
execution events. Metrics default to
ignored `local/requests.jsonl`; trace events use the sibling
`local/requests.traces.jsonl`. Both use the same owner-only (`0600`) persistence
implementation. Anonymous UUIDs are not customer identities. No conversation
content, reasoning, private tool results, credentials, or upstream exception body
is stored. The original Phase 2 `llm_request` metric fields remain available;
versioned historical benchmark fixtures retain their original meaning.

## Preserved request fields

| Fields | Meaning |
|---|---|
| `schema_version`, `event_type`, `source` | Contract and evidence source: `live` or explicitly `synthetic_fixture`; plans use `not_executed` in their manifest only |
| `request_id`, `session_id`, `timestamp` | Application UUIDs and UTC request start timestamp |
| `response_id` | API generation ID, when available; distinct from application request ID |
| `mode`, `requested_model`, `actual_model`, `provider` | Selected mode/ID and API-reported actual model/provider; missing identity stays null |
| `provider_sort`, `reasoning_effort`, `streaming` | Effective requested configuration (`default` means the corresponding optional parameter was omitted) |
| `cross_model_fallback_enabled`, `fallback_used` | Requested cross-model policy and actual exact-ID mismatch; null if actual model is unavailable |
| `provider_fallback_used`, `upstream_attempts` | Observed same-model provider failover and router-reported attempt count, when supplied |
| `retry_attempts` | Application/SDK retries, always zero in Phase 2; excludes OpenRouter's own attempts |
| `time_to_first_event_seconds` | Start to first decoded SDK event; excludes SSE comments/heartbeats, can include metadata/reasoning-only events |
| `ttft_seconds` | Start to first non-whitespace customer-visible content delivered to the presentation callback; excludes reasoning and metadata |
| `total_latency_seconds` | Generation call start through normal exhaustion/error/interruption and synchronous presentation; excludes post-stream metadata lookup and logging |
| `streaming_generation_seconds` | First visible content event to last content event; only for streaming, zero for a single content event |
| `provider_latency_seconds`, `provider_generation_seconds` | Generation endpoint's reported milliseconds converted to seconds; separate from client timings |
| `input_tokens`, `output_tokens`, `total_tokens`, `reasoning_tokens`, `cached_tokens` | Chat API usage counts as reported; no character estimates or invented totals |
| `native_input_tokens`, `native_output_tokens`, `native_reasoning_tokens`, `native_cached_tokens` | Separately named provider-native generation-endpoint counts; never substituted into a different token basis |
| `output_tokens_per_second` | Native completion tokens / provider-reported generation seconds, only for a completed response with both inputs and positive duration |
| `cost_usd` | Actual reported request cost: Chat usage cost, filled/reconciled with generation `total_cost` if a lookup occurs |
| `session_cost_usd`, `session_cost_known_requests` | Cumulative observed costs and coverage within this anonymous conversation's session; null if none known |
| `status` | `success`, `failed`, `incomplete`, or `interrupted`; an internal `pending` value is never intentionally persisted |
| `error_category`, `http_status` | Stable safe category and available HTTP error status; no response bodies/messages |
| `timeout_occurred`, `incomplete_stream`, `partial_output` | Reliability flags; partial output means content was dispatched before failure/interruption |
| `finish_reason` | Normalized API stop/length/filter/tool/error indicator; unrecognized values become `unknown` |
| `metadata_lookup_status`, `metadata_lookup_seconds` | `not_needed`, `success`, `unavailable`, or `interrupted`, plus separate local lookup time |

## Measurement limits

Client TTFT marks content dispatch to the presentation layer, not a provider's
internal token timestamp or a measured screen-render event. Buffered mode's first
visible content arrives with the whole reply and must not be compared as streaming
TTFT. Metadata-only chunks and hidden reasoning never trigger TTFT. A terminal
`stop` plus normal iterator exhaustion and non-empty text are required for success.
Truncation (`length`), filters, malformed/incomplete tool output, errors, and
interruption cannot commit a successful turn. A complete `tool_calls` response
continues the bounded loop; it is not itself a final answer.

Completion counts can include reasoning; provider completion throughput is not
visible-text tokens per second. Chunk boundaries do not identify token boundaries,
so local streaming duration alone cannot yield exact token throughput. Single-chunk
replies and missing usage remain valid cases with null throughput. Missing costs
are not free requests, and failed/aborted requests may still be billed.

Router metadata may be absent. Same-model provider fallback and upstream attempt
counts remain unknown when not exposed. Model attribution compares explicit IDs;
use canonical model IDs for controlled comparisons, since aliases may resolve to
another ID without a true model failover. Account routing/privacy preferences can
also change which providers are eligible.

## Collection controls and summaries

`observability.enabled` controls JSONL writes, while session measurement remains
available. `record_tokens`, `record_cost`, `record_latency`, and `record_provider`
null their corresponding recorded fields in memory and on disk. Content logging
is deliberately unsupported: setting `store_conversation_content=true` fails.
Synthetic fixture records are permitted in tests only with an explicit source label.

`generation_metadata="missing"` makes at most one short lookup when an API ID exists
and requested provider/cost information is missing. `"off"` avoids all lookups;
`"always"` requests one after each non-interrupted attempt with an API ID and may
make provider-native throughput available. It adds monitoring requests and time
between turns; no polling or retry occurs. Lookup errors do not invalidate an
otherwise complete reply. `metadata_timeout_seconds` defaults to two seconds.

Session and benchmark summaries include observed totals, sample counts/coverage,
median and P95 TTFT/latency, mean available throughput, known costs, failure rate,
timeouts, fallback, and provider identities. P95 uses linear interpolation.
Session latency summaries describe successful attempts, possibly including fallback;
comparative benchmark latency/throughput require successful explicit model attribution.
Benchmark costs cover all executed requests with reported costs, including failures.

## Phase 3A interaction aggregation

The conversation engine uses request measurements for each model call and emits
one aggregate interaction record. `request_id` is the application interaction ID;
`turn_id` and `trace_id` correlate its events. `response_id`, `actual_model`, and
`provider` preserve the last observed call identity; `actual_models` and `providers`
retain the observed identities across calls. Per-call trace request IDs are backend
generated and distinct from the API generation IDs used for metadata lookup.

| Added field | Meaning |
|---|---|
| `turn_id`, `trace_id` | Correlation with the complete interaction and its events |
| `model_call_count`, `tool_call_count` | Model generations attempted and tools executed in the interaction |
| `model_execution_seconds` | Sum of local model execution durations, excluding tool and metadata time |
| `tool_execution_seconds`, `tool_durations_seconds` | Total tool duration and duration grouped by allowlisted tool name |
| `tool_failure_count` | Tool outcomes that are validation/authorization/backend failures; an empty match is not itself an infrastructure failure |
| `validation_failure_count`, `authorization_denial_count` | Explicit validation and access-control outcomes |
| `overall_latency_seconds` | Full interaction wait, including post-generation metadata lookup |
| `cost_known_model_calls`, `observed_cost_usd` | Cost coverage and sum of costs actually reported for known calls |
| `token_coverage` | Number of model calls reporting each token metric |
| `actual_models`, `providers` | Safe distinct observed identity values across the interaction |

`cost_usd` and aggregate token fields require complete per-call coverage; missing
calls leave them null. `observed_cost_usd` is a known subtotal, never proof of the
full bill. Each request measurement merges cumulative usage snapshots before
aggregation, so repeated usage chunks do not double-count. Metadata reconciles
that same request rather than adding a second cost. Missing metrics are never
estimated from text. Session summaries retain cost/token coverage.

The summary's `total_cost_usd` sums only fully covered interaction costs, while
`observed_cost_usd` includes the known per-call subtotals from partially covered
interactions. Neither implies charges were absent for unreported calls. CLI
`/stats` shows the observed subtotal together with known/attempted model-call
coverage; complete-interaction coverage remains separately available. The legacy
`requests`/`cost_known_requests` names count interactions in Phase 3A.

Interaction `ttft_seconds` measures first customer-visible text from interaction
start; first-event time may precede any answer text. `total_latency_seconds`
measures through answer availability and excludes later metadata lookup;
`overall_latency_seconds` includes it. Individual model and tool durations remain
separate. A synchronous timeout is a bound on controllable phases rather than a
hard real-time deadline interrupting arbitrary blocking transport code.

## Typed execution-event contract

`TraceEvent` exposes `to_dict()` and the existing observer provides
`get_events(turn_id=None) -> list[TraceEvent]`. Returned objects are isolated
snapshots. The in-memory buffer retains the latest 2,000 events per observer;
JSONL retention/rotation is an operational responsibility. The conversation also
provides the latest turn trace for CLI/future interface consumers.

| Field | Meaning |
|---|---|
| `schema_version`, `event_type`, `timestamp` | Typed event contract, event name, UTC timestamp |
| `session_id`, `turn_id`, `trace_id` | Backend-generated anonymous correlation IDs |
| `span_id`, `llm_request_id`, `tool_call_id` | Backend-generated execution/request/tool correlation; raw model IDs are not persisted |
| `tool_name`, `sanitized_arguments` | Allowlisted name and minimized validated metadata; unknown names/free text/private order IDs are redacted |
| `source` | Logical data source such as SQLite or policy catalog; no filesystem path or raw SQL |
| `duration_seconds`, `result_count` | Monotonic execution measurement and safe count; null when not applicable |
| `status`, `error_category` | Stable execution outcome without exception messages or result bodies |
| `finish_reason`, `http_status` | Optional per-model-call terminal reason and HTTP code for interruption diagnosis (Phase 3B additive fields) |

Lifecycle events include `request_started`, `llm_request_started`,
`llm_request_completed`, `tool_call_requested`, `arguments_validated`,
`tool_execution_started`, `data_source_accessed`, `tool_execution_completed`,
`tool_result_returned`, `final_answer_generated`, and `request_completed` or
`request_failed`. A denied operation emits no successful private data-source access.
A source event describes observed execution, not proof of data freshness or final
answer accuracy.

`record_latency=false` also suppresses trace durations. Other existing collection
switches apply to their corresponding aggregate fields. Traces never contain raw
prompts, replies, reasoning, free-text searches, private row values, or secrets.
The CLI uses these actual events for `/trace` and optional `/debug on` output;
`/debug off` returns to concise presentation. Authorization is identical in every
presentation mode. The typed API is independent of terminal printing and can be
consumed by Phase 3B without reconstructing events from text. The Streamlit
Developer server consumes these sanitized events through `Conversation.send(on_event=...)`
as they occur, then uses `TurnResult.events` and the recorded metrics for details.
The callback receives an isolated copy after collection preferences apply. It never reads global JSONL
files or shows another browser session's data. Customer view does not render
these diagnostics. Missing final terminal reasons remain null rather than
inheriting a previous model call's `tool_calls` reason.

Sources: [router metadata](https://openrouter.ai/docs/guides/features/router-metadata),
[generation metadata](https://openrouter.ai/docs/api/api-reference/generations/get-generation),
[reasoning usage](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
