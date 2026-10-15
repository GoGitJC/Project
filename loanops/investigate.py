"""Root-cause notes built only from reconciliation rows.

The wording names the loan, the source values, the reporting values, and
the signed dollar impact already computed by the tie-out. It does not
infer a failure in a system this demo does not contain.
"""

from __future__ import annotations

import pandas as pd

from loanops.constants import DISCREPANCY_LABELS, DUPLICATE, INCORRECT_AMOUNT, INCORRECT_STATUS, MISSING
from loanops.formatting import money


def investigate(
    exceptions: pd.DataFrame,
    *,
    loan_id: str | None = None,
    discrepancy_type: str | None = None,
) -> dict:
    """Summarize one exception or a filtered set of them."""
    subset = exceptions
    if discrepancy_type and discrepancy_type != "All":
        subset = subset.loc[subset["discrepancy_type"].eq(discrepancy_type)]
    if loan_id and loan_id != "All":
        subset = subset.loc[subset["loan_id"].eq(loan_id)]
    subset = subset.reset_index(drop=True)
    if subset.empty:
        return {
            "title": "No matching discrepancy",
            "summary": "No exception row matches this selection.",
            "next_step": "Choose another discrepancy type or loan id from the exception table.",
            "signed_impact": 0,
            "loan_ids": [],
            "comparison": [],
            "lines": [],
        }
    if len(subset) == 1:
        return _one(subset.iloc[0])
    return _many(subset)


def _reporting_amount_text(row: pd.Series) -> str:
    if row["discrepancy_type"] == MISSING or pd.isna(row["reporting_amount"]):
        return "Not in extract"
    return money(int(row["reporting_amount"]))


def _reporting_status_text(row: pd.Series) -> str:
    if row["discrepancy_type"] == MISSING or row["reporting_status"] is None:
        return "Not in extract"
    if isinstance(row["reporting_status"], float) and pd.isna(row["reporting_status"]):
        return "Not in extract"
    return str(row["reporting_status"])


def _funding_date_text(row: pd.Series) -> str:
    value = row["funding_date"]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "None"
    return str(value)


def _comparison(row: pd.Series) -> list[dict[str, str]]:
    reporting_rows = "0" if int(row["reporting_copies"]) == 0 else str(int(row["reporting_copies"]))
    canonical = row["canonical_row_id"]
    canonical_text = "—" if canonical is None or pd.isna(canonical) else str(int(canonical))
    extra_ids = row["extra_row_ids"] if row["extra_row_ids"] else "—"
    return [
        {"field": "Loan ID", "source": str(row["loan_id"]), "reporting": _reporting_identity(row)},
        {"field": "Status", "source": str(row["source_status"]), "reporting": _reporting_status_text(row)},
        {
            "field": "Loan amount",
            "source": money(int(row["source_amount"])),
            "reporting": _reporting_amount_text(row),
        },
        {"field": "Funding date", "source": _funding_date_text(row), "reporting": _reporting_date(row)},
        {
            "field": "Property",
            "source": f"{row['property_type']} · {row['property_state']}",
            "reporting": _reporting_property(row),
        },
        {"field": "Extract rows", "source": "1 source record", "reporting": reporting_rows},
        {"field": "Canonical report row", "source": "—", "reporting": canonical_text},
        {"field": "Extra report rows", "source": "—", "reporting": str(extra_ids)},
        {
            "field": "Signed impact",
            "source": "—",
            "reporting": money(int(row["signed_impact"])),
        },
    ]


def _reporting_identity(row: pd.Series) -> str:
    if int(row["reporting_copies"]) == 0:
        return "Not in extract"
    return str(row["loan_id"])


def _reporting_date(row: pd.Series) -> str:
    if int(row["reporting_copies"]) == 0:
        return "Not in extract"
    return _funding_date_text(row)


def _reporting_property(row: pd.Series) -> str:
    if int(row["reporting_copies"]) == 0:
        return "Not in extract"
    return f"{row['property_type']} · {row['property_state']}"


def _one(row: pd.Series) -> dict:
    kind = str(row["discrepancy_type"])
    label = DISCREPANCY_LABELS[kind]
    loan_id = str(row["loan_id"])
    signed = int(row["signed_impact"])
    summary, next_step = _narrative(row)
    return {
        "title": f"{label} · {loan_id}",
        "summary": summary,
        "next_step": next_step,
        "signed_impact": signed,
        "loan_ids": [loan_id],
        "comparison": _comparison(row),
        "lines": [
            f"{loan_id} · {label} · signed impact {money(signed)}"
        ],
    }


