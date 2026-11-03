"""Small boundary types; no provider response objects escape the adapter."""

from dataclasses import dataclass
from copy import deepcopy
import re
from typing import Any, Iterator, Mapping, Protocol, Sequence

from timbre.config import AppConfig

# Plain message mappings leave room for future roles/content without an SDK dependency.
Message = Mapping[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class ToolCall:
    """A provider-neutral function call, or an indexed streaming fragment."""

    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""


class ToolCallAccumulator:
    """Bound and reconstruct deltas without parsing or executing arguments."""

    def __init__(self):
        self._calls: dict[int, ToolCall] = {}
        self._bytes = 0

    def __bool__(self):
        return bool(self._calls)

    def add(self, calls: Sequence[ToolCall]) -> None:
        for call in calls:
            if (not isinstance(call, ToolCall) or type(call.index) is not int
                    or not 0 <= call.index < 16 or not isinstance(call.arguments, str)
                    or (call.id is not None and not isinstance(call.id, str))
                    or (call.name is not None and not isinstance(call.name, str))):
                raise LLMError("tool_call_protocol")
            previous = self._calls.get(call.index, ToolCall(call.index))
            self._bytes += len(call.arguments.encode("utf-8"))
            identifier = (previous.id or "") + (call.id or "")
            name = (previous.name or "") + (call.name or "")
            if self._bytes > 65536 or len(identifier) > 256 or len(name) > 128:
                raise LLMError("tool_call_limit")
            self._calls[call.index] = ToolCall(call.index, identifier or None, name or None,
                                              previous.arguments + call.arguments)

    def complete(self) -> tuple[ToolCall, ...]:
        if not self._calls or set(self._calls) != set(range(len(self._calls))):
            raise LLMError("tool_call_protocol")
        calls = tuple(self._calls[index] for index in sorted(self._calls))
        if (len({call.id for call in calls}) != len(calls)
                or any(not call.id or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", call.id)
                       or not call.name or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call.name)
                       for call in calls)):
            raise LLMError("tool_call_protocol")
        return calls


class ReasoningAccumulator:
    """Reassemble native reasoning details solely for private protocol replay."""

    def __init__(self):
        self._details: dict[int, dict] = {}
        self._size = 0

    def add(self, details: Sequence[Mapping[str, Any]]) -> None:
        for position, detail in enumerate(details):
            index = detail.get("index", position)
            if type(index) is not int or not 0 <= index < 1024:
                raise LLMError("protocol")
            current = self._details.setdefault(index, {})
            for key, value in detail.items():
                if key in ("text", "summary", "data", "signature") and isinstance(value, str):
                    self._size += len(value.encode("utf-8"))
                    if self._size > 262144:
                        raise LLMError("protocol")
                    current[key] = current.get(key, "") + value
                elif key in ("type", "id", "format", "index"):
                    if key in current and current[key] != value:
                        raise LLMError("protocol")
                    current[key] = value

    def complete(self) -> tuple[dict, ...]:
        return tuple(deepcopy(self._details[index]) for index in sorted(self._details))


@dataclass(frozen=True)
class LLMEvent:
    text: str = ""
    response_id: str | None = None
    actual_model: str | None = None
    provider: str | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    native_usage: Usage | None = None
    provider_latency_seconds: float | None = None
    provider_generation_seconds: float | None = None
    upstream_attempts: int | None = None
    provider_fallback_used: bool | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    reasoning_details: tuple[dict, ...] = ()


class LLMError(Exception):
    """Only a stable category and optional HTTP status, never an upstream body."""

    def __init__(self, category: str, http_status: int | None = None):
        self.category = category
        self.http_status = http_status
        super().__init__(f"LLM request failed ({category}).")


class LLMClient(Protocol):
    def generate(self, messages: Sequence[Message], config: AppConfig, mode: str,
                 *, cross_model_fallback: bool,
                 tools: Sequence[Mapping[str, Any]] | None = None) -> Iterator[LLMEvent]: ...

    def generation_metadata(self, response_id: str, timeout_seconds: float) -> LLMEvent: ...
