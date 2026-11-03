# Phase 3A: Business Tools and Execution Tracing

Phase 3A extends the existing backend and CLI with real function calling over the
prepared SQLite snapshot and policy catalog. It preserves the pinned OpenRouter
SDK, configured Standard/Fast modes, streaming presentation, history, and observer.
It introduces no agent framework, web UI, authentication infrastructure, purchase,
stock mutation, payment processing, refund execution, or formal evaluation suite.

## Run and reproduce

From the repository root, after installing dependencies and preparing authorized
local materials as described in the [README](../README.md):

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m timbre
```

The offline test command uses synthetic fixtures and requires no credentials or
network. Original-material checks remain explicitly opt-in using the variables
in [validation instructions](validation.md). A CLI customer message makes live,
potentially billable model requests and requires a private `OPENROUTER_API_KEY`.
Do not paste credentials into chat or commit the local `.env`.

Use `/debug on`, enter `Which guitars are available under R$1,000?`, then `/trace`
and `/stats`. Follow with `What about the second one?` and `Can I pay for that in
six installments?` to inspect the retained context and actual tools selected.
`/debug off` restores concise output. Debug mode never grants order access.
`/mode standard` and `/mode fast` preserve context; `/clear` resets history while
retaining session statistics and system instructions.

The `[tools]` TOML table configures `database_path`, `policies_path`,
`max_iterations` (default 4), and `max_calls_per_turn` (default 12). Paths are trusted
application configuration, never model arguments. Configuration validation rejects
invalid limits. A missing database/catalog yields a safe backend outcome; it does
not trigger unrestricted fallback access or synthetic production answers.

## Tool catalog

| Tool | Business purpose and boundary |
|---|---|
| `search_products` | Name/category/brand/price search with bounded results; English category aliases; sellable availability requires active status and stock |
| `get_product_details` | Trusted catalog price, status, stock, description, and parsed specifications for one product; absent fields remain absent |
| `get_store_policy` | Relevant source-linked Portuguese policy sections, including related clauses; withdrawals, defects, exchanges, and warranty stay distinct |
| `get_active_promotions` | Flagged campaigns on sellable snapshot products with original price/discount; missing dates/eligibility remain explicit |
| `calculate_payment_options` | Trusted product price plus deterministic Decimal rules, non-stacking discounts, installment allocation and unavailable-option reasons |
| `get_my_order_status` | Minimal owner-filtered historical status/tracking; denied for every public unauthenticated CLI session |

Every definition has a unique name, purpose description, JSON object schema, and
validated Python implementation. Unknown fields/names, malformed JSON, invalid
IDs/types, and out-of-range limits cannot become unrestricted backend requests.
Results distinguish success, empty, invalid arguments, authorization denial, and
backend failure. Monetary values are serialized as decimal strings with source
metadata and safe error codes. Tool results are untrusted data, not instructions.

Brand is matched conservatively using product-name evidence; the schema has no
independent brand column. Category translation does not translate or overwrite
stored values. Positive stock alone never makes a discontinued or coming-soon
product sellable. A no-match search differs from unavailable matching products.
Campaign information remains snapshot evidence, not proof of live applicability.

## Tool-calling lifecycle

1. Send bounded history and tool definitions through the existing SDK adapter.
2. Collect indexed streaming deltas into complete call IDs, names, and arguments.
3. Require normal stream exhaustion and an appropriate terminal tool-call reason.
4. Validate the allowlist, JSON schema/types, limits, and trusted authorization.
5. Execute controlled read-only Python operations and record sanitized metadata.
6. Append the assistant tool calls and one result per matching tool-call ID.
7. Continue within the configured iteration/call budget, streaming final text through
   the existing callback.
8. Commit the complete turn only after a non-empty, successfully completed final
   response; failed or interrupted turns retain previous history.

Multiple calls in one response retain independent associations. The executor never
runs partial streamed JSON. There are no automatic application retries or side
effects. Follow-ups and comparisons reuse normal context and the same tools rather
than dedicated tools for each conversational phrasing. English is the default
response language for this phase; original source policy text remains Portuguese.

## Traces and metrics

The existing `Observer` exposes `get_events(turn_id=None) -> list[TraceEvent]` for
isolated event snapshots. The in-memory buffer retains the latest 2,000 events per
observer/session. `/trace` reads this interface, which a future web UI can reuse.
Metrics stay in ignored `local/requests.jsonl`; trace events use the sibling
`local/requests.traces.jsonl`. Both use the same owner-only writer and persistence
failure reporting. No raw database rows or conversation text are stored.

Each typed event contains `schema_version`, `event_type`, `timestamp`, `session_id`,
`turn_id`, `trace_id`, `span_id`, `llm_request_id`, `tool_call_id`, `tool_name`,
`sanitized_arguments`, `source`, `duration_seconds`, `result_count`, `status`, and
`error_category`. Trace tool IDs are generated by the backend; model-provided IDs
remain only in in-memory protocol messages to avoid PII hidden inside identifiers.

Events describe request start, tool request, validation, execution, logical source
access, result return, final generation, and completion/failure. Logical source
names identify tables or policy retrieval without exposing filesystem paths or SQL.
Free-text arguments/private identifiers are redacted. Unknown tool names and error
messages cannot inject arbitrary content into telemetry.

One metrics record covers the complete customer interaction. It aggregates usage
once per model call, preserving TTFT, request latency, reported cost, model/provider,
fallback, errors, and metadata coverage. Added fields include model/tool counts,
separate model/tool execution times, per-tool durations, failures, validation failures,
authorization denials, and overall customer-perceived latency. `cost_usd` and token
sums require complete coverage; `observed_cost_usd` records the known subtotal and
`cost_known_model_calls`/`token_coverage` explain missing values. Metadata lookup is
excluded from answer-available latency and included in overall latency.

See the [complete observability contract](observability.md). Trace success explains
execution, not the factual quality of every sentence produced by the model.

## Financial and policy decisions

Prices come from the trusted catalog, never model-generated amounts. Arithmetic
uses `Decimal` and exact cents, including remainder allocation for installments.
The implementation uses reviewed source-linked policy rules; it prevents campaign
and PIX stacking and reports unsupported requests or ambiguous conditions. Payment
methods must exist in the policy table; absent methods are not silently enabled.

The source does not fully resolve competing promotions, campaign dates/audiences,
installment wording, contact discrepancies, or the shipping threshold equality.
Those facts must remain qualified. A campaign merely mentioned in the manual is
not automatically active. Calculations and policy retrieval cannot authorize
commercial exceptions, process a payment, or approve a refund. See the
[ambiguity review](policy_review.md).

## Security and LGPD-oriented review

| Concern | Implemented boundary | Remaining production requirement |
|---|---|---|
| Purpose and minimization | Task-oriented reads; no customer directory; minimal order projection | Confirm lawful purpose/basis and production fields with the controller |
| Authorization | Deny-all public sessions; trusted opaque context; owner-filtered queries | Real identity verification, session lifecycle, abuse controls, and deployment isolation |
| External model providers | Bounded context/tool results; no credentials or raw customer tables; configured collection preferences | Review contracts, processor/subprocessor roles, retention, actual provider controls, and international transfers |
| Logging and retention | Sanitized content-free local JSONL; owner-only files; bounded in-memory events | Define deletion/rotation/retention/access policies for persistent metrics and backups |
| Repository exposure | Ignored supplied CSV/PDF/database/policy/credential files; synthetic public fixtures | Audit actual history/releases and redistribution rights before publication |
| Data accuracy and rights | Preserved source values/provenance; historical-snapshot disclaimers | Refresh cadence, policy/version approval, correction and data-subject request procedures |

The model cannot supply/override an authenticated customer ID. Names, email, phone,
order numbers, or a dictionary are insufficient authentication. A simulated customer
A must not read customer B's order. Private authorization runs before database
access, and nonexistent/other-owner orders share an unavailable outcome.
The requested phone/purchase-history disclosure has no allowlisted capability.

Policy text, descriptions, and customer input can contain prompt injection. They
never grant backend privileges or change allowed tool signatures. Prompt defenses
cannot guarantee that every model sentence is safe; backend access enforcement and
minimized data remain independent controls. File possession or arbitrary trusted
Python execution can bypass application interfaces, so SQLite is not a row-level
security boundary. These controls do not establish complete LGPD compliance.

## Validation record

### Initial live checks: 2026-11-03

The six bounded initial checks used the real SDK, configured models, prepared
SQLite snapshot, and policy catalog. Private response/trace evidence remains in
ignored `local/phase3a/smoke_results.json`; no original policy text or customer data
is copied into this report.

| Scenario | Mode | Observed execution and outcome |
|---|---|---|
| Available guitars below the requested budget | Standard | `search_products`; final response completed |
| Takamine GD20 price | Standard | `search_products`; final response completed |
| Store address | Standard | `get_store_policy`; final response completed; prompt refinement followed to avoid unsolicited conflicting contact details |
| Online purchase returns | Fast | `get_store_policy` returned data; final generation timed out at the default 45-second interaction budget |
| Product payment options | Fast | `search_products` returned data; interaction timed out before a completed payment explanation |
| Request for customer 15's phone and purchase history | Fast | Refused in English without tools or private disclosure |

These checks demonstrate actual tool selection and successful Standard-mode
operational answers. They also expose a Fast-mode latency limitation. A tool
return followed by timeout is a failed interaction, not a successful customer
answer. No broad quality, reliability, performance-ranking, or legal-compliance
claim follows from this small diagnostic sample.

Final automated verification on **2026-11-03**:

- `python -m unittest discover -s tests -v`: **128 tests run, 124 passed,
  4 opt-in original-material tests skipped**, with no failures.
- The four original-material tests passed separately with
  `TIMBRE_RAW_DIR=data/raw TIMBRE_POLICIES_PATH=knowledge/policies.json`.
  They check complete CSV parity, repeated import, policy provenance, and original
  PDF line preservation. They do not modify the supplied source files.
- CLI help, the synthetic query example, and whitespace checks passed.

Three bounded follow-ups investigated the initial failures:

| Follow-up | Observed result |
|---|---|
| Standard address after prompt refinement | Successful source-linked answer without unsolicited conflicting contact details |
| Fast payment, low reasoning and 90-second local deadline | Two invalid search requests, then a successful detail lookup, followed by timeout; no completed payment answer |
| Fast online returns, low reasoning and 90-second local deadline | Successful policy lookup and English answer in about 51 seconds |

The invalid-argument results were refined to return safe allowed/required field
names and explain that unused optional fields should be omitted rather than set
to `null`. Validation remains strict; feedback never echoes unknown keys or input
values. A final three-turn diagnostic verified:

- Standard beginner-instrument search followed by **"the second one"** resolved
  the previously listed product. The follow-up made two payment-calculator calls
  and one policy call, produced exact PIX amounts, and preserved the disputed
  six-installment minimum instead of claiming approval.
- Fast completed an explicitly directed payment-calculator request after the
  schema guidance refinement, with one successful tool call and a final English
  answer in about 52 seconds (90-second local deadline, low reasoning).

Response review caught one more issue: the first successful Fast payment response
overstated a snapshot calculation as checkout-ready pricing. Payment results now
explicitly return `quote_status="snapshot_calculation_only"`,
`live_quote_confirmed=false`, and `checkout_supported=false`. The prompt separates
policy-selection eligibility from current quote confirmation. One final Fast
follow-up completed with a calculator call and explicitly explained that the amount
was a snapshot, not a guaranteed live quote or authorization to check out.

These **thirteen customer turns** (ten completed, three failed), including
diagnostic failures, are the complete network-permitted live sample for this phase.
They made 29 model calls and 19 tool executions. Completion status alone is not a
quality score; the response review and its refinements are described above.
An initial sandbox network failure was retried only after
using the permitted network execution path. No cross-model fallback was enabled
in these checks. The original model IDs, routing, 45-second timeout, output budget,
and default reasoning settings remain unchanged in versioned configuration.
The diagnostic overrides are not evidence that Fast meets the default deadline
or selects the correct tools reliably for complex requests. Transport overhead
can exceed the requested synchronous deadline. Strict validation, missing cost
coverage, failure traces, and history rollback remained visible in failed turns.

Detailed responses and diagnostic scripts are private, ignored artifacts under
`local/phase3a/`. Sanitized metrics/events are in its `requests*.jsonl`,
`diagnostic_requests*.jsonl`, `final_requests*.jsonl`, and `quote_requests*.jsonl`
files. They are
implementation diagnostics, not a formal evaluation suite or submission report.

To reproduce the focused checks without running a benchmark:

```bash
python -m unittest discover -s tests -v
TIMBRE_RAW_DIR=data/raw TIMBRE_POLICIES_PATH=knowledge/policies.json \
  python -m unittest discover -s tests -p test_original_materials.py -v
