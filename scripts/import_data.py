"""Rebuild a local SQLite snapshot and report aggregate counts only."""

import argparse
import json
from pathlib import Path
import sys

from timbre.database.import_data import ImportValidationError, import_csvs
from timbre.local_files import write_private


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--database", type=Path, default=Path("data/store.db"))
    parser.add_argument("--report", type=Path, help="Optional private JSON report with counts and source hashes")
    arguments = parser.parse_args()
    try:
        report = import_csvs(arguments.raw_dir, arguments.database)
        if arguments.report is not None:
            write_private(arguments.report, (json.dumps(report.to_dict(), indent=2) + "\n").encode())
    except (ImportValidationError, OSError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    for table, count in report.counts.items():
        print(f"{table}: {count}")
    print(f"Total: {report.total_records}; integrity: ok; foreign keys: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
