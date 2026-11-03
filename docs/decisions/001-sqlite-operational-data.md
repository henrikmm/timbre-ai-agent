# ADR-001: SQLite for Operational Data

**Status:** Accepted; retrospective description of the inspected Phase 1 implementation.
**Date:** 2026-11-02.

## Context

The six supplied CSVs form a relational snapshot: categories have products;
customers have orders; order items reference orders and products; promotions
reference products. Relationships, original fields, and exact monetary values
matter more than concurrent write throughput. This record explains the current
implementation; it does not assert an undocumented historical deliberation.

## Decision

Use SQLite with primary/foreign keys, constraints, four query indexes, and an
explicit schema version. Validate all CSVs before atomically replacing the six
tables in one transaction. Preserve original source bytes locally and report
their SHA-256 fingerprints. Store BRL as integer cents and percentages as basis
points, returning `Decimal` values through specialized repositories.

## Alternatives considered

- Direct CSV/dataframe reads: simple exploration, but repeated joins and integrity
  enforcement would move into each caller.
- PostgreSQL or another database server: useful for concurrent services, but adds
  deployment and administration without a present requirement.
- A document store: less natural for the supplied foreign-key relationships.

## Rationale

SQLite supplies transactions, parameterized queries, referential validation, and
portable local setup using Python's standard library. The inspected importer
already refuses unrelated databases and unsupported schemas, preserves nulls and
Portuguese text, and rolls back failed snapshot replacement.

## Consequences and trade-offs

The data is a static snapshot, not a live inventory or ERP connection. Recorded
stock is not recalculated from historical orders. Historical unit prices and
promotion validity windows are absent, so current catalog totals cannot explain
old order totals or establish campaign validity. Complete snapshot replacement is
trusted maintenance, never a customer action. File access is not row-level
authorization; see [ADR-003](003-customer-data-security.md).

## Validation strategy

Offline synthetic tests cover exact conversions, constraints, literal SQL/LIKE
inputs, deterministic reads, repeated imports, and rollback. Explicit local
original-material checks compare every source field and reference. See the
[data model](../data_model.md) and [Phase 1 evidence](../validation.md).
