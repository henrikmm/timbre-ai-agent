# ADR-008: Execution Tracing

**Status:** Accepted for Phase 3A.
**Date:** 2026-11-03.

## Context

One customer interaction may now contain multiple model requests and tool calls.
Phase 2 request metrics alone cannot explain tool selection, validation, source
access, authorization denials, or the customer's full wait. Phase 3B needs actual
structured events rather than reconstructed terminal text.

## Decision

Extend the existing observer with typed trace events and per-turn aggregation.
Correlate anonymous session, conversation-turn, trace, model-request, tool-call,
and span IDs. Use UTC timestamps and monotonic durations. Events cover request
start, requested tool, argument validation, execution start, logical source access,
execution completion, result return, final answer, and turn completion/failure.
Retrieve events by turn through a small backend API independent of CLI printing.

Record only allowlisted metadata: logical source, known tool name, sanitized
arguments, status, error category, duration, and result count. Redact free text and
private identifiers; never log private tool rows, prompts, responses, reasoning,
credentials, or raw upstream errors. Do not interpolate unknown model-supplied tool
names or malformed arguments into logs. Owner-only local persistence and existing
observability switches remain applicable. Buffers are bounded.

Preserve existing request measurements while aggregating usage and cost once per
model call, rather than adding cumulative stream snapshots. Distinguish model time,
tool time, metadata lookup time, and overall interaction latency. Missing usage or
cost remains unavailable with coverage counts. Add model/tool call counts, per-tool
duration, failures, validation failures, and authorization denials. Fallback and
provider attribution remain observations, not assumptions.

The normal CLI stays concise. `/debug on` and `/debug off` control sanitized execution
details; `/trace` presents the latest turn. Debugging has no effect on authorization.
No web interface, hosted tracing processor, or second observability subsystem is
introduced.

## Alternatives considered

- Terminal print scraping: loses typed correlation and makes future visualization
  dependent on presentation text.
- Full argument/result logging: convenient diagnostics but excessive PII disclosure.
- A hosted observability platform: adds another external data processor before the
  local requirement is demonstrated.
- Summing every usage-bearing chunk: can double-count cumulative API usage.

## Consequences

Sanitized traces explain the execution path but deliberately cannot reconstruct
private conversations. Trace success proves protocol/backend outcomes, not factual
quality of every final sentence. Missing provider metrics/cost and incomplete calls
stay visible. Local filesystem access and trusted backend composition remain
security boundaries; telemetry is not a legal-compliance certification.

See the [observability schema](../observability.md) and
[LGPD-oriented limitations](../phase3a.md#security-and-lgpd-oriented-review).