python -m timbre
# /debug on
# /mode standard
# Which Yamaha guitars are available under R$1,000?
# What is the price and availability of the Takamine GD20?
# What is the store address?
# Find exactly two available beginner acoustic guitars under R$900.
# What about the second one? Explain PIX and six-installment options.
# /trace
# /stats
```

To reproduce the Fast diagnostic configuration, copy the complete default TOML
to ignored `local/phase3a.toml`, set `[llm].timeout_seconds = 90`,
`[llm].cross_model_fallback = false`, and
`[llm.modes.fast].reasoning_effort = "low"`; run
`python -m timbre --config local/phase3a.toml`, then `/mode fast`. Each customer
turn can make several billable model calls; no automatic retries occur.

Focused tests exercise backend validation/dispatch, streamed call reconstruction,
query behavior, money, authorization/ownership, failures, trace privacy, and metrics.
The existing Phase 2 benchmark is retained; this phase adds implementation tests
rather than a formal evaluation campaign. Its legacy `planned_requests` counts
interactions, which can each generate up to `max_iterations + 1` model calls.

## Implementation files

| Area | Files |
|---|---|
| Registry, dispatch, validation, business calculations | `src/timbre/tools/__init__.py`, `executor.py`, `payments.py` |
| Controlled data access | `src/timbre/database/repositories.py` |
| SDK protocol and reconstruction | `src/timbre/llm/types.py`, `openrouter.py` |
| Conversation lifecycle and metrics | `src/timbre/conversation.py`, `observability.py` |
| Configuration, prompt, CLI | `src/timbre/config.py`, `cli.py`, `resources/default.toml`, `resources/system_prompt.md` |
| Focused technical tests | `tests/test_tools.py`, `test_tool_call_adapter.py`, `test_tool_conversation.py`, `test_phase3a_integration.py`; extended `llm_support.py` and `test_llm_config.py` |
| Documentation | `README.md`, this guide, architecture/observability/policy review, ADR-006 through ADR-008 |

Existing Phase 2 changes were already present in the working tree before Phase 3A;
this file map identifies the relevant implementation surfaces, not a claim that all
of them originated in this phase. Original materials, local databases, credentials,
and derived policy content remain excluded from Git.

## Decisions and scope boundary

[ADR-006](decisions/006-function-calling-architecture.md) records the bounded SDK
loop and backend responsibilities. [ADR-007](decisions/007-tool-design-business-rules.md)
records tool granularity, structured results, money, and authorization.
[ADR-008](decisions/008-execution-tracing.md) records correlation, metrics, trace
privacy, CLI debugging, and future visualization requirements.

Phase 3B may consume these real events in a minimal UI. Phase 4 may add systematic
quality evaluation. Neither is implemented or started by Phase 3A.
