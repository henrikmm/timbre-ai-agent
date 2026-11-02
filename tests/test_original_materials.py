"""Opt-in local tests; supplied private materials are never required by public tests."""

import csv
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from timbre.database.connection import connect_database
from timbre.database.import_data import DESTINATION_COLUMNS, SOURCE_COLUMNS, discover_csv_files, import_csvs
from timbre.knowledge.extraction import is_page_artifact
from timbre.knowledge.policy_loader import PolicyCatalog


@unittest.skipUnless(os.environ.get("TIMBRE_RAW_DIR"), "set TIMBRE_RAW_DIR to validate local originals")
class OriginalSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.raw = Path(os.environ["TIMBRE_RAW_DIR"])
        self.database = Path(self.temporary.name) / "originals.db"
        self.report = import_csvs(self.raw, self.database)

    def test_expected_supplied_counts_and_repeated_import(self):
        self.assertEqual(self.report.counts, {"categories": 9, "products": 65, "customers": 50,
                                             "orders": 20, "order_items": 22, "promotions": 25})
        self.assertEqual(self.report.total_records, 191)
        self.assertEqual(self.report, import_csvs(self.raw, self.database))
        with connect_database(self.database) as connection:
            self.assertFalse(connection.execute("PRAGMA foreign_key_check").fetchall())

    def test_every_source_value_preserved_without_printing_private_data(self):
        for table, path in discover_csv_files(self.raw).items():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, self.report.source_sha256[table])
            with path.open(encoding="utf-8-sig", newline="") as stream:
                originals = list(csv.DictReader(stream))
            with connect_database(self.database) as connection:
                imported = connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            keys = ("order_id", "product_id") if table == "order_items" else (SOURCE_COLUMNS[table][0],)
            by_key = {tuple(row[key] for key in keys): row for row in imported}
            self.assertEqual(len(originals), len(imported))
            for index, source in enumerate(originals, 1):
                row = by_key[tuple(int(source[key]) for key in keys)]
                for column, stored_column in zip(SOURCE_COLUMNS[table], DESTINATION_COLUMNS[table]):
                    raw, stored = source[column], row[stored_column]
                    if raw == "":
                        equivalent = stored is None
                    elif column in {"price_brl", "total_brl", "discount_percent"}:
                        equivalent = Decimal(raw) * 100 == stored
                    elif column.endswith("_id") or column in {"quantity", "stock_quantity", "is_active"}:
                        equivalent = int(raw) == stored
                    else:
                        equivalent = raw == stored
                    # Do not include compared values in assertion diagnostics.
                    self.assertTrue(equivalent, f"source preservation failed: {table}, record {index}, field {column}")


@unittest.skipUnless(os.environ.get("TIMBRE_POLICIES_PATH"), "set TIMBRE_POLICIES_PATH to validate the local catalog")
class OriginalPolicyTests(unittest.TestCase):
    def test_all_sections_and_cross_page_provenance(self):
        catalog = PolicyCatalog(os.environ["TIMBRE_POLICIES_PATH"])
        self.assertEqual(catalog.section_count, 29)
        self.assertEqual(len(catalog.get_store_policy("returns")), 5)
        self.assertEqual(catalog.get_store_policy("shipping.other_cities")[-1]["source"]["pages"], [4, 5])
        self.assertEqual(catalog.get_store_policy("privacy")[0]["source"]["pages"], [7, 8])

    @unittest.skipUnless(os.environ.get("TIMBRE_RAW_DIR") and shutil.which("pdftotext"),
                         "original text-coverage comparison requires local PDF and Poppler")
    def test_every_non_header_source_line_is_preserved_in_order(self):
        catalog = PolicyCatalog(os.environ["TIMBRE_POLICIES_PATH"])
        pdf = Path(os.environ["TIMBRE_RAW_DIR"]) / catalog.document["name"]
        self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), catalog.document["sha256"])
        result = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
                                capture_output=True, check=True, timeout=30)
        expected = [line.strip() for page in result.stdout.decode("utf-8").split("\f")
                    for line in page.splitlines() if line.strip() and not is_page_artifact(line)]
        actual = [line.strip() for record in catalog._catalog["policies"]
                  for line in record["content"].splitlines() if line.strip()]
        self.assertTrue(expected == actual, "policy extraction lost, reordered, or modified source text lines")
