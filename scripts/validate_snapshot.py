"""Report aggregate validation evidence without personal data or policy text."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from timbre.database.connection import connect_database
from timbre.database.schema import TABLE_NAMES
from timbre.knowledge.policy_loader import InvalidPolicyCatalog, PolicyCatalog, PolicyFileMissing
from timbre.local_files import write_private

SUPPLIED_COUNTS = {"categories": 9, "products": 65, "customers": 50,
                   "orders": 20, "order_items": 22, "promotions": 25}


def validate_snapshot(database: Path, policies: Path) -> dict:
    with connect_database(database) as connection:
        counts = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in TABLE_NAMES}
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("database integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("foreign-key check failed")
        available = connection.execute("SELECT count(*) FROM products WHERE status = 'active' AND stock_quantity > 0").fetchone()[0]
        blocked_stock = connection.execute("SELECT count(*) FROM products WHERE status != 'active' AND stock_quantity > 0").fetchone()[0]
        flagged = connection.execute("SELECT count(*) FROM promotions WHERE is_active = 1").fetchone()[0]
        eligible = connection.execute("""SELECT count(*) FROM promotions r JOIN products p USING (product_id)
                                        WHERE r.is_active = 1 AND p.status = 'active' AND p.stock_quantity > 0""").fetchone()[0]
        differences = connection.execute("""SELECT count(*) FROM (
            SELECT o.order_id FROM orders o JOIN order_items i USING (order_id)
            JOIN products p USING (product_id) GROUP BY o.order_id
            HAVING o.total_cents != SUM(i.quantity * p.price_cents))""").fetchone()[0]
        nulls = {column: connection.execute(f"SELECT count(*) FROM orders WHERE {column} IS NULL").fetchone()[0]
                 for column in ("tracking_code", "estimated_delivery", "notes")}
    catalog = PolicyCatalog(policies)
    return {
        "counts": counts, "total_records": sum(counts.values()), "integrity": "ok", "foreign_keys": "ok",
        "available_products": available, "non_active_products_with_stock": blocked_stock,
        "flagged_promotions": flagged, "sellable_promotions": eligible,
        "historical_totals_differing_from_current_catalog": differences,
        "order_null_counts": nulls,
        "policy_sections": len(catalog._catalog["policies"]),
        "policy_pages": catalog.document["page_count"], "policy_topics": catalog.list_topics(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/store.db"))
    parser.add_argument("--policies", type=Path, default=Path("knowledge/policies.json"))
    parser.add_argument("--expect-supplied-snapshot", action="store_true",
                        help="Compare counts with this challenge's specific snapshot, not a permanent limit")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        report = validate_snapshot(arguments.database, arguments.policies)
        if arguments.expect_supplied_snapshot and report["counts"] != SUPPLIED_COUNTS:
            raise ValueError("row counts do not match the supplied snapshot")
        serialized = json.dumps(report, indent=2) + "\n"
        if arguments.report is not None:
            write_private(arguments.report, serialized.encode())
    except (OSError, ValueError, sqlite3.Error, InvalidPolicyCatalog, PolicyFileMissing):
        print("Validation failed; check local database, expected counts, and policy catalog.", file=sys.stderr)
        return 1
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
