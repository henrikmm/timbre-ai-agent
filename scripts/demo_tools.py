"""Exercise genuine business tools over prepared synthetic data, without inference."""

import json

from timbre.config import load_config
from timbre.tools import ToolExecutor


def main():
    config = load_config("config/demo.toml")
    executor = ToolExecutor(config.tools.database_path, config.tools.policies_path)
    print("SYNTHETIC DATA; real backend execution; no chatbot or API request.")
    for name, arguments in (
        ("search_products", {"category": "acoustic guitars", "max_price_brl": "900"}),
        ("calculate_payment_options", {"product_id": 101, "installments": 6}),
        ("get_store_policy", {"topic": "returns.online"}),
        ("get_my_order_status", {"order_id": 5001}),
    ):
        execution = executor.execute(name, json.dumps(arguments))
        print(name, json.dumps(execution.result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
