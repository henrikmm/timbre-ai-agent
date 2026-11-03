"""Synthetic function-calling protocol checks using the pinned SDK, offline."""

import json

import httpx
from openrouter import OpenRouter

from llm_support import OfflineTestCase, offline_config
from test_openrouter_adapter import chunk, sse, MODEL, SYNTHETIC_KEY
from timbre.llm.openrouter import OpenRouterClient
from timbre.llm.types import LLMError, ReasoningAccumulator, ToolCall, ToolCallAccumulator


TOOLS = [{"type": "function", "function": {"name": "get_product_details",
    "description": "Read a synthetic product.", "parameters": {"type": "object",
    "properties": {"product_id": {"type": "integer"}}, "required": ["product_id"],
    "additionalProperties": False}}}]


def tool_chunk(calls, *, finish=None, details=None):
    result = chunk(finish=finish)
    result["choices"][0]["delta"] = {"tool_calls": calls}
    if details is not None:
        result["choices"][0]["delta"]["reasoning_details"] = details
    return result


class ToolAdapterTests(OfflineTestCase):
    def client(self, handler, *, streaming=True):
        config = offline_config(streaming=streaming)
        transport = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(transport.close)
        sdk = OpenRouter(api_key=SYNTHETIC_KEY, client=transport)
        client = OpenRouterClient(SYNTHETIC_KEY, config, sdk=sdk)
        self.addCleanup(client.close)
        return client, config

    def test_interleaved_stream_fragments_are_reconstructed_by_index(self):
        events = [tool_chunk([
            {"index": 1, "id": "call_second", "type": "function", "function": {
                "name": "get_product_details", "arguments": '{"product_id":'}},
            {"index": 0, "id": "call_first", "type": "function", "function": {
                "name": "get_product_details", "arguments": '{"product_id":'}}]),
            tool_chunk([{"index": 0, "function": {"arguments": '41}'}},
                        {"index": 1, "function": {"arguments": '42}'}}]),
            chunk(finish="tool_calls")]
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse(events))

        client, config = self.client(handler)
        received = list(client.generate([], config, "fast", cross_model_fallback=False, tools=TOOLS))
        accumulator = ToolCallAccumulator()
        for event in received:
            accumulator.add(event.tool_calls)
        calls = accumulator.complete()
        self.assertEqual([call.id for call in calls], ["call_first", "call_second"])
        self.assertEqual([json.loads(call.arguments)["product_id"] for call in calls], [41, 42])
        self.assertEqual(received[-1].finish_reason, "tool_calls")
        self.assertEqual(requests[0]["tools"], TOOLS)
        self.assertEqual(requests[0]["tool_choice"], "auto")

    def test_buffered_calls_and_correct_tool_result_replay(self):
        calls = [{"id": "call_first", "type": "function", "function": {
            "name": "get_product_details", "arguments": '{"product_id":41}'}}]
        result = {"id": "gen-synthetic-tools", "created": 1, "model": MODEL,
            "object": "chat.completion", "system_fingerprint": None,
            "choices": [{"index": 0, "logprobs": None,
            "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": calls}}]}
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json=result)

        client, config = self.client(handler, streaming=False)
        received = list(client.generate([], config, "standard", cross_model_fallback=False, tools=TOOLS))
        self.assertEqual(received[0].tool_calls, (ToolCall(0, "call_first", "get_product_details", '{"product_id":41}'),))
        replay = [{"role": "assistant", "content": None, "tool_calls": calls},
                  {"role": "tool", "tool_call_id": "call_first", "content": '{"status":"empty"}'}]
        list(client.generate(replay, config, "standard", cross_model_fallback=False, tools=TOOLS))
        self.assertEqual(requests[-1]["messages"][1]["tool_call_id"], "call_first")
        self.assertEqual(requests[-1]["tools"], TOOLS)

    def test_native_reasoning_details_remain_separate_and_replayable(self):
        events = [tool_chunk([], details=[{"type": "reasoning.encrypted", "index": 0,
            "data": "SYNTHETIC-", "id": "rs_synthetic"}]),
            tool_chunk([], details=[{"type": "reasoning.encrypted", "index": 0,
            "data": "OPAQUE", "id": "rs_synthetic"}]), chunk("Final answer", finish="stop")]
        requests = []

        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse(events))

        client, config = self.client(handler)
        received = list(client.generate([], config, "fast", cross_model_fallback=False, tools=TOOLS))
        accumulator = ReasoningAccumulator()
        for event in received:
            accumulator.add(event.reasoning_details)
        self.assertEqual("".join(event.text for event in received), "Final answer")
        self.assertEqual(accumulator.complete()[0]["data"], "SYNTHETIC-OPAQUE")
        replay = [{"role": "assistant", "content": None,
            "reasoning_details": list(accumulator.complete()), "tool_calls": [{
                "id": "call_synthetic", "type": "function", "function": {
                "name": "get_product_details", "arguments": '{"product_id":41}'}}]},
            {"role": "tool", "tool_call_id": "call_synthetic", "content": '{"status":"empty"}'}]
        list(client.generate(replay, config, "fast", cross_model_fallback=False, tools=TOOLS))
        self.assertEqual(requests[-1]["messages"][0]["reasoning_details"][0]["data"], "SYNTHETIC-OPAQUE")


