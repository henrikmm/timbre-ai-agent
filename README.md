# Timbre

Timbre is the foundation of a customer service agent for **Empório da Música**, a
fictional Brazilian musical instrument store, developed for Artefact's AI Engineer
challenge. Phase 1 provides reproducible SQLite data, source-linked store policies,
and controlled read interfaces. Queries and tests need no LLM or external API.

**Implemented:** atomic CSV import, six related tables, public catalog queries,
private order status queries that deny access by default, structured policy
retrieval, and offline tests. The conversational agent is a later deliverable.

Engineering documentation, code, tests, and commit messages use English. Original
CSV values and extracted policy text remain Portuguese. Future customer-facing
conversations will use Brazilian Portuguese (pt-BR), with English scenario
explanations and translations where needed for evaluators.

## Requirements and installation

- Python **3.11+**, with SQLite **3.38+** and its JSON functions.
- No third-party Python runtime or test dependencies. Tests use `unittest`.
- **Poppler / `pdftotext`** only to prepare and verify the original PDF catalog.
  Loading prepared JSON needs no PDF dependency.
- `setuptools>=68` is an installation/build dependency, not a runtime dependency.
  Initial editable installation may download it.

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

Install Poppler if `pdftotext -v` is unavailable:

```bash
# macOS
brew install poppler
# Debian / Ubuntu
sudo apt-get install poppler-utils
```

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
or credentials are needed. `.env.example` documents that no provider integration
or dotenv reader exists in this phase.

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
and final test results.

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
`Decimal` for exact price filters; floats are rejected. A future JSON tool adapter
should serialize monetary decimals as strings. Product searches are
accent-insensitive, parameterized, paginated, and escape literal SQL `LIKE`
metacharacters. They do not search customer records.

Search defaults require `status == "active"` **and** positive recorded stock.
Details can describe an unavailable product with `available=False`. Promotions
must be flagged active and reference a sellable product. The result includes
original price and percentage; final pricing, PIX selection, competing discounts,
and rounding rules are deferred.

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
  database/
    connection.py            # internal read-only/writer connections
    schema.py                # six tables and indexes
    values.py                # exact money/percentage conversion
    import_data.py           # transactional snapshot replacement
    repositories.py          # catalog and private order status reads
  knowledge/
    extraction.py            # local PDF-to-section preparation
    policy_loader.py         # catalog validation and topic retrieval
scripts/                     # preparation, import, aggregate validation
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

**Project decisions:** standard-library runtime; integer cents and percentage
basis points; a composite item key verified against source rows; atomic snapshot
replacement; specialized read repositories; fail-closed private access; and local
JSON policies instead of embeddings. No framework is needed for Phase 1.

**Uncertainties:** conflicting contacts and installment wording, an undefined
shipping threshold boundary, absent campaign dates, mismatched product fields,
and historical totals differing from today's catalog. These remain visible in the
[review](docs/policy_review.md), with detailed source values only in ignored
`knowledge/policy_notes.md`. No source is silently corrected. Legal/compliance
statements remain source statements, not independently verified conclusions.

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

No GitHub publication or submission email is performed in this phase. Review
redistribution rights before publishing original or derived manual content.

## Limits and next steps

No agent, OpenRouter/LLM, function-calling schema, vector RAG, API, UI, WhatsApp,
conversation history, real authentication, sale/reservation, stock update, payment,
or refund processing is implemented. Repository examples demonstrate the
foundation; they are not working-agent conversations and do not yet satisfy the
final challenge's conversation deliverable.

Next: resolve business ambiguities; implement central deterministic pricing/payment
rules; add real identity verification; wrap read methods as allowlisted tools;
integrate a configurable OpenRouter model and pt-BR persona. Evaluate ambiguous,
unavailable, out-of-scope, and unauthorized requests, then capture 3–5 actual
conversations with English annotations for the final challenge submission.

## AI assistance

OpenAI Codex was used to inspect local materials, implement and review the Phase 1
code, structure policy extraction, create synthetic tests, execute validation,
and write documentation. The project owner supplied the scope, boundaries, and
language conventions. Automated evidence is reported explicitly; business
interpretations and production authentication still require human review.
