"""Investigation notes stay specific to the reconciliation evidence."""

import pytest

from loanops.formatting import money
from loanops.generate import build_database
from loanops.investigate import investigate
from loanops.reconcile import reconcile


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    path = tmp_path_factory.mktemp("investigate") / "loanops.db"
    build_database(path, write_manifest=False)
    return reconcile(path)


def _signed(result, loan_id: str) -> int:
    row = result.exceptions.loc[result.exceptions["loan_id"].eq(loan_id)].iloc[0]
    return int(row["signed_impact"])


def test_missing_note_names_the_loan_the_gap_and_a_backfill(result):
    report = investigate(result.exceptions, loan_id="LN-000012")
    impact = _signed(result, "LN-000012")
    text = f"{report['summary']} {report['next_step']}"
    assert "LN-000012" in text
    assert "Funded" in report["summary"]
    assert "no row" in report["summary"]
    assert money(impact) in report["summary"]
    assert "once" in report["summary"]
    assert "Backfill" in report["next_step"]
    assert "AI" not in text
    comparison = {item["field"]: item for item in report["comparison"]}
    assert comparison["Status"]["source"] == "Funded"
    assert comparison["Status"]["reporting"] == "Not in extract"
    assert comparison["Signed impact"]["reporting"] == money(impact)


def test_duplicate_note_counts_only_the_extra_copy(result):
    report = investigate(result.exceptions, loan_id="LN-000007")
    impact = _signed(result, "LN-000007")
    row = result.exceptions.loc[result.exceptions["loan_id"].eq("LN-000007")].iloc[0]
    full_double = money(int(row["source_amount"]) * 2)
    text = f"{report['summary']} {report['next_step']}"
    assert "Dedupe" in report["next_step"]
    assert money(impact) in report["summary"]
    assert "extra" in report["summary"].lower()
    assert "first" in report["summary"].lower()
    assert full_double not in text
    assert "AI" not in text
    assert str(int(row["canonical_row_id"])) in text


def test_status_and_amount_notes_quote_both_sides(result):
    downgrade = investigate(result.exceptions, loan_id="LN-000021")
    assert "Approved" in downgrade["summary"]
    assert "Funded" in downgrade["summary"]
    assert money(_signed(result, "LN-000021")) in downgrade["summary"]
    assert "status mapping" in downgrade["next_step"]

    upgrade = investigate(result.exceptions, loan_id="LN-000330")
    assert "Approved" in upgrade["summary"]
    assert "marks it Funded" in upgrade["summary"]
    assert "not reported as Funded" in upgrade["next_step"]
    assert "no funding date" in upgrade["summary"]

    amount = investigate(result.exceptions, loan_id="LN-000015")
    assert money(_signed(result, "LN-000015")) in amount["summary"]
    assert "difference once" in amount["summary"]
    assert "reported amount" in amount["next_step"]
    assert "true balance is not removed" in amount["summary"]


def test_type_rollups_sum_the_same_signed_impacts(result):
    for kind in result.exceptions["discrepancy_type"].unique():
        report = investigate(result.exceptions, discrepancy_type=kind)
        expected = int(
            result.exceptions.loc[
                result.exceptions["discrepancy_type"].eq(kind), "signed_impact"
            ].sum()
        )
        assert report["signed_impact"] == expected
        assert money(expected) in report["summary"]
        assert len(report["loan_ids"]) == (
            result.exceptions["discrepancy_type"].eq(kind).sum()
        )


def test_app_module_imports():
    import app

    assert callable(app.main)
