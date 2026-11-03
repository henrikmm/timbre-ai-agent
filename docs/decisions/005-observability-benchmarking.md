# ADR-005: Observability and Benchmarking

**Status:** Accepted; instrumentation verified offline, performance unmeasured.
**Date:** 2026-11-02.

## Context

A model can generate many tokens per second while taking a long time to start.
Provider fallback and incomplete metadata can also invalidate model attribution.
Timbre therefore needs measurements that separate the customer's wait, inference
behavior, cost coverage, reliability, and eventual response quality.

## Decision

Create a dedicated observability module, independent of SDK and presentation.
Use `time.perf_counter()` for request-relative timing and UTC for timestamps.
Separate first decoded event, first visible text content, full request duration,
and first-to-last visible streaming content duration. Record routing, anonymous
session/request IDs, usage, actual reported cost, safe failure categories, and
interruption status. Missing values are `null`, never zero-filled estimates.

Persist one allowlisted JSONL record per attempt with owner-only permissions.
Never persist prompts, customer/assistant text, reasoning, credentials, or upstream
error bodies. Session totals report known-cost/token coverage. Measurements exist
in memory even when JSONL persistence is disabled; persistence failures remain
explicit. `/stats` is separate from response streaming.

Request router metadata in the inference response. Optionally make one bounded
generation-metadata lookup after streaming to fill missing provider/cost data,
or always when explicitly configured. Exclude that lookup from request latency
and record its own duration. Compute throughput only when native completion
counts and provider generation time are both available. Do not infer token counts
from characters or divide mixed timing/token bases.

Use eight synthetic conversational scenarios, identical customer prompts, equivalent
configured settings, fresh sessions per mode/trial, alternating first-mode order,
and multiple repetitions. Generate JSON plus an English Markdown report. Require
an explicit `--live` flag; the default command only emits a plan. Cross-model
fallback is disabled; latency/throughput comparisons exclude unknown actual models
and any fallback success. Every paid attempt with known cost remains in cost totals.

## Alternatives considered

- Unstructured debug prints: cheap, but poor privacy control and aggregation.
- Latency-only ranking: misses quality, provider identity, failures, and cost.
- A hosted tracing platform: useful later, but adds dependencies and another data
  processor before local observability requirements have been validated.
- Estimated token/cost counters: misleading when presented as API measurements.

## Rationale

Stable records and a reusable measurement lifecycle support evidence-based model
selection while keeping missing information visible. They allow later tool/turn
events to correlate with existing session/request IDs without making database
calls in Phase 2. A future tool span must measure its own execution and policy/
authorization outcome, keeping private arguments/results out of telemetry.

## Consequences and trade-offs

P95 uses linear interpolation and is unstable with small samples. Provider load,
caching, nondeterminism, and model-dependent previous assistant messages prevent
strict reproducibility. Config/prompt/scenario fingerprints and runtime/code
metadata improve traceability rather than guaranteeing identical answers.
Provider throughput can include reasoning; it is not exact visible-text speed.
Unknown failed-request cost means observed totals can undercount billed cost.
Behavioral quality is not inferred from timing or automatically scored; opt-in
terminal display supports manual review against English expected outcomes.

## Validation strategy

Synthetic clocks, scripted streams, JSONL privacy/permission checks, SDK transport
fixtures, and aggregation/report fixtures run offline. No synthetic fixture is
reported as live evidence. See the [schema](../observability.md) and
[benchmark instructions](../phase2.md).
