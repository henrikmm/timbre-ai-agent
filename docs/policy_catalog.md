# Policy catalog and topic map

Local preparation extracts the complete Portuguese manual, version 2.1, using
`pdftotext -layout`. It splits numbered sections without summarizing clauses. Only
running headers and printed page numbers are removed. The cover remains because
its publication/contact information matters to the discrepancy review. This yields
**29 records from all 8 pages** in ignored `knowledge/policies.json`.

Original headings and bodies remain Portuguese inside `content`; IDs, topics,
titles, and descriptive metadata are English.

## Record contract

Top-level keys are `schema_version`, `document`, and `policies`. Document metadata
contains filename, version, SHA-256, page count, content language, and extraction
method. A synthetic record illustrates the contract:

```json
{
  "id": "synthetic_returns_online",
  "topic": "returns.online",
  "title": "Synthetic online returns",
  "parent_id": "synthetic_returns",
  "content": "Exemplo fictício, sem validade comercial.",
  "source": {
    "document": "synthetic_manual.pdf",
    "version": "test-1",
    "section": "1.1",
    "page": 1,
    "pages": [1, 2],
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "related_topics": ["returns.exclusions"]
}
```

Validation checks text, unique IDs/sections, matching document metadata, page ranges,
parent existence, absence of cycles, and valid related topics before exposing any
record. Missing files, invalid JSON/structure, and unknown topics have distinct
exceptions. Returned records are copies.

## Complete source map

| Section | English title | Topic | Page(s) |
|---|---|---|---|
| cover | Manual cover and publication details | `store` | 1 |
| 1 | Store overview and scope | `store.overview` | 2 |
| 1.1 | Mission | `store.mission` | 2 |
| 1.2 | Company information and contacts | `store.contacts` | 2 |
| 2 | Opening hours | `hours` | 2 |
| 3 | Payment methods | `payments` | 3 |
| 3.1 | Installment rules | `payments.installments` | 3 |
| 4 | Exchanges and returns | `returns` | 4 |
| 4.1 | Online purchase withdrawal | `returns.online` | 4 |
| 4.2 | Defective-product exchanges | `returns.defects` | 4 |
| 4.3 | Preference-based exchanges | `returns.preference` | 4 |
| 4.4 | Exchange exclusions | `returns.exclusions` | 4 |
| 5 | Shipping and deliveries | `shipping` | 4 |
| 5.1 | Metropolitan deliveries | `shipping.local` | 4 |
| 5.2 | Deliveries to other cities | `shipping.other_cities` | 4, 5 |
| 5.3 | Tracking codes | `tracking` | 5 |
| 6 | Promotions and discounts | `promotions` | 6 |
| 6.1 | Campaign types | `promotions.campaigns` | 6 |
| 6.2 | Promotion rules | `promotions.rules` | 6 |
| 7 | WhatsApp service | `whatsapp` | 6 |
| 7.1 | Service guidelines | `whatsapp.guidelines` | 6 |
| 7.2 | Standard service workflow | `whatsapp.workflow` | 6, 7 |
| 7.3 | Special service situations | `whatsapp.exceptions` | 7 |
| 8 | Warranty | `warranty` | 7 |
| 8.1 | Statutory warranty | `warranty.statutory` | 7 |
| 8.2 | Manufacturer warranty | `warranty.manufacturer` | 7 |
| 8.3 | Warranty exclusions | `warranty.exclusions` | 7 |
| 9 | Privacy and data protection | `privacy` | 7, 8 |
| 10 | Final provisions and management escalation | `escalation` | 8 |

Parent-child links follow numbered subsections. Related topics are explicit
reviewed references, not semantic similarity or vector search.

## Retrieval

`get_store_policy("returns")` returns the overview and all four return subsections
in source order. Online withdrawal, defects, preference, and exclusions stay
separate, with complete conditions and deadlines.

`get_store_policy("returns.online")` also keeps its parent introduction. With
`include_related=True`, it follows one hop of declared related topics, including
exclusions and escalation. Other supported top-level topics are `store`, `hours`,
`payments`, `shipping`, `tracking`, `promotions`, `whatsapp`, `warranty`, `privacy`,
and `escalation`. `PolicyCatalog.list_topics()` lists exact identifiers.

Unknown topics raise `UnknownPolicyTopic`; no generic policy answer is invented.
The loader does not select topics through an LLM or resolve business conflicts.
Preparation is scoped to the reviewed version and section structure. Changed
versions or missing/repeated/unrecognized sections fail and require manual review.
