"""SQLite system of record and reporting extract."""

import sqlite3
from pathlib import Path

from loanops.constants import DB_PATH

SCHEMA = """
CREATE TABLE loans (
    loan_id TEXT PRIMARY KEY,
    borrower_name TEXT NOT NULL,
    property_type TEXT NOT NULL,
    property_state TEXT NOT NULL,
    loan_purpose TEXT NOT NULL,
    application_date TEXT NOT NULL,
    funding_date TEXT,
    loan_amount INTEGER NOT NULL CHECK (loan_amount > 0),
    interest_rate TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE reporting_extract (
    report_row_id INTEGER PRIMARY KEY,
    loan_id TEXT NOT NULL,
    property_type TEXT NOT NULL,
    property_state TEXT NOT NULL,
    funding_date TEXT,
    loan_amount INTEGER NOT NULL CHECK (loan_amount > 0),
    status TEXT NOT NULL,
    extract_name TEXT NOT NULL
);

CREATE INDEX idx_reporting_loan_id ON reporting_extract (loan_id);

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_database(db_path: Path | None = None) -> Path:
    """Return the SQLite path, building it when the file is absent."""
    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        # Local import avoids a cycle: generate writes through this module's schema.
        from loanops.generate import build_database

        build_database(path)
    return path
