# Phase 2: configuration, operation, and live validation

The conversational infrastructure is implemented and tested offline. **No live
OpenRouter inference or paid benchmark has been executed.** SDK transport fixtures
prove local request/response handling, not credential validity, current provider
availability, response quality, real latency, or billed cost.

## Installation and private credentials

From the repository root with Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

The direct dependencies are the official `openrouter==1.3.107` SDK and
`python-dotenv==1.2.2` for a standard dotenv parser. Tests use `unittest`; the SDK's
transitive `httpx` dependency supplies an in-process test transport. SQLite and
structured policy functionality still use the standard library. No framework,
second provider SDK, embeddings, server, or web UI is added.

Create a private dotenv file without replacing an existing one:

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

Replace the placeholder on the `OPENROUTER_API_KEY=` line privately in your editor.
Never paste the key into a chat, shell command/history, screenshot, report, or Git.
Alternatively export that variable privately through your own secret-management
workflow. An existing shell value wins over `.env`, even if blank; remove an old
export when intending to use the file. No real key/file is created by Phase 2.

Only the key is read from the explicitly selected file (default `.env` in the
working directory); the application does not search parent folders, expand dotenv
interpolation, or mutate process environment variables. `--env-file PATH` selects
another private file. Missing/placeholder credentials fail clearly at startup,
while tests, help, and an offline benchmark plan require no key.

## Configuration and modes

The packaged, version-controlled configuration is
[`default.toml`](../src/timbre/resources/default.toml). To customize it:

```bash
mkdir -p local
cp src/timbre/resources/default.toml local/timbre.toml
nano local/timbre.toml
python -m timbre --config local/timbre.toml
```

| Mode | Initial model | Provider sort |
|---|---|---|
| Standard (default) | `deepseek/deepseek-v4.1-flash-1017` | Omitted: OpenRouter default balanced routing |
| Fast | `openai/gpt-oss-120b` | `latency` |

Model IDs and mode settings require no source edit. Both initial IDs were verified
against their official public model pages on 2026-11-02, not by inference. Provider
availability and account preferences still need live validation. High throughput
does not guarantee low TTFT or low total latency.

Shared settings include streaming (default true), 45-second transport timeout,
512-token output budget, 12-turn history limit, provider fallback, required
parameter support, data-collection preferences, and observability. Unknown fields,
invalid types/ranges, unsupported declared effort, and content logging fail explicitly.

Optional sampling parameters are not sent. `reasoning_effort="default"` omits the
reasoning object for both models rather than forcing the conceptual brief's `low`
onto every model/provider. Fast supports opt-in `low`, `medium`, or `high` from its
reviewed allowlist; Standard has no assumed effort contract. If changing a model
ID, independently review and update its effort allowlist before enabling reasoning.
The allowlist is an explicit operator declaration, not live capability discovery.
Non-default effort must be supported by every candidate in an enabled fallback
request or it is rejected before sending. Use `cross_model_fallback=false` to test
Fast-specific effort. The gateway's `require_parameters=true` further restricts
providers and exposes unsupported request settings as errors. Nested effort values
and provider/account behavior still require live verification.

The output budget can include hidden reasoning, so a small budget can end with
`length` and little/no visible text. Such attempts are incomplete, may be billed,
and never enter successful history. Increase the budget or change a supported
effort explicitly when live evidence warrants it.

## CLI and first live request

**The following step performs external, potentially billable inference when you
enter a message. Run it yourself after configuring your key.**

```bash
python -m timbre
# Equivalent installed console command: timbre
```

Type `Oi! Quem é você e como pode me ajudar?` (English: “Hi! Who are you and how can
you help me?”). Then use `/stats` to inspect observed counts, timing, cost coverage,
and providers. `/mode` shows the requested mode/model. Inspect the ignored JSONL
record for `actual_model`, fallback, finish status, and available usage. Missing
metrics remain null; a successful CLI response is the first live integration proof.

| Command | Behavior |
|---|---|
| `/help` | List commands |
| `/mode` | Show requested mode/model |
| `/mode standard`, `/mode fast` | Switch models, preserving history |
| `/clear` | Reset history and retain system instructions/session statistics |
| `/stats` | Show content-free session statistics |
| `/exit` | Close the CLI |

Changing models mid-conversation can change interpretation of previous context.
History is private in-memory state per `Conversation`; no persistent conversation
database exists. The limit counts complete user/assistant turns, including the
current pending turn. Oldest complete pairs are dropped together; the system
message remains first. Empty inputs create no request. Failed pending turns are
rolled back, so an explicit retry cannot duplicate an abandoned user entry.

The SDK streams content to a callback; the CLI flushes fragments immediately.
Only one assembled assistant message is committed after a non-empty terminal
`stop` and normal stream exhaustion. Hidden reasoning is never displayed or saved.
Ctrl+C during generation closes the stream, records interruption, and returns to
input. Partial errors are marked incomplete; there is no automatic replay or
concatenated alternate answer. Ctrl+C at the input prompt exits the session.

Timeouts apply to SDK transport operations, with an elapsed-time check between
decoded events. This synchronous implementation is not a strict real-time deadline:
an in-progress transport operation can consume its own timeout after the local
budget was nearly exhausted. SDK/application retries are disabled. OpenRouter may
still make multiple provider/model attempts before its single response; available
router metadata records those separately.

