# ADR-006: Function Calling Architecture

**Status:** Accepted for Phase 3A.
**Date:** 2026-11-03.

## Context

Phase 2 already provides the official pinned OpenRouter SDK adapter, streaming,
transactional conversation history, two model modes, and private observability.
Operational answers require authoritative local data rather than model recollection.
The solution must preserve those layers without introducing an agent framework.

## Decision

Extend the existing Chat Completions adapter with function definitions and normalized
tool-call deltas. Preserve the configured model IDs, routing, reasoning settings,
error categories, and optional metadata lookup. Verify the installed SDK models and
transport behavior as well as the [OpenRouter tool-calling contract](https://openrouter.ai/docs/guides/features/tool-calling).

The conversation engine owns a bounded loop: send messages and tool definitions,
collect a complete assistant response, reconstruct indexed tool calls, validate
protocol completion, execute each requested call, append the assistant call message
and a tool result with its matching ID, and ask the model to continue. A configurable
iteration/call budget prevents uncontrolled execution. Incomplete or truncated calls
never reach Python implementations. Multiple calls retain their own IDs and results.

The model selects tools and explains results. The backend owns schema validation,
allowlisting, authorization, database queries, exact money calculations, structured
results, sanitization, and safe failures. All initial tools are read-only. There is
no arbitrary SQL, path access, code execution, mutation, or authentication tool.

Preserve complete tool exchanges within bounded in-memory conversation turns, so
references such as "the second one" retain product IDs and earlier results. Commit
history only after a complete final response. Failed turns leave prior history
intact. Stream customer-visible answer text through the existing presentation
callback; do not send reasoning or raw tool arguments to that callback.

## Alternatives considered

- LangChain/LangGraph or a separate orchestration service: adds dependencies and a
  competing lifecycle without a demonstrated need.
- Injecting the entire database/manual into the prompt: excessive disclosure,
  token use, stale interpretation, and no independent authorization/calculation.
- A generic SQL tool: exposes unrelated private tables and weakens least privilege.
- One tool for each table or conversational phrasing: couples intent to storage and
  duplicates product comparison/follow-up behavior already supported by context.

## Consequences

Both configured models share one protocol and backend. Schema compatibility and
live tool-selection behavior still depend on the selected provider. The loop is
synchronous and bounded; concurrent use of one conversation object is unsupported.
Prompt instructions improve behavior but cannot prove grounding or authorization.
Policy/database text is untrusted data and cannot override system instructions.
Safe errors let the model explain unavailable information without exposing paths,
SQL, private rows, or upstream exception bodies.

See [ADR-007](007-tool-design-business-rules.md),
[ADR-008](008-execution-tracing.md), and the [operation guide](../phase3a.md).