def _narrative(row: pd.Series) -> tuple[str, str]:
    kind = str(row["discrepancy_type"])
    loan_id = str(row["loan_id"])
    source_amount = int(row["source_amount"])
    signed = int(row["signed_impact"])
    property_text = f"{row['property_type']} in {row['property_state']}"
    funding = _funding_date_text(row)

    if kind == MISSING:
        summary = (
            f"Loan {loan_id} is Funded in the source system for {money(source_amount)} "
            f"({property_text}, funding date {funding}). "
            f"The reporting extract has no row for this loan id. "
            f"Signed impact is {money(signed)}, the source amount once. "
            f"That lowers the reporting funded total by {money(source_amount)}."
        )
        next_step = (
            f"Backfill {loan_id} into the reporting extract from the source system "
            f"at {money(source_amount)} with status Funded, then rerun the funded tie-out. "
            f"Before reloading, confirm an extract filter on funding date, channel, or status "
            f"did not drop the loan."
        )
        return summary, next_step

    if kind == DUPLICATE:
        copies = int(row["reporting_copies"])
        extra = int(row["extra_copies"])
        canonical = int(row["canonical_row_id"])
        extra_ids = row["extra_row_ids"]
        copy_word = "copy" if extra == 1 else "copies"
        row_word = "row" if extra == 1 else "rows"
        summary = (
            f"Loan {loan_id} is one Funded loan in the source system for {money(source_amount)} "
            f"({property_text}, funding date {funding}). "
            f"The reporting extract contains {copies} rows for this loan id. "
            f"The first row, report_row_id {canonical}, matches the source status and amount. "
            f"The extra {copy_word} ({extra_ids}) add {money(signed)}. "
            f"That is the extra funded dollars only. The legitimate first copy is not an error, "
            f"and the loan's true balance is not also treated as missing."
        )
        next_step = (
            f"Dedupe the reporting extract on loan_id before publishing funded totals. "
            f"Keep report_row_id {canonical} for {loan_id} and drop extra report "
            f"{row_word} {extra_ids}, which add {money(signed)}."
        )
        return summary, next_step

    if kind == INCORRECT_STATUS:
        reporting_status = str(row["reporting_status"])
        reporting_amount = int(row["reporting_amount"])
        if row["source_status"] == "Funded":
            summary = (
                f"Loan {loan_id} is Funded in the source system for {money(source_amount)} "
                f"({property_text}, funding date {funding}) and is present in the reporting extract. "
                f"The extract maps it to {reporting_status} for {money(reporting_amount)}. "
                f"Because the reporting status is not Funded, the loan drops out of the reporting "
                f"funded total. Signed impact is {money(signed)}, counted once."
            )
            next_step = (
                f"Correct the status mapping for {loan_id}: source status Funded is reported as "
                f"{reporting_status}. Update the status crosswalk and reload the loan so the "
                f"funded total includes {money(source_amount)} once."
            )
            return summary, next_step
        date_note = ""
        if funding == "None":
            date_note = " The source record has no funding date, which matches a non-funded status."
        summary = (
            f"Loan {loan_id} is {row['source_status']} in the source system for {money(source_amount)} "
            f"({property_text}) and is not in the source funded population. "
            f"The reporting extract marks it Funded for {money(reporting_amount)}, so that amount "
            f"is included in the reporting funded total. Signed impact is {money(signed)}, counted once."
            f"{date_note}"
        )
        next_step = (
            f"Correct the status mapping for {loan_id} so source status {row['source_status']} "
            f"is not reported as Funded. Remove {money(reporting_amount)} from the reporting "
            f"funded population and rerun the tie-out."
        )
        return summary, next_step

    if kind == INCORRECT_AMOUNT:
        reporting_amount = int(row["reporting_amount"])
        summary = (
            f"Loan {loan_id} is Funded in both the source system and the reporting extract, "
            f"but the amounts disagree ({property_text}, funding date {funding}). "
            f"Source amount is {money(source_amount)}. Reporting amount is {money(reporting_amount)}. "
            f"Signed impact is {money(signed)}, the difference once. "
            f"The loan stays in both funded populations, so its true balance is not removed."
        )
        next_step = (
            f"Correct the reported amount for {loan_id} from {money(reporting_amount)} "
            f"to the source amount {money(source_amount)}. "
            f"Check for a stale balance or a field mapping that pulled a different amount, "
            f"then rerun the tie-out."
        )
        return summary, next_step

    raise KeyError(f"unknown discrepancy type {kind}")


