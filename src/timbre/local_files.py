"""Small helpers for private, atomically replaced local artifacts."""

import os
from pathlib import Path
import tempfile


def write_private(path: str | Path, content: bytes) -> None:
    """Write a generated artifact with owner-only permissions, then replace atomically."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
