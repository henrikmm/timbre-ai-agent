"""Controlled synthetic scenarios, content-free measurements, and honest reports."""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
from importlib import metadata
from importlib.resources import files
import json
from pathlib import Path
import platform
import subprocess
import sys
from uuid import uuid4

from timbre.config import AppConfig, ConfigurationError, load_config, load_system_prompt
from timbre.conversation import Conversation
from timbre.llm.openrouter import OpenRouterClient
from timbre.local_files import write_private
from timbre.observability import Observer, RequestMetrics, summarize


def load_scenarios() -> list[dict]:
    return json.loads(files("timbre").joinpath("resources/benchmark_scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def run_manifest(config: AppConfig, scenarios: list[dict], repetitions: int, *, source: str) -> dict:
    settings = {"modes": {name: asdict(mode) for name, mode in config.modes.items()},
                "streaming": config.streaming, "max_output_tokens": config.max_output_tokens,
                "timeout_seconds": config.timeout_seconds, "history_turn_limit": config.history_turn_limit,
                "routing": asdict(config.routing), "cross_model_fallback": False,
                "observability": {key: value for key, value in asdict(config.observability).items() if key != "jsonl_path"}}
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=5).stdout)
    except (OSError, subprocess.SubprocessError):
        revision, dirty = None, None
    return {"schema_version": 1, "source": source, "created_at": datetime.now(timezone.utc).isoformat(),
            "settings": settings, "settings_sha256": _digest(settings),
            "system_prompt_sha256": hashlib.sha256(load_system_prompt().encode()).hexdigest(),
            "scenarios_sha256": _digest(scenarios), "repetitions": repetitions,
            "scenario_count": len(scenarios), "planned_requests": sum(len(s["turns"]) for s in scenarios) * repetitions * 2,
            "python_version": platform.python_version(), "sdk_version": metadata.version("openrouter"),
            "git_revision": revision, "git_dirty": dirty,
            "schedule": "Scenario/repetition order; alternate the first mode per trial; fresh conversation for each mode/trial."}


def comparative_summary(records: list[RequestMetrics]) -> dict:
    result = summarize(records)
    comparable = [record for record in records if record.status == "success"
                  and record.actual_model == record.requested_model and record.fallback_used is False]
    controlled = summarize(comparable)
    for field in ("median_ttft_seconds", "p95_ttft_seconds", "ttft_samples",
                  "median_total_latency_seconds", "p95_total_latency_seconds", "latency_samples",
                  "mean_output_tokens_per_second", "throughput_samples"):
        result[field] = controlled[field]
    result["comparable_successful_requests"] = len(comparable)
    result["excluded_successful_requests"] = result["successful_requests"] - len(comparable)
    return result


def build_report(records: list[RequestMetrics], manifest: dict, *, trials=None, status="completed") -> dict:
    sources = {record.source for record in records}
    if sources - {manifest["source"]}:
        raise ValueError("Report source must match every request; synthetic fixtures cannot be labeled live.")
    return {"manifest": manifest, "status": status, "executed_requests": len(records),
            "modes": {mode: comparative_summary([record for record in records if record.mode == mode])
                      for mode in ("standard", "fast")},
            "trials": trials or [], "requests": [record.to_dict() for record in records],
            "behavioral_quality": "Not scored. Review the scenario expectations and observe live responses explicitly."}


def markdown_summary(report: dict) -> str:
    def fmt(value):
        return "N/A" if value is None else f"{value:.6g}"

    source = report["manifest"]["source"]
    lines = ["# Timbre model benchmark", "", f"Evidence source: **{source}**. Run status: **{report['status']}**.", ""]
    if source != "live":
        lines += ["**No real API performance evidence. These values are synthetic fixtures or an unexecuted plan.**", ""]
    lines += ["## Measurements", "", "| Metric | Standard | Fast |", "|---|---:|---:|"]
    fields = [("Executed requests", "requests"), ("Successful requests", "successful_requests"),
              ("Comparable successes", "comparable_successful_requests"),
              ("Excluded successes (fallback/unattributed)", "excluded_successful_requests"),
              ("Error rate", "error_rate"), ("Median TTFT (s)", "median_ttft_seconds"),
              ("P95 TTFT (s)", "p95_ttft_seconds"), ("TTFT samples", "ttft_samples"),
              ("Median total latency (s)", "median_total_latency_seconds"),
              ("P95 total latency (s)", "p95_total_latency_seconds"), ("Latency samples", "latency_samples"),
              ("Mean provider completion throughput (tokens/s)", "mean_output_tokens_per_second"),
              ("Throughput samples", "throughput_samples"), ("Mean observed request cost (USD)", "mean_cost_usd"),
              ("Total observed cost (USD)", "total_cost_usd"), ("Requests with known cost", "cost_known_requests"),
              ("Cross-model fallback occurrences", "fallback_occurrences"), ("Timeouts", "timeouts")]
    for label, field in fields:
        lines.append(f"| {label} | {fmt(report['modes']['standard'][field])} | {fmt(report['modes']['fast'][field])} |")
    for label, field in (("Actual providers", "providers"), ("Actual models", "actual_models")):
        cells = [", ".join(report["modes"][mode][field]) or "N/A" for mode in ("standard", "fast")]
        lines.append(f"| {label} | {cells[0]} | {cells[1]} |")
    lines += ["", "## Interpretation limits", "",
              "No model-quality ranking is inferred from latency. Behavioral quality has not been scored.",
              "Latency/throughput use successful, explicitly attributed requests only; fallback and unknown-model successes are excluded.",
              "Costs cover every executed attempt with reported cost, including failures; missing costs are not zero.",
              "P95 uses linear interpolation and is unstable with small samples. N/A means unavailable.",
              "Provider throughput uses native completion tokens / provider-reported generation time, including reasoning when counted by that provider; it is not visible-text speed.",
              "Cross-model fallback is disabled. Provider fallback remains configurable and actual providers are reported.",
              "The prompts/settings are controlled; provider load, caching, previous generated context, and nondeterminism prevent strict reproducibility.",
              "Follow-up turns are skipped after a failed turn; consult planned/executed counts and trial records.",
              "Metadata lookup time is recorded separately and excluded from response latency.", ""]
    return "\n".join(lines)


