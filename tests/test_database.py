"""Import fidelity, exact values, integrity constraints, and atomic replacement."""

import csv
from decimal import Decimal
import hashlib
import sqlite3

from timbre.database.connection import connect_database
from timbre.database.import_data import ImportValidationError, import_csvs
from timbre.database.values import from_cents, to_cents
from tests.support import DatabaseTestCase


class ImportTests(DatabaseTestCase):
    def change(self, table, transform):
        path = self.raw / f"{table}.csv"
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            rows, headers = list(reader), reader.fieldnames
        transform(rows)
        with path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def snapshot(self):
        with connect_database(self.database) as connection:
            return {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                    for table in self.report.counts}

    def test_all_tables_counts_and_foreign_keys(self):
        self.assertEqual(self.report.counts, {"categories": 2, "products": 6, "customers": 2,
                                             "orders": 3, "order_items": 4, "promotions": 5})
        self.assertEqual(self.report.total_records, 22)
        with connect_database(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            columns = connection.execute("PRAGMA table_info(order_items)").fetchall()
            self.assertEqual({row["name"]: row["pk"] for row in columns},
                             {"order_id": 1, "quantity": 0, "product_id": 2})

    def test_exact_money_json_nulls_and_historical_total_preserved(self):
        with connect_database(self.database) as connection:
            product = connection.execute("SELECT * FROM products WHERE product_id = 101").fetchone()
            self.assertEqual(product["price_cents"], 44990)
            self.assertEqual(product["specs"], '{"strings": "6", "color": "Azul"}')
            order = connection.execute("SELECT * FROM orders WHERE order_id = 5001").fetchone()
            self.assertEqual(order["total_cents"], 44050)
            self.assertEqual(order["notes"], "Synthetic private remark A")
            nulls = connection.execute("SELECT tracking_code, estimated_delivery, notes FROM orders WHERE order_id = 5003").fetchone()
            self.assertEqual(tuple(nulls), (None, None, None))
            self.assertIsNone(connection.execute("SELECT specs FROM products WHERE product_id = 106").fetchone()[0])
            self.assertEqual(connection.execute("SELECT stock_quantity FROM products WHERE product_id = 101").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT discount_basis_points FROM promotions WHERE promotion_id = 5").fetchone()[0], 1250)

    def test_idempotence_and_source_bytes_unchanged(self):
        before = self.snapshot()
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.raw.iterdir()}
        repeated = import_csvs(self.raw, self.database)
        self.assertEqual(self.report, repeated)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(hashes, {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.raw.iterdir()})

    def test_late_foreign_key_failure_rolls_back_entire_snapshot(self):
        before = self.snapshot()
        self.change("promotions", lambda rows: rows[-1].update(product_id="999999"))
        with self.assertRaises(ImportValidationError):
            import_csvs(self.raw, self.database)
        self.assertEqual(before, self.snapshot())

    def test_duplicate_composite_key_is_rejected_without_partial_updates(self):
        before = self.snapshot()
        self.change("order_items", lambda rows: rows.append(rows[0].copy()))
        with self.assertRaises(ImportValidationError):
            import_csvs(self.raw, self.database)
        self.assertEqual(before, self.snapshot())

    def test_invalid_source_values_never_replace_the_database(self):
        invalid = [("products", "price_brl", "1.001"), ("products", "price_brl", "NaN"),
                   ("products", "specs", "[]"), ("products", "specs", '{"x": NaN}'),
                   ("products", "stock_quantity", "-1"), ("products", "created_at", "2025-02-30"),
                   ("promotions", "is_active", "true"), ("promotions", "discount_percent", "101"),
                   ("order_items", "quantity", "0")]
        before = self.snapshot()
        for table, field, value in invalid:
            with self.subTest(table=table, field=field, value=value):
                path = self.raw / f"{table}.csv"
                original = path.read_bytes()
                self.change(table, lambda rows: rows[0].update({field: value}))
                with self.assertRaises(ImportValidationError):
                    import_csvs(self.raw, self.database)
                self.assertEqual(before, self.snapshot())
                path.write_bytes(original)

    def test_missing_ambiguous_and_malformed_sources_fail_closed(self):
        path = self.raw / "customers.csv"
        alias = self.raw / "desafio_tecnico_ai_eng - customers.csv"
        alias.write_bytes(path.read_bytes())
        with self.assertRaises(ImportValidationError):
            import_csvs(self.raw, self.database)
        alias.unlink()
        path.unlink()
        with self.assertRaises(ImportValidationError):
            import_csvs(self.raw, self.database)
        path.write_text("customer_id,name\n1,Synthetic\n", encoding="utf-8")
        with self.assertRaises(ImportValidationError):
            import_csvs(self.raw, self.database)

    def test_error_messages_do_not_echo_private_values(self):
        secret = "SYNTHETIC_PRIVATE_MARKER"
        self.change("customers", lambda rows: rows[0].update(customer_id=secret))
        with self.assertRaises(ImportValidationError) as raised:
            import_csvs(self.raw, self.database)
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("customers", str(raised.exception))

    def test_read_connections_cannot_write_or_create(self):
        with connect_database(self.database) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM customers")
        missing = self.directory / "missing.db"
        with self.assertRaises(sqlite3.OperationalError):
            with connect_database(missing):
                pass
        self.assertFalse(missing.exists())

    def test_failed_first_import_does_not_publish_a_partial_database(self):
        self.change("promotions", lambda rows: rows[0].update(product_id="999999"))
        path = self.directory / "new.db"
        with self.assertRaises(ImportValidationError):
            import_csvs(self.raw, path)
        self.assertFalse(path.exists())

    def test_unrelated_database_is_not_rebuilt(self):
        unrelated = self.directory / "unrelated.db"
        with sqlite3.connect(unrelated) as connection:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
            connection.execute("INSERT INTO unrelated VALUES ('synthetic retained value')")
        with self.assertRaises(ImportValidationError):
            import_csvs(self.raw, unrelated)
        with sqlite3.connect(unrelated) as connection:
            self.assertEqual(connection.execute("SELECT value FROM unrelated").fetchone()[0],
                             "synthetic retained value")

    def test_duplicate_headers_and_wrong_record_shapes_are_rejected(self):
        path = self.raw / "customers.csv"
        for contents in ["customer_id,name,phone,email,name\n1,A,,,B\n",
                         "customer_id,name,phone,email,city\n1,A,,,City,unexpected\n",
                         "customer_id,name,phone,email,city\n1,A\n"]:
            with self.subTest(case=contents):
                path.write_text(contents, encoding="utf-8")
                with self.assertRaises(ImportValidationError):
                    import_csvs(self.raw, self.database)


class MoneyTests(DatabaseTestCase):
    def test_decimal_conversion_is_exact(self):
        for source, expected in [("0.10", 10), ("449.9", 44990), ("1.2300", 123), ("0", 0)]:
            self.assertEqual(to_cents(source), expected)
            self.assertEqual(from_cents(expected), Decimal(source))
        self.assertEqual(to_cents(Decimal("0.1") + Decimal("0.2")), 30)

    def test_inexact_nonfinite_negative_and_overflow_values_are_rejected(self):
        for value in [0.1, True, "-1", "1.001", "NaN", "Infinity", "92233720368547758.08"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                to_cents(value)
