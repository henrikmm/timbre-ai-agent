"""Focused synthetic checks for tool-loop transaction and privacy invariants."""

import json
from unittest.mock import patch

from llm_support import ManualClock, OfflineTestCase, ScriptedClient, offline_config, synthetic_reply
from support import DatabaseTestCase, SimulatedAuthorizer
from timbre.conversation import Conversation
from timbre.llm.types import LLMEvent, ToolCall, Usage
from timbre.tools import ToolExecutor


def request_tool(*calls, usage=None):
    return [LLMEvent(tool_calls=tuple(calls)), LLMEvent(finish_reason="tool_calls", usage=usage)]


def product_call(index=0, identifier="call_synthetic_product", product_id=101):
    return ToolCall(index, identifier, "get_product_details", json.dumps({"product_id": product_id}))


class ToolConversationTests(DatabaseTestCase, OfflineTestCase):
    def setUp(self):
        OfflineTestCase.setUp(self)
        DatabaseTestCase.setUp(self)

    def conversation(self, scripts, *, config=None, clock=None, authorizer=None, context=None):
        options = {"clock": clock} if clock is not None else {}
        executor = ToolExecutor(self.database, self.raw / "policies.synthetic.json",
                                authorizer=authorizer, **options)
        client = ScriptedClient(scripts, **options)
        conversation = Conversation(client, config or offline_config(), executor=executor,
                                    trusted_session_context=context, source="synthetic_fixture", **options)
        return conversation, client, executor

    def test_history_limit_keeps_complete_tool_groups_for_followups(self):
        scripts = []
        for index in range(3):
            scripts.extend([request_tool(product_call(identifier=f"call_synthetic_{index}")),
                            synthetic_reply(f"Synthetic product answer {index}")])
        conversation, client, _ = self.conversation(scripts, config=offline_config(history_turn_limit=2))
        for text in ("First product", "The second one", "Can I pay for that?"):
            self.assertEqual(conversation.send(text).metrics.status, "success")
        history = conversation.history
        self.assertEqual([message["role"] for message in history],
                         ["system", "user", "assistant", "tool", "assistant",
                          "user", "assistant", "tool", "assistant"])
        self.assertNotIn("First product", str(history))
        self.assertEqual(client.calls[-2]["messages"][2]["tool_calls"][0]["id"], "call_synthetic_1")
        self.assertEqual(history[3]["tool_call_id"], history[2]["tool_calls"][0]["id"])
        exposed = conversation.history
        exposed[2]["tool_calls"][0]["function"]["arguments"] = "tampered"
        self.assertNotIn("tampered", str(conversation.history))

    def test_truncated_or_stop_terminated_tool_stream_never_executes(self):
        for finish in (None, "length", "stop"):
            events = [LLMEvent(tool_calls=(product_call(),))]
            if finish:
                events.append(LLMEvent(finish_reason=finish))
            conversation, _, executor = self.conversation([events])
            with self.subTest(finish=finish), patch.object(executor, "execute", wraps=executor.execute) as execute:
                result = conversation.send("Synthetic operational question")
                self.assertNotEqual(result.metrics.status, "success")
                execute.assert_not_called()
                self.assertEqual(conversation.history, [conversation.history[0]])

    def test_malformed_json_returns_matching_tool_result_then_model_can_recover(self):
        call = ToolCall(0, "call_synthetic_bad_json", "get_product_details", '{"product_id":')
        conversation, client, _ = self.conversation([request_tool(call), synthetic_reply("I could not read that product.")])
        result = conversation.send("Synthetic product question")
        self.assertEqual(result.metrics.status, "success")
        self.assertEqual(result.metrics.validation_failure_count, 1)
        forwarded = client.calls[-1]["messages"][-1]
        self.assertEqual(forwarded["tool_call_id"], call.id)
        self.assertEqual(json.loads(forwarded["content"])["status"], "invalid_arguments")

    def test_reused_call_id_in_same_turn_fails_without_repeating_execution(self):
        conversation, _, executor = self.conversation([
            request_tool(product_call()), request_tool(product_call()), synthetic_reply()])
        with patch.object(executor, "execute", wraps=executor.execute) as execute:
            result = conversation.send("Synthetic product question")
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(result.metrics.error_category, "protocol")
        self.assertEqual(len(conversation.history), 1)

    def test_usage_snapshots_replace_within_call_and_sum_across_model_calls(self):
        clock = ManualClock()
        first_usage = Usage(input_tokens=2, output_tokens=3, total_tokens=5, cost_usd=.01)
        events = request_tool(product_call(), product_call(1, "call_synthetic_other", 106), usage=first_usage)
        events.append(LLMEvent(usage=first_usage))
        final = [LLMEvent(text="Synthetic grounded answer", finish_reason="stop",
                          usage=Usage(input_tokens=4, output_tokens=5, total_tokens=9, cost_usd=.02))]
        conversation, _, executor = self.conversation([events, final], clock=clock)
        original = executor.catalog.get_product_details

        def slow_read(product_id):
            clock.advance(.25)
            return original(product_id)

        with patch.object(executor.catalog, "get_product_details", side_effect=slow_read):
            result = conversation.send("Compare synthetic instruments")
        metrics = result.metrics
        self.assertEqual(metrics.model_call_count, 2)
        self.assertEqual(metrics.tool_call_count, 2)
        self.assertEqual((metrics.input_tokens, metrics.output_tokens, metrics.total_tokens), (6, 8, 14))
        self.assertAlmostEqual(metrics.cost_usd, .03)
        self.assertEqual(metrics.cost_known_model_calls, 2)
        self.assertEqual(metrics.model_execution_seconds, 4)
        self.assertEqual(metrics.tool_execution_seconds, .5)
        self.assertEqual(metrics.total_latency_seconds, 4.5)
        self.assertEqual(metrics.ttft_seconds, 4.5)

    def test_missing_usage_keeps_aggregate_unknown_and_preserves_observed_cost(self):
        conversation, _, _ = self.conversation([
            request_tool(product_call(), usage=Usage(input_tokens=5, cost_usd=.01)),
            [LLMEvent(text="Synthetic final answer", finish_reason="stop")]])
        metrics = conversation.send("Synthetic product question").metrics
        self.assertIsNone(metrics.cost_usd)
        self.assertIsNone(metrics.input_tokens)
        self.assertEqual(metrics.observed_cost_usd, .01)
        self.assertEqual(metrics.cost_known_model_calls, 1)
        self.assertEqual(metrics.token_coverage["input_tokens"], 1)

    def test_authorized_private_results_are_not_copied_to_trace_events(self):
        authorizer = SimulatedAuthorizer()
        context = authorizer.issue_for_test(9001)
        call = ToolCall(0, "call_synthetic_sensitive_id", "get_my_order_status", '{"order_id":5001}')
        conversation, client, _ = self.conversation([request_tool(call), synthetic_reply("Your synthetic order was shipped.")],
            authorizer=authorizer, context=context)
        result = conversation.send("Synthetic private order question")
        self.assertEqual(result.metrics.status, "success")
        private_result = json.loads(client.calls[-1]["messages"][-1]["content"])
        self.assertEqual(private_result["data"]["tracking_code"], "SYNTHETIC-A")
        trace = json.dumps([event.to_dict() for event in result.events])
        for private in ('"order_id": 5001', '"customer_id": 9001', "SYNTHETIC-A", call.id, "Synthetic private order question"):
            self.assertNotIn(private, trace)
        completed = [event for event in result.events if event.event_type == "tool_execution_completed"]
        self.assertEqual(completed[0].sanitized_arguments, {"order_id": "[redacted]"})

    def test_other_customer_order_is_uniform_empty_and_public_session_is_denied(self):
        authorizer = SimulatedAuthorizer()
        context = authorizer.issue_for_test(9001)
        call = ToolCall(0, "call_synthetic_foreign_order", "get_my_order_status", '{"order_id":5002}')
        for trusted in (None, context):
            conversation, client, _ = self.conversation([request_tool(call), synthetic_reply("I cannot retrieve that order.")],
                authorizer=authorizer, context=trusted)
            result = conversation.send("Show another customer's synthetic order")
            status = json.loads(client.calls[-1]["messages"][-1]["content"])["status"]
            self.assertEqual(status, "empty" if trusted is context else "authorization_denied")
            self.assertNotIn("SYNTHETIC-B", str(client.calls))
            self.assertEqual(result.metrics.authorization_denial_count, 0 if trusted is context else 1)
