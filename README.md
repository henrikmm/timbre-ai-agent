# Timbre

Timbre is a conversational customer service agent for **Empório da Música**, a
fictional Brazilian musical instrument store, developed for Artefact's AI Engineer
challenge. Phase 1 provides reproducible SQLite data, source-linked store policies,
and controlled read interfaces. Phase 2 adds an observable OpenRouter conversation
engine and terminal CLI. Phase 3A connects that engine to controlled business tools
and structured execution traces. Phase 3B adds a local Streamlit chat over the same
engine. Offline tests need no key or external API.

**Implemented:** streaming conversations, both configured model modes, bounded
transactional history, six read-only business tools, deterministic payment
calculations, deny-by-default order access, private metrics, structured traces,
and Customer/Developer web views. See the [Phase 3B guide](docs/phase3b.md) for the
interface and streaming diagnosis, and the [Phase 3A record](docs/phase3a.md) for backend capabilities,
reproduction commands, and the distinction between offline and live evidence.

Engineering documentation, code, tests, and commit messages use English. Original
CSV values and extracted policy text remain Portuguese. Static CLI/web labels use
English. The shared system prompt follows the customer's language, including
natural Brazilian Portuguese and English, or an explicit language preference.
Scenario explanations and technical annotations remain English.

## Requirements and installation

- Python **3.11+**, with SQLite **3.38+** and its JSON functions.
- Pinned official `openrouter==1.3.107` and `python-dotenv==1.2.2` runtime
  dependencies; tests use `unittest` and the SDK's in-process HTTP test transport.
  Phase 1 data/policy code still uses the standard library.
- **Poppler / `pdftotext`** only to prepare and verify the original PDF catalog.
  Loading prepared JSON needs no PDF dependency.
- `setuptools>=68` is an installation/build dependency, not a runtime dependency.
  Initial editable installation may download it.
- The optional web extra pins **Streamlit 1.66.0**. The CLI remains usable without it.

