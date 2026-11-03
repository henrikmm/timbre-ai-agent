# ADR-009: Local Streamlit Presentation

**Status:** Accepted for Phase 3B.
**Date:** 2026-11-03.

## Context

A short local demonstration needs a clean conversation view and an understandable
developer trace. Phase 3A already supplies transactional history, a streaming text
callback, controlled tools, authorization, and sanitized correlated events. A new
frontend/backend boundary would add complexity without helping this requirement.

## Decision

Use optional, pinned Streamlit with native chat, Markdown, segmented controls,
containers, metrics, and expanders. Keep dark-theme/loopback configuration in
`.streamlit/config.toml` and a small CSS block in `app.py`. No Node toolchain,
JavaScript visualization framework, API server, or additional database is needed.

Each browser session stores one `WebSession`/`Conversation` in `st.session_state`.
Only `Conversation` owns the LLM history. Display records contain customer text,
visible output, and returned `TurnResult` references; they are never fed back to
the model. Consume queued input before `send` so page rerenders cannot repeat a
request. Model changes preserve backend context. The server selects Customer or
Developer with `TIMBRE_WEB_VIEW` at startup.
There is no view toggle or URL override. Customer contains no model IDs or generic
engineering warnings. Reset clears the conversation and its visible attempts.

Call the existing synchronous `send(on_text=...)` once, updating a native Markdown
placeholder as chunks arrive. A callback fits the existing interface without
threads, queues bridging worker threads, or a second tool loop. Escape literal BRL
dollar markers only for Markdown rendering. Failed partial output remains visibly
incomplete and cannot enter committed model history. Retry is an explicit, separate
turn. No rigid response truncation or product-specific rendering is introduced.

Developer receives isolated sanitized events through the existing engine's optional
`on_event` callback during execution. It shows per-call progress and returned counts
above the answer, then uses `TurnResult.events` and metrics for detailed inspection.
It exposes operation timings separately from answer-available and
overall interaction latency, and preserves `N/A`/coverage for missing metrics.
It supplies no identity controls or additional capabilities. Bind to loopback and
do not treat the startup view as authentication.

## Streaming correction

The local CLI failure ended with `finish_reason=length` under the versioned
512-token per-model-call budget. The existing ignored 2,048-token diagnostic
completed all six interactions. Raise the shared default to 2,048; retain failure
detection and rollback for every nonterminal, truncated, empty, or interrupted
response. Do not automatically retry. Add optional finish reason/HTTP status to
each model-completion trace, and prevent a missing final terminal event from
inheriting an earlier tool-call finish reason. Separate visible text from successive
model calls with paragraph boundaries; this does not alter tool protocol messages
or token measurements. See [Phase 3B evidence](../phase3b.md).

## Alternatives and consequences

- React or an API service would require a second stack and session boundary.
- A separate Streamlit agent loop would duplicate tool rules and risk history drift.
- Worker-thread streaming would complicate cancellation and Streamlit contexts.
- A custom product-card renderer would depend on unsupported images/metadata.

The result is deliberately a local demonstration: session history is ephemeral,
detailed metrics appear after completion, and provider deadlines/output limits can
still fail. Native widgets keep the layout responsive, but do not reproduce every
decorative element in the reference. Production authentication, public deployment,
and Phase 4 evaluation remain outside this decision.

References: [native chat](https://docs.streamlit.io/develop/api-reference/chat),
[session state](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state),
[AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
