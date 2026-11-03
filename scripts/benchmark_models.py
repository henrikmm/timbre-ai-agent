"""Plan offline by default; actual inference requires the explicit --live flag."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from timbre.benchmark import main

if __name__ == "__main__":
    raise SystemExit(main())