def _many(subset: pd.DataFrame) -> dict:
    kinds = list(subset["discrepancy_type"].unique())
    signed = int(subset["signed_impact"].sum())
    loan_ids = [str(value) for value in subset["loan_id"]]
    lines = [
        f"{row.loan_id} · {DISCREPANCY_LABELS[row.discrepancy_type]} · signed impact {money(int(row.signed_impact))}"
        for row in subset.itertuples(index=False)
    ]
    if len(kinds) == 1:
        title = DISCREPANCY_LABELS[kinds[0]]
        summary, next_step = _group_narrative(kinds[0], subset, signed)
    else:
        title = "Selected discrepancies"
        parts = []
        for kind in (MISSING, INCORRECT_STATUS, INCORRECT_AMOUNT, DUPLICATE):
            block = subset.loc[subset["discrepancy_type"].eq(kind)]
            if block.empty:
                continue
            parts.append(
                f"{DISCREPANCY_LABELS[kind]}: {len(block)} loan"
                f"{'' if len(block) == 1 else 's'}, signed impact {money(int(block['signed_impact'].sum()))}."
            )
        summary = (
            f"{len(subset)} exception rows are in this selection. "
            + " ".join(parts)
            + f" Combined signed impact is {money(signed)}. "
            f"Each figure is the impact already on the exception row, so a loan's true balance "
            f"is not added again on top of a duplicate or a status break."
        )
        next_step = (
            "Work one discrepancy type at a time. Dedupe extra extract rows, backfill funded "
            "loans that are absent, correct status mappings that cross the funded boundary, "
            "and correct amount differences where both sides are Funded. "
            "Investigate a single loan id to see the source and reporting values behind each figure."
        )
    return {
        "title": title,
        "summary": summary,
        "next_step": next_step,
        "signed_impact": signed,
        "loan_ids": loan_ids,
        "comparison": [],
        "lines": lines,
    }


def _group_narrative(kind: str, subset: pd.DataFrame, signed: int) -> tuple[str, str]:
    count = len(subset)
    ids = ", ".join(str(value) for value in subset["loan_id"])
    label = DISCREPANCY_LABELS[kind]
    if kind == MISSING:
        summary = (
            f"{count} source loans are Funded and have no reporting row: {ids}. "
            f"Combined signed impact is {money(signed)}. Each loan contributes its source amount once."
        )
        next_step = (
            f"Backfill these {count} funded loans into the reporting extract at the source amount "
            f"and status, then rerun the tie-out. Confirm the extract did not drop them on a "
            f"funding-date, channel, or status filter."
        )
        return summary, next_step
    if kind == DUPLICATE:
        extras = int(subset["extra_copies"].sum())
        summary = (
            f"{count} loans appear more than once in the reporting extract: {ids}. "
            f"Combined signed impact is {money(signed)}, from {extras} extra "
            f"{'copy' if extras == 1 else 'copies'}. The first copy of each loan is excluded."
        )
        next_step = (
            f"Dedupe the reporting extract on loan_id. Drop the extra rows for {ids} "
            f"and keep the earliest report_row_id for each loan. That removes {money(signed)} "
            f"from the reporting funded total."
        )
        return summary, next_step
    if kind == INCORRECT_STATUS:
        dropped = subset.loc[subset["source_status"].eq("Funded")]
        added = subset.loc[~subset["source_status"].eq("Funded")]
        sentences = [
            f"{count} loans are present in both systems with a status that changes the funded total: {ids}.",
            f"Combined signed impact is {money(signed)}.",
        ]
        if not dropped.empty:
            dropped_ids = ", ".join(str(value) for value in dropped["loan_id"])
            sentences.append(
                f"Reported as not funded ({len(dropped)}): {dropped_ids}, "
                f"signed impact {money(int(dropped['signed_impact'].sum()))}."
            )
        if not added.empty:
            added_ids = ", ".join(str(value) for value in added["loan_id"])
            sentences.append(
                f"Reported as Funded while the source is not ({len(added)}): {added_ids}, "
                f"signed impact {money(int(added['signed_impact'].sum()))}."
            )
        next_bits = []
        if not dropped.empty:
            next_bits.append(
                "Reload the loans whose source status is Funded so they rejoin the funded total"
            )
        if not added.empty:
            next_bits.append(
                "remove the loans reported as Funded while the source status is not Funded"
            )
        next_step = (
            "Correct the status crosswalk. "
            + ", and ".join(next_bits)
            + ". Then rerun the tie-out."
        )
        return " ".join(sentences), next_step
    if kind == INCORRECT_AMOUNT:
        summary = (
            f"{count} loans are Funded on both sides with a different amount: {ids}. "
            f"Combined signed impact is {money(signed)}, each difference taken once. "
            f"These loans remain in both funded populations."
        )
        next_step = (
            f"Correct the reported amounts for {ids} to the source amounts. "
            f"The net amount correction is {money(signed)}. "
            f"Check for a stale balance or a mapped field other than the source loan amount, "
            f"then rerun the tie-out."
        )
        return summary, next_step
    raise KeyError(kind)