def run_benchmark(client, config: AppConfig, repetitions: int, *, scenarios=None, show_responses=False,
                  output=None, source="live", manifest=None) -> dict:
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ValueError("Use between 1 and 100 repetitions.")
    output = sys.stdout if output is None else output
    scenarios = load_scenarios() if scenarios is None else scenarios
    config = replace(config, cross_model_fallback=False)
    manifest = manifest or run_manifest(config, scenarios, repetitions, source=source)
    records, trials = [], []
    status = "completed"
    try:
        for scenario_index, scenario in enumerate(scenarios):
            for repetition in range(repetitions):
                modes = ("standard", "fast") if (scenario_index + repetition) % 2 == 0 else ("fast", "standard")
                for mode in modes:
                    conversation = Conversation(client, config, observer=Observer(config.observability), source=source)
                    conversation.set_mode(mode)
                    trial = {"scenario_id": scenario["id"], "repetition": repetition + 1, "mode": mode,
                             "request_ids": [], "skipped_turns": 0}
                    trials.append(trial)
                    for turn, prompt in enumerate(scenario["turns"]):
                        if show_responses:
                            print(f"\n[{scenario['title']} | {mode} | repetition {repetition + 1} | turn {turn + 1}]", file=output)
                            print(f"Expected: {scenario['expected_behavior']}", file=output)
                        callback = (lambda chunk: print(chunk, end="", file=output, flush=True)) if show_responses else None
                        result = conversation.send(prompt, on_text=callback, cross_model_fallback=False)
                        records.append(result.metrics)
                        trial["request_ids"].append(result.metrics.request_id)
                        if show_responses:
                            print(f"\nAttempt status: {result.metrics.status}", file=output)
                        if conversation.observer.persistence_failed:
                            raise OSError("Cannot persist benchmark request records; check the output directory.")
                        if result.metrics.status != "success":
                            trial["skipped_turns"] = len(scenario["turns"]) - turn - 1
                            if result.metrics.status == "interrupted":
                                raise KeyboardInterrupt
                            break
    except KeyboardInterrupt:
        status = "interrupted"
    return build_report(records, manifest, trials=trials, status=status)


def save_report(report: dict, directory: str | Path) -> None:
    path = Path(directory)
    write_private(path / "results.json", (json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode())
    write_private(path / "summary.md", markdown_summary(report).encode())


def _load_fixture(path: str | Path) -> list[RequestMetrics]:
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = RequestMetrics(**json.loads(line))
            if record.source != "synthetic_fixture":
                raise ValueError("Offline fixtures must explicitly declare source=synthetic_fixture.")
            records.append(record)
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Plan a benchmark offline; --live explicitly permits billable model requests.")
    parser.add_argument("--config", help="Complete TOML configuration path")
    parser.add_argument("--env-file", default=".env")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--live", action="store_true", help="Execute billable requests with cross-model fallback disabled")
    action.add_argument("--fixture", help="Render an explicitly synthetic JSONL fixture offline")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output-dir", help="Private ignored destination; default is a new local/benchmarks run directory")
    parser.add_argument("--show-responses", action="store_true", help="Display synthetic-scenario responses for manual behavioral review; never store them")
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.repetitions <= 100:
        parser.error("--repetitions must be between 1 and 100")
    try:
        config = load_config(arguments.config)
        config = replace(config, cross_model_fallback=False,
                         observability=replace(config.observability, enabled=True))
        scenarios = load_scenarios()
        source = "synthetic_fixture" if arguments.fixture else "live" if arguments.live else "not_executed"
        manifest = run_manifest(config, scenarios, arguments.repetitions, source=source)
        if not arguments.live and not arguments.fixture:
            print(json.dumps(manifest, indent=2))
            print("No requests executed. Configure a private key and explicitly pass --live to run this plan.")
            return 0
        directory = Path(arguments.output_dir) if arguments.output_dir else Path("local/benchmarks") / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
        if arguments.fixture:
            manifest["planned_requests"] = None
            manifest["repetitions"] = None
            manifest["settings"] = None
            manifest["settings_sha256"] = None
            manifest["system_prompt_sha256"] = None
            manifest["scenarios_sha256"] = None
            manifest["schedule"] = "Offline fixture rendering only; no run settings or repetitions are claimed."
            report = build_report(_load_fixture(arguments.fixture), manifest)
        else:
            # Resolve credentials before creating output artifacts or sending requests.
            with OpenRouterClient.from_environment(config, arguments.env_file) as client:
                if directory.exists():
                    raise ValueError("Choose a new output directory to keep separate runs isolated.")
                config = replace(config, observability=replace(config.observability, enabled=True,
                                 jsonl_path=str(directory / "requests.jsonl")))
                print(f"Executing up to {manifest['planned_requests']} billable requests; no application retries or cross-model fallback.")
                report = run_benchmark(client, config, arguments.repetitions, scenarios=scenarios,
                                       show_responses=arguments.show_responses, manifest=manifest)
        save_report(report, directory)
        print(f"Results: {directory / 'results.json'}\nSummary: {directory / 'summary.md'}")
        return 130 if report["status"] == "interrupted" else 0
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError):
        print("Cannot read/write benchmark artifacts or configuration; check paths and the synthetic fixture schema.", file=sys.stderr)
        return 2
