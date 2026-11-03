# Policy and Catalog Decision Review

The original source issues remain recorded here for engineering review. The
project owner authorized adopted service behavior for the demonstration; the
[decision register](decisions/010-customer-service-decisions.md) is authoritative
for that behavior. Source files and Portuguese extracted text remain unchanged.
Detailed business values/comparisons stay in ignored `knowledge/policy_notes.md`.
These are project decisions, not verified corrections, contact-delivery tests, legal
conclusions, or production policy approval.

## Findings and current handling

| Issue and source | Adopted customer service behavior | Implementation / remaining business handoff |
|---|---|---|
| Different phones: cover, §1.2, §7 | Give all requested phone alternatives neutrally | Source-derived, deduplicated contact projection; confirm primary channels in production |
| Different email spellings: cover, §1.2 | Give both exact alternatives, without correcting or labeling either wrong | Preserve accented spelling and provenance; production deliverability unverified |
| General card minimum versus §3.1 tiers | Detailed installment schedule takes precedence | Calculator checks the tier minimum after exact cent allocation |
| Ambiguous short-plan exception, §3.1 | Treat the stated exception amount as the per-installment minimum | An adopted interpretation, documented for owner review before production |
| Local shipping equality gap, §5.1 | Free shipping includes the threshold; fixed fee below it | Resolved source-derived threshold/fee metadata |
| Preference exchange start, §4.3 | Count from receipt | Resolved service metadata; do not rewrite the clause |
| Exclusions versus withdrawal/defects/warranty, §§4,8 | Keep channels separate; preference exclusions do not automatically deny the others | Explain the relevant conditions; no automated approval/refund/legal adjudication |
| Campaign dates/audience absent, CSV and §§6.1–6.2 | Active flags define the demonstration offer catalog | No invented dates/expiry; production needs real validity/eligibility fields |
| Competing discounts, §6.2 and CSV | Lowest single PIX option, without stacking | Calculator compares base PIX against individual campaign prices; stable tie-breaking |
| Positive stock with unavailable status, CSV and §7.3 | Sellable requires active status and positive stock | Existing backend checks remain enforced |
| Historical totals versus current prices, related CSVs | Retain recorded order facts; do not invent a historical price explanation | Current private tool does not expose charge reconciliation |
| Conflicting name/prose/specifications, products CSV | Name for identity, structured specifications for attributes; omit contested prose | Shared prompt governs presentation; original fields remain unchanged |
| Manual breadth versus partial catalog, §1 and CSV | Answer the available catalog results without an exhaustive coverage claim | Do not dump dataset caveats into routine answers |
| Multiple carriers, no order carrier field, §5.3 and CSV | Give owner-authorized recorded tracking without a fabricated carrier/link | Production carrier integration remains absent |
| Other-city freight lacks operational dimensions, §5.2 | Ask relevant delivery details and offer the supported staff route | No invented freight amount or claim of a completed quote |
| Mixed payments, §3.1 | Describe the sourced qualifying condition and offer staff arrangement | No mixed-payment calculator or transaction execution is implemented |
| Privacy/compliance assertions, §9 | Explain supported service steps without claiming legal certification or completed deletion | Independent backend access checks remain mandatory |

## Deterministic business rules

`knowledge.customer_policy.customer_policy` builds a resolved, source-linked
projection at retrieval time. Contact alternatives and the local shipping boundary
are derived from the supplied catalog, not copied into public code. Installment
counts/minima and PIX percentages are parsed from reviewed policy shapes.
Missing/changed payment rule shapes fail closed; the customer receives a concise
service limitation, not an internal document diagnosis.

Payment calculations use Decimal and exact cents. The detailed tier's minimum
applies to every allocated installment. Active offers require sellable products;
no additional PIX percentage is applied to a promotional price. All original
candidate arithmetic remains inspectable by trusted code, and the lowest single
PIX option is identified explicitly. These calculations do not reserve inventory,
charge, refund, or approve a sale.

The system prompt uses resolved service terms and preserves language adaptation.
It avoids automatic snapshot/document-conflict disclaimers and internal-reconciliation
narratives. Missing facts, failed lookups, authentication requirements, and unsupported
actions still receive truthful, focused explanations and useful next steps.

## Source and test boundaries

No original CSV, policy heading, body, or source reference is edited. Public tests
use different synthetic contacts, amounts, tiers, thresholds, and products. The
source-parity tests still validate the original local materials separately.
Production sign-off must replace demonstration assumptions with approved business
rules and current integrations. That handoff is an engineering responsibility,
not a repeated warning embedded in the ordinary customer conversation.