Run commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/queries.py
```

These tests and examples use **synthetic fixtures** without the supplied materials.
Four original-material tests are explicitly skipped until opted in. For an offline
checkout without installation, use `PYTHONPATH=src`, for example:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Phase 2 SDK tests still require the pinned runtime dependencies to be installed.
They do not need a key and block socket connections for LLM tests.
Install `.[web]` to include the focused Streamlit AppTest checks; otherwise those
checks are explicitly skipped.

Install Poppler if `pdftotext -v` is unavailable:

```bash
# macOS
brew install poppler
# Debian / Ubuntu
sudo apt-get install poppler-utils
```

## OpenRouter setup and CLI

Create/edit credentials **privately**; never paste the key into a conversation:

```bash
cp -n .env.example .env
chmod 600 .env
nano .env
```

Replace the placeholder on the `OPENROUTER_API_KEY=` line in your editor. An exported
shell value takes precedence. Then start the CLI (entering a message sends a
potentially billable request):

```bash
python -m timbre
```

After preparing the local snapshot below, type `Which guitars are available under
R$1,000?`, then `/trace` and `/stats`. Ordinary greetings need no business tool.
Offline success does not prove current provider availability, credentials, model
behavior, or API cost. Live findings are recorded separately in the
[Phase 3A guide](docs/phase3a.md).

| Command | Behavior |
|---|---|
| `/help` | List commands |
| `/mode` | Show current requested mode/model |
| `/mode standard` | Select `deepseek/deepseek-v4.1-flash-1017` with default routing |
| `/mode fast` | Select `reflection/beam-1.0-501b-a23b` with latency-prioritized routing |
| `/clear` | Reset history, keeping system instructions/session statistics |
| `/stats` | Show observed session metrics and cost coverage |
| `/debug on`, `/debug off` | Enable/disable sanitized execution details |
| `/trace` | Show the latest turn's structured execution trace |
| `/exit` | Close the session |

Mode switching preserves history and can affect interpretation of earlier context.
The versioned [TOML settings](src/timbre/resources/default.toml) configure models,
streaming, history, timeouts, optional reasoning, provider preferences, and
cross-model fallback. Pass `--config local/timbre.toml` for a custom complete file.
Reasoning/sampling parameters are omitted by default; unsupported optional settings
are rejected explicitly. Provider fallback and cross-model fallback are separate;
actual-model differences are recorded and announced. The `[tools]` table adds
local database/policy paths and bounded execution limits. See the
[Phase 3A guide](docs/phase3a.md); the [Phase 2 guide](docs/phase2.md) records the
original provider configuration and historical validation procedure.

## Local web interface

Use the same prepared snapshot and private `.env` as the CLI. From the repository
root, with the virtual environment active:

```bash
python -m pip install -e '.[web]'
streamlit run app.py
```

Open [the local interface](http://127.0.0.1:8501). The versioned Streamlit config
binds to loopback, disables usage telemetry, and selects a charcoal/teal dark theme.
The interface is intended for a local demonstration. It has no production login
or deployment controls; do not expose it as an unauthenticated public service.

The server chooses its presentation at startup. There is no Customer/Developer
switch in the page and URL parameters cannot enable diagnostics:

```bash
# Customer (default), on port 8501
streamlit run app.py
# Developer, optionally alongside Customer on another port
TIMBRE_WEB_VIEW=developer streamlit run app.py --server.port 8502
```

Customer shows native chat, streaming text, Standard/Fast response choices, and
**New chat**. Model selection preserves context; reset clears visible/model history
and pending attempts while retaining session metrics. Internal model IDs, technical
status, language-adaptation slogans, and blanket data warnings are absent. Static
interface labels remain English. Markdown escapes literal `R$` currency markers
for display without rewriting the recorded response. No product images or invented
product cards are added.

Developer receives the same engine's sanitized events **during execution** through
`Conversation.send(on_event=...)`. A live activity panel shows catalog/policy/payment
calls, in-progress/completed/denied states, result counts, sources, and durations.
It summarizes actual returns; it does not expose raw tool result bodies. Detailed
per-turn metrics and expandable events remain below the conversation. No SQL,
private rows, system prompt, hidden reasoning, identity override, or extra business
permission is exposed. Both servers remain unauthenticated local demonstrations;
private order access is still denied by the backend.

End-to-end latency includes metadata lookup; answer-available latency and individual
operation times are identified separately. Missing cost/tokens/provider values use
`N/A`, with cost subtotals and coverage labelled explicitly. Nested event durations
overlap and must not be summed into customer wait time.

The web app calls `Conversation.send(on_text=..., on_event=...)` exactly once per submitted turn.
`st.session_state` holds that backend instance, presentation records, pending input,
model selection, startup view, and returned trace references. Display records never become
a second LLM message history. Controls are disabled while a request executes.
Failed partial text is labelled incomplete, kept for inspection, and excluded
from backend history. **Retry last message** makes a separate explicit attempt;
it never concatenates responses or retries automatically. Provider/network failures,
deadlines, token limits, and tool limits can still interrupt a response.

The shared output budget is now **2,048 tokens per model call**, including reasoning
and tool-call output. This corrects an observed 512-token truncation; it does not
guarantee completion. See the [diagnosis and validation record](docs/phase3b.md).

For trusted custom paths/settings, set `TIMBRE_CONFIG` to a complete TOML file and
optionally `TIMBRE_ENV_FILE` to a private dotenv path before launch. They are read
at session creation; reload the page after changing them. A browser reload/new tab
starts a new in-memory session. Closing/restarting the server loses chat history;
only sanitized local metrics/events persist. Developer activity is streamed; final
metrics and the detailed trace are shown after execution. Provider latency and
model answer quality can still vary. Fast now uses Beam 1.0; see the dated
[model-selection evidence](docs/fast-model-selection.md) and
[refinement validation](docs/phase3b-refinement.md).

The adopted [customer service decisions](docs/decisions/010-customer-service-decisions.md)
resolve contact alternatives, installment tiers, the local free-shipping boundary,
return channels, campaign selection, and product field precedence. The backend
returns resolved policy data alongside source evidence; original CSVs and Portuguese
policy text are unchanged. Customer replies give the useful conditions/next step
without narrating internal discrepancies. Source limitations and production handoff
stay in engineering documentation; unsupported actions and failed lookups still
receive truthful, concise answers.

## Observability and benchmarking

The dedicated observer records anonymous IDs, requested/actual model, provider,
monotonic first-event/first-visible-text/total timing, available usage/reasoning/
cache tokens, reported cost, coverage, fallback, and safe reliability outcomes.
Missing values remain null. Content-free, owner-only JSONL defaults to ignored
`local/requests.jsonl`. No prompts, replies, customer data, keys, or upstream error
bodies are logged. See the [stable schema and limitations](docs/observability.md).

Each interaction aggregates its model calls without adding cumulative usage
snapshots twice. Tool time is measured separately, and traces correlate the
session, turn, model request, and tool-call spans. Free text arguments, private
order identifiers/results, prompts, and replies are excluded from trace metadata.
Metadata retrieval is bounded. Throughput requires matching provider-native counts
and generation timing; missing measurements remain unavailable.

```bash
# Offline plan, no credentials or inference
python scripts/benchmark_models.py
# Offline report demonstration, explicitly synthetic
python scripts/benchmark_models.py --fixture tests/fixtures/benchmark_metrics.synthetic.jsonl --output-dir local/fixture-report
# Optional legacy benchmark: 54 interactions, up to 270 model generations at default tool limits
python scripts/benchmark_models.py --live --repetitions 3
```

The eight synthetic scenarios cover identity, natural pt-BR, tone, multi-turn
context, unverified prices, unauthenticated orders, accessories, and instruction
override. Live reports contain JSONL, JSON results, and an English Markdown summary
under a unique ignored `local/benchmarks/` directory. Comparative runs disable
cross-model fallback; fallback/unknown attribution cannot masquerade as selected-
model latency. P95 is unstable with small samples. Quality is not inferred from
speed; use `--show-responses` for manual behavioral review. This existing Phase 2
benchmark infrastructure is retained; Phase 3A does not add a formal evaluation
suite or a large benchmark campaign. Its scenarios retain their original pt-BR
inputs and pre-tool expectations, so they are not Phase 3A quality evidence.
The runner's legacy `planned_requests` field counts interactions; each interaction
can make up to `tools.max_iterations + 1` model generations. The example above can
therefore issue up to 270 generations at the default limit, and is not required
for the bounded Phase 3A smoke checks.

## Architecture & Design Decisions

The layers are terminal presentation → per-session conversation state → normalized
LLM events → isolated SDK adapter. The conversation loop dispatches validated
calls through an allowlisted executor to the existing SQLite repositories and
policy catalog. The existing observer collects per-turn metrics and typed trace
events independently of terminal printing. The [architecture](docs/architecture.md)
describes data access, history, authorization, and provider boundaries.

- [ADR-001: SQLite for Operational Data](docs/decisions/001-sqlite-operational-data.md)
- [ADR-002: Structured Policy Retrieval](docs/decisions/002-structured-policy-retrieval.md)
- [ADR-003: Customer Data Access and Security](docs/decisions/003-customer-data-security.md)
- [ADR-004: OpenRouter and Model Strategy](docs/decisions/004-openrouter-model-strategy.md)
- [ADR-005: Observability and Benchmarking](docs/decisions/005-observability-benchmarking.md)
- [ADR-006: Function Calling Architecture](docs/decisions/006-function-calling-architecture.md)
- [ADR-007: Tool Design and Business Rules](docs/decisions/007-tool-design-business-rules.md)
- [ADR-008: Execution Tracing](docs/decisions/008-execution-tracing.md)

Phase 1 records describe inspected implementation decisions retrospectively.
Phase 2 validation reports are historical snapshots. Phase 3A evidence is recorded
in its [operation and validation guide](docs/phase3a.md); targeted smoke tests do
not establish a comparative model ranking.

## Prepare the supplied snapshot locally

Original materials are intentionally excluded from Git. Obtain authorized copies
and keep the supplied directory locally, for example in `Material_suporte/`.
The preparation script searches recursively and requires exactly one of each:

```text
desafio_tecnico_ai_eng_artefact.pdf
políticas_da_loja.pdf
desafio_tecnico_ai_eng - categories.csv
desafio_tecnico_ai_eng - products.csv
desafio_tecnico_ai_eng - customers.csv
desafio_tecnico_ai_eng - orders.csv
desafio_tecnico_ai_eng - order_items.csv
desafio_tecnico_ai_eng - promotions.csv
```

It reports missing or ambiguous files instead of inventing replacements. All eight
files are present in the local materials supplied for this implementation.

```bash
python scripts/prepare_data.py --source-dir Material_suporte
python scripts/import_data.py --report local/import_report.json
python scripts/prepare_policies.py
python scripts/validate_snapshot.py --expect-supplied-snapshot --report local/validation_report.json
```

Preparation copies the original bytes into `data/raw/`; it does not translate or
modify the supplied files. The database is `data/store.db` and the policy catalog
is `knowledge/policies.json`. These artifacts are ignored by Git and written with
owner-only file permissions. Keep the working directory private.

If the six CSVs are already in `data/raw/`, copying is unnecessary. The importer
accepts original names or canonical names such as `products.csv`; having both for
a table is an error. All scripts accept path arguments (`--help`). No source edits
or credentials are needed for data preparation. OpenRouter credentials apply only
to live conversation/benchmark execution, independently of these maintenance steps.

Re-running the import **replaces the complete six-table snapshot** in a single
transaction. Failure leaves the prior snapshot intact. Use a dedicated Timbre
database: imports refuse unrelated tables and unsupported schema versions. This
maintenance operation is never a future customer tool.

## Verified snapshot results

| Source table | Imported records |
|---|---:|
| `categories` | 9 |
| `products` | 65 |
| `customers` | 50 |
| `orders` | 20 |
| `order_items` | 22 |
| `promotions` | 25 |
| **Total** | **191** |

Local validation on **2026-11-02** passed SQLite integrity and foreign-key checks.
It found **61 sellable products**, **4 flagged and sellable promotions**, and **29
policy records from all 8 manual pages**. These observations describe the supplied
snapshot; they are not permanent limits or live inventory claims.

Original-material tests compare every CSV field with its stored equivalent,
re-import the snapshot, and compare every non-header PDF text line with the policy
records in source order. See [validation evidence](docs/validation.md) for commands
and final test results. To opt in explicitly after preparing authorized originals:

```bash
TIMBRE_RAW_DIR=data/raw TIMBRE_POLICIES_PATH=knowledge/policies.json python -m unittest discover -s tests -v
```

`TIMBRE_RAW_DIR` enables CSV checks; `TIMBRE_POLICIES_PATH` enables policy checks.
The full PDF text-coverage check additionally requires both variables and Poppler.

## Query examples

After local preparation:

```python
from timbre.database.repositories import CatalogRepository
from timbre.knowledge import get_store_policy

