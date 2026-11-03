"""Load explicitly synthetic public fixtures through the ordinary data importer."""

import argparse
from pathlib import Path

from timbre.database.import_data import import_csvs
from timbre.knowledge.policy_loader import PolicyCatalog
from timbre.local_files import write_private


def prepare_demo(database=Path("data/demo/store.db"), policies=Path("local/demo/policies.json")):
    fixtures = Path(__file__).resolve().parents[1] / "tests/fixtures/demo"
    source = fixtures / "policies.synthetic.json"
    PolicyCatalog(source)
    report = import_csvs(fixtures, database)
    write_private(policies, source.read_bytes())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = prepare_demo()
    print(f"SYNTHETIC DEMO: {report.total_records} records; not original assessment data.")
    print("Database: data/demo/store.db; policies: local/demo/policies.json")
    print("Use --config config/demo.toml (CLI) or TIMBRE_CONFIG=config/demo.toml (web).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
