"""Strict, non-secret TOML settings and explicit local credential loading."""

from dataclasses import dataclass
from importlib.resources import files
import math
import os
from pathlib import Path
import re
import tomllib
from types import MappingProxyType
from typing import Mapping


class ConfigurationError(ValueError):
    """Actionable configuration failure without echoing supplied values."""


@dataclass(frozen=True)
class ModeConfig:
    model: str
    provider_sort: str = "default"
    reasoning_effort: str = "default"
    supported_reasoning_efforts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutingConfig:
    allow_provider_fallbacks: bool = True
    require_parameters: bool = True
    data_collection: str = "deny"
    zdr: bool = False


@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = True
    jsonl_path: str = "local/requests.jsonl"
    record_tokens: bool = True
    record_cost: bool = True
    record_latency: bool = True
    record_provider: bool = True
    store_conversation_content: bool = False
    generation_metadata: str = "missing"
    metadata_timeout_seconds: float = 2


@dataclass(frozen=True)
class ToolConfig:
    database_path: str = "data/store.db"
    policies_path: str = "knowledge/policies.json"
    max_iterations: int = 4
    max_calls_per_turn: int = 12


@dataclass(frozen=True)
class AppConfig:
    modes: Mapping[str, ModeConfig]
    default_mode: str = "standard"
    streaming: bool = True
    timeout_seconds: float = 45
    max_output_tokens: int = 512
    history_turn_limit: int = 12
    cross_model_fallback: bool = True
    routing: RoutingConfig = RoutingConfig()
    observability: ObservabilityConfig = ObservabilityConfig()
    tools: ToolConfig = ToolConfig()


def _table(value: object, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise ConfigurationError(f"Invalid or unknown settings in {label}; see the default TOML.")
    return value


def _bool(value: object, name: str) -> None:
    if type(value) is not bool:
        raise ConfigurationError(f"{name} must be a boolean.")


def _number(value: object, name: str, low: float, high: float, *, integer=False) -> None:
    if (type(value) not in ((int,) if integer else (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ConfigurationError(f"{name} must be between {low} and {high}.")


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load one complete TOML file; credentials are never read here."""
    try:
        content = (Path(path).read_bytes() if path is not None else
                   files("timbre").joinpath("resources/default.toml").read_bytes())
        root = tomllib.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        raise ConfigurationError("Cannot read configuration; use a valid UTF-8 TOML file.") from None
    _table(root, {"llm", "routing", "observability", "tools"}, "root")
    llm = _table(root.get("llm"), {"modes", "default_mode", "streaming", "timeout_seconds",
                 "max_output_tokens", "history_turn_limit", "cross_model_fallback"}, "llm")
    raw_modes = _table(llm.get("modes"), {"standard", "fast"}, "llm.modes")
    if set(raw_modes) != {"standard", "fast"}:
        raise ConfigurationError("Configure both standard and fast modes.")
    modes = {}
    efforts = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
    for name, raw in raw_modes.items():
        _table(raw, {"model", "provider_sort", "reasoning_effort", "supported_reasoning_efforts"},
               f"llm.modes.{name}")
        model = raw.get("model")
        supported = raw.get("supported_reasoning_efforts", [])
        if not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9_.:/-]+/[a-zA-Z0-9_.:/-]+", model):
            raise ConfigurationError(f"llm.modes.{name}.model must be an explicit model ID.")
        if (not isinstance(supported, list) or any(not isinstance(e, str) or e not in efforts for e in supported)
                or len(set(supported)) != len(supported)):
            raise ConfigurationError("supported_reasoning_efforts must list verified, unique effort names.")
        mode = ModeConfig(**{**raw, "supported_reasoning_efforts": tuple(supported)})
        if mode.provider_sort not in ("default", "latency", "price", "throughput"):
            raise ConfigurationError("provider_sort must be default, latency, price, or throughput.")
        if mode.reasoning_effort != "default" and mode.reasoning_effort not in supported:
            raise ConfigurationError("Reasoning effort is not in the mode's verified supported efforts.")
        modes[name] = mode
    routing_raw = _table(root.get("routing", {}), set(RoutingConfig.__dataclass_fields__), "routing")
    observation_raw = _table(root.get("observability", {}), set(ObservabilityConfig.__dataclass_fields__),
                             "observability")
    routing = RoutingConfig(**routing_raw)
    observation = ObservabilityConfig(**observation_raw)
    tools = ToolConfig(**_table(root.get("tools", {}), set(ToolConfig.__dataclass_fields__), "tools"))
    config = AppConfig(**{key: value for key, value in llm.items() if key != "modes"},
                       modes=MappingProxyType(modes), routing=routing, observability=observation, tools=tools)
    if not isinstance(config.default_mode, str) or config.default_mode not in modes:
        raise ConfigurationError("default_mode must be standard or fast.")
    for key in ("streaming", "cross_model_fallback"):
        _bool(getattr(config, key), key)
    for key in ("allow_provider_fallbacks", "require_parameters", "zdr"):
        _bool(getattr(routing, key), key)
    if routing.data_collection not in ("allow", "deny"):
        raise ConfigurationError("data_collection must be allow or deny.")
    if not routing.require_parameters:
        raise ConfigurationError("require_parameters must remain true to reject unsupported settings explicitly.")
    for key in ("enabled", "record_tokens", "record_cost", "record_latency", "record_provider",
                "store_conversation_content"):
        _bool(getattr(observation, key), key)
    if observation.store_conversation_content:
        raise ConfigurationError("Conversation content logging is not supported; keep it false.")
    if observation.generation_metadata not in ("off", "missing", "always"):
        raise ConfigurationError("generation_metadata must be off, missing, or always.")
    if not isinstance(observation.jsonl_path, str) or not observation.jsonl_path.strip():
        raise ConfigurationError("jsonl_path must be a non-empty local path.")
    _number(config.timeout_seconds, "timeout_seconds", 1, 300)
    _number(config.max_output_tokens, "max_output_tokens", 1, 32768, integer=True)
    _number(config.history_turn_limit, "history_turn_limit", 1, 1000, integer=True)
    _number(observation.metadata_timeout_seconds, "metadata_timeout_seconds", 0.1, 10)
    _number(tools.max_iterations, "tools.max_iterations", 1, 10, integer=True)
    _number(tools.max_calls_per_turn, "tools.max_calls_per_turn", 1, 32, integer=True)
    for path in (tools.database_path, tools.policies_path):
        if not isinstance(path, str) or not path.strip():
            raise ConfigurationError("Tool data paths must be non-empty local paths.")
    return config


def load_api_key(env_file: str | Path = ".env", *, environ: Mapping[str, str] | None = None) -> str:
    """Read only the key from the explicit file; never mutate the process environment."""
    environment = os.environ if environ is None else environ
    key = environment.get("OPENROUTER_API_KEY")
    if key is None and Path(env_file).is_file():
        from dotenv import dotenv_values

        try:
            key = dotenv_values(env_file, interpolate=False).get("OPENROUTER_API_KEY")
        except (OSError, UnicodeError):
            raise ConfigurationError("Cannot read the private dotenv file; check its permissions and UTF-8 encoding.") from None
    if not isinstance(key, str) or not key.strip() or key.strip() == "replace-with-your-private-key":
        raise ConfigurationError(
            "Set OPENROUTER_API_KEY privately in .env (copy .env.example) or export it in your shell."
        )
    return key.strip()


def load_system_prompt() -> str:
    return files("timbre").joinpath("resources/system_prompt.md").read_text(encoding="utf-8").strip()
