"""Read-only frames for the workspace.

These helpers aggregate loans and exception rows that reconciliation already
produced. They do not classify defects or recompute the funded tie-out.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from loanops.constants import DISCREPANCY_LABELS, DUPLICATE, INCORRECT_AMOUNT, INCORRECT_STATUS, MISSING
from loanops.database import connect
from loanops.formatting import money

# Display grouping for the workspace. Not a risk model and not used by reconcile().
SEVERITY_BY_TYPE = {
    MISSING: "Critical",
    DUPLICATE: "Critical",
    INCORRECT_STATUS: "Warning",
    INCORRECT_AMOUNT: "Attention",
}
SEVERITY_TONE = {
    "Critical": "critical",
    "Warning": "warning",
    "Attention": "attention",
}


def load_source_loans(db_path: Path | None = None) -> pd.DataFrame:
    """Return the source portfolio for charts. Reconciliation stays in reconcile()."""
    with connect(db_path) as connection:
        frame = pd.read_sql_query(
            """
            SELECT loan_id, borrower_name, property_type, property_state,
                   loan_purpose, application_date, funding_date,
                   loan_amount, interest_rate, status
            FROM loans
            ORDER BY loan_id
            """,
            connection,
        )
    frame["loan_amount"] = frame["loan_amount"].astype(int)
    return frame


def funding_trend(loans: pd.DataFrame) -> pd.DataFrame:
    """Source funded volume by funding month. Undated funded loans stay in the sum."""
    funded = loans.loc[loans["status"].eq("Funded")].copy()
    month = funded["funding_date"].fillna("Undated").astype(str).str.slice(0, 7)
    funded = funded.assign(month=month)
    grouped = (
        funded.groupby("month", as_index=False)
        .agg(funded_loans=("loan_id", "size"), funded_volume=("loan_amount", "sum"))
        .sort_values("month")
    )
    grouped["funded_loans"] = grouped["funded_loans"].astype(int)
    grouped["funded_volume"] = grouped["funded_volume"].astype(int)
    return grouped.reset_index(drop=True)


def mix_by(loans: pd.DataFrame, column: str, *, funded_only: bool = True) -> pd.DataFrame:
    frame = loans.loc[loans["status"].eq("Funded")] if funded_only else loans
    grouped = (
        frame.groupby(column, as_index=False)
        .agg(loans=("loan_id", "size"), volume=("loan_amount", "sum"))
        .sort_values(["volume", column], ascending=[False, True])
    )
    grouped["loans"] = grouped["loans"].astype(int)
    grouped["volume"] = grouped["volume"].astype(int)
    return grouped.reset_index(drop=True)


def exception_summary(exceptions: pd.DataFrame) -> pd.DataFrame:
    """One row per discrepancy type, including types with no open rows."""
    order = list(DISCREPANCY_LABELS)
    if exceptions.empty:
        grouped = pd.DataFrame({"discrepancy_type": order, "loans": 0, "signed_impact": 0})
    else:
        aggregated = exceptions.groupby("discrepancy_type", as_index=False).agg(
            loans=("loan_id", "size"),
            signed_impact=("signed_impact", "sum"),
        )
        grouped = pd.DataFrame({"discrepancy_type": order}).merge(
            aggregated, on="discrepancy_type", how="left"
        )
        grouped["loans"] = grouped["loans"].fillna(0)
        grouped["signed_impact"] = grouped["signed_impact"].fillna(0)
    grouped["loans"] = grouped["loans"].astype(int)
    grouped["signed_impact"] = grouped["signed_impact"].astype(int)
    grouped["absolute_impact"] = grouped["signed_impact"].abs().astype(int)
    grouped["label"] = grouped["discrepancy_type"].map(DISCREPANCY_LABELS)
    grouped["severity"] = grouped["discrepancy_type"].map(SEVERITY_BY_TYPE)
    return grouped


def severity_summary(summary: pd.DataFrame) -> pd.DataFrame:
    order = ["Critical", "Warning", "Attention"]
    grouped = summary.groupby("severity", as_index=False).agg(
        loans=("loans", "sum"),
        absolute_impact=("absolute_impact", "sum"),
        signed_impact=("signed_impact", "sum"),
    )
    grouped = pd.DataFrame({"severity": order}).merge(grouped, on="severity", how="left").fillna(0)
    for column in ("loans", "absolute_impact", "signed_impact"):
        grouped[column] = grouped[column].astype(int)
    return grouped


def impact_by_state(exceptions: pd.DataFrame) -> pd.DataFrame:
    if exceptions.empty:
        return pd.DataFrame(columns=["property_state", "loans", "absolute_impact", "signed_impact"])
    frame = exceptions.copy()
    frame["absolute_impact"] = frame["signed_impact"].abs()
    grouped = frame.groupby("property_state", as_index=False).agg(
        loans=("loan_id", "size"),
        absolute_impact=("absolute_impact", "sum"),
        signed_impact=("signed_impact", "sum"),
    )
    for column in ("loans", "absolute_impact", "signed_impact"):
        grouped[column] = grouped[column].astype(int)
    return grouped.sort_values(["absolute_impact", "property_state"], ascending=[False, True]).reset_index(
        drop=True
    )


def filter_exceptions(
    exceptions: pd.DataFrame,
    *,
    type_label: str,
    state: str,
    property_type: str,
    severity: str,
    query: str,
    label_to_type: dict[str, str],
) -> pd.DataFrame:
    view = exceptions
    if type_label != "All":
        view = view.loc[view["discrepancy_type"].eq(label_to_type[type_label])]
    if state != "All":
        view = view.loc[view["property_state"].eq(state)]
    if property_type != "All":
        view = view.loc[view["property_type"].eq(property_type)]
    if severity != "All":
        view = view.loc[view["discrepancy_type"].map(SEVERITY_BY_TYPE).eq(severity)]
    needle = query.strip()
    if needle:
        view = view.loc[view["loan_id"].str.contains(needle, case=False, na=False, regex=False)]
    return view.reset_index(drop=True)


def preferred_loan(exceptions: pd.DataFrame, discrepancy_type: str, preferred: str) -> str | None:
    values = exceptions.loc[exceptions["discrepancy_type"].eq(discrepancy_type), "loan_id"].astype(str)
    listed = values.tolist()
    if preferred in listed:
        return preferred
    return listed[0] if listed else None


def tie_out_status(unexplained: int, open_count: int) -> tuple[str, str, str]:
    """Return label, tone, and hint from the residual and the open-row count."""
    if unexplained != 0:
        return (
            "Break",
            "critical",
            f"Unexplained residual {money(unexplained)}. The bridge does not close.",
        )
    if open_count == 0:
        return (
            "Clear",
            "success",
            "Funded totals match and no exceptions are open.",
        )
    return (
        "Explained",
        "warning",
        f"Unexplained residual {money(unexplained)}. Exceptions are still open.",
    )


def _amount_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return "Not in extract"
    return money(int(value))


def rank_exceptions(frame: pd.DataFrame) -> pd.DataFrame:
    """Largest absolute signed impact first, so a row click matches the table."""
    if frame.empty:
        return frame.reset_index(drop=True)
    return (
        frame.assign(_abs=frame["signed_impact"].abs())
        .sort_values(["_abs", "loan_id"], ascending=[False, True])
        .drop(columns="_abs")
        .reset_index(drop=True)
    )


def exception_display(frame: pd.DataFrame) -> pd.DataFrame:
    """Operator table. Amounts are display strings from money(), not a new tie-out."""
    columns = [
        "Loan",
        "Severity",
        "Discrepancy",
        "Signed impact",
        "Source status",
        "Reporting status",
        "Source amount",
        "Reporting amount",
        "State",
        "Property",
        "Funding date",
        "Extract rows",
        "Extra copies",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    ordered = frame
    return pd.DataFrame(
        {
            "Loan": ordered["loan_id"].tolist(),
            "Severity": ordered["discrepancy_type"].map(SEVERITY_BY_TYPE).tolist(),
            "Discrepancy": ordered["discrepancy_type"].map(DISCREPANCY_LABELS).tolist(),
            "Signed impact": [money(int(value)) for value in ordered["signed_impact"]],
            "Source status": ordered["source_status"].tolist(),
            "Reporting status": ordered["reporting_status"].fillna("Not in extract").astype(str).tolist(),
            "Source amount": [_amount_text(value) for value in ordered["source_amount"]],
            "Reporting amount": [_amount_text(value) for value in ordered["reporting_amount"]],
            "State": ordered["property_state"].tolist(),
            "Property": ordered["property_type"].tolist(),
            "Funding date": ordered["funding_date"].fillna("—").astype(str).tolist(),
            "Extract rows": ordered["reporting_copies"].astype(int).tolist(),
            "Extra copies": ordered["extra_copies"].astype(int).tolist(),
        }
    )


def exception_export(frame: pd.DataFrame) -> bytes:
    """Numeric CSV for the rows currently in view."""
    if frame.empty:
        columns = [
            "loan_id",
            "severity",
            "discrepancy",
            "property_type",
            "property_state",
            "funding_date",
            "source_status",
            "reporting_status",
            "source_amount",
            "reporting_amount",
            "reporting_copies",
            "extra_copies",
            "signed_impact",
        ]
        return pd.DataFrame(columns=columns).to_csv(index=False).encode("utf-8")
    export = frame.copy()
    export["severity"] = export["discrepancy_type"].map(SEVERITY_BY_TYPE)
    export["discrepancy"] = export["discrepancy_type"].map(DISCREPANCY_LABELS)
    export = export[
        [
            "loan_id",
            "severity",
            "discrepancy",
            "property_type",
            "property_state",
            "funding_date",
            "source_status",
            "reporting_status",
            "source_amount",
            "reporting_amount",
            "reporting_copies",
            "extra_copies",
            "signed_impact",
        ]
    ]
    return export.to_csv(index=False).encode("utf-8")


def status_display(breakdown: pd.DataFrame) -> pd.DataFrame:
    display = breakdown.copy()
    display["Source amount"] = display["source_amount"].map(lambda value: money(int(value)))
    display["Reporting amount"] = display["reporting_amount"].map(lambda value: money(int(value)))
    return pd.DataFrame(
        {
            "Status": display["status"],
            "Source loans": display["source_loans"].astype(int),
            "Source amount": display["Source amount"],
            "Reporting rows": display["reporting_rows"].astype(int),
            "Reporting loans": display["reporting_loans"].astype(int),
            "Reporting amount": display["Reporting amount"],
        }
    )
