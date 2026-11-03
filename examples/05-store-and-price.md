# Store location and named-product price

These are two complete, independent one-turn conversations, each with a fresh session. They demonstrate the public equivalents of the assessment location and named-product questions. The original Takamine case was evaluated separately against the restricted data.

## Store location

Evidence: actual OpenRouter interaction on 2026-11-03; **synthetic data**; mode `fast`.
System prompt SHA-256: `6865f24034067daf3e2cac4fb6e9b0c8e00b0a140ef8543d6a2aa15416d2cebe`.

**Customer**

What is the store's address?

**Actual assistant response**

Here's the store's address:

**Rua do Exemplo, 100, Cidade Fictícia, MS**

Contact email: suporte@demo.invalid

Is there anything else you'd like to know?

**Sanitized tool execution**

```json
[
  {
    "name": "get_store_policy",
    "arguments": {
      "topic": "store"
    },
    "status": "success",
    "result_count": 2,
    "duration_seconds": 0.0028540420171339065
  }
]
```

Observed: `success`; 2 model calls, 1 tool calls; end-to-end 2.022 s; reported cost US$0.000515.

Deterministic checks: **pass**. Qualitative review is separate; no statistical quality claim is implied.
## Specific product price

Evidence: actual OpenRouter interaction on 2026-11-03; **synthetic data**; mode `fast`.
System prompt SHA-256: `6865f24034067daf3e2cac4fb6e9b0c8e00b0a140ef8543d6a2aa15416d2cebe`.

**Customer**

How much does Demo Cedar Acoustic cost?

**Actual assistant response**

The Demo Cedar Acoustic is currently on promotion:

- **Original price:** R$449.90
- **Promotional price (10% off):** R$404.91

It's in stock with 3 units available. Would you like to know the payment options (PIX, installments, etc.) or any other details about this guitar?

**Sanitized tool execution**

```json
[
  {
    "name": "search_products",
    "arguments": {
      "query": "[redacted]"
    },
    "status": "success",
    "result_count": 1,
    "duration_seconds": 0.0024995830026455224
  },
  {
    "name": "get_active_promotions",
    "arguments": {
      "product_id": 101
    },
    "status": "success",
    "result_count": 1,
    "duration_seconds": 0.0030767919961363077
  }
]
```

Observed: `success`; 3 model calls, 2 tool calls; end-to-end 3.225 s; reported cost US$0.000672.

Deterministic checks: **pass**. Qualitative review is separate; no statistical quality claim is implied.
The location, email and product prices here are entirely invented. Campaign arithmetic is returned by the backend; the model did not invent a discount.
