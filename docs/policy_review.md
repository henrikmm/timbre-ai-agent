# Policy and snapshot ambiguity review

This public review records sources and engineering consequences without copying
internal contacts or full commercial terms. Detailed source comparisons stay in
ignored `knowledge/policy_notes.md`. Interpretations below are project decisions
or open questions, not corrected source facts or legal conclusions.

## Findings

| Issue and source | Impact | Handling / proposed interpretation | Clarification |
|---|---|---|---|
| Telephone/WhatsApp differs: cover, §1.2 vs §7 | Could direct a customer to the wrong channel | Retain both in retrieval; no silently chosen official number | Confirm primary/alternative channels |
| Email spelling differs: cover vs §1.2 | Normalizing it could change the destination | Preserve spelling and references | Confirm official email; delivery was not tested |
| Payment table vs installment minima: §§3,3.1 p.3 | Could approve/reject a wrong plan | Retrieve both; calculator accepts only plans meeting both minima and flags disputed plans | Confirm precedence and short-plan exception meaning |
| Shipping wording leaves exact threshold uncovered: §5.1 p.4 | Equality has no explicit fee | Do not invent a boundary | Confirm exact-equality handling |
| Exchange exclusions vs withdrawal/defect/warranty: §§4.1–4.4,8 | Blanket exclusion could incorrectly resolve a case | Retrieve relevant clauses and escalate | Confirm precedence and qualified interpretation |
| Campaigns lack dates/audience fields: promotions CSV; §§6.1–6.2 | Name/month does not prove validity or public scope | Use flag and sellability as snapshot evidence only | Confirm validity windows and exclusivity labels |
| Multiple campaign rows per product | Could encourage unsupported stacking/selection | Return separate candidate amounts; no automatic winner or stacking | Confirm winner/priority rule |
| Positive stock with unavailable status: products CSV; §7.3 | Stock alone could imply permission to sell | Require exact `active` and positive stock | Confirm any exceptions |
| Historical totals differ from current catalog sums: three related CSVs | Could falsely claim a pricing error | Preserve totals; two differences are diagnostics | Historical unit prices, freight, discounts are absent |
| Product names/descriptions/JSON disagree: products CSV | Could assert wrong brand/features | Preserve fields without inferred repair | Confirm authoritative catalog values |
| Manual catalog breadth exceeds snapshot: §1, products CSV | Could imply complete inventory coverage | Describe results as the supplied snapshot | Confirm coverage/refresh cadence |
| Multiple carriers, no carrier field: §5.3, orders CSV | Could invent a carrier/link | Return source tracking only to its owner | Confirm carrier mapping |
| Privacy/compliance assertions: §9 pp.7–8 | Could imply a legal audit or executable deletion | Keep as source text; neither implemented | Verify operational/legal handling separately |

## Deterministic rules and textual knowledge

The manual remains the source of commercial terms. Phase 3A references source
locations rather than duplicating private numeric constants in public documents.
The payment calculator parses reviewed source-linked rules from the validated local
catalog; missing/changed rule shapes fail closed and require staff confirmation.
Synthetic test rules use deliberately different values.

| Rule / information | Source | Boundary |
|---|---|---|
| Sale eligibility | Status, §7.3 | Implemented: exact `active` |
| Recorded stock availability | Stock, §§6.2,7.3 | Implemented: positive stock; no historical subtraction |
| Snapshot promotion eligibility | Flag, §6.2 | Implemented: flagged campaign and sellable product |
| PIX discount and base | §§3,6.2 | Implemented exact calculation; numeric value stays in local catalog |
| Promotion non-cumulativity | §6.2 | Implemented: campaigns and PIX remain separate, never stacked |
| Competing promotion/PIX choice | §6.2, CSV | Separate candidates with confirmation requirement; no automatic priority |
| Installment counts and minima | §§3,3.1 | Conservative intersection of minima; disputed plans require confirmation |
| Minimum installment calculation | §3.1 | Implemented exact cents; check every installment after remainder allocation |
| Mixed payments | §3.1 | Future eligibility after boundary clarification |
| Shipping fees/quotes | §§5.1,5.2 | Future deterministic logic after equality and dimensions are resolved |
| Hours, scope, and tone | §§1,2,7.1 | Textual; future holiday calculations need a trusted calendar |
| Distinct returns, warranty, delivery, escalation | §§4,5,7.3,8,10 | Complete textual retrieval; no automatic approvals/refunds/legal adjudication |
| Privacy/consent | §9 | Textual policy plus independent backend enforcement |

Sales, reservations, payment/refund processing, stock updates, and identity inference
are absent. An LLM following prose is never the enforcement mechanism for financial
or access-control rules.
