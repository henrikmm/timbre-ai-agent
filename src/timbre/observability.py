"""Content-free request records, monotonic measurements, and session aggregation."""

from dataclasses import asdict, dataclass, replace
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import statistics
import time
from uuid import uuid4

from timbre.config import ObservabilityConfig
from timbre.llm.types import LLMEvent


@dataclass
class RequestMetrics:
    request_id: str
    session_id: str
    timestamp: str
    mode: str
    requested_model: str
    source: str = "live"
    schema_version: int = 1
    event_type: str = "llm_request"
    response_id: str | None = None
    actual_model: str | None = None
    provider: str | None = None
    provider_sort: str = "default"
    reasoning_effort: str = "default"
    streaming: bool = True
    cross_model_fallback_enabled: bool = False
    fallback_used: bool | None = None
    provider_fallback_used: bool | None = None
    upstream_attempts: int | None = None
    retry_attempts: int = 0
    time_to_first_event_seconds: float | None = None
    ttft_seconds: float | None = None
    total_latency_seconds: float | None = None
    streaming_generation_seconds: float | None = None
    provider_latency_seconds: float | None = None
    provider_generation_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    native_input_tokens: int | None = None
    native_output_tokens: int | None = None
    native_reasoning_tokens: int | None = None
    native_cached_tokens: int | None = None
    output_tokens_per_second: float | None = None
    cost_usd: float | None = None
    session_cost_usd: float | None = None
    session_cost_known_requests: int = 0
    status: str = "pending"
    error_category: str | None = None
    http_status: int | None = None
    timeout_occurred: bool = False
    incomplete_stream: bool = False
    partial_output: bool = False
    finish_reason: str | None = None
    metadata_lookup_status: str = "not_needed"
    metadata_lookup_seconds: float | None = None
    turn_id: str | None = None
    trace_id: str | None = None
    model_call_count: int = 1
    tool_call_count: int = 0
    model_execution_seconds: float | None = None
    tool_execution_seconds: float | None = None
    tool_durations_seconds: dict | None = None
    tool_failure_count: int = 0
    validation_failure_count: int = 0
    authorization_denial_count: int = 0
    overall_latency_seconds: float | None = None
    cost_known_model_calls: int = 0
    observed_cost_usd: float | None = None
    token_coverage: dict | None = None
    actual_models: list | None = None
    providers: list | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TraceEvent:
    """Content-free execution event shared by terminal and future web consumers."""

    event_type: str
    timestamp: str
    session_id: str
    turn_id: str
    trace_id: str
    span_id: str
    llm_request_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    sanitized_arguments: dict | None = None
    source: str | None = None
    duration_seconds: float | None = None
    result_count: int | None = None
    status: str | None = None
    error_category: str | None = None
    finish_reason: str | None = None
    http_status: int | None = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def _tag(value: str | None) -> str | None:
    """Reject controls, emails, and free-form bodies in provider identity fields."""
    if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_.:/ -]{1,160}", value):
        return value
    return None


class RequestMeasurement:
    def __init__(self, session_id: str, mode: str, model: str, *, clock=time.perf_counter,
                 streaming=True, source="live", provider_sort="default", reasoning_effort="default",
                 cross_model_fallback=False):
        self.clock = clock
        self.started = clock()
        self.first_text = None
        self.last_text = None
        self.saw_text = False
        self.metrics = RequestMetrics(
            request_id=str(uuid4()), session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(), mode=mode, requested_model=model,
            streaming=streaming, source=source, provider_sort=provider_sort,
            reasoning_effort=reasoning_effort, cross_model_fallback_enabled=cross_model_fallback)

    def event(self, event: LLMEvent) -> None:
        now = self.clock()
        if self.metrics.time_to_first_event_seconds is None:
            self.metrics.time_to_first_event_seconds = now - self.started
        if event.text:
            self.saw_text = True
            if self.first_text is None and event.text.strip():
                self.first_text = now
                self.metrics.ttft_seconds = now - self.started
            if self.first_text is not None:
                self.last_text = now
        self.merge(event)

    def merge(self, event: LLMEvent) -> None:
        for field in ("response_id", "actual_model", "provider"):
            value = _tag(getattr(event, field))
            if value is not None:
                setattr(self.metrics, field, value)
        for field in ("finish_reason", "provider_latency_seconds", "provider_generation_seconds",
                      "upstream_attempts", "provider_fallback_used"):
            value = getattr(event, field)
            if value is not None:
                setattr(self.metrics, field, value)
        if event.usage is not None:
            for field, value in asdict(event.usage).items():
                if value is not None:
                    setattr(self.metrics, field, value)
        if event.native_usage is not None:
            for field in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens"):
                value = getattr(event.native_usage, field)
                if value is not None:
                    setattr(self.metrics, "native_" + field, value)

    def finish(self, status: str, *, category=None, http_status=None) -> RequestMetrics:
        metrics = self.metrics
        metrics.total_latency_seconds = self.clock() - self.started
        if metrics.streaming and self.first_text is not None and self.last_text is not None:
            metrics.streaming_generation_seconds = self.last_text - self.first_text
        metrics.status = status
        metrics.error_category = category
        metrics.http_status = http_status
        metrics.timeout_occurred = category == "timeout"
        metrics.incomplete_stream = metrics.streaming and status != "success"
        metrics.partial_output = self.saw_text and status != "success"
        return metrics

    def finalize(self) -> None:
        metrics = self.metrics
        if metrics.actual_model is not None:
            metrics.fallback_used = metrics.actual_model != metrics.requested_model
        # Provider-native token counts and provider generation time share a basis.
        # Chunk boundaries do not disclose token counts; do not derive local TPS.
        if (metrics.status == "success" and metrics.native_output_tokens is not None
                and metrics.provider_generation_seconds is not None
                and metrics.provider_generation_seconds > 0):
            metrics.output_tokens_per_second = metrics.native_output_tokens / metrics.provider_generation_seconds