catalog = CatalogRepository("data/store.db")
products = catalog.search_products("violao", max_price_brl="1000", limit=20)
categories = catalog.list_categories()
product = catalog.get_product_details(81)
promotions = catalog.get_active_promotions(product_id=81)
returns = get_store_policy("returns")
online_returns = get_store_policy("returns.online", include_related=True)
```

Money and percentages are returned as `Decimal`. Use strings, integers, or
`Decimal` for exact repository price filters; floats are rejected by that API.
The JSON tool adapter serializes monetary decimals as strings. Product searches are
accent-insensitive, parameterized, paginated, and escape literal SQL `LIKE`
metacharacters. They do not search customer records.

Search defaults require `status == "active"` **and** positive recorded stock.
Details can describe an unavailable product with `available=False`. Promotions
must be flagged active and reference a sellable product. The result includes
original price and percentage. The payment tool derives prices from trusted data,
uses exact decimal calculations, prevents discount stacking, and reports unresolved
policy/campaign conditions rather than granting unsupported commercial permission.

```python
from timbre.authorization import AccessDenied
from timbre.database.repositories import OrderRepository

try:
    OrderRepository("data/store.db").get_order_for_customer(
        1, context={"customer_id": 1}
    )
except AccessDenied:
    print("Private access denied: a claimed ID is not authentication.")
