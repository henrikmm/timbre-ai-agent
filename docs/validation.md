# Phase 1 validation evidence

Executed locally on **2026-11-02**. This report describes the data/knowledge
foundation, not a completed conversational agent or production authentication.

## Environment and installation

| Environment | SQLite | Result |
|---|---|---|
| Python 3.14.6, local editable virtual environment | 3.50.4 | 40 tests passed, no skips |
| Python 3.11.15, source checkout via `PYTHONPATH=src` | 3.53.3 | 40 tests passed, no skips |
| Public-files-only copy, Python 3.14.6, without originals | 3.50.4 | 36 tests passed; 4 original-material tests explicitly skipped |

Editable installation with `python -m pip install -e .` succeeded after fetching
the setuptools build dependency. There are no third-party Python runtime/test
dependencies. `pip check` reported no broken requirements. Poppler was already
available locally. The test suites make no API or LLM calls.

## Input review and import

All eight expected files were found. Both PDFs were extracted in full, and the
policy pages relevant to tables and cross-page boundaries were also rendered for
visual inspection. The CSV review checked all schemas, nulls, primary keys,
composite-key uniqueness, status values, JSON, and reference integrity.

| Table | Expected supplied count | Imported count |
|---|---:|---:|
| `categories` | 9 | 9 |
| `products` | 65 | 65 |
| `customers` | 50 | 50 |
| `orders` | 20 | 20 |
| `order_items` | 22 | 22 |
| `promotions` | 25 | 25 |
| **Total** | **191** | **191** |

- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: no violations; connections enable enforcement.
- Composite `(order_id, product_id)`: no duplicates in the supplied items.
- Every imported field matches its source or its exact documented conversion.
- All 8 copied originals match `Material_suporte/` byte for byte.
- Repeated import preserves logical records and source fingerprints.
- Synthetic late foreign-key failure and duplicate item keys roll back the entire
  prior snapshot. Invalid initial loads do not publish a partial database.
- Money remains exact; malformed amounts, JSON, dates, booleans, headers, and record
  shapes are rejected. Source values are not echoed in import error messages.
- Unrelated databases are refused without deleting their existing tables.

Diagnostic observations: 61 products satisfy `active` plus positive stock; two
non-active products still have stock; 4 of 25 campaigns are flagged active and
sellable. Orders contain 12 null tracking codes, 12 null estimates, and 16 null
notes. Two totals differ from current catalog quantity sums. No historical unit
prices exist, so those differences were not treated as financial errors.

## Policy evidence

The generated catalog contains 29 records from all 8 manual pages. The original
Portuguese text remains intact apart from removed running headers/page numbers.
An independent comparison against `pdftotext -layout` confirms every other source
text line is retained in order. Document fingerprint, version, section, first page,
full page span, hierarchy, and related topics are preserved and validated.

Cross-page cases were verified: shipping to other cities (pp.4–5), service workflow
(pp.6–7), and privacy (pp.7–8). Online returns, defects, preference, and exclusions
remain distinct. Missing files, unknown topics, invalid structures, duplicate JSON
keys, broken hierarchy/references, and out-of-range pages produce explicit errors.

The top-level topics are `store`, `hours`, `payments`, `returns`, `shipping`,
`tracking`, `promotions`, `whatsapp`, `warranty`, `privacy`, and `escalation`.
See [all topics and subsections](policy_catalog.md) for the complete 29-record map.

## Access-control demonstration

All security records and sessions in this table are synthetic.

| Case | Result |
|---|---|
| Public catalog search without a session | Allowed; only public fields |
| Default private order lookup without a session | `AccessDenied`, before database access |
| Default lookup with a claimed customer ID, name, phone, or simulated session | `AccessDenied` |
| Test issuer's session A reads A's order | Allowed; five status fields only |
| Session A requests B's order | Same `OrderNotFound` response as a nonexistent order |
| Caller tries a `customer_id` query override | Unsupported argument; cannot replace bound identity |
| Fabricated context/object claims to be authenticated | `AccessDenied` |
| Authorized history list | Only that synthetic owner's orders |
| Public SQL/LIKE injection attempts | Treated as literal input; no customer records returned |

The five authorized fields are `order_id`, `order_date`, `status`, `tracking_code`,
and `estimated_delivery`. No customer names, contacts, notes, or full customer
profiles are exposed by these query projections. This demonstrates backend
interface behavior, not real-world authentication or database-file isolation.

## Publication audit

The current public/prospective files and existing local Git history were checked
for restricted paths. A literal-value scan also compared known source customer
names/phones/emails and order notes against public files and historical blobs;
there were no matches. The only tracked CSVs are explicitly synthetic fixtures.
The original PDFs, support folder, database, reports, policy JSON, and detailed
policy notes remain ignored. Generated raw copies, database, and policy JSON have
owner-only `0600` permissions. The detailed notes also have `0600` permissions.

The audit covers the local tracked tree and Git history.
The public-files-only copy contained no originals, database, or derived policy
JSON, and its synthetic tests and runnable examples succeeded.

## Reproduce the checks

From the repository root after editable installation and Poppler setup:

```bash
# Public, offline tests and synthetic examples
python -m unittest discover -s tests -v
python examples/queries.py

# Local original-material preparation
python scripts/prepare_data.py --source-dir Material_suporte
python scripts/import_data.py --report local/import_report.json
python scripts/prepare_policies.py
python scripts/validate_snapshot.py --expect-supplied-snapshot --report local/validation_report.json

# Explicitly opt in to the four private-material integration tests
TIMBRE_RAW_DIR=data/raw TIMBRE_POLICIES_PATH=knowledge/policies.json python -m unittest discover -s tests -v
```

`--expect-supplied-snapshot` checks this delivery's counts; those counts are not
hard-coded limits in the importer. Private aggregate reports are generated under
ignored `local/`. No source-code changes are required to use alternative paths.

## Completion boundaries

The implemented tree and execution instructions are in the [README](../README.md).
The [six-table schema](data_model.md), [component/security design](architecture.md),
[policy map](policy_catalog.md), and [ambiguity/rule review](policy_review.md)
complete the Phase 1 documentation. Detailed source comparisons are local only.

The remaining business questions cover contacts, installment wording, the shipping
boundary, return/warranty precedence, campaign scope/selection, catalog accuracy,
and refresh/carrier information. Resolve these before enabling the affected
deterministic calculations. Then add verified identity, allowlisted tools, the
configurable OpenRouter integration, and a pt-BR conversational persona. Capture
actual annotated conversations when that agent exists; no such behavior was
implemented or claimed in this phase.
