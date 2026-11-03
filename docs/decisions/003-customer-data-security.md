# ADR-003: Customer Data Access and Security

**Status:** Accepted; Phase 1 boundary preserved in Phase 2.
**Date:** 2026-11-02.

## Context

Catalog information and general service policies are public business information.
Customer identities, individual orders, tracking codes, and free-text notes are
restricted. An LLM can produce plausible identifiers or follow a customer's
claimed identity without having verified either. The assessment has no trusted
production identity service to integrate at this stage.

## Decision

Keep public catalog reads separate from private owner-scoped order reads. Private
access is denied by default before opening the database. A future trusted backend
must inject a `CustomerAuthorizer` that verifies an opaque session and resolves
its customer identity outside model arguments. The requested order ID is separate
from that identity; both owner and order filter the query. Nonexistent and
another customer's orders have the same not-found behavior.

Private status projections expose only five necessary operational fields, omitting
customer profiles, notes, and payment data. Authentication simulations remain
exclusively in test support. Phase 2 imports no operational repositories and sends
no CSV/database content to the LLM.

## Alternatives considered

- Trusting a supplied customer ID, phone, name, or order number: convenient but
  permits impersonation and enumeration.
- Using an LLM/prompt as the permission check: nondeterministic and bypassable.
- Shipping a demo login or environment bypass: risks confusing a simulation with
  a production security boundary.

## Rationale

Least privilege and backend ownership checks remain meaningful even when prompts
are malicious or the model invents IDs. Real authentication is deferred until
there is a verified identity flow and a service boundary to enforce it.

## Consequences and trade-offs

Private operations remain unavailable to normal callers. Someone who can open
the SQLite file or run arbitrary trusted Python can bypass application interfaces;
SQLite read-only mode prevents writes, not confidential reads. Original materials,
database files, policy derivatives, detailed notes, credentials, and raw execution
artifacts stay outside Git. Public fixtures are explicitly synthetic.

User-entered chat text still travels to OpenRouter and inference providers.
Content-free local metrics and open weights do not make external inference private
or establish legal compliance. Configure provider data preferences and use
synthetic inputs until data processing has been reviewed.

## Validation strategy

Offline tests cover default denial, forged sessions, ownership, minimal projections,
and existence probes. Phase 2 tests verify that messages, responses, upstream error
bodies, and synthetic credentials never enter request logs. Prompt resistance
remains a live behavioral evaluation, not a security guarantee from these tests.
