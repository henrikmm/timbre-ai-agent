# Phase 3B: Local Chat Interface and Streaming Diagnostics

This file retains the initial Phase 3B evidence below. The current startup views,
live tracing, replacement Fast model, and adopted policy behavior are documented
in [the refinement record](phase3b-refinement.md).

## Initial operation (superseded presentation)

Install `python -m pip install -e '.[web]'`, then run `streamlit run app.py`
from the repository root. Streamlit is pinned to **1.66.0**. The existing CLI
continues to run with `python -m timbre`, independently of the web extra.
Both use the same configuration, prompt, `Conversation`, tool executor, and observer.

The dark single-page interface uses native chat/Markdown, Standard/Fast and
Customer/Developer selectors, a reset button, and a pinned input. Customer is the
default. Model changes retain context; view changes make no model request.
Developer shows actual per-turn sanitized events in a scrollable vertical timeline,
with expandable details and recorded latency, model/provider, counts, tokens,
cost/coverage, errors, and fallback status. Missing values remain `N/A`.

Session state holds the backend instance and display records, rather than another
LLM history. Pending input is consumed before sending, and controls are disabled
during execution. Only the backend commits successful turns. Failed partial text
stays labelled incomplete; explicit retry creates a separate attempt. New chat
clears pending input, visible attempts, and model context while retaining metrics.
Reloading starts a fresh session. No business rules, prompts, or tool loop are
duplicated in Streamlit. No trace view grants authentication or private access.

## Streaming diagnosis

The existing CLI record at `2026-11-03T16:06:31Z` ended with
`status=incomplete`, `error_category=incomplete_response`, and
`finish_reason=length`. It made four model calls and twelve tool calls before
the final response truncated. The versioned budget was 512 tokens per model call;
the record's 1,377 output tokens are the aggregate across calls, not a per-call
limit. Reasoning and tool-call output share each call's budget.

This record provides evidence of output-budget exhaustion. It does not establish
a network outage, timeout, parser failure, or tool-iteration failure. The earlier
ignored 2,048-token diagnostic was inspected: all six turns completed without
incomplete streams. Raise the shared default to **2,048**, keeping the original
45-second deadline, model IDs, routing, reasoning settings, and tool limits.
This increases the available budget, not a completion guarantee.

The engine already rejects missing/abnormal terminal events and rolls back failed
turns. Keep those checks and disable automatic retries. Add optional per-call
`finish_reason`/`http_status` to real completion events for useful diagnostics.
Correct a metadata edge case where a missing final terminal event could retain
an earlier call's `tool_calls` finish reason. Retain measured timings/usage rather
than inferring tokens from visible chunks.

Live browser inspection also exposed joined tool-preamble/final-answer text and
BRL dollar markers parsed as Markdown math. Add paragraph boundaries between text
from successive model calls and escape `R$` only in web rendering. Do not truncate,
translate, or rigidly reformat stored answers. CLI static help, prompts, status,
debug labels, errors, and notices now use English, with `N/A` for missing metrics.
Source values/policies remain unchanged. The single shared prompt controls customer
language and prefers proportional summaries over unsolicited catalog tables.

## Validation on 2026-11-03

| Check | Executed evidence and result |
|---|---|
| Offline suite | Default run: 133 passed, 4 optional source checks skipped. Final full run with original-material opt-ins: all 137 passed |
| Original materials | Four opt-in source/CSV/policy checks passed separately |
| Launch and installation | Streamlit 1.66.0 launched on loopback; documented editable web-extra installation verified |
| UI state and streaming | AppTest exercised progressive callbacks, assembled text, multi-turn history, Standard/Fast, reset, and request-free view switching |
| Interrupted response | Synthetic `length` response stayed incomplete and outside backend history; rerender made no request; explicit retry completed as a separate attempt |
| Real traces and metrics | AppTest matched event counts/status to returned backend events; missing values stayed unavailable; browser showed actual live events |
| Privacy | Developer-mode order call remained denied; private identifiers were redacted; Customer view rendered no diagnostics; existing cross-owner authorization tests passed |
| CLI | Command dispatch/history/stats/errors/debug checks passed; CLI `--help` and synthetic query examples executed |
| Rendering | Literal BRL prices verified in AppTest and browser; stored answer remained unchanged; desktop and narrow layouts inspected |

Exactly **four** user-authorized live customer interactions were sent through the
browser, with no automatic retries or benchmark campaign:

| Scenario | Mode | Protocol outcome | Response review |
|---|---|---|---|
| Portuguese assortment overview | Standard | Completed; 4 model calls, 12 tools; 10.711 s | Portuguese, no price table; still verbose; proportional-response guidance subsequently tightened |
| English bounded product search | Standard | Completed; 3 model calls, 4 tools; 8.241 s | English answer; browser exposed currency/math rendering issue, subsequently fixed |
| Reference to the second product after switching models | Fast | Completed; 1 model call, no tools; 1.383 s | Resolved prior product correctly, but answered the English question in Portuguese |
| Fresh English bounded search after initial prompt refinement | Fast | Completed; 2 model calls, 1 tool; 26.772 s | BRL displayed correctly; answered in Portuguese and overstated immediate purchase availability |

Reported cost across these four turns was **USD 0.006890914**, with complete cost
coverage for all ten model calls. The sample executed seventeen tools. Standard
was attributed to DigitalOcean and Fast to Cerebras. No model fallback was reported;
provider fallback was reported on both Fast turns and remained visible in the UI.
View/model selections themselves added no requests.
Sanitized local telemetry and private screenshots remain under ignored `local/`.

Completion does **not** mean all quality requirements passed. After the Fast
findings, the shared prompt was tightened to explicitly follow the latest message's
language, translate source summaries accordingly, and avoid promising immediate
purchase from snapshot stock. That final wording was not rechecked live because
the four-interaction authorization was exhausted. Offline fixtures verify mechanics,
not model language compliance or factual quality. No additional paid calls were made.

## Limits and visual differences

- Traces appear after execution; text streams through the existing callback.
- Native Markdown and widgets replace decorative product cards, photos, action
  icons, and the reference's custom timeline. No unsupported product data is added.
- In-memory state is local and ephemeral. The server binds to loopback; Developer
  is a diagnostic view, not authentication or a public production interface.
- Provider/network failures, output/tool limits, and Fast-mode deadlines can still
  interrupt requests. Streaming failures remain visible and do not commit history.
- Fast language compliance and snapshot wording remain observed quality concerns.
  The final prompt refinement is not a demonstrated resolution.
- No production authentication, public deployment, mutation, or Phase 4 evaluation
  was added. No commit or push is implied by this implementation record.

## Implementation map

| Area | Files created or changed |
|---|---|
| Web presentation | `app.py`, `.streamlit/config.toml`, `src/timbre/web.py` |
| Shared status/CLI | `src/timbre/presentation.py`, `src/timbre/cli.py` |
| Stream assembly/diagnostics | `src/timbre/conversation.py`, `src/timbre/observability.py` |
| Shared settings/prompt/tool description | `src/timbre/config.py`, `resources/default.toml`, `resources/system_prompt.md`, `tools/executor.py` |
| Optional dependency | `pyproject.toml` |
| Focused checks | `tests/test_web.py`, `test_tool_conversation.py`, `test_benchmark_cli.py`, `test_llm_config.py` |
| Documentation | `README.md`, `docs/architecture.md`, `docs/observability.md`, this record, [ADR-009](decisions/009-streamlit-presentation.md) |
