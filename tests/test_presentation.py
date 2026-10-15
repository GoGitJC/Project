"""Presentation aggregates must agree with the reconciliation result."""

from pathlib import Path

from loanops.charts import status_figure, waterfall_figure
from loanops.constants import DISCREPANCY_LABELS, MISSING
from loanops.generate import build_database
from loanops.presentation import (
    exception_display,
    exception_summary,
    filter_exceptions,
    funding_trend,
    load_source_loans,
    preferred_loan,
    rank_exceptions,
    tie_out_status,
)
from loanops.reconcile import reconcile

LABEL_TO_TYPE = {label: key for key, label in DISCREPANCY_LABELS.items()}


def test_charts_and_views_follow_the_tie_out(tmp_path: Path):
    path = tmp_path / "loanops.db"
    build_database(path, write_manifest=False)
    result = reconcile(path)
    loans = load_source_loans(path)
    trend = funding_trend(loans)

    assert int(trend["funded_volume"].sum()) == result.source_funded_total
    assert int(trend["funded_loans"].sum()) == result.source_funded_count

    summary = exception_summary(result.exceptions)
    assert int(summary["signed_impact"].sum()) == result.net_variance
    assert int(summary["loans"].sum()) == len(result.exceptions)
    assert set(summary["discrepancy_type"]) == set(DISCREPANCY_LABELS)

    ranked = rank_exceptions(result.exceptions)
    assert list(exception_display(ranked)["Loan"]) == list(ranked["loan_id"])

    missing = filter_exceptions(
        result.exceptions,
        type_label="Missing from reporting",
        state="All",
        property_type="All",
        severity="All",
        query="",
        label_to_type=LABEL_TO_TYPE,
    )
    assert set(missing["discrepancy_type"]) == {MISSING}
    assert preferred_loan(result.exceptions, MISSING, "LN-000012") in set(missing["loan_id"])

    label, tone, _hint = tie_out_status(result.unexplained, len(result.exceptions))
    assert result.unexplained == 0
    assert label == "Explained"
    assert tone == "warning"

    assert waterfall_figure(result.bridge).data
    assert status_figure(result.status_breakdown).data