class AccumulatorTests(OfflineTestCase):
    def test_split_identifier_name_and_empty_object_arguments(self):
        accumulator = ToolCallAccumulator()
        accumulator.add((ToolCall(0, "call_", "get_", "{"),))
        accumulator.add((ToolCall(0, "synthetic", "store_policy", "}"),))
        self.assertEqual(accumulator.complete(), (ToolCall(0, "call_synthetic", "get_store_policy", "{}"),))

    def test_duplicate_identifiers_and_missing_names_are_protocol_errors(self):
        for calls in ((ToolCall(0, "call_same", "a", "{}"), ToolCall(1, "call_same", "b", "{}")),
                      (ToolCall(0, "call_missing", None, "{}"),), (ToolCall(1, "call_gap", "a", "{}"),)):
            with self.subTest(calls=calls), self.assertRaises(LLMError):
                accumulator = ToolCallAccumulator()
                accumulator.add(calls)
                accumulator.complete()

    def test_invalid_indices_and_unbounded_arguments_are_rejected(self):
        for call in (ToolCall(True, "call", "a", "{}"), ToolCall(-1, "call", "a", "{}"),
                     ToolCall(16, "call", "a", "{}"), ToolCall(0, "call", "a", "x" * 65537),
                     ToolCall(0, "call", "a", "é" * 32769)):
            with self.subTest(index=call.index), self.assertRaises(LLMError):
                ToolCallAccumulator().add((call,))

    def test_incomplete_json_is_preserved_for_executor_validation(self):
        accumulator = ToolCallAccumulator()
        accumulator.add((ToolCall(0, "call_synthetic", "a", '{"product_id":'),))
        self.assertEqual(accumulator.complete()[0].arguments, '{"product_id":')

    def test_empty_or_unsafe_call_identifiers_fail_without_exposing_values(self):
        for identifier in ("", "synthetic.person@example.invalid", "call\nunsafe"):
            accumulator = ToolCallAccumulator()
            accumulator.add((ToolCall(0, identifier, "a", "{}"),))
            with self.assertRaises(LLMError) as caught:
                accumulator.complete()
            self.assertNotIn(identifier or "synthetic.person", str(caught.exception))

    def test_reasoning_reconstruction_is_bounded_and_defensive(self):
        accumulator = ReasoningAccumulator()
        accumulator.add(({"type": "reasoning.text", "index": 0, "text": "Synthetic"},))
        snapshot = accumulator.complete()
        snapshot[0]["text"] = "Modified"
        self.assertEqual(accumulator.complete()[0]["text"], "Synthetic")
        with self.assertRaises(LLMError):
            accumulator.add(({"type": "reasoning.text", "index": 0, "text": "x" * 262145},))
