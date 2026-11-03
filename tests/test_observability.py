"""Synthetic measurements verify timing semantics, coverage, and private JSONL."""

from dataclasses import replace
import json
from pathlib import Path
import stat
import tempfile

from timbre.config import ObservabilityConfig
from timbre.conversation import Conversation
from timbre.llm.types import LLMEvent, Usage
from timbre.observability import Observer, RequestMeasurement, percentile
from llm_support import ManualClock, OfflineTestCase, ScriptedClient, offline_config


class MeasurementTests(OfflineTestCase):
    def test_metadata_and_whitespace_do_not_count_as_first_visible_text(self):
        clock = ManualClock()
        measurement = RequestMeasurement("synthetic-session", "fast", "synthetic/model", clock=clock, source="synthetic_fixture")
        clock.advance(.5)
        measurement.event(LLMEvent(response_id="gen-synthetic-fixture"))
        clock.advance(.5)
        measurement.event(LLMEvent(text=" "))
        clock.advance(1)
        measurement.event(LLMEvent(text="Olá"))
        clock.advance(3)
        measurement.event(LLMEvent(text="!"))
        clock.advance(1)
        measurement.event(LLMEvent(finish_reason="stop", usage=Usage(input_tokens=10, output_tokens=6, total_tokens=16)))
        metrics = measurement.finish("success")
        measurement.finalize()
        self.assertEqual(metrics.time_to_first_event_seconds, .5)
        self.assertEqual(metrics.ttft_seconds, 2)
        self.assertEqual(metrics.total_latency_seconds, 6)
        self.assertEqual(metrics.streaming_generation_seconds, 3)
        self.assertIsNone(metrics.output_tokens_per_second)
        self.assertIsNone(metrics.cost_usd)
        self.assertIsNone(metrics.fallback_used)

    def test_missing_usage_stays_null_and_native_throughput_has_a_consistent_basis(self):
        measurement = RequestMeasurement("synthetic", "standard", "synthetic/model", source="synthetic_fixture")
        measurement.event(LLMEvent(text="Synthetic content", actual_model="synthetic/model"))
        metrics = measurement.finish("success")
        measurement.merge(LLMEvent(native_usage=Usage(output_tokens=60, reasoning_tokens=20), provider_generation_seconds=2))
        measurement.finalize()
        self.assertIsNone(metrics.output_tokens)
        self.assertIsNone(metrics.total_tokens)
        self.assertEqual(metrics.output_tokens_per_second, 30)
        self.assertFalse(metrics.fallback_used)

    def test_percentile_singletons_missing_and_interpolation(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile([4], .95), 4)
        self.assertAlmostEqual(percentile([1, 3], .95), 2.9)

    def test_jsonl_does_not_contain_customer_messages_responses_or_exception_bodies(self):
        secret = "synthetic-secret-for-privacy-test"
        personal = "synthetic.person@example.invalid"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requests.jsonl"
            observation = replace(ObservabilityConfig(), jsonl_path=str(path), generation_metadata="off")
            config = offline_config(observability=observation)
            client = ScriptedClient([[LLMEvent(text="Synthetic private reply " + personal), RuntimeError(secret)]])
            conversation = Conversation(client, config, source="synthetic_fixture")
            conversation.send("Synthetic private customer " + personal + secret)
            raw = path.read_text()
            record = json.loads(raw)
            for private in (secret, personal, "Synthetic private reply", "Synthetic private customer"):
                self.assertNotIn(private, raw)
            self.assertEqual(record["source"], "synthetic_fixture")
            self.assertEqual(record["status"], "incomplete")
            self.assertEqual(record["error_category"], "internal")
            self.assertIsNone(record["cost_usd"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_session_totals_have_known_cost_and_token_coverage(self):
        observer = Observer(ObservabilityConfig(enabled=False))
        for cost in (.01, None, 0.0):
            measurement = RequestMeasurement("synthetic-session", "standard", "synthetic/model", source="synthetic_fixture")
            measurement.event(LLMEvent(usage=Usage(input_tokens=5, cost_usd=cost)))
            observer.record(measurement.finish("success"))
        stats = observer.summary()
        self.assertEqual(stats["total_cost_usd"], .01)
        self.assertEqual(stats["mean_cost_usd"], .005)
        self.assertEqual(stats["cost_known_requests"], 2)
        self.assertEqual(stats["input_tokens"], 15)
        self.assertEqual(observer.records[-1].session_cost_usd, .01)
        self.assertEqual(observer.records[-1].session_cost_known_requests, 2)
        self.assertIsNone(Observer(ObservabilityConfig(enabled=False)).summary()["total_cost_usd"])

    def test_metric_preferences_are_applied_to_both_memory_and_jsonl(self):
        observer = Observer(ObservabilityConfig(enabled=False, record_tokens=False, record_cost=False,
                                              record_latency=False, record_provider=False))
        measurement = RequestMeasurement("synthetic", "standard", "synthetic/model", source="synthetic_fixture")
        measurement.event(LLMEvent(text="Hi", provider="SyntheticProvider", usage=Usage(input_tokens=10, cost_usd=1)))
        observer.record(measurement.finish("success"))
        result = observer.records[0]
        for field in ("input_tokens", "cost_usd", "provider", "ttft_seconds", "total_latency_seconds"):
            self.assertIsNone(getattr(result, field))

    def test_log_failure_retains_session_metrics_and_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            observer = Observer(ObservabilityConfig(jsonl_path=directory))
            measurement = RequestMeasurement("synthetic", "standard", "synthetic/model", source="synthetic_fixture")
            observer.record(measurement.finish("failed"))
            self.assertTrue(observer.persistence_failed)
            self.assertEqual(observer.summary()["requests"], 1)
