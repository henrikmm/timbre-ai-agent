# Phase 3B Refinement: Customer Experience and Live Developer Activity

**Verified:** 2026-11-03.

## Result and launch

Fast now selects `reflection/beam-1.0-501b-a23b`. Standard is unchanged.
The [dated selection review](fast-model-selection.md) compares OpenRouter speed,
availability, recency, tool support, and routing rather than treating popularity
or maximum tokens/s as proof of application stability.

Start from the repository root with the installed web extra:

```bash
# Customer (default)
streamlit run app.py
# Developer; separate port if Customer is also running
TIMBRE_WEB_VIEW=developer streamlit run app.py --server.port 8502
```

There is no view switch in the page. A query parameter cannot enable diagnostics.
`TIMBRE_WEB_VIEW` is trusted server configuration, validated before client creation.
Each browser session still owns one shared-engine conversation; model changes,
history, reset, incomplete attempts, and explicit retries retain their semantics.
This remains local-only demonstration software, not production authentication.

Customer retains branding, Standard/Fast response selection, reset, conversation,
streaming, and input. It omits model IDs, internal telemetry/persistence notices,
language-adaptation slogans, blanket snapshot disclaimers, and history-management
details in errors. Static labels remain English; customer answers follow language.

Developer receives isolated sanitized events as execution occurs through the
optional `Conversation.send(on_event=...)` callback. It shows actual tool calls,
pending/completed/denied status, returned counts, source, and measured duration
above the final answer. The detailed timeline and metrics remain below it.
"Returned" describes the real tool outcome; no successful call is synthesized.
Raw result bodies, private rows, SQL, prompts, and hidden reasoning are not shown.

## Business decisions and source integrity

[ADR-010](decisions/010-customer-service-decisions.md) records the owner-authorized
decisions for all identified source issues. The backend derives resolved contact
alternatives and shipping terms from the local source. Payment calculations use
the detailed installment tiers and lowest single PIX offer without discount stacking.
Return channels, product-field precedence, mixed-payment limitations, and production
handoff are explicit. The shared prompt presents the useful service answer rather
than internal source reconciliation. Failed lookups/unsupported actions stay truthful.

No original CSV, policy JSON, or Portuguese source heading/text was edited. The
resolved projection has decision IDs and provenance; it is not a replacement source.
Live inventory, real campaign validity/audience, contact deliverability, legal
applicability, commercial transactions, and production authentication remain outside
the local demonstration. Those boundaries belong here rather than repeated warnings
inserted into ordinary customer answers.

## Executed validation

- Full suite with the documented original-material opt-ins: **145 tests passed**.
- UI tests verify server-selected views, invalid view rejection, isolated sessions,
  no query-parameter escalation, absence of Customer diagnostics, progressive event
  delivery before final text, real returned counts, unchanged authorization denials,
  model switching, retries, streaming, and source preservation.
- Synthetic policy tests use distinct contacts, a distinct freight threshold and
  fee, and distinct payment terms. They verify exact spellings/deduplication,
  inclusive threshold metadata, detailed-tier precedence, rounding, non-stacking,
  source bytes unchanged, and that callbacks cannot mutate stored trace events.
- CLI `--help`, synthetic repository examples, compile checks, and whitespace checks
  passed. Both loopback servers launched. Customer and Developer were inspected in
  a browser. Source content stays outside Git.

Exactly **four** newly authorized live interactions used Fast, the real SDK, the
prepared local sources, and the existing backend, with no automatic application retry:

| Interaction | Presentation | Calls: model / tools | End-to-end | Response review |
|---|---|---|---|---|
| Portuguese phones and emails | Developer | 2 / 2 | 5.812 s | Both phone and exact email alternatives, no contradiction narrative |
| Portuguese PIX and six-installment request | Developer | 3 / 3 | 6.427 s | Exact calculator totals/remainder amounts; no disputed-minimum or snapshot disclaimer |
| English online-return policy after Portuguese turns | Developer | 2 / 1 | 3.952 s | English answer with deadline, condition, reimbursement and return-shipping terms |
| Portuguese freight at the exact local threshold | Customer | 2 / 1 | 4.999 s | Free shipping at equality; no internal caveats, model name or trace in the page |

All four ended with `stop` and committed successfully. Reported cost was
**USD 0.01231825**, with coverage for all **9 model calls**; **7 tools** executed.
The actual model remained Beam and the attributed final provider was Nebius.
Three turns reported provider fallback; none reported cross-model fallback.
These timings include multiple model calls and do not equal provider-level TTFT.
They are a bounded smoke sample, not a general reliability/quality benchmark or SLA.

The original GPT-OSS failures remain historical evidence in
[the initial Phase 3B record](phase3b.md). They are not reported as successful
validation of the replacement. Public OpenRouter metadata, private screenshots,
and sanitized live records remain in ignored `local/phase3b-refinement/`.

## Implementation map

| Responsibility | Files |
|---|---|
| Startup view and display session | `src/timbre/web.py`, `app.py` |
| Live safe event delivery | `src/timbre/conversation.py`, `src/timbre/observability.py` |
| Resolved service policy | `src/timbre/knowledge/customer_policy.py`, `src/timbre/tools/executor.py`, `src/timbre/tools/payments.py` |
| Shared customer behavior and errors | `src/timbre/resources/system_prompt.md`, `src/timbre/presentation.py` |
| Fast selection | `src/timbre/resources/default.toml` |
| Focused checks | `tests/test_customer_policy.py`, `test_web.py`, configuration/SDK/CLI/payment checks |
| Decisions and documentation | README, architecture/observability/policy review, ADR-009, ADR-010, selection review, this record |

No new frontend framework, worker thread, API server, database, auth simulation,
business mutation, external message, commit/push, or Phase 4 evaluation was added.
