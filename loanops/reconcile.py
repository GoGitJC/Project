"""Compare the source funded population with the reporting extract.

Totals come from SQL. Row classification uses the SQL join below plus
Pandas. Signed impacts are defined so they add back to the reporting
funded total without counting a loan's true balance twice:

    reporting funded total
        = source funded total
        + missing impact            (negative: funded loan absent)
        + incorrect status impact   (signed change on the first extract row)
        + incorrect amount impact   (reporting − source, both funded)
        + duplicate impact          (funded dollars on extra rows only)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from loanops.constants import (
    DB_PATH,
    DUPLICATE,
    EXTRACT_NAME,
    INCORRECT_AMOUNT,
    INCORRECT_STATUS,
    MISSING,
    STATUSES,
)
from loanops.database import connect

# One row per source loan. copies is null when the loan is absent.
# extra_funded_amount is the funded dollars on every reporting row except
# the earliest report_row_id (the legitimate copy).
COMPARISON_SQL = """
WITH canon AS (
    SELECT
        loan_id,
        MIN(report_row_id) AS canonical_row_id,
        COUNT(*) AS copies
    FROM reporting_extract
    GROUP BY loan_id
),
extras AS (
    SELECT
        r.loan_id,
        COALESCE(
            SUM(CASE WHEN r.status = 'Funded' THEN r.loan_amount ELSE 0 END),
            0
        ) AS extra_funded_amount,
        GROUP_CONCAT(r.report_row_id) AS extra_row_ids
    FROM reporting_extract AS r
    INNER JOIN canon AS c ON c.loan_id = r.loan_id
    WHERE r.report_row_id <> c.canonical_row_id
    GROUP BY r.loan_id
)
SELECT
    s.loan_id,
    s.property_type,
    s.property_state,
    s.funding_date,
    s.status AS source_status,
    s.loan_amount AS source_amount,
    r.status AS reporting_status,
    r.loan_amount AS reporting_amount,
    c.canonical_row_id,
    c.copies,
    COALESCE(e.extra_funded_amount, 0) AS extra_funded_amount,
    e.extra_row_ids
