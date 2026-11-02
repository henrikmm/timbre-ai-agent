"""Local, version-specific PDF section extraction; business text stays in Portuguese."""

import hashlib
from pathlib import Path
import re
import shutil
import subprocess

from timbre.knowledge.policy_loader import validate_catalog


class PolicyPreparationError(ValueError):
    """Source text or extraction prerequisites do not match the reviewed manual."""


# English metadata only. Original headings remain in each record's content.
# This map describes the reviewed version's structure, not its business rules.
SECTION_METADATA = {
    "cover": ("manual_cover", "store", "Manual cover and publication details", ()),
    "1": ("store_overview", "store.overview", "Store overview and scope", ("whatsapp.guidelines",)),
    "1.1": ("store_mission", "store.mission", "Mission", ()),
    "1.2": ("store_contacts", "store.contacts", "Company information and contacts", ("whatsapp",)),
    "2": ("opening_hours", "hours", "Opening hours", ("whatsapp.guidelines",)),
    "3": ("payment_methods", "payments", "Payment methods", ("promotions.rules",)),
    "3.1": ("payment_installments", "payments.installments", "Installment rules", ("promotions.rules",)),
    "4": ("returns_overview", "returns", "Exchanges and returns", ("warranty",)),
    "4.1": ("returns_online", "returns.online", "Online purchase withdrawal", ("returns.exclusions", "escalation")),
    "4.2": ("returns_defects", "returns.defects", "Defective-product exchanges", ("warranty", "returns.exclusions")),
    "4.3": ("returns_preference", "returns.preference", "Preference-based exchanges", ("returns.exclusions",)),
    "4.4": ("returns_exclusions", "returns.exclusions", "Exchange exclusions", ("escalation",)),
    "5": ("shipping_overview", "shipping", "Shipping and deliveries", ("tracking",)),
    "5.1": ("shipping_local", "shipping.local", "Metropolitan deliveries", ()),
    "5.2": ("shipping_other_cities", "shipping.other_cities", "Deliveries to other cities", ("tracking",)),
    "5.3": ("tracking", "tracking", "Tracking codes", ("privacy",)),
    "6": ("promotions_overview", "promotions", "Promotions and discounts", ()),
    "6.1": ("promotion_campaigns", "promotions.campaigns", "Campaign types", ("promotions.rules",)),
    "6.2": ("promotion_rules", "promotions.rules", "Promotion rules", ("payments",)),
    "7": ("whatsapp_overview", "whatsapp", "WhatsApp service", ("store.contacts", "hours")),
    "7.1": ("whatsapp_guidelines", "whatsapp.guidelines", "Service guidelines", ("hours", "store.overview")),
    "7.2": ("whatsapp_workflow", "whatsapp.workflow", "Standard service workflow", ("privacy",)),
    "7.3": ("whatsapp_exceptions", "whatsapp.exceptions", "Special service situations", ("escalation",)),
    "8": ("warranty_overview", "warranty", "Warranty", ("returns.defects",)),
    "8.1": ("warranty_statutory", "warranty.statutory", "Statutory warranty", ()),
    "8.2": ("warranty_manufacturer", "warranty.manufacturer", "Manufacturer warranty", ()),
    "8.3": ("warranty_exclusions", "warranty.exclusions", "Warranty exclusions", ("escalation",)),
    "9": ("privacy", "privacy", "Privacy and data protection", ()),
    "10": ("escalation", "escalation", "Final provisions and management escalation", ("whatsapp.exceptions",)),
}


def is_page_artifact(line: str) -> bool:
    """Recognize only the repeated running header and printed page number."""
    stripped = line.strip()
    return bool(re.fullmatch(r"Página\s+\d+", stripped)
                or re.fullmatch(r".+\s+Manual de Políticas e Procedimentos", stripped))


def parse_policy_pages(pages: list[str], *, document_name: str, source_sha256: str) -> dict:
    """Preserve every non-header/footer line in its original section and page span."""
    if not pages or not any(page.strip() for page in pages):
        raise PolicyPreparationError("policy document has no extractable text")
    version_match = re.search(r"Versão\s+(\d+(?:\.\d+)*)", pages[0])
    if version_match is None or version_match.group(1) != "2.1":
        raise PolicyPreparationError("manual version is not the reviewed version 2.1")
    version = version_match.group(1)
    sections = {"cover": {"lines": [], "pages": set()}}
    current = "cover"
    heading_pattern = re.compile(r"^([1-9][0-9]*(?:\.[0-9]+)*)\.?\s+(\S.*)$")
    for page_number, page in enumerate(pages, 1):
        for line in page.splitlines():
            if is_page_artifact(line):
                continue
            heading = heading_pattern.match(line)
            if heading is not None:
                section = heading.group(1)
                if section not in SECTION_METADATA or section in sections:
                    raise PolicyPreparationError(f"unexpected or repeated section on page {page_number}")
                current = section
                sections[current] = {"lines": [], "pages": set()}
            sections[current]["lines"].append(line.rstrip())
            if line.strip():
                sections[current]["pages"].add(page_number)
    if tuple(sections) != tuple(SECTION_METADATA):
        raise PolicyPreparationError("manual sections differ from the reviewed structure; manual review required")
    records = []
    for section, block in sections.items():
        identifier, topic, title, related = SECTION_METADATA[section]
        parent_section = section.rsplit(".", 1)[0] if "." in section else None
        source_pages = sorted(block["pages"])
        records.append({
            "id": identifier, "topic": topic, "title": title,
            "parent_id": SECTION_METADATA[parent_section][0] if parent_section is not None else None,
            "content": "\n".join(block["lines"]).strip(),
            "source": {"document": document_name, "version": version, "section": section,
                       "page": source_pages[0], "pages": source_pages, "sha256": source_sha256},
            "related_topics": list(related),
        })
    catalog = {
        "schema_version": 1,
        "document": {"name": document_name, "version": version, "sha256": source_sha256,
                     "page_count": len(pages), "content_language": "pt-BR",
                     "extraction_method": "pdftotext -layout; section-based extraction; running headers and page numbers removed"},
        "policies": records,
    }
    validate_catalog(catalog)
    return catalog


def extract_policy_catalog(pdf_path: str | Path) -> dict:
    """Use local Poppler only; refuse unreviewed layouts instead of guessing."""
    path = Path(pdf_path)
    if not path.is_file():
        raise PolicyPreparationError("source policy PDF is missing")
    executable = shutil.which("pdftotext")
    if executable is None:
        raise PolicyPreparationError("pdftotext is required for preparation; install Poppler")
    try:
        source_bytes = path.read_bytes()
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        # Hash and extract the same byte snapshot even if the input path changes.
        result = subprocess.run([executable, "-layout", "-enc", "UTF-8", "-", "-"],
                                input=source_bytes, capture_output=True, check=True, timeout=30)
        pages = result.stdout.decode("utf-8").split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
    except (OSError, UnicodeError, subprocess.SubprocessError):
        raise PolicyPreparationError("local PDF text extraction failed") from None
    return parse_policy_pages(pages, document_name=path.name, source_sha256=source_digest)