def percentile(values: list[float], fraction: float) -> float | None:
    """Linear interpolation, including the singleton case; no synthetic samples."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(records: list[RequestMetrics]) -> dict:
    successful = [record for record in records if record.status == "success"]
    costs = [record.cost_usd for record in records if record.cost_usd is not None]
    observed_costs = [record.observed_cost_usd if record.observed_cost_usd is not None else record.cost_usd
                      for record in records if record.observed_cost_usd is not None or record.cost_usd is not None]
    ttft = [record.ttft_seconds for record in successful if record.ttft_seconds is not None]
    latency = [record.total_latency_seconds for record in successful if record.total_latency_seconds is not None]
    throughput = [record.output_tokens_per_second for record in successful if record.output_tokens_per_second is not None]
    result = {"requests": len(records), "successful_requests": len(successful),
              "error_rate": (len(records) - len(successful)) / len(records) if records else None,
              "median_ttft_seconds": statistics.median(ttft) if ttft else None,
              "p95_ttft_seconds": percentile(ttft, .95), "ttft_samples": len(ttft),
              "median_total_latency_seconds": statistics.median(latency) if latency else None,
              "p95_total_latency_seconds": percentile(latency, .95), "latency_samples": len(latency),
              "mean_output_tokens_per_second": statistics.mean(throughput) if throughput else None,
              "throughput_samples": len(throughput),
              "total_cost_usd": sum(costs) if costs else None,
              "mean_cost_usd": statistics.mean(costs) if costs else None,
              "cost_known_requests": len(costs),
              "providers": sorted({value for record in records
                                   for value in (record.providers or ([record.provider] if record.provider else []))}),
              "actual_models": sorted({value for record in records
                                       for value in (record.actual_models or ([record.actual_model] if record.actual_model else []))}),
              "fallback_occurrences": sum(record.fallback_used is True for record in records),
              "fallback_unknown_requests": sum(record.fallback_used is None for record in records),
              "provider_fallback_occurrences": sum(record.provider_fallback_used is True for record in records),
              "timeouts": sum(record.timeout_occurred for record in records),
              "incomplete_streams": sum(record.incomplete_stream for record in records)}
    result.update(model_calls=sum(record.model_call_count for record in records),
                  tool_calls=sum(record.tool_call_count for record in records),
                  tool_failures=sum(record.tool_failure_count for record in records),
                  validation_failures=sum(record.validation_failure_count for record in records),
                  authorization_denials=sum(record.authorization_denial_count for record in records),
                  observed_cost_usd=sum(observed_costs) if observed_costs else None,
                  cost_known_model_calls=sum(record.cost_known_model_calls for record in records))
    for field in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cached_tokens"):
        known = [getattr(record, field) for record in records if getattr(record, field) is not None]
        result[field] = sum(known) if known else None
        result[field + "_known_requests"] = len(known)
    return result


class Observer:
    """Session metrics always exist; enabled controls JSONL persistence only."""

    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self.records: list[RequestMetrics] = []
        self._events = deque(maxlen=2000)
        self.persistence_failed = False

    def trace(self, event: TraceEvent) -> TraceEvent:
        # Events contain backend-owned tags and executor-sanitized metadata only.
        safe = deepcopy(event)
        if not self.config.record_latency:
            safe = replace(safe, duration_seconds=None)
        self._events.append(safe)
        if self.config.enabled:
            path = Path(self.config.jsonl_path)
            self._persist(path.with_name(path.stem + ".traces.jsonl"), safe.to_dict())
        return deepcopy(safe)

    def get_events(self, turn_id: str | None = None) -> list[TraceEvent]:
        """Return isolated snapshots, bounded to the latest 2,000 session events."""
        return deepcopy([event for event in self._events if turn_id is None or event.turn_id == turn_id])

    def _persist(self, path: Path, record: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
        except OSError:
            self.persistence_failed = True

    def record(self, metrics: RequestMetrics) -> None:
        config = self.config
        if not config.record_tokens:
            for field in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cached_tokens",
                          "native_input_tokens", "native_output_tokens", "native_reasoning_tokens", "native_cached_tokens",
                          "output_tokens_per_second"):
                setattr(metrics, field, None)
            metrics.token_coverage = None
        if not config.record_cost:
            metrics.cost_usd = None
            metrics.observed_cost_usd = None
            metrics.cost_known_model_calls = 0
        if not config.record_latency:
            for field in ("time_to_first_event_seconds", "ttft_seconds", "total_latency_seconds",
                          "streaming_generation_seconds", "provider_latency_seconds", "provider_generation_seconds",
                          "metadata_lookup_seconds", "output_tokens_per_second"):
                setattr(metrics, field, None)
            metrics.model_execution_seconds = None
            metrics.tool_execution_seconds = None
            metrics.tool_durations_seconds = None
            metrics.overall_latency_seconds = None
        if not config.record_provider:
            metrics.provider = None
            metrics.providers = None
        known = [record.cost_usd for record in self.records if record.cost_usd is not None]
        if metrics.cost_usd is not None:
            known.append(metrics.cost_usd)
        partial = [record.observed_cost_usd if record.observed_cost_usd is not None else record.cost_usd
                   for record in [*self.records, metrics]
                   if record.observed_cost_usd is not None or record.cost_usd is not None]
        metrics.session_cost_usd = sum(partial) if partial else None
        metrics.session_cost_known_requests = len(known)
        self.records.append(metrics)
        if config.enabled:
            self._persist(Path(config.jsonl_path), metrics.to_dict())

    def summary(self) -> dict:
        return summarize(self.records)
