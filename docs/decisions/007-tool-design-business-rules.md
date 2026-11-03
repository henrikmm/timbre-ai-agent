# ADR-007: Tool Design and Business Rules

**Status:** Accepted for Phase 3A; unresolved source ambiguities remain explicit.
**Date:** 2026-11-03.

## Context

The existing SQLite repositories already restrict catalog reads and private order
projections. The policy loader preserves complete Portuguese sections and source
references. Source ambiguities include installment wording, campaign priority,
missing campaign validity windows, and conflicting product fields. Calculations
must not silently turn those ambiguities into commercial permissions.

## Decision

Expose six task-oriented, read-only capabilities: `search_products`,
`get_product_details`, `get_store_policy`, `get_active_promotions`,
`calculate_payment_options`, and `get_my_order_status`. Register unique descriptions,
JSON schemas, validated implementations, and structured results in one allowlist.
Reject unknown fields and tool names; do not coerce claimed identity into authority.
Distinguish success, empty results, invalid arguments, authorization denial, and
backend failure. Serialize monetary values as decimal strings.

Use parameterized repository queries. Sale eligibility requires both exact commercial
`active` status and positive recorded stock. Explicitly requested unavailable product
details remain descriptive. English category aliases map to the Portuguese catalog;
brand filtering uses available product-name evidence because there is no independent
brand column. Do not repair conflicting names, descriptions, or specifications.

Policy retrieval retains relevant subsections and provenance, keeping online
withdrawal, defective-product exchange, preference exchange, and warranty distinct.
Source text remains Portuguese; the assistant explains it in English by default.
Neither a policy campaign description nor a CSV flag proves current live eligibility.

Payment calculations load authoritative product prices and reviewed, source-linked
rules. Use `Decimal`, cent rounding, explicit discount bases, and exact installment
allocation. Never stack campaign and PIX discounts. Explain unavailability and
unresolved campaign/minimum-installment conditions rather than inventing exceptions.
No model-supplied amount can replace the catalog price. Full-payment methods are
derived from the policy table; a missing method is unavailable rather than assumed
permitted. Numerical source rules and
detailed original policy text remain in ignored local artifacts; public fixtures are
explicitly synthetic.

Calculation eligibility is distinct from a confirmed live quote. Payment results
explicitly identify snapshot-only calculations and declare checkout unsupported;
an eligible policy selection cannot authorize a transaction or guarantee current
pricing. This boundary was refined after a live response overstated certainty.

Bind private order context in trusted Python composition, outside model arguments.
Default `DenyAllAuthorizer` rejects public sessions before database access. A verified
owner query filters by both order ID and backend-resolved customer ID. Other-owner
and nonexistent orders have the same unavailable response. Expose only minimal
historical status/delivery/tracking information, with no customer contact data.
Test-only issuers remain exclusively in test support; there is no CLI impersonation.

## Alternatives considered

- Prices, discounts, or customer IDs supplied by the model: untrusted input cannot
  establish commercial truth or identity.
- Automatically choosing the largest campaign: missing priority/audience/date
  fields make that choice an unsupported business assumption.
- Floating-point arithmetic: unsuitable for deterministic cent-level allocation.
- Making private tools available only by prompt convention: backend enforcement
  must remain effective when a model requests an unauthorized operation.

## Consequences

Some customer questions end with a qualified answer or escalation instead of an
invented yes/no. Snapshot information is authoritative for its recorded fields,
not a live ERP or carrier integration. Real authentication, business clarification,
policy version review, and data refresh remain production responsibilities.

See the [policy ambiguity review](../policy_review.md) and
[Phase 3A operating limits](../phase3a.md).
