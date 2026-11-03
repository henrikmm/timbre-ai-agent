# Phase 2 offline validation evidence

Executed locally on **2026-11-02**. No live OpenRouter inference, generation-metadata
request, real credential use, or paid benchmark was performed. Public documentation
and model pages were read, and public packages were installed from PyPI.

## Results

| Environment / check | Result |
|---|---|
| Python 3.14.6, editable installation, default offline suite | 82 passed; 4 original-material checks explicitly skipped |
| Python 3.14.6, explicit original-material opt-in | 86 passed; no failures or skips |
| Python 3.11.15, isolated environment using the installed built wheel, explicit original-material opt-in | 86 passed; no failures or skips |
| Official SDK `1.3.107` with in-process HTTP transport and blocked sockets | Streaming, buffered replies, routing/usage, errors, timeouts, metadata, and zero retries passed |
| Editable package installation and `pip check` | Succeeded; no broken requirements |
| `python -m timbre --help` and installed `timbre --help` | Both entry points succeeded without credentials |
| Built wheel loaded outside the source checkout | Default TOML, compact prompt, and all 8 scenarios loaded successfully |
| Wheel publication boundary | No CSV, PDF, database, JSONL, or derived policy catalog included |
| Offline fixture report command | JSON results and English Markdown generated; explicitly marked `synthetic_fixture` |
| Ignore rules | Credentials, request JSONL, benchmark outputs, database, and derived policy catalog excluded |
| Prospective public text scan against local source customer names/phones/emails and order notes | No matches; compared values were not printed |
| `git diff --check` | Passed |

The suite grew from 40 to 86 tests: 46 new Phase 2 tests plus the existing 40.
Two direct SQLite connections in an existing test now close explicitly, removing
Python 3.14 resource warnings without changing production database behavior.

## What the tests establish

The configuration tests exercise defaults, custom models/modes, strict validation,
explicit optional reasoning, fallback request ordering, missing/placeholder keys,
and dotenv precedence without environment mutation. Conversation tests cover
whole-turn trimming/reset/isolation, streaming assembly, partial errors, truncation,
empty responses, timeouts, interruption cleanup, no hidden replay, model attribution,
and post-stream metadata failure isolation.

Timing tests distinguish metadata events, whitespace, visible content, and total
duration with a synthetic monotonic clock. Cost/token summaries retain coverage;
throughput needs matching provider-native counts/timing. JSONL checks verify nulls,
stable serialization, private permissions, failed persistence visibility, and the
absence of synthetic prompts, replies, identities, and credentials. Benchmark tests
verify aggregation, fixture labeling, fallback exclusion, fresh trials, multi-turn
context, skipped follow-ups, explicit live opt-in, and missing-key behavior.

The SDK tests use its real serializer and SSE parser over `httpx.MockTransport`,
not a handwritten approximation of the SDK. All new LLM tests forbid socket
connections. Original-material tests remain local: they compare source data in
temporary databases and complete policy text without sending anything to a model.

## Reproduction

After activating the project environment and installing the package:

```bash
python -m unittest discover -s tests -v
TIMBRE_RAW_DIR=data/raw TIMBRE_POLICIES_PATH=knowledge/policies.json python -m unittest discover -s tests -v
python -m pip check
python -m timbre --help
timbre --help
python scripts/benchmark_models.py
python scripts/benchmark_models.py --fixture tests/fixtures/benchmark_metrics.synthetic.jsonl --output-dir local/fixture-report
git diff --check
```

Original-material checks require authorized local originals and Poppler. The
default suite's four explicit skips are expected, not hidden failed tests.
The temporary Python 3.11 environment and built wheel are validation artifacts,
not additional project dependencies or a committed environment.

## Evidence limits and stopping point

Synthetic timings/costs in fixtures are arbitrary test inputs, never performance
results. These checks do not prove API availability, accepted nested model parameters,
account/provider preferences, semantic context retention, pt-BR fluency, instruction
resistance, real cost, latency, or service privacy. No real conversation transcript
or measured model ranking exists yet.

The implementation stops at private key configuration. Follow the
[live-validation guide](phase2.md) to enter `OPENROUTER_API_KEY` privately, send the
first request, inspect actual-model/provider/usage coverage, review synthetic
scenario responses, and explicitly run comparative benchmarks. Function calling,
real authentication, and LLM access to SQLite/policy retrieval remain Phase 3 work.
