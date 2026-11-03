"""Focused integration checks for trace persistence, recovery, and CLI debugging."""

from dataclasses import replace
import io
import json
from pathlib import Path
import stat
from unittest.mock import patch

from timbre.cli import run_chat
from timbre.config import ConfigurationError, load_config
from timbre.conversation import Conversation
from timbre.llm.types import LLMEvent, ToolCall, Usage
from timbre.tools import ToolExecutor
from llm_support import ManualClock, ScriptedClient, offline_config, synthetic_reply
from tests.support import DatabaseTestCase, FIXTURES


def request(name, arguments, identifier="synthetic-call"):
    return [LLMEvent(tool_calls=(ToolCall(0, identifier, name, arguments),)),
            LLMEvent(finish_reason="tool_calls", usage=Usage(input_tokens=5, output_tokens=2, total_tokens=7, cost_usd=.001))]


class Phase3AIntegrationTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.executor = ToolExecutor(self.database, FIXTURES / "policies.synthetic.json")

    def conversation(self, scripts, **kwargs):
        return Conversation(ScriptedClient(scripts), offline_config(), executor=self.executor, source="synthetic_fixture", **kwargs)

    def test_invalid_and_backend_error_results_reach_model_with_correct_ids(self):
        scripts = [request("get_product_details", '{"product_id":true}', "invalid-call"),
                   request("unregistered_tool", '{}', "unknown-call"),
                   request("get_product_details", '{"product_id":101}', "failed-call"),
                   synthetic_reply("The source is unavailable.")]
        conversation = self.conversation(scripts)
        with patch.object(self.executor.catalog, "get_product_details", side_effect=OSError("synthetic secret path")):
            result = conversation.send("Synthetic operational question")
        self.assertEqual(result.metrics.status, "success")
        self.assertEqual(result.metrics.tool_call_count, 3)
        self.assertEqual(result.metrics.validation_failure_count, 2)
        self.assertEqual(result.metrics.tool_failure_count, 3)
        tools = [m for m in conversation.history if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tools], ["invalid-call", "unknown-call", "failed-call"])
        self.assertEqual([json.loads(m["content"])["status"] for m in tools],
                         ["invalid_arguments", "invalid_arguments", "backend_error"])
        self.assertNotIn("synthetic secret", str(conversation.get_trace()))
        self.assertEqual(conversation.client.closed_streams, 4)

    def test_private_persistence_uses_existing_observer_without_content_or_private_ids(self):
        log = self.directory / "requests.jsonl"
        config = offline_config()
        config = replace(config, observability=replace(config.observability, enabled=True, jsonl_path=str(log)))
        client = ScriptedClient([request("get_my_order_status", '{"order_id":5001}', "synthetic-5001-private"),
                                 synthetic_reply("Authentication is required.")])
        conversation = Conversation(client, config, executor=self.executor, source="synthetic_fixture")
        result = conversation.send("Show synthetic.person@example.invalid private information")
        self.assertEqual(result.metrics.authorization_denial_count, 1)
        self.assertEqual(len(log.read_text().splitlines()), 1)
        traces = log.with_name("requests.traces.jsonl")
        raw = traces.read_text() + log.read_text()
        for private in ('"order_id": 5001', "synthetic.person", "Authentication is required", "synthetic-5001-private"):
            self.assertNotIn(private, raw)
        self.assertEqual(stat.S_IMODE(traces.stat().st_mode), 0o600)
        events = conversation.get_trace(result.turn_id)
        self.assertEqual(events[0].event_type, "request_started")
        self.assertEqual(events[-1].event_type, "request_completed")
        self.assertEqual({e.turn_id for e in events}, {result.turn_id})
        self.assertEqual(len({e.llm_request_id for e in events if e.llm_request_id}), 2)
        external = next(e for e in events if e.sanitized_arguments)
        external.sanitized_arguments["order_id"] = "mutated"
        self.assertNotIn("mutated", str(conversation.get_trace()))

    def test_metric_preferences_apply_to_all_new_timing_and_coverage_fields(self):
        config = offline_config()
        config = replace(config, observability=replace(config.observability, record_tokens=False,
            record_cost=False, record_provider=False, record_latency=False))
        result = Conversation(ScriptedClient([synthetic_reply()]), config, executor=self.executor).send("Hello")
        for field in ("model_execution_seconds", "tool_execution_seconds", "tool_durations_seconds",
                      "overall_latency_seconds", "observed_cost_usd", "token_coverage", "providers"):
            self.assertIsNone(getattr(result.metrics, field))
        self.assertTrue(all(e.duration_seconds is None for e in result.events))

    def test_debug_commands_do_not_send_model_requests_or_change_authorization(self):
        conversation = self.conversation([request("get_my_order_status", '{"order_id":5001}'),
                                          synthetic_reply("Please authenticate through support.")])
        entries = iter(["/trace", "/debug on", "My order", "/debug off", "/trace", "/exit"])
        output = io.StringIO()
        run_chat(conversation, input_fn=lambda _: next(entries), output=output)
        rendered = output.getvalue()
        self.assertIn("No execution trace", rendered)
        self.assertIn("Debug on", rendered)
        self.assertIn("authorization_denied", rendered)
        self.assertNotIn('"order_id": 5001', rendered)
        self.assertEqual(len(conversation.client.calls), 2)

    def test_reentrant_metadata_cannot_modify_or_replace_pending_history(self):
        config = offline_config()
        config = replace(config, observability=replace(config.observability, generation_metadata="always"))
        client = ScriptedClient([synthetic_reply()])
        conversation = Conversation(client, config, executor=self.executor)
        attempts = []
        def metadata(*args):
            for action in (conversation.clear, lambda: conversation.send("Reentrant"), lambda: conversation.set_mode("fast")):
                with self.assertRaises(RuntimeError):
                    action()
                attempts.append(True)
            return LLMEvent()
        client.generation_metadata = metadata
        self.assertEqual(conversation.send("Hello").metrics.status, "success")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(conversation.history), 3)

    def test_total_turn_deadline_includes_tools_and_prevents_followup_model_request(self):
        clock = ManualClock()
        conversation = self.conversation([request("get_product_details", '{"product_id":101}')], clock=clock)
        original = self.executor.execute
        def execute(*args, **kwargs):
            result = original(*args, **kwargs)
            clock.advance(46)
            return result
        with patch.object(self.executor, "execute", side_effect=execute):
            result = conversation.send("Details")
        self.assertEqual(result.metrics.error_category, "timeout")
        self.assertEqual(len(conversation.client.calls), 1)
        self.assertEqual(len(conversation.history), 1)

    def test_tool_config_limits_and_path_types_are_validated(self):
        from importlib.resources import files
        content = files("timbre").joinpath("resources/default.toml").read_text()
        path = self.directory / "settings.toml"
        for before, after in (("max_iterations = 4", "max_iterations = 0"),
                              ("max_calls_per_turn = 12", "max_calls_per_turn = true"),
                              ('database_path = "data/store.db"', "database_path = []")):
            path.write_text(content.replace(before, after))
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_iteration_and_call_limits_stop_before_extra_execution(self):
        for changes, scripts, executed in (
            ({"max_iterations": 1}, [request("get_product_details", '{"product_id":101}', "first"),
                                     request("get_product_details", '{"product_id":106}', "second")], 1),
            ({"max_calls_per_turn": 1}, [[LLMEvent(tool_calls=(
                ToolCall(0, "first", "get_product_details", '{"product_id":101}'),
                ToolCall(1, "second", "get_product_details", '{"product_id":106}')),
                finish_reason="tool_calls")]], 0),
        ):
            with self.subTest(changes=changes):
                config = offline_config()
                config = replace(config, tools=replace(config.tools, **changes))
                conversation = Conversation(ScriptedClient(scripts), config, executor=self.executor)
                with patch.object(self.executor, "execute", wraps=self.executor.execute) as execute:
                    result = conversation.send("Synthetic repeated request")
                self.assertEqual(result.metrics.error_category, "tool_limit")
                self.assertEqual(execute.call_count, executed)
                self.assertEqual(len(conversation.history), 1)

    def test_partial_cost_is_visible_in_session_subtotal_without_claiming_full_coverage(self):
        scripts = [request("get_product_details", '{"product_id":101}'),
                   [LLMEvent(text="Synthetic answer", finish_reason="stop")], synthetic_reply()]
        conversation = self.conversation(scripts)
        first = conversation.send("Product question")
        self.assertIsNone(first.metrics.cost_usd)
        self.assertAlmostEqual(first.metrics.observed_cost_usd, .001)
        second = conversation.send("Hello")
        self.assertAlmostEqual(second.metrics.session_cost_usd, .0011)
        summary = conversation.observer.summary()
        self.assertAlmostEqual(summary["observed_cost_usd"], .0011)
        self.assertAlmostEqual(summary["total_cost_usd"], .0001)
        self.assertEqual(summary["cost_known_model_calls"], 2)
        self.assertEqual(summary["cost_known_requests"], 1)
