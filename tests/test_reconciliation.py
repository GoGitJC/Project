"""Reconciliation counts, signed impacts, and the funded dollar tie-out."""

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from loanops.constants import (
    DB_PATH,
    DUPLICATE,
    INCORRECT_AMOUNT,
    INCORRECT_STATUS,
    MANIFEST_PATH,
    MISSING,
)
from loanops.defects import (
    AMOUNT_DELTAS,
    DUPLICATE_EXTRA_COPIES,
    MISSING_FROM_REPORTING,
    STATUS_DOWNGRADES,
    STATUS_UPGRADES,
    oracle_signed_impact,
)
from loanops.generate import build_database, build_source
from loanops.reconcile import reconcile

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("recon") / "loanops.db"
    build_database(path, write_manifest=False)
    return path


@pytest.fixture(scope="module")
def result(db_path):
    return reconcile(db_path)


@pytest.fixture(scope="module")
def source():
    return build_source().set_index("loan_id")


def _row(result, loan_id: str):
    matches = result.exceptions.loc[result.exceptions["loan_id"].eq(loan_id)]
    assert len(matches) == 1, loan_id
    return matches.iloc[0]


def test_reconciler_does_not_read_the_defect_key():
    source = (ROOT / "loanops" / "reconcile.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "defects" in node.module:
            pytest.fail("reconcile.py must classify from the tables, not the planted-defect key")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "defects" not in alias.name


def test_exception_counts_match_the_planted_sets(result):
    counts = result.exceptions["discrepancy_type"].value_counts().to_dict()
    assert counts[MISSING] == len(MISSING_FROM_REPORTING) == 8
    assert counts[DUPLICATE] == len(DUPLICATE_EXTRA_COPIES) == 6
    assert counts[INCORRECT_STATUS] == len(STATUS_DOWNGRADES) + len(STATUS_UPGRADES) == 9
    assert counts[INCORRECT_AMOUNT] == len(AMOUNT_DELTAS) == 4
    assert len(result.exceptions) == 27


def test_each_planted_loan_has_one_exception_and_the_oracle_impact(result, source):
    assert not result.exceptions["loan_id"].duplicated().any()
    planted = (
        list(MISSING_FROM_REPORTING)
        + list(DUPLICATE_EXTRA_COPIES)
        + list(STATUS_DOWNGRADES)
        + list(STATUS_UPGRADES)
        + list(AMOUNT_DELTAS)
    )
    assert set(result.exceptions["loan_id"]) == set(planted)
    for loan_id in planted:
        kind, signed = oracle_signed_impact(loan_id, int(source.loc[loan_id, "loan_amount"]))
        row = _row(result, loan_id)
        assert row["discrepancy_type"] == kind
        assert int(row["signed_impact"]) == signed


def test_missing_impact_is_the_source_amount_once(result, source):
    for loan_id in MISSING_FROM_REPORTING:
        row = _row(result, loan_id)
        amount = int(source.loc[loan_id, "loan_amount"])
        assert int(row["signed_impact"]) == -amount
        assert int(row["reporting_copies"]) == 0
        assert row["reporting_status"] is None or pd.isna(row["reporting_status"])


def test_duplicate_impact_is_extra_copies_only(result, source):
    for loan_id, extra_copies in DUPLICATE_EXTRA_COPIES.items():
        row = _row(result, loan_id)
        amount = int(source.loc[loan_id, "loan_amount"])
        assert int(row["extra_copies"]) == extra_copies
        assert int(row["reporting_copies"]) == extra_copies + 1
        assert int(row["signed_impact"]) == extra_copies * amount
        assert int(row["signed_impact"]) != (extra_copies + 1) * amount
        assert int(row["reporting_amount"]) == amount
        assert row["reporting_status"] == "Funded"


def test_status_impact_is_the_signed_funded_change_once(result, source):
    for loan_id in STATUS_DOWNGRADES:
        row = _row(result, loan_id)
        amount = int(source.loc[loan_id, "loan_amount"])
        assert row["source_status"] == "Funded"
        assert row["reporting_status"] == STATUS_DOWNGRADES[loan_id]
        assert int(row["signed_impact"]) == -amount
        assert int(row["reporting_copies"]) == 1
    for loan_id in STATUS_UPGRADES:
        row = _row(result, loan_id)
        amount = int(source.loc[loan_id, "loan_amount"])
        assert row["source_status"] != "Funded"
        assert row["reporting_status"] == "Funded"
        assert int(row["reporting_amount"]) == amount
        assert int(row["signed_impact"]) == amount


def test_amount_impact_is_the_delta_once_and_keeps_the_balance(result, source):
    component = 0
    for loan_id, delta in AMOUNT_DELTAS.items():
        row = _row(result, loan_id)
        amount = int(source.loc[loan_id, "loan_amount"])
        assert row["source_status"] == "Funded"
        assert row["reporting_status"] == "Funded"
        assert int(row["reporting_amount"]) == amount + delta
        assert int(row["signed_impact"]) == delta
        assert int(row["signed_impact"]) != -amount
        component += delta
    booked = int(
        result.exceptions.loc[
            result.exceptions["discrepancy_type"].eq(INCORRECT_AMOUNT), "signed_impact"
        ].sum()
    )
    assert booked == component


def test_tie_out_bridges_source_funded_to_reporting_funded(result):
    explained = int(result.exceptions["signed_impact"].sum())
    assert result.source_funded_total + explained == result.reporting_funded_total
    assert result.net_variance == result.reporting_funded_total - result.source_funded_total
    assert result.unexplained == 0
    assert int(result.bridge.iloc[-1]["running_total"]) == result.reporting_funded_total
    relative = result.bridge.loc[result.bridge["measure"].eq("relative"), "amount"]
    assert int(relative.sum()) == result.net_variance
    steps = dict(zip(result.bridge["step"], result.bridge["amount"].astype(int)))
    status = result.exceptions.loc[result.exceptions["discrepancy_type"].eq(INCORRECT_STATUS)]
    assert steps["Reported as not funded"] == int(
        status.loc[status["source_status"].eq("Funded"), "signed_impact"].sum()
    )
    assert steps["Reported as funded in error"] == int(
        status.loc[~status["source_status"].eq("Funded"), "signed_impact"].sum()
    )
    assert steps["Duplicate extra copies"] == int(
        result.exceptions.loc[
            result.exceptions["discrepancy_type"].eq(DUPLICATE), "signed_impact"
        ].sum()
    )
    funded = result.status_breakdown.loc[result.status_breakdown["status"].eq("Funded")].iloc[0]
    assert int(funded["source_amount"]) == result.source_funded_total
    assert int(funded["reporting_amount"]) == result.reporting_funded_total


def test_named_cases_used_in_the_demo(result, source):
    missing = _row(result, "LN-000012")
    duplicate = _row(result, "LN-000007")
    downgrade = _row(result, "LN-000021")
    upgrade = _row(result, "LN-000330")
    amount = _row(result, "LN-000015")
    assert missing["discrepancy_type"] == MISSING
    assert duplicate["discrepancy_type"] == DUPLICATE
    assert downgrade["discrepancy_type"] == INCORRECT_STATUS
    assert downgrade["reporting_status"] == "Approved"
    assert upgrade["discrepancy_type"] == INCORRECT_STATUS
    assert upgrade["source_status"] == "Approved"
    assert amount["discrepancy_type"] == INCORRECT_AMOUNT
    assert int(amount["signed_impact"]) == -25_000
    assert int(duplicate["signed_impact"]) == int(source.loc["LN-000007", "loan_amount"])


def test_manifest_totals_match_reconciliation(result):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    totals = manifest["totals"]
    assert totals["source_funded_total"] == result.source_funded_total
    assert totals["reporting_funded_total"] == result.reporting_funded_total
    assert totals["explained_signed_impact"] == result.net_variance
    for kind, item in totals["by_type"].items():
        booked = result.exceptions.loc[result.exceptions["discrepancy_type"].eq(kind)]
        assert item["count"] == len(booked)
        assert item["signed_impact"] == int(booked["signed_impact"].sum())


def test_committed_database_reconciles(result):
    committed = reconcile(DB_PATH)
    assert committed.source_funded_total == result.source_funded_total
    assert committed.reporting_funded_total == result.reporting_funded_total
    assert committed.net_variance == result.net_variance
    assert len(committed.exceptions) == len(result.exceptions)
