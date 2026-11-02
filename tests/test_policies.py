"""Policy retrieval, hierarchy, source provenance, and malformed catalogs."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from timbre.knowledge.extraction import PolicyPreparationError, SECTION_METADATA, parse_policy_pages
from timbre.knowledge.policy_loader import (InvalidPolicyCatalog, PolicyCatalog, PolicyFileMissing,
                                           UnknownPolicyTopic, get_store_policy)
from tests.support import FIXTURES


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.path = FIXTURES / "policies.synthetic.json"
        self.catalog = PolicyCatalog(self.path)

    def test_load_and_retrieve_multiple_complete_sections(self):
        records = self.catalog.get_store_policy("returns")
        self.assertEqual(len(records), 3)
        self.assertIn("não representa a loja", records[0]["content"])
        self.assertEqual(records[1]["source"]["pages"], [1, 2])
        self.assertEqual(records[1]["source"]["version"], "test-1")
        self.assertEqual(records[1]["source"]["document"], "synthetic_manual.pdf")

    def test_subtopic_keeps_parent_and_optional_related_exclusions(self):
        selected = self.catalog.get_store_policy("returns.online")
        self.assertEqual([record["topic"] for record in selected], ["returns", "returns.online"])
        related = self.catalog.get_store_policy("returns.online", include_related=True)
        self.assertEqual([record["topic"] for record in related], ["returns", "returns.online", "returns.exclusions"])

    def test_returned_records_and_metadata_cannot_mutate_catalog(self):
        self.catalog.get_store_policy("returns")[0]["source"]["pages"].append(999)
        metadata = self.catalog.document
        metadata["version"] = "changed"
        self.assertEqual(self.catalog.get_store_policy("returns")[0]["source"]["pages"], [1])
        self.assertEqual(self.catalog.document["version"], "test-1")

    def test_convenience_function_and_topic_listing(self):
        self.assertEqual(len(get_store_policy("payments", policies_path=self.path)), 1)
        self.assertEqual(self.catalog.list_topics(), ["payments", "returns", "returns.exclusions", "returns.online"])

    def test_unknown_topics_and_missing_files_have_explicit_errors(self):
        for topic in ["nonexistent", "returns.nonexistent", "", None]:
            with self.assertRaises(UnknownPolicyTopic):
                self.catalog.get_store_policy(topic)
        with self.assertRaises(PolicyFileMissing):
            PolicyCatalog(self.path.parent / "missing.json")

    def test_invalid_json_and_encoding_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            for content in [b"{", b"\xff\xfe"]:
                path.write_bytes(content)
                with self.assertRaises(InvalidPolicyCatalog):
                    PolicyCatalog(path)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            contents = self.path.read_text(encoding="utf-8")
            path.write_text(contents.replace('"schema_version": 1,',
                                            '"schema_version": 9, "schema_version": 1,'), encoding="utf-8")
            with self.assertRaises(InvalidPolicyCatalog):
                PolicyCatalog(path)

    def test_invalid_structure_source_and_hierarchy_are_rejected(self):
        base = json.loads(self.path.read_text())
        transforms = [
            lambda value: value.update(schema_version=True),
            lambda value: value.update(policies=[]),
            lambda value: value["policies"][0].update(content=""),
            lambda value: value["policies"][1].update(id=value["policies"][0]["id"]),
            lambda value: value["policies"][1].update(parent_id="missing_parent"),
            lambda value: value["policies"][0].update(parent_id="synthetic_returns_online"),
            lambda value: value["policies"][0]["source"].update(page=True),
            lambda value: value["policies"][0]["source"].update(pages=[99]),
            lambda value: value["policies"][0]["source"].update(pages=[2, 1]),
            lambda value: value["policies"][0]["source"].update(version="wrong-version"),
            lambda value: value["policies"][0]["source"].update(sha256="1" * 64),
            lambda value: value["policies"][0].update(related_topics=["missing"]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            for index, transform in enumerate(transforms):
                with self.subTest(case=index):
                    value = deepcopy(base)
                    transform(value)
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(InvalidPolicyCatalog):
                        PolicyCatalog(path)


class SectionExtractionTests(unittest.TestCase):
    def synthetic_pages(self):
        lines = ["Synthetic manual", "Versão 2.1"]
        for number in SECTION_METADATA:
            if number == "cover":
                continue
            marker = "." if "." not in number else ""
            lines.extend([f"{number}{marker} Synthetic heading", f"Synthetic content for section {number}."])
            if number == "5.2":
                lines.append("\fSynthetic running Manual de Políticas e Procedimentos")
                lines.append("Synthetic continuation across a page break.")
        lines.append("                         Página 2")
        return "\n".join(lines).split("\f")

    def test_complete_structure_and_page_continuations(self):
        catalog = parse_policy_pages(self.synthetic_pages(), document_name="synthetic.pdf", source_sha256="0" * 64)
        self.assertEqual(len(catalog["policies"]), 29)
        section = next(record for record in catalog["policies"] if record["source"]["section"] == "5.2")
        self.assertEqual(section["source"]["pages"], [1, 2])
        self.assertIn("Synthetic continuation across a page break.", section["content"])
        self.assertNotIn("Synthetic running", section["content"])

    def test_unknown_version_and_missing_sections_require_manual_review(self):
        pages = self.synthetic_pages()
        for invalid in [["Synthetic empty manual"], [pages[0].replace("Versão 2.1", "Versão 9.0")], pages[:-1], []]:
            with self.assertRaises(PolicyPreparationError):
                parse_policy_pages(invalid, document_name="synthetic.pdf", source_sha256="0" * 64)
