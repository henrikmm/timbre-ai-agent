"""Prepare the ignored policy catalog from the complete original manual."""

import argparse
import json
from pathlib import Path
import sys

from timbre.knowledge.extraction import PolicyPreparationError, extract_policy_catalog
from timbre.knowledge.policy_loader import InvalidPolicyCatalog
from timbre.local_files import write_private


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=Path("data/raw/políticas_da_loja.pdf"))
    parser.add_argument("--output", type=Path, default=Path("knowledge/policies.json"))
    arguments = parser.parse_args()
    try:
        catalog = extract_policy_catalog(arguments.pdf)
        write_private(arguments.output, (json.dumps(catalog, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except (PolicyPreparationError, InvalidPolicyCatalog, OSError) as error:
        print(f"Policy preparation failed: {error}", file=sys.stderr)
        return 1
    print(f"Prepared {len(catalog['policies'])} source sections from {catalog['document']['page_count']} pages.")
    print("Original policy text remains in Portuguese; metadata is in English. Output is restricted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
