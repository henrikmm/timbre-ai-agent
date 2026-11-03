# Phase 2 completion report

**Implementation complete; offline validated; live inference not executed.**
The stopping point is private `OPENROUTER_API_KEY` configuration. No real key was
created, inspected, or used. No operational data was sent to a model.

## Files created or modified

All paths below are repository-relative; generated private artifacts are separate.

| Change | Files |
|---|---|
| Modified project setup | `pyproject.toml`, `.env.example`, `.gitignore` |
| Modified existing documentation | `README.md`, `docs/architecture.md` |
| Modified test cleanup | `tests/test_database.py` (close two test SQLite connections) |
| New conversation/configuration/presentation | `src/timbre/config.py`, `src/timbre/conversation.py`, `src/timbre/cli.py`, `src/timbre/__main__.py` |
| New provider boundary | `src/timbre/llm/__init__.py`, `src/timbre/llm/types.py`, `src/timbre/llm/openrouter.py` |
| New observability and benchmarking | `src/timbre/observability.py`, `src/timbre/benchmark.py`, `scripts/benchmark_models.py` |
| New packaged resources | `src/timbre/resources/default.toml`, `src/timbre/resources/system_prompt.md`, `src/timbre/resources/benchmark_scenarios.json` |
| New offline test support/fixtures | `tests/llm_support.py`, `tests/fixtures/benchmark_metrics.synthetic.jsonl` |
| New test modules | `tests/test_llm_config.py`, `tests/test_conversation.py`, `tests/test_openrouter_adapter.py`, `tests/test_observability.py`, `tests/test_benchmark_cli.py` |
| New operating/evidence documentation | `docs/phase2.md`, `docs/observability.md`, `docs/phase2_validation.md`, `docs/phase2_completion.md` |
| New decision records | `docs/decisions/001-sqlite-operational-data.md`, `002-structured-policy-retrieval.md`, `003-customer-data-security.md`, `004-openrouter-model-strategy.md`, `005-observability-benchmarking.md` |

The only generated repository-local report is under ignored
`local/phase2-fixture-report/`; it is explicitly synthetic. Original CSV/PDF bytes,
production data/policy code, deny-all authorization, and the private snapshot remain
unchanged. The package version is `0.2.0`; changes are available in the working tree.

## Implemented architecture

The CLI delegates to a per-session conversation engine, which consumes normalized
LLM events from the official OpenRouter adapter. A dedicated observer handles
monotonic measurement, structured JSONL, and session summaries. Benchmark trials
reuse that engine/observer. The provider SDK is pinned to `1.3.107`; dotenv parsing
is pinned to `1.2.2`. TOML uses the standard library. No framework or second SDK
adapter was introduced.

Standard defaults to `deepseek/deepseek-v4.1-flash-1017` with default provider
routing. Fast uses `openai/gpt-oss-120b` with latency sorting. `/mode` reports the
selection; `/mode standard` and `/mode fast` preserve history. Provider fallback
and optional cross-model fallback are distinct. Actual-model changes are recorded
and announced, and comparative benchmarks disable cross-model fallback. Optional
reasoning is omitted by default and must satisfy a declared supported-effort contract.

The CLI progressively flushes content, filters hidden reasoning, and commits one
assembled assistant message only after successful completion. Empty, truncated,
failed, or interrupted turns cannot pollute history. Mode changes retain context,
reset retains system instructions, and trimming removes whole oldest turn pairs.
There are no persistent customer sessions or database tools.

## Metrics and limitations

The [schema](observability.md) covers request/session/routing identity, first event,
first visible text, total/streaming/provider timing, available usage/reasoning/cache
counts, API cost and observed cumulative session cost, retry/fallback outcomes,
timeouts, failures, and incomplete streams. Raw JSONL excludes content and secrets.
Missing values remain null, with sample/cost/token coverage in summaries.

One optional short metadata lookup occurs after streaming and outside measured
response latency. Provider throughput is calculated only from matching native
completion counts and provider generation time; defaults may leave it unavailable.
It can include reasoning and is not visible-text speed. Cost totals may undercount
unreported charges. Model/provider availability, account routing, actual parameter
acceptance, behavior, and performance await live validation. Synchronous transport
timeouts are not strict end-to-end real-time deadlines.

## Validation and documentation

The standard offline run passes **82 tests with 4 documented original-material
skips**. Explicit original opt-in passes **all 86 tests** on Python **3.14.6** and
**3.11.15**, including the real SDK over a blocked-socket in-process HTTP transport.
Editable installation, dependency checks, CLI entry points, wheel resources,
synthetic report generation, ignore rules, public-value scans, and diff checks
passed. Detailed results are in [validation evidence](phase2_validation.md).

The five [ADRs](../README.md#architecture--design-decisions) document SQLite,
structured JSON policy retrieval, data access/security, OpenRouter/model strategy,
and observability/benchmarking. Phase 1 rationale is explicitly retrospective;
Phase 2 model choices are hypotheses, with no fabricated benchmark conclusions.
The README now covers installation, modes/commands, observability, benchmarks,
architecture links, limits, Phase 3, and AI-assistance disclosure. The
[operation guide](phase2.md) provides the detailed configuration and privacy contract.

## Exact private live-validation steps

From the repository root:

```bash
source .venv/bin/activate
cp -n .env.example .env
chmod 600 .env
nano .env
```

Privately replace the placeholder on `OPENROUTER_API_KEY=` in the editor; an exported
shell variable takes precedence. Never paste the key into a conversation. Then:

```bash
python -m timbre
```

Enter `Oi! Quem é você e como pode me ajudar?`, then `/stats`, `/mode`, and `/exit`.
Check the actual-model/provider fields and available usage/cost in the private
JSONL record. That successful request is the first live integration proof.

Inspect the plan offline before explicitly authorizing inference yourself:

```bash
python scripts/benchmark_models.py
python scripts/benchmark_models.py --live --repetitions 1 --show-responses
python scripts/benchmark_models.py --live --repetitions 3
```

The first comparative run plans up to 18 inference requests, the second up to 54;
failed first turns skip their follow-ups. Reports remain in ignored unique
`local/benchmarks/` directories. P95 is unstable with small samples. Review actual
answers against the English scenario expectations; no automatic quality scoring
or quality ranking is claimed.

## Phase 3 work

Design function-calling contracts, real backend identity verification, allowlisted
SQLite/policy reads, reviewed deterministic commercial rules, and tool spans.
Resolve the recorded policy ambiguities, add operational/quality evaluations, and
review external data processing before real customer use. SQL access by the LLM,
authentication, tools, web/API/WhatsApp interfaces, commercial actions, and database
mutations have not been introduced in Phase 2.
