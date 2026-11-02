"""Internal database connections, never intended as conversational tools."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import unicodedata


def search_key(value: str) -> str:
    """Make catalog searches accent-insensitive without changing stored data."""
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


@contextmanager
def connect_database(path: str | Path, *, readonly: bool = True) -> Iterator[sqlite3.Connection]:
    """Open an internal connection; reads cannot create a missing database."""
    database_path = Path(path).resolve()
    if readonly:
        connection = sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(database_path, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        if readonly:
            connection.execute("PRAGMA query_only = ON")
        connection.create_function("search_key", 1, search_key, deterministic=True)
        yield connection
    finally:
        connection.close()
