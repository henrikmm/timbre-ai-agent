"""Validate and replace a complete CSV snapshot in one SQLite transaction."""

from dataclasses import asdict, dataclass
from datetime import date
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3

from timbre.database.connection import connect_database
from timbre.database.schema import SCHEMA_STATEMENTS, SCHEMA_VERSION, TABLE_NAMES
from timbre.database.values import SQLITE_MAX_INTEGER, scaled_integer, to_cents


class ImportValidationError(ValueError):
    """A safe import error containing locations, never source record values."""


SOURCE_COLUMNS = {
    "categories": ("category_id", "name", "description"),
    "products": ("product_id", "price_brl", "name", "category_id", "description", "stock_quantity", "status", "specs", "created_at"),
    "customers": ("customer_id", "name", "phone", "email", "city"),
    "orders": ("order_id", "customer_id", "order_date", "status", "total_brl", "payment_method", "tracking_code", "estimated_delivery", "notes"),
    "order_items": ("order_id", "quantity", "product_id"),
    "promotions": ("promotion_id", "product_id", "discount_percent", "description", "is_active"),
}
DESTINATION_COLUMNS = {
    table: tuple({"price_brl": "price_cents", "total_brl": "total_cents", "discount_percent": "discount_basis_points"}.get(column, column) for column in columns)
    for table, columns in SOURCE_COLUMNS.items()
}
NULLABLE_COLUMNS = {
    "categories": {"description"},
    "products": {"description", "specs"},
    "customers": {"phone", "email", "city"},
    "orders": {"payment_method", "tracking_code", "estimated_delivery", "notes"},
    "order_items": set(),
    "promotions": {"description"},
}


@dataclass(frozen=True)
class ImportReport:
    """Aggregate evidence safe to print without personal data."""

    counts: dict[str, int]
    source_sha256: dict[str, str]
    schema_version: int = SCHEMA_VERSION

    @property
    def total_records(self) -> int:
        return sum(self.counts.values())

    def to_dict(self) -> dict:
        return {**asdict(self), "total_records": self.total_records}


def discover_csv_files(raw_dir: str | Path) -> dict[str, Path]:
    """Accept canonical or original filenames, rejecting absent/ambiguous sources."""
    directory = Path(raw_dir)
    files = {}
    for table in TABLE_NAMES:
        candidates = [directory / name for name in (f"{table}.csv", f"desafio_tecnico_ai_eng - {table}.csv")]
        matches = [path for path in candidates if path.is_file()]
        if len(matches) != 1:
            raise ImportValidationError(f"{table}: expected exactly one source CSV; found {len(matches)}")
        files[table] = matches[0]
    return files


def _convert_value(table: str, column: str, value: str):
    if value == "":
        if column in NULLABLE_COLUMNS[table]:
            return None
        raise ValueError("required field is empty")
    if column.endswith("_id") or column in {"quantity", "stock_quantity"}:
        if not re.fullmatch(r"0|[1-9][0-9]*", value):
            raise ValueError("expected an unsigned integer")
        integer = int(value)
        minimum = 0 if column == "stock_quantity" else 1
        if not minimum <= integer <= SQLITE_MAX_INTEGER:
            raise ValueError("integer is outside the supported range")
        return integer
    if column in {"price_brl", "total_brl"}:
        return to_cents(value)
    if column == "discount_percent":
        return scaled_integer(value, maximum=10000)
    if column == "is_active":
        if value not in {"0", "1"}:
            raise ValueError("expected boolean 0 or 1")
        return int(value)
    if column in {"created_at", "order_date", "estimated_delivery"}:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("expected an ISO date in YYYY-MM-DD format")
    if column == "specs":
        def reject_constant(_value: str):
            raise ValueError("non-standard JSON constant")
        if not isinstance(json.loads(value, parse_constant=reject_constant), dict):
            raise ValueError("expected a JSON object")
    if not value.strip() and column not in NULLABLE_COLUMNS[table]:
        raise ValueError("required text is blank")
    return value


def read_source_table(table: str, path: Path) -> tuple[list[tuple], str]:
    """Read bytes once so the fingerprint covers the imported snapshot exactly."""
    try:
        contents = path.read_bytes()
        source = io.StringIO(contents.decode("utf-8-sig"), newline="")
        reader = csv.DictReader(source, strict=True)
        columns = reader.fieldnames
        expected = SOURCE_COLUMNS[table]
        if columns is None or len(columns) != len(set(columns)) or set(columns) != set(expected):
            raise ImportValidationError(f"{table}: CSV headers do not match the source schema")
        result = []
        for record_number, row in enumerate(reader, 1):
            if None in row or any(value is None for value in row.values()):
                raise ImportValidationError(f"{table}: record {record_number} has the wrong number of fields")
            record = []
            for column in expected:
                try:
                    record.append(_convert_value(table, column, row[column]))
                except (ValueError, OverflowError):
                    raise ImportValidationError(f"{table}: record {record_number}, field {column} is invalid") from None
            result.append(tuple(record))
        return result, hashlib.sha256(contents).hexdigest()
    except (OSError, UnicodeError, csv.Error):
        raise ImportValidationError(f"{table}: source CSV cannot be read as valid UTF-8 CSV") from None


def import_csvs(raw_dir: str | Path, database_path: str | Path) -> ImportReport:
    """Rebuild all six tables atomically, leaving an existing snapshot intact on failure.

    Call only from trusted local maintenance code. This function is not a tool for
    customers, and does not alter, recalculate, or reconcile source business data.
    """
    files = discover_csv_files(raw_dir)
    destination = Path(database_path).resolve()
    if destination in {path.resolve() for path in files.values()}:
        raise ImportValidationError("database destination must not overwrite a source CSV")
    parsed = {table: read_source_table(table, files[table]) for table in TABLE_NAMES}
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    existed = destination.exists()
    try:
        with connect_database(destination, readonly=False) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, SCHEMA_VERSION}:
                    raise ImportValidationError("unsupported database schema version; import refused")
                for table in reversed(TABLE_NAMES):
                    connection.execute(f"DROP TABLE IF EXISTS {table}")
                for statement in SCHEMA_STATEMENTS:
                    connection.execute(statement)
                for table in TABLE_NAMES:
                    columns = DESTINATION_COLUMNS[table]
                    placeholders = ", ".join("?" for _ in columns)
                    connection.executemany(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                        parsed[table][0],
                    )
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ImportValidationError("foreign-key validation failed")
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ImportValidationError("database integrity validation failed")
                counts = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in TABLE_NAMES}
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        destination.chmod(0o600)
    except (sqlite3.Error, OSError):
        if not existed:
            destination.unlink(missing_ok=True)
        raise ImportValidationError("database import failed; no partial snapshot was committed") from None
    return ImportReport(counts, {table: parsed[table][1] for table in TABLE_NAMES})
