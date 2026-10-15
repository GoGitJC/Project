"""Source portfolio shape and the planted reporting defects."""

import json
import sqlite3

import pandas as pd
import pytest

from loanops.constants import (
    DB_PATH,
    LOAN_COUNT,
    MANIFEST_PATH,
    SEED,
    STATUS_BANDS,
    loan_id_for,
    status_for_sequence,
)
from loanops.defects import (
    AMOUNT_DELTAS,
    DUPLICATE_EXTRA_COPIES,
    MISSING_FROM_REPORTING,
    STATUS_DOWNGRADES,
    STATUS_UPGRADES,
)
from loanops.generate import build_database, build_source


@pytest.fixture(scope="module")
def fresh_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("loanops") / "loanops.db"
    build_database(path, write_manifest=False)
    return path


def _frames(path):
    connection = sqlite3.connect(path)
    loans = pd.read_sql_query("SELECT * FROM loans ORDER BY loan_id", connection)
    reporting = pd.read_sql_query(
        "SELECT * FROM reporting_extract ORDER BY report_row_id", connection
    )
    connection.close()
    return loans, reporting


def test_source_has_500_unique_stable_ids():
    source = build_source(SEED)
    assert len(source) == LOAN_COUNT
    assert source["loan_id"].is_unique
    assert source["loan_id"].tolist() == [loan_id_for(n) for n in range(1, LOAN_COUNT + 1)]
    assert set(source["status"]) == {status for status, _, _ in STATUS_BANDS}


def test_status_bands_match_the_documented_ranges():
    source = build_source(SEED)
    for status, start, end in STATUS_BANDS:
        ids = source.loc[source["status"].eq(status), "loan_id"]
        assert ids.min() == loan_id_for(start)
        assert ids.max() == loan_id_for(end)
        assert len(ids) == end - start + 1
        assert status_for_sequence(start) == status


def test_regeneration_is_deterministic(tmp_path):
    first = tmp_path / "a.db"
    second = tmp_path / "b.db"
    build_database(first, write_manifest=False)
    build_database(second, write_manifest=False)
    left_loans, left_reporting = _frames(first)
    right_loans, right_reporting = _frames(second)
    pd.testing.assert_frame_equal(left_loans, right_loans)
    pd.testing.assert_frame_equal(left_reporting, right_reporting)


def test_planted_rows_match_the_spec(fresh_db):
    loans, reporting = _frames(fresh_db)
    loans = loans.set_index("loan_id")
    for loan_id in MISSING_FROM_REPORTING:
        assert loans.loc[loan_id, "status"] == "Funded"
        assert reporting.loc[reporting["loan_id"].eq(loan_id)].empty

    for loan_id, copies in DUPLICATE_EXTRA_COPIES.items():
        rows = reporting.loc[reporting["loan_id"].eq(loan_id)]
        assert len(rows) == copies + 1
        assert set(rows["status"]) == {"Funded"}
        assert set(rows["loan_amount"].astype(int)) == {int(loans.loc[loan_id, "loan_amount"])}
        first = rows.sort_values("report_row_id").iloc[0]
        assert int(first["report_row_id"]) == int(rows["report_row_id"].min())

    for loan_id, status in STATUS_DOWNGRADES.items():
        rows = reporting.loc[reporting["loan_id"].eq(loan_id)]
        assert len(rows) == 1
        assert rows.iloc[0]["status"] == status
        assert int(rows.iloc[0]["loan_amount"]) == int(loans.loc[loan_id, "loan_amount"])
        assert loans.loc[loan_id, "status"] == "Funded"

    for loan_id, status in STATUS_UPGRADES.items():
        rows = reporting.loc[reporting["loan_id"].eq(loan_id)]
        assert len(rows) == 1
        assert rows.iloc[0]["status"] == status == "Funded"
        assert loans.loc[loan_id, "status"] != "Funded"
        assert int(rows.iloc[0]["loan_amount"]) == int(loans.loc[loan_id, "loan_amount"])

    for loan_id, delta in AMOUNT_DELTAS.items():
        rows = reporting.loc[reporting["loan_id"].eq(loan_id)]
        assert len(rows) == 1
        assert rows.iloc[0]["status"] == "Funded"
        assert int(rows.iloc[0]["loan_amount"]) == int(loans.loc[loan_id, "loan_amount"]) + delta


def test_committed_database_matches_generator(tmp_path):
    assert DB_PATH.exists(), "commit data/loanops.db so streamlit run needs no extra step"
    fresh_loans, fresh_reporting = _frames(DB_PATH)
    rebuilt = tmp_path / "rebuilt.db"
    build_database(rebuilt, write_manifest=False)
    again_loans, again_reporting = _frames(rebuilt)
    pd.testing.assert_frame_equal(fresh_loans, again_loans)
    pd.testing.assert_frame_equal(fresh_reporting, again_reporting)


def test_manifest_lists_every_planted_case():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["seed"] == SEED
    assert manifest["loan_count"] == LOAN_COUNT
    defects = manifest["defects"]
    assert [case["loan_id"] for case in defects["missing_from_reporting"]] == list(
        MISSING_FROM_REPORTING
    )
    assert [case["loan_id"] for case in defects["duplicate_in_reporting"]] == list(
        DUPLICATE_EXTRA_COPIES
    )
    assert len(defects["incorrect_status"]) == len(STATUS_DOWNGRADES) + len(STATUS_UPGRADES)
    assert len(defects["incorrect_amount"]) == len(AMOUNT_DELTAS)
