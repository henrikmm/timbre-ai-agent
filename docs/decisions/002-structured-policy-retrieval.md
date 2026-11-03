# ADR-002: Structured Policy Retrieval

**Status:** Accepted; retrospective description of the inspected Phase 1 implementation.
**Date:** 2026-11-02.

## Context

The small Portuguese manual has numbered sections and related but distinct
commercial clauses. Retrieval must preserve source conditions and uncertainty.
The existing extraction produces 29 ordered records across all eight pages of
the reviewed version. The public repository excludes the original and derived
manual text. This record assesses existing code rather than inventing historical
decision evidence.

## Decision

Use a locally prepared JSON topic catalog instead of embeddings. Preserve original
Portuguese headings and text, surrounded by English IDs, titles, and metadata.
Each record retains document name, version, hash, section, and complete page span.
Validate hierarchy, source consistency, related topics, and unique identifiers
before returning copied records. Retrieve complete relevant clauses, including
parents/descendants and optional one-hop reviewed relationships.

## Alternatives considered

- Full-manual prompting: duplicates internal text on every request and weakens
  focus/provenance control.
- Vector retrieval: useful for a larger changing corpus, but introduces an
  embedding service, similarity thresholds, and possible partial-clause matches.
- Handwritten summaries alone: compact but liable to omit qualifications or hide
  contradictory source statements.

## Rationale

Explicit topics are inspectable, deterministic, inexpensive, and sufficient for
this document's size. The version-specific extractor fails on unexpected section
structure instead of quietly treating changed documents as already reviewed.

## Consequences and trade-offs

Topic selection currently belongs to trusted callers; there is no semantic query
planner. Manual changes require reviewed re-extraction. Ambiguities remain in
the public [issue map](../policy_review.md), with detailed values in ignored local
notes. No telephone, installment, or shipping discrepancy is silently repaired.
Numeric pricing/payment/eligibility rules will need one separate, reviewed
deterministic implementation; prose is not its enforcement mechanism.

Phase 2 uses only a compact, explicitly authorized persona summary. It does not
call the catalog or send the full manual to a provider. Model-driven policy
retrieval remains Phase 3 work.

## Validation strategy

Synthetic tests validate topics, boundaries, copies, hierarchy, malformed catalogs,
and unknown versions. Optional original checks compare every non-header PDF text
line in order. See the [policy catalog](../policy_catalog.md).
