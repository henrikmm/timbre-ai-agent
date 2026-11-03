"""Explicitly synthetic LLM fixtures and a socket guard; never live inference."""

from dataclasses import replace
import socket
import unittest
from unittest.mock import patch

from timbre.config import load_config
from timbre.llm.types import LLMError, LLMEvent, Usage


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect"):
            guard = patch(target, side_effect=AssertionError("Network access is forbidden in offline tests."))
            guard.start()
            self.addCleanup(guard.stop)


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def offline_config(**changes):
    config = load_config()
    config = replace(config, observability=replace(config.observability, enabled=False, generation_metadata="off"))
    return replace(config, **changes)


def synthetic_reply(text="Olá! Sou o Timbre.", model=None):
    return [LLMEvent(response_id="gen-synthetic-fixture", actual_model=model),
            LLMEvent(text=text, actual_model=model),
            LLMEvent(finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=6, total_tokens=16, cost_usd=.0001))]


class ScriptedClient:
    def __init__(self, scripts=(), *, clock=None, metadata=None):
        self.scripts = list(scripts)
        self.calls = []
        self.metadata_calls = []
        self.closed_streams = 0
        self.clock = clock
        self.metadata = metadata

    def generate(self, messages, config, mode, *, cross_model_fallback, tools=None):
        self.calls.append({"messages": [dict(message) for message in messages], "mode": mode,
                           "cross_model_fallback": cross_model_fallback, "tools": tools})
        script = self.scripts.pop(0)
        try:
            for event in script:
                if self.clock:
                    self.clock.advance(1)
                if isinstance(event, BaseException):
                    raise event
                yield event
        finally:
            self.closed_streams += 1

    def generation_metadata(self, response_id, timeout_seconds):
        self.metadata_calls.append((response_id, timeout_seconds))
        if self.clock:
            self.clock.advance(2)
        if isinstance(self.metadata, BaseException):
            raise self.metadata
        return self.metadata if self.metadata is not None else LLMEvent()
