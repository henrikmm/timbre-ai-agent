# Representative conversations

All five examples contain actual model/UI responses and genuine tool execution.
Their inputs and business facts are **synthetic**, never original customer records
or extracted internal policies. Responses are preserved, including recovery paths.
They are observations, not golden replies guaranteed on a later model run.

| Example | Demonstrates |
|---|---|
| [Product discovery](01-product-discovery.md) | Available instruments, price filter and stock |
| [Commercial reasoning](02-commercial-reasoning.md) | Multiple tools, offers, exact PIX and installments |
| [Online withdrawal](03-online-return.md) | Receipt-based deadline and limited action authority |
| [Privacy boundary](04-privacy-boundary.md) | Real backend authorization denial and no returned private row |
| [Store and named price](05-store-and-price.md) | Location and catalog/promotion facts, in two independent sessions |

The original Takamine/store questions were also run privately against the supplied
assessment package; only aggregate outcomes are public. Examples were collected
during consolidation, with prompt hashes where available. Later prompt refinements
and source expansion are recorded in [evaluation](../docs/evaluation.md).

For a key-free backend demonstration, run `python scripts/demo_tools.py` after
`python scripts/prepare_demo.py`. The older `python examples/queries.py` uses the
smaller edge-case fixtures in a temporary database and also makes no model calls.
