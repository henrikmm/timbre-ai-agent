"""Validate a local policy catalog and retrieve complete sections by topic."""

from copy import deepcopy
import json
from pathlib import Path
import re


class PolicyFileMissing(FileNotFoundError):
    """The local restricted catalog has not been prepared."""


class InvalidPolicyCatalog(ValueError):
    """The JSON or its source/hierarchy metadata does not satisfy the catalog contract."""


class UnknownPolicyTopic(LookupError):
    """No policy matches the requested topic."""


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidPolicyCatalog("duplicate JSON object key")
        result[key] = value
    return result


def _require(condition: bool, description: str) -> None:
    if not condition:
        raise InvalidPolicyCatalog(description)


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_catalog(catalog: object) -> None:
    """Validate the full structure before any record is exposed."""
    _require(isinstance(catalog, dict), "catalog must be an object")
    _require(type(catalog.get("schema_version")) is int and catalog["schema_version"] == 1,
             "unsupported catalog schema version")
    document = catalog.get("document")
    _require(isinstance(document, dict), "document metadata is required")
    for key in ("name", "version", "content_language", "extraction_method"):
        _require(_text(document.get(key)), f"document.{key} must be non-empty text")
    digest = document.get("sha256")
    _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
             "document.sha256 must be a SHA-256 digest")
    page_count = document.get("page_count")
    _require(type(page_count) is int and page_count > 0, "document.page_count must be positive")
    records = catalog.get("policies")
    _require(isinstance(records, list) and len(records) > 0, "policies must be a non-empty array")
    by_id, sections, topics = {}, set(), set()
    for record in records:
        _require(isinstance(record, dict), "each policy must be an object")
        identifier = record.get("id")
        _require(isinstance(identifier, str) and re.fullmatch(r"[a-z][a-z0-9_]*", identifier) is not None,
                 "policy.id must be an English-style identifier")
        _require(identifier not in by_id, "duplicate policy ID")
        topic = record.get("topic")
        _require(isinstance(topic, str) and re.fullmatch(r"[a-z][a-z_]*(?:\.[a-z][a-z_]*)*", topic) is not None,
                 "policy.topic must use a dotted identifier")
        for key in ("title", "content"):
            _require(_text(record.get(key)), f"policy.{key} must be non-empty text")
        _require("parent_id" in record and (record["parent_id"] is None or _text(record["parent_id"])),
                 "policy.parent_id must be null or a policy ID")
        related = record.get("related_topics")
        _require(isinstance(related, list) and all(_text(item) for item in related),
                 "policy.related_topics must be an array of topic identifiers")
        _require(len(related) == len(set(related)), "duplicate related topic")
        source = record.get("source")
        _require(isinstance(source, dict), "policy.source is required")
        _require(source.get("document") == document["name"] and source.get("version") == document["version"]
                 and source.get("sha256") == digest, "policy source must match document metadata")
        section = source.get("section")
        _require(_text(section), "source.section must be non-empty text")
        _require(section not in sections, "duplicate source section")
        sections.add(section)
        pages = source.get("pages")
        _require(isinstance(pages, list) and len(pages) > 0
                 and all(type(page) is int and 1 <= page <= page_count for page in pages),
                 "source.pages must contain valid document page numbers")
        _require(pages == sorted(set(pages)), "source.pages must be sorted and unique")
        _require(type(source.get("page")) is int and source["page"] == pages[0],
                 "source.page must match the first source page")
        by_id[identifier] = record
        topics.add(topic)
    for record in records:
        seen, parent = {record["id"]}, record["parent_id"]
        while parent is not None:
            _require(parent in by_id, "missing parent policy")
            _require(parent not in seen, "cyclic policy hierarchy")
            seen.add(parent)
            parent = by_id[parent]["parent_id"]
        for related in record["related_topics"]:
            _require(any(topic == related or topic.startswith(related + ".") for topic in topics),
                     "related topic does not exist in this catalog")


class PolicyCatalog:
    """A validated snapshot; returned dictionaries cannot mutate the cached records."""

    def __init__(self, path: str | Path):
        try:
            with Path(path).open(encoding="utf-8") as source:
                catalog = json.load(source, object_pairs_hook=_unique_object)
        except FileNotFoundError:
            raise PolicyFileMissing("policy catalog missing; run scripts/prepare_policies.py") from None
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise InvalidPolicyCatalog("policy catalog is not readable UTF-8 JSON") from None
        validate_catalog(catalog)
        self._catalog = catalog
        self._by_id = {record["id"]: record for record in catalog["policies"]}

    @property
    def document(self) -> dict:
        return deepcopy(self._catalog["document"])

    @property
    def section_count(self) -> int:
        return len(self._catalog["policies"])

    def list_topics(self) -> list[str]:
        return sorted({record["topic"] for record in self._catalog["policies"]})

    def get_store_policy(self, topic: str, *, include_related: bool = False) -> list[dict]:
        """Match a topic and descendants, always retaining their parent introductions.

        Set include_related explicitly to add one hop of cross-referenced topics.
        Unknown topics fail clearly instead of returning invented policy content.
        """
        if not isinstance(topic, str) or re.fullmatch(r"[a-z][a-z_]*(?:\.[a-z][a-z_]*)*", topic) is None:
            raise UnknownPolicyTopic("unknown policy topic")
        records = self._catalog["policies"]
        matched = [record for record in records if record["topic"] == topic or record["topic"].startswith(topic + ".")]
        if not matched:
            raise UnknownPolicyTopic("unknown policy topic")
        selected = {record["id"] for record in matched}
        if include_related:
            related = {item for record in matched for item in record["related_topics"]}
            selected.update(record["id"] for record in records
                            if any(record["topic"] == item or record["topic"].startswith(item + ".") for item in related))
        for identifier in tuple(selected):
            parent = self._by_id[identifier]["parent_id"]
            while parent is not None:
                selected.add(parent)
                parent = self._by_id[parent]["parent_id"]
        return deepcopy([record for record in records if record["id"] in selected])


def get_store_policy(topic: str, *, policies_path: str | Path = "knowledge/policies.json",
                     include_related: bool = False) -> list[dict]:
    """Convenience entry point; no automatic topic selection or external service."""
    return PolicyCatalog(policies_path).get_store_policy(topic, include_related=include_related)
