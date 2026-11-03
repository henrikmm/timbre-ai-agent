"""Copy all required original materials into an ignored local raw directory."""

import argparse
import hashlib
from pathlib import Path
import sys
import unicodedata

from timbre.database.schema import TABLE_NAMES
from timbre.local_files import write_private


def prepare_sources(source_dir: Path, raw_dir: Path) -> dict[str, str]:
    """Require the complete supplied set, copying bytes without translation or editing."""
    expected = [f"desafio_tecnico_ai_eng - {table}.csv" for table in TABLE_NAMES]
    expected += ["políticas_da_loja.pdf", "desafio_tecnico_ai_eng_artefact.pdf"]
    candidates = {}
    for name in expected:
        matches = [path for path in source_dir.rglob("*") if path.is_file()
                   and unicodedata.normalize("NFC", path.name) == name]
        if len(matches) != 1:
            raise ValueError(f"{name}: expected exactly one supplied file; found {len(matches)}")
        candidates[name] = matches[0]
    # Locate everything first, so an incomplete input set is never silently accepted.
    snapshots = {name: path.read_bytes() for name, path in candidates.items()}
    source_paths = {path.resolve() for path in candidates.values()}
    # Preflight the entire destination set before writing even one byte.
    if any((raw_dir / name).resolve() in source_paths for name in snapshots):
        raise ValueError("source and raw directories must be different")
    for name, contents in snapshots.items():
        destination = raw_dir / name
        write_private(destination, contents)
    return {name: hashlib.sha256(contents).hexdigest() for name, contents in snapshots.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    arguments = parser.parse_args()
    try:
        hashes = prepare_sources(arguments.source_dir, arguments.raw_dir)
    except (OSError, ValueError) as error:
        print(f"Source preparation failed: {error}", file=sys.stderr)
        return 1
    print(f"Prepared {len(hashes)} original files; file bytes are unchanged. Local outputs are restricted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
