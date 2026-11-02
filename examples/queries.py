"""Run a public, synthetic demonstration of foundation queries; no conversation is simulated."""

import json
from pathlib import Path
import tempfile

from timbre.authorization import AccessDenied
from timbre.database.import_data import import_csvs
from timbre.database.repositories import CatalogRepository, OrderRepository
from timbre.knowledge.policy_loader import get_store_policy


def main() -> None:
    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "synthetic.db"
        import_csvs(fixtures, database)
        catalog = CatalogRepository(database)
        print("Synthetic public catalog search (no authentication):")
        print(json.dumps(catalog.search_products("violao", max_price_brl="500"), default=str, ensure_ascii=False, indent=2))
        print("Synthetic active promotions for sellable products:")
        print(json.dumps(catalog.get_active_promotions(), default=str, indent=2))
        print("Synthetic policy sections with parent and related exclusions:")
        for record in get_store_policy("returns.online", policies_path=fixtures / "policies.synthetic.json", include_related=True):
            print(record["id"], record["title"], record["source"]["pages"])
        try:
            OrderRepository(database).get_order_for_customer(5001, context={"customer_id": 9001})
        except AccessDenied:
            print("Private query with a claimed customer ID: DENIED (expected).")
        print("Authorized access simulations run only in tests.test_repositories.SecurityTests.")


if __name__ == "__main__":
    main()
