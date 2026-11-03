# ADR-010: Adopted Customer Service Decisions

**Status:** Accepted for the local demonstration.
**Date:** 2026-11-03.

## Context and authority

The supplied business document and catalog contain discrepancies and incomplete
rules. Repeating those internal issues in every customer answer creates a poor
service experience. The project owner authorized resolving the demonstration's
service behavior, explicitly including all listed telephone and email alternatives.
These are adopted project decisions, not corrections to source facts, verified
contact delivery, legal conclusions, or production business approval.

## Decision register

| Issue | Adopted service behavior | Technical implementation / production handoff |
|---|---|---|
| Different phones and emails | Offer all requested alternatives neutrally, with exact source spelling and deduplication | Extract from company/cover and WhatsApp sections; retain provenance. Confirm primary channels and deliverability with a real business owner before production |
| General card minimum versus detailed tiers | The detailed installment schedule takes precedence; interpret the short-plan exception as a per-installment minimum | Calculator uses the applicable tier after cent allocation. Return supported options rather than a disputed-policy warning |
| Local shipping equality gap | Include equality in the free-shipping threshold; the fixed fee applies strictly below it | Expose source-derived `free_from_brl` and `fee_below_brl` as resolved service data |
| Preference exchange has no start event | Start its window at receipt | Resolved metadata; preserve the separate source deadlines for online withdrawal, defects, and warranty |
| Broad exchange exclusions | Apply them to discretionary preference exchanges; do not automatically deny other channels | Route withdrawal/defect requests through their own sections. Particular cases are assessed; the bot does not approve refunds/exchanges |
| Active campaigns lack dates/audience fields | Active flags define the demonstration's public offer catalog; do not infer dates or expiry from names | Available products only. Production requires real eligibility and campaign validity data |
| Competing discounts | Use the lowest single eligible PIX option, with stable ID tie-breaking; never compound discounts | Compare list-price PIX with each campaign price. No additional PIX discount on an already discounted campaign |
| Mixed payments | Describe the sourced qualifying condition and offer staff arrangement | No split-payment calculator, charge, or completed staff handoff is implemented |
| Conflicting product prose | Product name determines identity, structured specifications determine technical attributes; omit conflicting prose claims | Do not overwrite CSVs, infer another brand from descriptions, or explain catalog reconciliation to customers |
| Stock versus commercial status | Require active status and positive stock | Existing backend eligibility remains enforced; availability is not a reservation or completed sale |
| Historical totals versus today's prices | Retain recorded order facts; do not recompute or invent an explanation for historical charges | Existing minimized owner-filtered order tool remains unchanged |
| Catalog coverage / missing carrier or freight inputs | Answer the available result; request the information needed for the next service step | No invented stock totals, carrier links, delivery quote, legal certification, or completed human transfer |

## Implementation boundary

Original CSVs, the Portuguese document, extracted headings/text, and policy JSON
are unchanged. `knowledge.customer_policy` builds a source-derived projection at
retrieval time, with decision IDs and provenance. The calculator applies monetary
decisions deterministically with Decimal arithmetic. The single system prompt
uses these resolved fields and keeps internal diagnostics out of ordinary answers.
It never turns a failed lookup into success or hides a material inability to act.

Contacts and source amounts are not hard-coded into public code or fixtures.
Public tests use deliberately different synthetic data. Detailed source comparisons
and the provided business values remain ignored/local. Developer traces remain
content-free: safe tool status/count/source, not raw result bodies or private rows.

Customer replies give useful conditions and next steps, without automatic document
contradiction, snapshot, or unconfirmed-selection disclaimers. An unsupported action
or missing fact still requires a concise truthful answer. All tools remain read-only;
customer authorization and financial transaction boundaries are unchanged.

Before a real deployment, replace demonstration assumptions with business-approved
rules and operational integrations. This handoff belongs in engineering material,
not a repetitive disclaimer inserted into the customer's conversation.
