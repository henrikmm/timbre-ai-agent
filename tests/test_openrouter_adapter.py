"""Exercise the pinned official SDK over an in-process HTTP transport only."""

from dataclasses import replace
import json
from unittest.mock import patch

import httpx
from openrouter import OpenRouter as RealOpenRouter

from timbre.config import load_config
from timbre.llm.openrouter import OpenRouterClient
from timbre.llm.types import LLMError
from llm_support import OfflineTestCase


SYNTHETIC_KEY = "synthetic-fixture-not-a-credential"
MODEL = "reflection/beam-1.0-501b-a23b"


def chunk(content=None, *, finish=None, **extras):
    delta = {} if content is None else {"content": content}
    return {"id": "gen-synthetic-fixture", "created": 1, "model": MODEL,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **extras}


def sse(events):
    return ": synthetic keepalive\n\n" + "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"


class AdapterTests(OfflineTestCase):
    def client(self, handler, config=None):
        config = load_config() if config is None else config
        transport = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(transport.close)

        def factory(**kwargs):
            self.assertEqual(kwargs["retry_config"].strategy, "none")
            self.assertFalse(kwargs["retry_config"].retry_connection_errors)
            return RealOpenRouter(client=transport, **kwargs)

        with patch("openrouter.OpenRouter", side_effect=factory):
            client = OpenRouterClient(SYNTHETIC_KEY, config)
        self.addCleanup(client.close)
        return client, config

    def test_sdk_streaming_shapes_usage_routing_and_reasoning_filter(self):
        requests = []
        routing = {"requested": MODEL, "strategy": "direct", "region": None,
                   "summary": "Synthetic fixture", "attempt": 2, "is_byok": False,
                   "endpoints": {"total": 2, "available": [
                       {"provider": "SyntheticB", "model": MODEL, "selected": True}]},
                   "attempts": [{"provider": "SyntheticA", "model": MODEL, "status": 503},
                                {"provider": "SyntheticB", "model": MODEL, "status": 200}]}
        reasoning = chunk()
        reasoning["choices"][0]["delta"] = {"reasoning": "SYNTHETIC HIDDEN REASONING"}
        events = [chunk(), reasoning, chunk("Olá, "), chunk("sou o Timbre."), chunk(finish="stop"),
                  {**chunk(), "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18,
                    "completion_tokens_details": {"reasoning_tokens": 2}, "prompt_tokens_details": {"cached_tokens": 3},
                    "cost": .00002}, "openrouter_metadata": routing}]

        def handler(request):
            requests.append(request)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse(events))

        client, config = self.client(handler)
        received = list(client.generate([{"role": "user", "content": "Synthetic customer prompt"}], config, "fast", cross_model_fallback=False))
        self.assertEqual("".join(event.text for event in received), "Olá, sou o Timbre.")
        self.assertEqual(received[-1].provider, "SyntheticB")
        self.assertEqual(received[-1].upstream_attempts, 2)
        self.assertTrue(received[-1].provider_fallback_used)
        self.assertEqual(received[-1].usage.reasoning_tokens, 2)
        self.assertEqual(received[-1].usage.cached_tokens, 3)
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["provider"]["sort"], "latency")
        self.assertEqual(requests[0].headers["X-OpenRouter-Metadata"], "enabled")
        self.assertEqual(len(requests), 1)

    def test_buffered_response_and_missing_usage(self):
        result = {"id": "gen-synthetic-buffered", "created": 1, "model": MODEL,
                  "object": "chat.completion", "system_fingerprint": None,
                  "choices": [{"index": 0, "finish_reason": "stop", "logprobs": None,
                               "message": {"role": "assistant", "content": "Olá!", "refusal": None}}]}
        client, config = self.client(lambda _: httpx.Response(200, json=result), replace(load_config(), streaming=False))
        received = list(client.generate([], config, "fast", cross_model_fallback=False))
        self.assertEqual(received[0].text, "Olá!")
        self.assertEqual(received[0].finish_reason, "stop")
        self.assertIsNone(received[0].usage)

    def test_http_errors_are_safe_and_not_retried(self):
        for status, category in ((400, "invalid_request_or_unsupported_parameter"),
                                 (401, "authentication_or_permission"), (402, "billing"),
                                 (429, "rate_limit"), (500, "provider_unavailable"), (504, "timeout")):
            calls = []

            def handler(request):
                calls.append(request)
                return httpx.Response(status, json={"error": {"code": status,
                    "message": SYNTHETIC_KEY + " synthetic.person@example.invalid"}})

            with self.subTest(status=status):
                client, config = self.client(handler)
                with self.assertRaises(LLMError) as caught:
                    list(client.generate([], config, "standard", cross_model_fallback=False))
                self.assertEqual(caught.exception.category, category)
                self.assertEqual(caught.exception.http_status, status)
                self.assertNotIn(SYNTHETIC_KEY, str(caught.exception))
                self.assertNotIn("example.invalid", str(caught.exception))
                self.assertEqual(len(calls), 1)

    def test_timeout_and_network_error_are_not_retried(self):
        for error, category in ((httpx.ReadTimeout(SYNTHETIC_KEY), "timeout"),
                                (httpx.ConnectError(SYNTHETIC_KEY), "network")):
            calls = []

            def handler(request):
                calls.append(request)
                raise error

            client, config = self.client(handler)
            with self.assertRaises(LLMError) as caught:
                list(client.generate([], config, "fast", cross_model_fallback=False))
            self.assertEqual(caught.exception.category, category)
            self.assertEqual(len(calls), 1)

    def test_in_band_error_after_partial_text_does_not_retry(self):
        events = [chunk("Partial fixture"), chunk(finish="error", error={"code": 503, "message": SYNTHETIC_KEY})]
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse(events))

        client, config = self.client(handler)
        stream = client.generate([], config, "fast", cross_model_fallback=False)
        self.assertEqual(next(stream).text, "Partial fixture")
        with self.assertRaises(LLMError):
            next(stream)
        self.assertEqual(len(calls), 1)

    def test_malformed_sse_is_a_safe_protocol_error(self):
        client, config = self.client(lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, text='data: {"unexpected":"synthetic private value"}\n\n'))
        with self.assertRaises(LLMError) as caught:
            list(client.generate([], config, "fast", cross_model_fallback=False))
        self.assertNotIn("synthetic private value", str(caught.exception))

    def test_generation_metadata_uses_native_tokens_and_converts_milliseconds(self):
        from openrouter.components.generationresponse import GenerationResponseData

        data = {name: None for name, field in GenerationResponseData.model_fields.items() if field.is_required()}
        data.update({"id": "gen-synthetic-fixture", "model": MODEL, "provider_name": "SyntheticProvider",
                     "created_at": "2026-11-02T00:00:00Z", "data_region": "global", "is_byok": False,
                     "origin": "synthetic-fixture", "total_cost": .0002, "usage": .0002,
                     "latency": 1200, "generation_time": 800, "native_tokens_completion": 40,
                     "native_tokens_prompt": 20, "native_tokens_reasoning": 10, "native_tokens_cached": 4})
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.params["id"], "gen-synthetic-fixture")
            return httpx.Response(200, json={"data": data})

        client, _ = self.client(handler)
        event = client.generation_metadata("gen-synthetic-fixture", 2)
        self.assertEqual(event.provider_latency_seconds, 1.2)
        self.assertEqual(event.provider_generation_seconds, .8)
        self.assertEqual(event.native_usage.output_tokens, 40)
        self.assertIsNone(event.usage.output_tokens)
        self.assertEqual(event.usage.cost_usd, .0002)
        self.assertEqual(len(calls), 1)