```

The default denies **all** private calls, including supplied names, phone numbers,
order numbers, dictionaries, or simulated test sessions. A future backend must
inject a real `CustomerAuthorizer` and bind an opaque verified session outside
model arguments. There is no `customer_id` override in a query. The isolated issuer
in `tests/support.py` is test-only, not production authentication.

## Architecture and directory structure

```text
Material_suporte/             # ignored original delivery
data/                        # ignored raw files and store.db
knowledge/
  README.md
  policies.json              # generated, ignored
  policy_notes.md            # detailed local review, ignored
src/timbre/
  authorization.py           # backend contract and deny-all default
  local_files.py             # private atomic artifact writes
  config.py                  # strict TOML and explicit private dotenv loading
  conversation.py            # bounded transactional in-memory turns
  observability.py           # per-turn metrics, typed traces, private JSONL
  cli.py, __main__.py         # terminal presentation and entry point
  web.py, presentation.py    # session display state and shared static errors
  benchmark.py               # controlled scenarios and honest reports
  llm/                       # provider-neutral tool deltas and official SDK adapter
  tools/                     # allowlist, validation, business reads and exact payments
  resources/                 # packaged TOML, compact prompt, synthetic scenarios
  database/
    connection.py            # internal read-only/writer connections
    schema.py                # six tables and indexes
    values.py                # exact money/percentage conversion
    import_data.py           # transactional snapshot replacement
    repositories.py          # catalog and private order status reads
  knowledge/
    extraction.py            # local PDF-to-section preparation
    policy_loader.py         # catalog validation and topic retrieval
scripts/                     # preparation, import, validation, benchmark entry point
app.py                       # native Streamlit chat and sanitized trace presentation
.streamlit/config.toml       # local-only server and dark theme
tests/
  fixtures/                  # synthetic CSVs and policy JSON
  support.py                 # isolated test-session simulation
  test_*.py
