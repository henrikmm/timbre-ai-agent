"""Transactional tool-calling turns, independent of terminal presentation."""

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import time
from typing import Callable
from uuid import uuid4

from timbre.config import AppConfig, ConfigurationError, load_system_prompt
from timbre.llm.types import LLMClient, LLMError, ReasoningAccumulator, ToolCallAccumulator
from timbre.observability import Observer, RequestMeasurement, RequestMetrics, TraceEvent
from timbre.tools import ToolExecutor


@dataclass(frozen=True)
class TurnResult:
    text: str
    metrics: RequestMetrics
    turn_id: str
    events: tuple[TraceEvent, ...] = ()


class Conversation:
    def __init__(self, client: LLMClient, config: AppConfig, *, observer: Observer | None = None,
                 system_prompt: str | None = None, clock=time.perf_counter, source="live",
                 executor: ToolExecutor | None = None, trusted_session_context: object | None = None):
        self.client = client
        self.config = config
        self.observer = observer if observer is not None else Observer(config.observability)
        self.executor = executor if executor is not None else ToolExecutor(
            config.tools.database_path, config.tools.policies_path, clock=clock)
        self._trusted_context = trusted_session_context
        self.session_id = str(uuid4())
        self.last_turn_id = None
        self.mode = config.default_mode
        self.clock = clock
        self.source = source
        self._system = system_prompt if system_prompt is not None else load_system_prompt()
        if not self._system.strip():
            raise ValueError("System instructions must not be empty.")
        self._turns: list[list[dict]] = []
        self._history = [{"role": "system", "content": self._system}]
        self._busy = False

    @property
    def history(self) -> list[dict]:
        return deepcopy(self._history)

    def set_mode(self, mode: str) -> None:
        if self._busy:
            raise RuntimeError("Cannot change mode during a request.")
        if mode not in self.config.modes:
            raise ValueError("Mode must be standard or fast.")
        self.mode = mode

    def clear(self) -> None:
        if self._busy:
            raise RuntimeError("Cannot reset during a request.")
        self._turns = []
        self._history = [{"role": "system", "content": self._system}]

    def get_trace(self, turn_id: str | None = None) -> list[TraceEvent]:
        return self.observer.get_events(turn_id or self.last_turn_id)

    def _metadata(self, attempt: RequestMeasurement) -> None:
        metrics = attempt.metrics
        observation = self.config.observability
        if (observation.generation_metadata == "off" or not metrics.response_id
                or metrics.status == "interrupted"
                or (observation.generation_metadata != "always"
                    and not (observation.record_provider and metrics.provider is None)
                    and not (observation.record_cost and metrics.cost_usd is None))):
            return
        started = self.clock()
        try:
            attempt.merge(self.client.generation_metadata(metrics.response_id, observation.metadata_timeout_seconds))
            metrics.metadata_lookup_status = "success"
        except KeyboardInterrupt:
            metrics.metadata_lookup_status = "interrupted"
        except Exception:
            metrics.metadata_lookup_status = "unavailable"
        metrics.metadata_lookup_seconds = self.clock() - started

    def send(self, text: str, *, on_text: Callable[[str], None] | None = None,
             cross_model_fallback: bool | None = None) -> TurnResult:
        if self._busy:
            raise RuntimeError("A conversation can have only one active request.")
        self._busy = True
        try:
            return self._send(text, on_text=on_text, cross_model_fallback=cross_model_fallback)
        finally:
            self._busy = False

    def _send(self, text: str, *, on_text=None, cross_model_fallback=None) -> TurnResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Enter a non-empty customer message.")
        mode = self.mode
        selected = self.config.modes[mode]
        fallback = self.config.cross_model_fallback if cross_model_fallback is None else cross_model_fallback
        keep = self.config.history_turn_limit - 1
        previous = self._turns[-keep:] if keep else []
        group = [{"role": "user", "content": text.strip()}]
        pending = [{"role": "system", "content": self._system},
                   *deepcopy([message for turn in previous for message in turn]), *group]
        measurement = RequestMeasurement(self.session_id, mode, selected.model, clock=self.clock,
            streaming=self.config.streaming, source=self.source, provider_sort=selected.provider_sort,
            reasoning_effort=selected.reasoning_effort, cross_model_fallback=fallback)
        metrics = measurement.metrics
        metrics.schema_version = 2
        metrics.event_type = "conversation_turn"
        metrics.turn_id = str(uuid4())
        metrics.trace_id = str(uuid4())
        self.last_turn_id = metrics.turn_id
        metrics.model_call_count = 0
        metrics.tool_execution_seconds = 0.0
        metrics.tool_durations_seconds = {}
        attempts = []
        chunks = []
        seen_ids = set()

        def emit(event_type, *, span_id=None, llm_request_id=None, tool_call_id=None,
                 tool_name=None, **metadata):
            self.observer.trace(TraceEvent(event_type=event_type,
                timestamp=datetime.now(timezone.utc).isoformat(), session_id=self.session_id,
                turn_id=metrics.turn_id, trace_id=metrics.trace_id,
                span_id=span_id or metrics.trace_id, llm_request_id=llm_request_id,
                tool_call_id=tool_call_id, tool_name=tool_name, **metadata))

        emit("request_started", status="pending")
        try:
            for iteration in range(self.config.tools.max_iterations + 1):
                remaining = self.config.timeout_seconds - (self.clock() - measurement.started)
                if remaining <= 0:
                    raise LLMError("timeout")
                attempt = RequestMeasurement(self.session_id, mode, selected.model, clock=self.clock,
                    streaming=self.config.streaming, source=self.source, provider_sort=selected.provider_sort,
                    reasoning_effort=selected.reasoning_effort, cross_model_fallback=fallback)
                attempts.append(attempt)
                metrics.model_call_count += 1
                request_id = attempt.metrics.request_id
                emit("llm_request_started", span_id=request_id, llm_request_id=request_id, status="pending")
                calls = ToolCallAccumulator()
                reasoning = ReasoningAccumulator()
                call_chunks = []
                saw_calls = False
                iterator = None
                try:
                    iterator = self.client.generate(pending, replace(self.config, timeout_seconds=remaining), mode,
                        cross_model_fallback=fallback, tools=self.executor.definitions)
                    for event in iterator:
                        if (event.text or event.tool_calls) and attempt.metrics.finish_reason is not None:
                            raise LLMError("protocol")
                        attempt.event(event)
                        measurement.event(event)
                        if self.clock() - measurement.started > self.config.timeout_seconds:
                            raise LLMError("timeout")
                        calls.add(event.tool_calls)
                        reasoning.add(event.reasoning_details)
                        saw_calls = saw_calls or bool(event.tool_calls)
                        if event.text:
                            chunks.append(event.text)
                            call_chunks.append(event.text)
                            if on_text is not None:
                                on_text(event.text)
                    finish = attempt.metrics.finish_reason
                    if finish not in ("stop", "tool_calls"):
                        raise LLMError("incomplete_response")
                    if finish == "stop" and (saw_calls or not "".join(call_chunks).strip()):
                        raise LLMError("protocol" if saw_calls else "empty_response")
                    complete = calls.complete() if finish == "tool_calls" else ()
                    if finish == "tool_calls" and not complete:
                        raise LLMError("protocol")
                    attempt.finish("success")
                except BaseException as error:
                    category = (error.category if isinstance(error, LLMError) else
                                "interrupted" if isinstance(error, KeyboardInterrupt) else
                                "configuration" if isinstance(error, ConfigurationError) else "internal")
                    attempt.finish("interrupted" if category == "interrupted" else "failed", category=category)
                    raise
                finally:
                    try:
                        if iterator is not None and hasattr(iterator, "close"):
                            iterator.close()
                    except Exception:
                        attempt.finish("failed", category="stream_cleanup")
                        raise LLMError("stream_cleanup") from None
                    finally:
                        if attempt.metrics.total_latency_seconds is None:
                            attempt.finish("failed", category="internal")
                        emit("llm_request_completed", span_id=request_id, llm_request_id=request_id,
                             duration_seconds=attempt.metrics.total_latency_seconds, status=attempt.metrics.status,
                             error_category=attempt.metrics.error_category)
                assistant = {"role": "assistant", "content": "".join(call_chunks) or None}
                details = reasoning.complete()
                if details:
                    assistant["reasoning_details"] = list(details)
                if finish == "stop":
                    pending.append(assistant)
                    group.append(assistant)
                    emit("final_answer_generated", llm_request_id=request_id, status="success")
                    break
                if (iteration >= self.config.tools.max_iterations
                        or metrics.tool_call_count + len(complete) > self.config.tools.max_calls_per_turn):
                    raise LLMError("tool_limit")
                if any(call.id in seen_ids for call in complete):
                    raise LLMError("protocol")
                seen_ids.update(call.id for call in complete)
                assistant["tool_calls"] = [{"id": call.id, "type": "function", "function": {
                    "name": call.name, "arguments": call.arguments}} for call in complete]
                pending.append(assistant)
                group.append(assistant)
                known_names = {tool["function"]["name"] for tool in self.executor.definitions}
                for call in complete:
                    if self.clock() - measurement.started > self.config.timeout_seconds:
                        raise LLMError("timeout")
                    # Never persist untrusted model identifiers or arbitrary tool names.
                    trace_call_id = str(uuid4())
                    span_id = str(uuid4())
                    safe_name = call.name if call.name in known_names else "unknown_tool"

                    def tool_event(event_type, **metadata):
                        emit(event_type, span_id=span_id, llm_request_id=request_id,
                             tool_call_id=trace_call_id, tool_name=safe_name, **metadata)

                    tool_event("tool_call_requested", status="pending")
                    execution = self.executor.execute(call.name, call.arguments,
                        context=self._trusted_context, on_event=tool_event)
                    metrics.tool_call_count += 1
                    metrics.tool_execution_seconds += execution.duration_seconds
                    metrics.tool_durations_seconds[safe_name] = (
                        metrics.tool_durations_seconds.get(safe_name, 0) + execution.duration_seconds)
                    status = execution.result["status"]
                    metrics.tool_failure_count += status not in ("success", "empty")
                    metrics.validation_failure_count += status == "invalid_arguments"
                    metrics.authorization_denial_count += status == "authorization_denied"
                    result = {"role": "tool", "tool_call_id": call.id,
                              "content": json.dumps(execution.result, ensure_ascii=False, allow_nan=False)}
                    pending.append(result)
                    group.append(result)
                    tool_event("tool_result_returned", status=status,
                        sanitized_arguments=execution.sanitized_arguments,
                        result_count=execution.result_count)
            measurement.finish("success")
        except KeyboardInterrupt:
            measurement.finish("interrupted", category="interrupted")
        except (LLMError, ConfigurationError) as error:
            category = error.category if isinstance(error, LLMError) else "configuration"
            status = "incomplete" if measurement.saw_text or category == "incomplete_response" else "failed"
            measurement.finish(status, category=category, http_status=getattr(error, "http_status", None))
        except Exception:
            measurement.finish("incomplete" if measurement.saw_text else "failed", category="internal")
        # Retrieve per-generation metadata once, after visible output, without retries.
        for attempt in attempts:
            if metrics.status != "interrupted":
                self._metadata(attempt)
            attempt.finalize()
        measurement.finalize()
        records = [attempt.metrics for attempt in attempts]
        self._aggregate(metrics, records)
        if metrics.status == "success" and not fallback and metrics.fallback_used:
            metrics.status = "incomplete"
            metrics.error_category = "unexpected_model"
            metrics.incomplete_stream = self.config.streaming
            metrics.partial_output = measurement.saw_text
            metrics.output_tokens_per_second = None
        metrics.overall_latency_seconds = self.clock() - measurement.started
        if metrics.status == "success":
            self._turns = [*previous, deepcopy(group)]
            self._history = [{"role": "system", "content": self._system},
                             *[message for turn in self._turns for message in turn]]
        emit("request_completed" if metrics.status == "success" else "request_failed",
             duration_seconds=metrics.overall_latency_seconds, status=metrics.status,
             error_category=metrics.error_category)
        self.observer.record(metrics)
        return TurnResult("".join(chunks), metrics, metrics.turn_id, tuple(self.get_trace(metrics.turn_id)))

    @staticmethod
    def _aggregate(metrics: RequestMetrics, records: list[RequestMetrics]) -> None:
        """Sum once per model response; retain explicit coverage for missing values."""
        metrics.model_execution_seconds = sum(record.total_latency_seconds or 0 for record in records)
        metrics.actual_models = sorted({record.actual_model for record in records if record.actual_model})
        metrics.providers = sorted({record.provider for record in records if record.provider})
        metrics.actual_model = records[-1].actual_model if records else None
        metrics.provider = records[-1].provider if records else None
        for field in ("fallback_used", "provider_fallback_used"):
            values = [getattr(record, field) for record in records]
            setattr(metrics, field, True if True in values else (False if values and all(v is False for v in values) else None))
        metrics.token_coverage = {}
        for field in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cached_tokens",
                      "native_input_tokens", "native_output_tokens", "native_reasoning_tokens", "native_cached_tokens",
                      "provider_latency_seconds", "provider_generation_seconds"):
            values = [getattr(record, field) for record in records]
            known = [value for value in values if value is not None]
            setattr(metrics, field, sum(known) if known and len(known) == len(records) else None)
            if "tokens" in field:
                metrics.token_coverage[field] = len(known)
        costs = [record.cost_usd for record in records if record.cost_usd is not None]
        metrics.cost_known_model_calls = len(costs)
        metrics.observed_cost_usd = sum(costs) if costs else None
        metrics.cost_usd = sum(costs) if costs and len(costs) == len(records) else None
        lookups = [record for record in records if record.metadata_lookup_seconds is not None]
        metrics.metadata_lookup_seconds = sum(record.metadata_lookup_seconds for record in lookups) if lookups else None
        metrics.metadata_lookup_status = ("unavailable" if any(record.metadata_lookup_status == "unavailable" for record in lookups)
            else "interrupted" if any(record.metadata_lookup_status == "interrupted" for record in lookups)
            else "success" if lookups else "not_needed")
        metrics.output_tokens_per_second = None
        if (metrics.status == "success" and metrics.native_output_tokens is not None
                and metrics.provider_generation_seconds is not None and metrics.provider_generation_seconds > 0):
            metrics.output_tokens_per_second = metrics.native_output_tokens / metrics.provider_generation_seconds
