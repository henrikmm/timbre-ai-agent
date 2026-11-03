"""Benchmark and terminal behavior using synthetic fixtures and blocked sockets."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from timbre.benchmark import (_load_fixture, build_report, comparative_summary, load_scenarios,
                              main as benchmark_main, markdown_summary, run_benchmark)
from timbre.cli import main as cli_main, run_chat
from timbre.conversation import Conversation
from timbre.llm.types import LLMError
from llm_support import OfflineTestCase, ScriptedClient, offline_config, synthetic_reply

FIXTURE = Path(__file__).parent / "fixtures/benchmark_metrics.synthetic.jsonl"


class BenchmarkTests(OfflineTestCase):
    def test_scenarios_cover_all_eight_initial_evaluations_with_translations(self):
        scenarios = load_scenarios()
        self.assertEqual(len(scenarios), 8)
        self.assertEqual(sum(len(s["turns"]) for s in scenarios), 9)
        self.assertEqual(len({s["id"] for s in scenarios}), 8)
        for scenario in scenarios:
            self.assertEqual(len(scenario["turns"]), len(scenario["translations"]))
            self.assertTrue(scenario["expected_behavior"])

    def test_fixture_aggregation_and_markdown_are_explicitly_synthetic(self):
        records = _load_fixture(FIXTURE)
        report = build_report(records, {"source": "synthetic_fixture"})
        summary = report["modes"]["standard"]
        self.assertEqual(summary["median_ttft_seconds"], 2)
        self.assertAlmostEqual(summary["p95_ttft_seconds"], 2.9)
        self.assertEqual(summary["total_cost_usd"], .004)
        self.assertEqual(summary["mean_output_tokens_per_second"], 30)
        self.assertEqual(report["modes"]["fast"]["error_rate"], .5)
        self.assertEqual(report["modes"]["fast"]["cost_known_requests"], 1)
        markdown = markdown_summary(report)
        self.assertIn("No real API performance evidence", markdown)
        self.assertIn("unstable with small samples", markdown)
        self.assertIn("SyntheticProviderA", markdown)
        self.assertIn("N/A", markdown)
        with self.assertRaises(ValueError):
            build_report(records, {"source": "live"})

    def test_fallback_and_unattributed_successes_do_not_enter_latency_comparison(self):
        sample = _load_fixture(FIXTURE)[0]
        fallback = replace(sample, request_id="synthetic-fallback", actual_model="synthetic/alternate", fallback_used=True, ttft_seconds=100)
        unknown = replace(sample, request_id="synthetic-unknown", actual_model=None, fallback_used=None, ttft_seconds=200)
        summary = comparative_summary([sample, fallback, unknown])
        self.assertEqual(summary["successful_requests"], 3)
        self.assertEqual(summary["comparable_successful_requests"], 1)
        self.assertEqual(summary["excluded_successful_requests"], 2)
        self.assertEqual(summary["median_ttft_seconds"], 1)
        self.assertEqual(summary["fallback_occurrences"], 1)

    def test_runner_preserves_context_with_fresh_trials_and_disables_fallback(self):
        scenarios = [load_scenarios()[3]]
        client = ScriptedClient([synthetic_reply() for _ in range(8)])
        report = run_benchmark(client, offline_config(), 2, scenarios=scenarios, source="synthetic_fixture")
        self.assertEqual(report["executed_requests"], 8)
        self.assertEqual(len(report["trials"]), 4)
        self.assertEqual(len({record["session_id"] for record in report["requests"]}), 4)
        self.assertTrue(all(not call["cross_model_fallback"] for call in client.calls))
        self.assertEqual([len(call["messages"]) for call in client.calls], [2, 4, 2, 4, 2, 4, 2, 4])
        self.assertEqual([call["mode"] for call in client.calls], ["standard", "standard", "fast", "fast", "fast", "fast", "standard", "standard"])

    def test_failed_first_turn_skips_followup_and_interrupt_stops_run(self):
        scenarios = [load_scenarios()[3]]
        client = ScriptedClient([[LLMError("timeout")], [KeyboardInterrupt()]])
        report = run_benchmark(client, offline_config(), 1, scenarios=scenarios, source="synthetic_fixture")
        self.assertEqual(report["executed_requests"], 2)
        self.assertEqual(report["status"], "interrupted")
        self.assertEqual([trial["skipped_turns"] for trial in report["trials"]], [1, 1])

    def test_default_command_is_a_no_network_no_credentials_plan(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("timbre.benchmark.OpenRouterClient.from_environment") as factory:
            self.assertEqual(benchmark_main([]), 0)
            factory.assert_not_called()
        self.assertIn('"planned_requests": 54', output.getvalue())
        self.assertIn('"source": "not_executed"', output.getvalue())
        self.assertIn('"cross_model_fallback": false', output.getvalue())

    def test_fixture_command_writes_machine_readable_results_and_english_summary(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), patch("timbre.benchmark.OpenRouterClient.from_environment") as factory:
            self.assertEqual(benchmark_main(["--fixture", str(FIXTURE), "--output-dir", directory]), 0)
            factory.assert_not_called()
            report = json.loads((Path(directory) / "results.json").read_text())
            self.assertEqual(report["manifest"]["source"], "synthetic_fixture")
            self.assertIsNone(report["manifest"]["settings"])
            self.assertTrue((Path(directory) / "summary.md").is_file())

    def test_live_flag_without_key_fails_before_requests_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()):
            destination = Path(directory) / "must-not-exist"
            code = benchmark_main(["--live", "--env-file", str(Path(directory) / "missing.env"),
                                   "--output-dir", str(destination)])
            self.assertEqual(code, 2)
            self.assertFalse(destination.exists())


class CLITests(OfflineTestCase):
    def test_command_dispatch_switching_clear_and_stats_need_no_model_requests(self):
        config = offline_config()
        client = ScriptedClient([synthetic_reply(model=config.modes["standard"].model),
                                 synthetic_reply(model=config.modes["fast"].model)])
        conversation = Conversation(client, config, source="synthetic_fixture")
        entries = iter(["", "/help", "/mode", "Oi", "/mode fast", "Algo em conta", "/stats", "/clear", "/mode invalid", "/unknown", "/exit"])
        output = io.StringIO()
        run_chat(conversation, input_fn=lambda _: next(entries), output=output)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(client.calls[-1]["messages"]), 4)
        self.assertEqual(len(conversation.history), 1)
        self.assertIn("History preserved", output.getvalue())
        self.assertIn("Requests: 2", output.getvalue())
        self.assertIn("Mode: standard", output.getvalue())
        self.assertIn("Mode: fast", output.getvalue())

    def test_partial_response_is_marked_incomplete_without_hidden_retry(self):
        from timbre.llm.types import LLMEvent

        client = ScriptedClient([[LLMEvent(text="Resposta parcial"), LLMError("network")]])
        conversation = Conversation(client, offline_config(), source="synthetic_fixture")
        entries = iter(["Oi", "/exit"])
        output = io.StringIO()
        run_chat(conversation, input_fn=lambda _: next(entries), output=output)
        self.assertIn("Resposta parcial", output.getvalue())
        self.assertIn("attempt was not saved", output.getvalue())
        self.assertEqual(len(client.calls), 1)

    def test_missing_key_error_is_actionable_without_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), redirect_stderr(io.StringIO()) as output:
            self.assertEqual(cli_main(["--env-file", str(Path(directory) / "missing.env")]), 2)
        self.assertIn("OPENROUTER_API_KEY", output.getvalue())

    def test_effective_fallback_model_is_announced_after_streaming(self):
        config = offline_config()
        client = ScriptedClient([synthetic_reply(model=config.modes["fast"].model)])
        conversation = Conversation(client, config, source="synthetic_fixture")
        entries = iter(["Oi", "/exit"])
        output = io.StringIO()
        run_chat(conversation, input_fn=lambda _: next(entries), output=output)
        self.assertIn("fallback model reflection/beam-1.0-501b-a23b", output.getvalue())
