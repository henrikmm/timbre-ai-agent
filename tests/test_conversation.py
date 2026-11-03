"""Synthetic streamed turns exercise state transitions without a provider."""

from dataclasses import replace

from timbre.conversation import Conversation
from timbre.llm.types import LLMError, LLMEvent, Usage
from llm_support import ManualClock, OfflineTestCase, ScriptedClient, offline_config, synthetic_reply


class ConversationTests(OfflineTestCase):
    def test_default_switch_preserves_history_and_mode_used_for_next_request(self):
        config = offline_config()
        client = ScriptedClient([synthetic_reply(), synthetic_reply()])
        conversation = Conversation(client, config, source="synthetic_fixture")
        self.assertEqual(conversation.mode, "standard")
        conversation.send("Quero um violão para iniciante.")
        original = conversation.history
        conversation.set_mode("fast")
        self.assertEqual(conversation.history, original)
        conversation.send("Algo em conta.")
        self.assertEqual(client.calls[-1]["mode"], "fast")
        self.assertEqual(client.calls[-1]["messages"][1]["content"], "Quero um violão para iniciante.")
        self.assertEqual([message["role"] for message in conversation.history], ["system", "user", "assistant", "user", "assistant"])
        with self.assertRaises(ValueError):
            conversation.set_mode("unconfigured")

    def test_streaming_assembles_one_assistant_message_and_streams_progressively(self):
        clock = ManualClock()
        events = [LLMEvent(), LLMEvent(text="Olá, "), LLMEvent(text="vamos conversar!", finish_reason="stop")]
        client = ScriptedClient([events], clock=clock)
        conversation = Conversation(client, offline_config(), clock=clock, source="synthetic_fixture")
        displayed = []
        result = conversation.send("Oi", on_text=lambda text: displayed.append((text, clock())))
        self.assertEqual(result.text, "Olá, vamos conversar!")
        self.assertEqual(displayed, [("Olá, ", 2), ("vamos conversar!", 3)])
        self.assertEqual(conversation.history[-1]["content"], result.text)
        self.assertEqual(result.metrics.status, "success")
        self.assertEqual(result.metrics.time_to_first_event_seconds, 1)
        self.assertEqual(result.metrics.ttft_seconds, 2)
        self.assertEqual(result.metrics.streaming_generation_seconds, 1)

    def test_failed_and_truncated_turns_roll_back_without_retries_or_duplicate_users(self):
        scripts = [synthetic_reply(), [LLMEvent(text="Resposta parcial"), LLMError("network")],
                   [LLMEvent(text="Truncada", finish_reason="length")], synthetic_reply()]
        client = ScriptedClient(scripts)
        conversation = Conversation(client, offline_config(), source="synthetic_fixture")
        conversation.send("Primeira")
        original = conversation.history
        for message in ("Tentativa", "Tentativa"):
            result = conversation.send(message)
            self.assertEqual(result.metrics.status, "incomplete")
            self.assertTrue(result.metrics.partial_output)
            self.assertEqual(conversation.history, original)
        conversation.send("Tentativa")
        self.assertEqual([m["content"] for m in conversation.history].count("Tentativa"), 1)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(client.closed_streams, 4)

    def test_empty_missing_finish_filtered_and_unexpected_tool_responses_are_not_success(self):
        for events in ([LLMEvent(finish_reason="stop")], [LLMEvent(text="  ", finish_reason="stop")],
                       [LLMEvent(text="Abrupt end")], [LLMEvent(finish_reason="content_filter")],
                       [LLMEvent(finish_reason="tool_calls")]):
            with self.subTest(events=events):
                conversation = Conversation(ScriptedClient([events]), offline_config(), source="synthetic_fixture")
                result = conversation.send("Synthetic input")
                self.assertNotEqual(result.metrics.status, "success")
                self.assertEqual(len(conversation.history), 1)

    def test_interruption_closes_stream_does_not_commit_and_can_continue(self):
        client = ScriptedClient([synthetic_reply(), synthetic_reply()])
        conversation = Conversation(client, offline_config(), source="synthetic_fixture")

        def interrupt(_):
            raise KeyboardInterrupt

        result = conversation.send("Oi", on_text=interrupt)
        self.assertEqual(result.metrics.status, "interrupted")
        self.assertEqual(len(conversation.history), 1)
        self.assertEqual(client.closed_streams, 1)
        self.assertEqual(conversation.send("Oi").metrics.status, "success")

    def test_timeouts_and_errors_are_instrumented(self):
        for failure in (LLMError("timeout", 504), LLMError("rate_limit", 429), RuntimeError("synthetic secret")):
            with self.subTest(failure=type(failure).__name__):
                conversation = Conversation(ScriptedClient([[failure]]), offline_config(), source="synthetic_fixture")
                metrics = conversation.send("Oi").metrics
                self.assertEqual(metrics.status, "failed")
                self.assertNotIn("synthetic secret", str(metrics.to_dict()))
                self.assertEqual(metrics.timeout_occurred, isinstance(failure, LLMError) and failure.category == "timeout")
                self.assertEqual(len(conversation.observer.records), 1)

    def test_history_limit_retains_whole_turns_and_reset_preserves_instructions_and_stats(self):
        client = ScriptedClient([synthetic_reply() for _ in range(4)])
        conversation = Conversation(client, offline_config(history_turn_limit=2), system_prompt="Synthetic system", source="synthetic_fixture")
        for message in ("One", "Two", "Three"):
            conversation.send(message)
        self.assertEqual(len(conversation.history), 5)
        self.assertEqual(client.calls[-1]["messages"][1]["content"], "Two")
        exposed = conversation.history
        exposed[0]["content"] = "Tampered"
        self.assertEqual(conversation.history[0]["content"], "Synthetic system")
        conversation.clear()
        self.assertEqual(conversation.history, [{"role": "system", "content": "Synthetic system"}])
        self.assertEqual(len(conversation.observer.records), 3)
        conversation.send("Fresh")
        self.assertEqual(len(client.calls[-1]["messages"]), 2)

    def test_sessions_are_isolated_and_empty_input_creates_no_request(self):
        client = ScriptedClient([synthetic_reply()])
        first = Conversation(client, offline_config(), source="synthetic_fixture")
        second = Conversation(client, offline_config(), source="synthetic_fixture")
        first.send("Synthetic customer input")
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual(len(second.history), 1)
        with self.assertRaises(ValueError):
            second.send(" \n ")
        self.assertEqual(len(client.calls), 1)

    def test_fallback_attribution_and_disabled_fallback_rejects_unexpected_model(self):
        config = offline_config()
        alternate = config.modes["fast"].model
        client = ScriptedClient([synthetic_reply(model=alternate), synthetic_reply(model=alternate)])
        conversation = Conversation(client, config, source="synthetic_fixture")
        result = conversation.send("Oi")
        self.assertTrue(result.metrics.fallback_used)
        self.assertEqual(result.metrics.actual_model, alternate)
        original = conversation.history
        result = conversation.send("Oi de novo", cross_model_fallback=False)
        self.assertEqual(result.metrics.error_category, "unexpected_model")
        self.assertEqual(conversation.history, original)

    def test_metadata_lookup_happens_after_output_and_is_outside_request_latency(self):
        clock = ManualClock()
        config = offline_config()
        config = replace(config, observability=replace(config.observability, generation_metadata="missing"))
        client = ScriptedClient([[LLMEvent(text="Oi", response_id="gen-synthetic", finish_reason="stop")]], clock=clock,
                                metadata=LLMEvent(provider="SyntheticProvider", usage=Usage(cost_usd=.01),
                                                  native_usage=Usage(output_tokens=20), provider_generation_seconds=2))
        displayed = []
        result = Conversation(client, config, clock=clock, source="synthetic_fixture").send("Oi", on_text=lambda _: displayed.append(clock()))
        self.assertEqual(displayed, [1])
        self.assertEqual(result.metrics.total_latency_seconds, 1)
        self.assertEqual(result.metrics.metadata_lookup_seconds, 2)
        self.assertEqual(result.metrics.output_tokens_per_second, 10)
        self.assertEqual(len(client.metadata_calls), 1)

    def test_metadata_failure_cannot_turn_completed_answer_into_failure(self):
        config = offline_config()
        config = replace(config, observability=replace(config.observability, generation_metadata="missing"))
        client = ScriptedClient([synthetic_reply()], metadata=LLMError("timeout"))
        result = Conversation(client, config, source="synthetic_fixture").send("Oi")
        self.assertEqual(result.metrics.status, "success")
        self.assertEqual(result.metrics.metadata_lookup_status, "unavailable")
        self.assertIsNone(result.metrics.provider)

    def test_reentrant_requests_and_mode_changes_are_rejected(self):
        conversation = Conversation(ScriptedClient([synthetic_reply()]), offline_config(), source="synthetic_fixture")

        def callback(_):
            for action in (lambda: conversation.send("Other"), lambda: conversation.set_mode("fast"), conversation.clear):
                with self.assertRaises(RuntimeError):
                    action()

        self.assertEqual(conversation.send("Oi", on_text=callback).metrics.status, "success")
