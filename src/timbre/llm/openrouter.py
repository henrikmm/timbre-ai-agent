"""Official SDK adapter, with no application retries or operational data access."""

from collections.abc import Mapping, Sequence
import math
from typing import Iterator

from timbre.config import AppConfig, ConfigurationError, load_api_key
from timbre.llm.types import LLMError, LLMEvent, Message, ToolCall, Usage


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _amount(value) -> float | None:
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _text(value) -> str | None:
    return value if isinstance(value, str) and value else None


def _usage(value) -> Usage | None:
    if value is None:
        return None
    return Usage(
        input_tokens=_count(_get(value, "prompt_tokens")),
        output_tokens=_count(_get(value, "completion_tokens")),
        total_tokens=_count(_get(value, "total_tokens")),
        reasoning_tokens=_count(_get(_get(value, "completion_tokens_details"), "reasoning_tokens")),
        cached_tokens=_count(_get(_get(value, "prompt_tokens_details"), "cached_tokens")),
        cost_usd=_amount(_get(value, "cost")),
    )


def _category(status: int | None) -> str:
    if status in (408, 504, 524):
        return "timeout"
    if status in (401, 403):
        return "authentication_or_permission"
    if status == 402:
        return "billing"
    if status == 429:
        return "rate_limit"
    if status is not None and status >= 500:
        return "provider_unavailable"
    if status in (400, 404, 422):
        return "invalid_request_or_unsupported_parameter"
    return "provider_error"


def request_parameters(messages: Sequence[Message], config: AppConfig, mode: str,
                       *, cross_model_fallback: bool, tools: Sequence[dict] | None = None) -> dict:
    """Build documented SDK parameters; never silently drop an optional setting."""
    selected = config.modes[mode]
    candidates = [selected]
    if cross_model_fallback:
        candidates.extend(value for name, value in config.modes.items()
                          if name != mode and value.model != selected.model)
    provider = {
        "allow_fallbacks": config.routing.allow_provider_fallbacks,
        "require_parameters": config.routing.require_parameters,
        "data_collection": config.routing.data_collection,
        "zdr": config.routing.zdr,
    }
    if selected.provider_sort != "default":
        provider["sort"] = selected.provider_sort
    parameters = {"messages": [dict(message) for message in messages],
                  "stream": config.streaming, "max_tokens": config.max_output_tokens,
                  "provider": provider, "timeout_ms": round(config.timeout_seconds * 1000),
                  "x_open_router_metadata": "enabled"}
    if tools is not None:
        parameters["tools"] = list(tools)
        parameters["tool_choice"] = "auto"
    if len(candidates) > 1:
        parameters["models"] = [candidate.model for candidate in candidates]
    else:
        parameters["model"] = selected.model
    if selected.reasoning_effort != "default":
        if any(selected.reasoning_effort not in candidate.supported_reasoning_efforts for candidate in candidates):
            raise ConfigurationError("Reasoning effort is not verified for every fallback model; disable cross-model fallback or use default effort.")
        parameters["reasoning"] = {"effort": selected.reasoning_effort}
    return parameters


def _tool_calls(payload, *, streaming: bool) -> tuple[ToolCall, ...]:
    calls = _get(payload, "tool_calls")
    if calls is None:
        return ()
    if not isinstance(calls, (list, tuple)) or len(calls) > 16:
        raise LLMError("tool_call_protocol")
    result = []
    for position, call in enumerate(calls):
        kind = _get(call, "type")
        if kind not in (None, "function"):
            raise LLMError("tool_call_protocol")
        function = _get(call, "function")
        arguments = _get(function, "arguments")
        if arguments is None and streaming:
            arguments = ""
        if not isinstance(arguments, str):
            raise LLMError("tool_call_protocol")
        result.append(ToolCall(_get(call, "index") if streaming else position,
                              _get(call, "id"), _get(function, "name"), arguments))
    return tuple(result)


def _reasoning_details(payload) -> tuple[dict, ...]:
    """Keep native replay context in memory; never expose it as answer text."""
    details = _get(payload, "reasoning_details")
    if not isinstance(details, (list, tuple)):
        return ()
    result = []
    for item in details:
        if hasattr(item, "model_dump"):
            item = item.model_dump(by_alias=True, exclude_unset=True)
        if not isinstance(item, Mapping):
            continue
        if item.get("type") not in ("reasoning.text", "reasoning.encrypted", "reasoning.summary"):
            continue
        result.append({key: value for key, value in item.items()
                       if key in ("type", "id", "format", "index", "text", "summary", "data", "signature")
                       and value is not None})
    return tuple(result)


