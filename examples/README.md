# Executable foundation examples

Run `python examples/queries.py` after installation, or
`PYTHONPATH=src python3 examples/queries.py`. It uses synthetic fixtures and a
temporary database. It is a data-layer demo, not an LLM conversation or real login.

| Scenario | Operation | Observed behavior |
|---|---|---|
| Affordable available instrument | `search_products("violao", max_price_brl="500")` | Synthetic product 101 at `Decimal("449.90")`, without authentication |
| Eligible snapshot campaigns | `get_active_promotions()` | Synthetic campaigns 1 and 5; other offers excluded |
| Complete online-return subsection | Synthetic `get_store_policy("returns.online", include_related=True)` | Parent and exclusions retained with source metadata |
| Claimed identity rejected | Default order repository with a customer-ID dictionary | `AccessDenied`, no private data printed |

Security tests additionally issue **test-only** opaque sessions: A can read A's
synthetic orders, cannot read B's, and cannot override its identity. These labels
are not actual customers. Portuguese `violao` means “acoustic guitar”; Portuguese
fixture strings are synthetic business content.

Future actual conversations will use pt-BR exchanges and English scenario titles,
behavior explanations, technical annotations, and necessary translations. No
unimplemented agent response is presented as an observed result here.