examples/                    # runnable synthetic query examples
docs/                        # model, architecture, policies, evidence
local/                       # ignored generated reports
AGENTS.md                    # project language and access conventions
.env.example
.gitignore
pyproject.toml
README.md
```

Source preparation, storage, policy retrieval, and access checks are separate.
There is no generic SQL interface intended for an LLM. Read the
[data model](docs/data_model.md), [architecture and security boundaries](docs/architecture.md),
[complete policy map](docs/policy_catalog.md), and
[ambiguities and deterministic rule plan](docs/policy_review.md).

## Facts, decisions, and unresolved assumptions

**Provided facts:** CSV schemas and values, statuses, campaign flags, and the
Portuguese manual with source references. The challenge PDF requires Python, a
public Git history, README justifications, AI-assistance disclosure, and eventual
agent conversation examples. English submission requirements were relayed from
the recruitment instructions by the project owner; the PDF does not itself state
that language requirement.

**Project decisions:** standard-library data/policy foundation; integer cents and percentage
basis points; a composite item key verified against source rows; atomic snapshot
replacement; specialized read repositories; fail-closed private access; and local
JSON policies instead of embeddings; a small official SDK adapter; transactional
conversation history; and content-free observability. No agent framework is needed.

**Source issues and adopted decisions:** contacts, installment wording, freight
threshold equality, absent campaign dates, and conflicting product fields are
recorded in the [review](docs/policy_review.md). The owner-authorized
[decision register](docs/decisions/010-customer-service-decisions.md) defines the
demonstration's service behavior. Detailed source values stay in ignored
`knowledge/policy_notes.md`; no original source is corrected. Historical charges,
real contact deliverability, live campaign data, and legal/compliance claims remain
production verification matters.

## Security and publication

Catalog/category data, specifications, commercial availability, snapshot promotions,
and service policies are public business information. Customer records, individual
orders, tracking codes, and notes are restricted. Order status projections omit
names, phones, email, city, notes, payment details, and customer identifiers.

SQLite stores both classes. File possession or arbitrary Python/SQL execution
bypasses these application interfaces; **the database is not an authorization
barrier**. The future backend must verify sessions and expose only allowlisted
methods/results. Read-only connections prevent accidental writes, not arbitrary
reads by someone who can open the file.

`.gitignore` excludes supplied materials, `data/`, derived policy text and notes,
PDFs, non-fixture CSVs, databases, `.env` files, and common secrets. Only synthetic
fixture CSVs are permitted. Never force-add restricted artifacts. Ignoring a file
does not remove it from earlier commits. Inspect the tree and history:

```bash
git ls-files
git log --all --name-only --format=
git check-ignore Material_suporte data/store.db knowledge/policies.json knowledge/policy_notes.md .env
```

The public repository contains code, English documentation, and synthetic fixtures.
Original materials and restricted derivatives stay local. Review redistribution
rights before publishing original or derived manual content. Submission email is
outside this phase.

## Limits and next steps

The local snapshot is historical business data, not live inventory or a transport
integration. Active campaign flags are adopted as the demonstration offer catalog,
not proof of real-world validity or eligibility. Internal source issues remain
documented; payment results cannot authorize a sale, reservation, charge, refund,
or policy exception. Initial Fast-mode return
and payment checks reached a tool but timed out at the default 45-second interaction
budget; see the validation record before assuming this budget fits every workflow. Production authentication
is absent and public CLI sessions cannot retrieve private orders.

Model tool selection and answer quality remain probabilistic; backend validation,
read-only queries, calculation, and authorization provide independent controls.
Context and trace buffers are bounded and local, with no persistent customer
history. This phase adds no separate API/WhatsApp interface, inventory mutation,
transaction processing, or formal quality evaluation suite.

Phase 3B provides a local Streamlit interface over these actual trace events. Phase 4
systematic evaluation has not started. Before real customer
use, resolve the production data-processing, authentication, retention, and policy
requirements in the [Phase 3A guide](docs/phase3a.md).

## AI assistance

OpenAI Codex was used to inspect local materials and the existing implementation,
implement/review Phase 1 data and policy code, verify public SDK/model documentation,
build the conversation/CLI/observability layers, implement Phase 3A function
calling and controlled business tools, add the Streamlit presentation and streaming
diagnostics, create synthetic tests, run validation,
and write the README and ADRs. The project owner
supplied scope, security boundaries, model choices, and language conventions.
No agent framework was added to the application. Automated and live evidence
are distinguished explicitly; business interpretations, data-processing suitability,
and production authentication still need human review.