def _event(response, *, streaming: bool) -> LLMEvent:
    routing = _get(response, "openrouter_metadata")
    endpoints = _get(_get(routing, "endpoints"), "available", []) or []
    selected = next((endpoint for endpoint in endpoints if _get(endpoint, "selected") is True), None)
    provider = _text(_get(selected, "provider"))
    attempts = _count(_get(routing, "attempt"))
    route_attempts = _get(routing, "attempts", []) or []
    # More than one attempted provider for the same model proves provider fallback.
    provider_fallback = None
    if attempts is not None:
        provider_fallback = False if attempts <= 1 else None
    if route_attempts:
        provider_fallback = any(
            _get(earlier, "model") == _get(later, "model")
            and _get(earlier, "provider") != _get(later, "provider")
            for index, earlier in enumerate(route_attempts) for later in route_attempts[index + 1:]
        )
    choices = _get(response, "choices", []) or []
    choice = next((choice for choice in choices if _get(choice, "index") == 0), None)
    payload = _get(choice, "delta" if streaming else "message")
    # Unstructured reasoning/debug bodies are never customer-visible.
    text = _get(payload, "content")
    finish = _text(_get(choice, "finish_reason"))
    if finish is not None and finish not in ("stop", "length", "content_filter", "tool_calls", "error"):
        finish = "unknown"
    error = _get(response, "error")
    if error is not None:
        code = _count(_get(error, "code"))
        raise LLMError(_category(code), code if code and 100 <= code <= 599 else None)
    return LLMEvent(text=text if isinstance(text, str) else "",
                    response_id=_text(_get(response, "id")),
                    actual_model=_text(_get(response, "model")), provider=provider,
                    finish_reason=finish, usage=_usage(_get(response, "usage")),
                    upstream_attempts=attempts, provider_fallback_used=provider_fallback,
                    tool_calls=_tool_calls(payload, streaming=streaming),
                    reasoning_details=_reasoning_details(payload))


def _convert_error(error: Exception) -> LLMError:
    import httpx

    if isinstance(error, httpx.TimeoutException) or isinstance(error, TimeoutError):
        return LLMError("timeout")
    if isinstance(error, httpx.TransportError):
        return LLMError("network")
    status = _get(error, "status_code")
    if type(status) is not int:
        status = _get(_get(error, "raw_response"), "status_code")
    if type(status) is int:
        return LLMError(_category(status), status)
    # SDK/Pydantic decoding errors can contain entire responses; never expose them.
    return LLMError("protocol" if isinstance(error, ValueError) else "provider_error")


class OpenRouterClient:
    def __init__(self, api_key: str, config: AppConfig, *, sdk=None):
        if not isinstance(api_key, str) or not api_key.strip() or api_key == "replace-with-your-private-key":
            raise ConfigurationError("Set OPENROUTER_API_KEY privately before starting the CLI.")
        if sdk is None:
            from openrouter import OpenRouter
            from openrouter.utils.retries import BackoffStrategy, RetryConfig

            sdk = OpenRouter(
                api_key=api_key, timeout_ms=round(config.timeout_seconds * 1000),
                retry_config=RetryConfig(strategy="none", retry_connection_errors=False,
                    backoff=BackoffStrategy(initial_interval=0, max_interval=0,
                                            exponent=1, max_elapsed_time=0)),
            )
        self._sdk = sdk

    @classmethod
    def from_environment(cls, config: AppConfig, env_file=".env"):
        return cls(load_api_key(env_file), config)

    def generate(self, messages: Sequence[Message], config: AppConfig, mode: str,
                 *, cross_model_fallback: bool, tools: Sequence[dict] | None = None) -> Iterator[LLMEvent]:
        parameters = request_parameters(messages, config, mode,
                                        cross_model_fallback=cross_model_fallback, tools=tools)
        try:
            result = self._sdk.chat.send(**parameters)
            if config.streaming:
                with result as stream:
                    for chunk in stream:
                        yield _event(chunk, streaming=True)
            else:
                yield _event(result, streaming=False)
        except LLMError:
            raise
        except Exception as error:
            raise _convert_error(error) from None

    def generation_metadata(self, response_id: str, timeout_seconds: float) -> LLMEvent:
        try:
            response = self._sdk.generations.get_generation(
                id=response_id, timeout_ms=round(timeout_seconds * 1000))
            data = response.data
            latency = _amount(_get(data, "latency"))
            generation = _amount(_get(data, "generation_time"))
            return LLMEvent(
                actual_model=_text(_get(data, "model")), provider=_text(_get(data, "provider_name")),
                usage=Usage(cost_usd=_amount(_get(data, "total_cost"))),
                native_usage=Usage(input_tokens=_count(_get(data, "native_tokens_prompt")),
                                   output_tokens=_count(_get(data, "native_tokens_completion")),
                                   reasoning_tokens=_count(_get(data, "native_tokens_reasoning")),
                                   cached_tokens=_count(_get(data, "native_tokens_cached"))),
                provider_latency_seconds=None if latency is None else latency / 1000,
                provider_generation_seconds=None if generation is None else generation / 1000,
            )
        except Exception as error:
            raise _convert_error(error) from None

    def close(self):
        self._sdk.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