FROM loans AS s
LEFT JOIN canon AS c ON c.loan_id = s.loan_id
LEFT JOIN reporting_extract AS r ON r.report_row_id = c.canonical_row_id
LEFT JOIN extras AS e ON e.loan_id = s.loan_id
ORDER BY s.loan_id
"""

EXCEPTION_COLUMNS = [
    "loan_id",
    "discrepancy_type",
    "property_type",
    "property_state",
    "funding_date",
    "source_status",
    "reporting_status",
    "source_amount",
    "reporting_amount",
    "canonical_row_id",
    "reporting_copies",
    "extra_copies",
    "extra_row_ids",
    "signed_impact",
]


class ReconciliationError(RuntimeError):
    """Raised when classified impacts do not bridge the two funded totals."""


@dataclass
class ReconResult:
    source_funded_total: int
    reporting_funded_total: int
    net_variance: int
    gross_absolute_impact: int
    unexplained: int
    source_loan_count: int
    source_funded_count: int
    reporting_row_count: int
    reporting_funded_row_count: int
    extract_name: str
    exceptions: pd.DataFrame
    bridge: pd.DataFrame
    status_breakdown: pd.DataFrame


def _scalar(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    value = connection.execute(sql, params).fetchone()[0]
    return int(value or 0)


def _blank(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _as_int(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return int(value)


def _classify(comparison: pd.DataFrame) -> pd.DataFrame:
    """Turn the SQL comparison into exception rows with signed impacts."""
    rows: list[dict] = []
    for record in comparison.itertuples(index=False):
        copies = 0 if pd.isna(record.copies) else int(record.copies)
        source_amount = int(record.source_amount)
        source_funded = source_amount if record.source_status == "Funded" else 0
        reporting_amount = _as_int(record.reporting_amount)
        reporting_status = _blank(record.reporting_status)
        canon_funded = (
            reporting_amount
            if reporting_status == "Funded" and reporting_amount is not None
            else 0
        )
        canonical_delta = canon_funded - source_funded
        extra_funded = int(record.extra_funded_amount)
        extra_copies = max(copies - 1, 0)
        base = {
            "loan_id": record.loan_id,
            "property_type": record.property_type,
            "property_state": record.property_state,
            "funding_date": _blank(record.funding_date),
            "source_status": record.source_status,
            "reporting_status": reporting_status,
            "source_amount": source_amount,
            "reporting_amount": reporting_amount,
            "canonical_row_id": _as_int(record.canonical_row_id),
            "reporting_copies": copies,
            "extra_copies": extra_copies,
            "extra_row_ids": _blank(record.extra_row_ids),
        }
        if copies == 0 and record.source_status == "Funded":
            rows.append(
                {
                    **base,
                    "discrepancy_type": MISSING,
                    "extra_copies": 0,
                    "signed_impact": -source_amount,
                }
            )
            continue
        if copies == 0:
            continue

        status_changes_funded_total = (
            record.source_status != reporting_status and canonical_delta != 0
        )
        amount_changes_funded_total = (
            record.source_status == "Funded"
            and reporting_status == "Funded"
            and reporting_amount is not None
            and reporting_amount != source_amount
        )
        if status_changes_funded_total:
            rows.append(
                {
                    **base,
                    "discrepancy_type": INCORRECT_STATUS,
                    "signed_impact": canonical_delta,
                }
            )
        elif amount_changes_funded_total:
            rows.append(
                {
                    **base,
                    "discrepancy_type": INCORRECT_AMOUNT,
                    "signed_impact": reporting_amount - source_amount,
                }
            )
        if copies > 1:
            rows.append(
                {
                    **base,
                    "discrepancy_type": DUPLICATE,
                    "signed_impact": extra_funded,
                }
            )

    frame = pd.DataFrame(rows, columns=EXCEPTION_COLUMNS)
    if frame.empty:
        return frame
    # Pandas turns None into NaN inside mixed columns. Keep real nulls so
    # "not in the extract" stays distinct from a status or a date.
    for column in ("reporting_status", "funding_date", "extra_row_ids"):
        frame[column] = [None if pd.isna(value) else value for value in frame[column]]
    type_order = {name: index for index, name in enumerate(
        (MISSING, INCORRECT_STATUS, INCORRECT_AMOUNT, DUPLICATE)
    )}
    frame["_order"] = frame["discrepancy_type"].map(type_order)
    frame = frame.sort_values(["_order", "loan_id"]).drop(columns="_order")
    frame["signed_impact"] = frame["signed_impact"].astype(int)
    return frame.reset_index(drop=True)


def _sum_mask(exceptions: pd.DataFrame, mask: pd.Series) -> int:
    if exceptions.empty:
        return 0
    return int(exceptions.loc[mask, "signed_impact"].sum())


def _bridge(source_funded_total: int, exceptions: pd.DataFrame) -> pd.DataFrame:
    if exceptions.empty:
        missing = status_dropped = status_added = amount_delta = duplicates = 0
    else:
        kind = exceptions["discrepancy_type"]
        status = kind.eq(INCORRECT_STATUS)
        missing = _sum_mask(exceptions, kind.eq(MISSING))
        status_dropped = _sum_mask(
            exceptions, status & exceptions["source_status"].eq("Funded")
        )
        status_added = _sum_mask(
            exceptions, status & ~exceptions["source_status"].eq("Funded")
        )
        amount_delta = _sum_mask(exceptions, kind.eq(INCORRECT_AMOUNT))
        duplicates = _sum_mask(exceptions, kind.eq(DUPLICATE))

    steps = [
        ("Source funded total", source_funded_total, "absolute"),
        ("Missing from reporting", missing, "relative"),
        ("Reported as not funded", status_dropped, "relative"),
        ("Reported as funded in error", status_added, "relative"),
        ("Amount differences", amount_delta, "relative"),
        ("Duplicate extra copies", duplicates, "relative"),
    ]
    running = 0
    records = []
    for label, amount, measure in steps:
        if measure == "absolute":
            running = amount
        else:
            running += amount
        records.append(
            {
                "step": label,
                "measure": measure,
                "amount": amount,
                "running_total": running,
            }
        )
    records.append(
        {
            "step": "Reporting funded total",
            "measure": "total",
            "amount": running,
            "running_total": running,
        }
    )
    return pd.DataFrame(records)


def _status_breakdown(connection: sqlite3.Connection) -> pd.DataFrame:
    source = pd.read_sql_query(
        """
        SELECT status, COUNT(*) AS source_loans, SUM(loan_amount) AS source_amount
        FROM loans
        GROUP BY status
        """,
        connection,
    )
    reporting = pd.read_sql_query(
        """
        SELECT
            status,
            COUNT(*) AS reporting_rows,
            COUNT(DISTINCT loan_id) AS reporting_loans,
            SUM(loan_amount) AS reporting_amount
        FROM reporting_extract
        GROUP BY status
        """,
        connection,
    )
    frame = pd.DataFrame({"status": list(STATUSES)})
    frame = frame.merge(source, on="status", how="left")
    frame = frame.merge(reporting, on="status", how="left")
    for column in (
        "source_loans",
        "source_amount",
        "reporting_rows",
        "reporting_loans",
        "reporting_amount",
    ):
        frame[column] = frame[column].fillna(0).astype(int)
    return frame


def reconcile(db_path: Path | None = None) -> ReconResult:
    """Reconcile source funded dollars to the reporting extract."""
    path = Path(db_path) if db_path else DB_PATH
    connection = connect(path)
    try:
        source_funded_total = _scalar(
            connection,
            "SELECT COALESCE(SUM(loan_amount), 0) FROM loans WHERE status = 'Funded'",
        )
        reporting_funded_total = _scalar(
            connection,
            """
            SELECT COALESCE(SUM(loan_amount), 0)
            FROM reporting_extract
            WHERE status = 'Funded'
            """,
        )
        source_loan_count = _scalar(connection, "SELECT COUNT(*) FROM loans")
        source_funded_count = _scalar(
            connection, "SELECT COUNT(*) FROM loans WHERE status = 'Funded'"
        )
        reporting_row_count = _scalar(connection, "SELECT COUNT(*) FROM reporting_extract")
        reporting_funded_row_count = _scalar(
            connection,
            "SELECT COUNT(*) FROM reporting_extract WHERE status = 'Funded'",
        )
        extract_row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'extract_name'"
        ).fetchone()
        extract_name = str(extract_row["value"]) if extract_row else EXTRACT_NAME
        comparison = pd.read_sql_query(COMPARISON_SQL, connection)
        status_breakdown = _status_breakdown(connection)
    finally:
        connection.close()

    exceptions = _classify(comparison)
    explained = int(exceptions["signed_impact"].sum()) if not exceptions.empty else 0
    net_variance = reporting_funded_total - source_funded_total
    unexplained = net_variance - explained
    if unexplained != 0:
        raise ReconciliationError(
            "Tie-out failed: "
            f"source {source_funded_total} + explained {explained} "
            f"= {source_funded_total + explained}, reporting funded total is "
            f"{reporting_funded_total} (residual {unexplained})."
        )
    bridge = _bridge(source_funded_total, exceptions)
    if int(bridge.iloc[-1]["running_total"]) != reporting_funded_total:
        raise ReconciliationError("Bridge running total does not equal the reporting funded total.")
    gross = int(exceptions["signed_impact"].abs().sum()) if not exceptions.empty else 0
    return ReconResult(
        source_funded_total=source_funded_total,
        reporting_funded_total=reporting_funded_total,
        net_variance=net_variance,
        gross_absolute_impact=gross,
        unexplained=unexplained,
        source_loan_count=source_loan_count,
        source_funded_count=source_funded_count,
        reporting_row_count=reporting_row_count,
        reporting_funded_row_count=reporting_funded_row_count,
        extract_name=extract_name,
        exceptions=exceptions,
        bridge=bridge,
        status_breakdown=status_breakdown,
    )