## Fallback and privacy

Manual mode selection changes the requested model for the next turn. Provider
fallback can select another endpoint serving that model. Cross-model fallback is
separately controlled by `llm.cross_model_fallback`; when enabled it supplies an
ordered `models` list, selected model first, other configured model second.
The selected mode's routing/optional parameters apply to the whole fallback list.
An actual-model mismatch is recorded and announced after streaming. Missing model
identity stays unknown; it is never reported as proof that the requested model ran.

Defaults request `data_collection="deny"`; `routing.zdr=true` additionally restricts
eligible endpoints. Tight preferences may leave no available provider. These
controls and open weights do not imply local processing or a privacy/compliance
guarantee. Interactive text is sent to OpenRouter/external inference providers;
use synthetic conversations for initial validation. No database, customer records,
orders, full policy manual, or private local files are placed in model context.

The versioned [system prompt](../src/timbre/resources/system_prompt.md) summarizes
identity/scope/style and explicitly limits information access. Its source review
covered manual v2.1 §§1/1.1 (p.2), §§7.1–7.3 (pp.6–7), §9 (pp.7–8), and §10 (p.8).
It excludes conflicting contacts and commercial terms. General instrument guidance
is permitted; current prices, stock, promotions, order checks, and commercial
actions cannot be invented. Prompt instructions guide behavior but are not a
backend authorization mechanism or a guarantee of live model compliance.

## Observability

See the [stable schema and measurement limits](observability.md). JSONL is ignored
and content-free by default. `/stats` uses observed values and coverage. Missing
metrics are null, and cost totals may undercount requests whose cost was unavailable.
Lookup failures are non-fatal and no upstream exception body is exposed.

`generation_metadata="missing"` limits monitoring to one post-response lookup only
when requested provider/cost information is missing. For a controlled investigation
of provider-reported timing and native-token throughput, explicitly choose
`generation_metadata="always"` in a custom config. `"off"` makes no metadata calls.
The default can therefore leave throughput/provider timing unavailable even when
the generation endpoint might supply it. Lookup duration is separate from response
latency, and reasoning-inclusive provider throughput is not visible-text speed.

## Comparative benchmark

First inspect the offline plan; it reads no key and sends no requests:

```bash
python scripts/benchmark_models.py
```

Eight synthetic scenarios cover identity, pt-BR, tone, context, unverified pricing,
unauthenticated order requests, accessories, and instruction overrides. English
titles/expectations/translations are packaged in
[`benchmark_scenarios.json`](../src/timbre/resources/benchmark_scenarios.json).
Each repetition contains nine turns per mode. Three repetitions plan **up to 54
inference requests**; follow-ups are skipped if a preceding turn failed.

Only after private credential setup, explicitly run live inference:

```bash
# Small first comparative run: up to 18 inference requests
python scripts/benchmark_models.py --live --repetitions 1 --show-responses
# Multiple repetitions: up to 54 inference requests
python scripts/benchmark_models.py --live --repetitions 3
# Custom routing/reasoning/metadata settings
python scripts/benchmark_models.py --live --repetitions 3 --config local/timbre.toml
```

The runner always disables cross-model fallback and enables content-free raw JSONL
for traceability; it does not change provider fallback/privacy preferences. It
alternates first-mode order and starts fresh sessions per scenario/repetition/mode.
Customer prompts match; model-generated earlier answers can make later context
differ. Defaults omit model-specific reasoning, so provider default reasoning can
also differ. These are controls for a useful comparison, not strict reproducibility.

A unique ignored `local/benchmarks/<run>/` contains `requests.jsonl`, `results.json`,
and `summary.md`. `--output-dir PATH` chooses a fresh private destination. Results
include settings, prompt/scenario hashes, SDK/Python versions, Git revision/dirty
state, per-trial request IDs, skipped turns, and aggregate measurements/coverage.
P95 is unstable with small samples. Costs include known failed-attempt costs;
latency/throughput exclude successful fallback or unknown-model results.

`--show-responses` displays synthetic-scenario answers in the terminal for manual
review against expectations, without saving text. Timing does not score quality,
Portuguese fluency, or safety. Do not claim behavioral validation until actual
answers have been reviewed. Interrupted runs save partial reports with explicit
status. Raw reports remain local; publish only a deliberately reviewed, sanitized
English summary with evidence source and missing-data limitations preserved.

The report pipeline can also be exercised entirely offline:

```bash
python scripts/benchmark_models.py --fixture tests/fixtures/benchmark_metrics.synthetic.jsonl --output-dir local/fixture-report
```

Its outputs state **synthetic_fixture** and are not API benchmark measurements.

## Phase 3 boundary

The engine and provider adapter do not import database/policy repositories and do
not send tools or function schemas. Phase 3 must design explicit tool contracts,
backend identity verification, allowlisted operational reads, reviewed deterministic
business rules, tool spans, and richer quality evaluations. It must resolve existing
policy ambiguities before commercial calculations. Web/API/WhatsApp channels,
persistent customer conversations, and commercial mutations remain outside this
implementation. No placeholder tool is presented as a working integration.
