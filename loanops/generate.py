"""Build the synthetic source portfolio and the defective reporting extract."""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from loanops.constants import (
    AS_OF_DATE,
    DATA_DIR,
    DB_PATH,
    DUPLICATE,
    EXTRACT_NAME,
    GIVEN_NAMES,
    INCORRECT_AMOUNT,
    INCORRECT_STATUS,
    LOAN_COUNT,
    LOAN_PURPOSES,
    MANIFEST_PATH,
    MISSING,
    PROPERTY_STATES,
    PROPERTY_TYPES,
    PROPERTY_WEIGHTS,
    PURPOSE_WEIGHTS,
    SEED,
    STATUS_BANDS,
    STATUSES,
    SURNAMES,
    loan_id_for,
    status_for_sequence,
)
from loanops.database import SCHEMA, connect
from loanops.defects import (
    AMOUNT_DELTAS,
    DUPLICATE_EXTRA_COPIES,
    MISSING_FROM_REPORTING,
    STATUS_DOWNGRADES,
    STATUS_UPGRADES,
    oracle_signed_impact,
    planted_loan_ids,
)
from loanops.formatting import money

AS_OF = date.fromisoformat(AS_OF_DATE)
FUNDED_DATE_START = date(2024, 7, 1)
OPEN_APP_START = date(2025, 1, 6)
OPEN_APP_END = date(2026, 3, 10)

_RULES = {
    MISSING: "In source as Funded, absent from reporting. Impact = -source amount, once.",
    DUPLICATE: (
        "Same loan more than once. Impact = extra copies only. "
        "The first reporting row is the legitimate copy."
    ),
    INCORRECT_STATUS: (
        "Present in both, and the reporting status crosses the funded boundary. "
        "Impact = the signed change in funded dollars, once."
    ),
    INCORRECT_AMOUNT: (
        "Funded in both, amounts differ. Impact = reporting amount - source amount, once."
    ),
}


def build_source(seed: int = SEED) -> pd.DataFrame:
    """500 unique loans. Status comes from the documented id bands."""
    rng = random.Random(seed)
    rows: list[dict] = []
    for sequence in range(1, LOAN_COUNT + 1):
        status = status_for_sequence(sequence)
        if status == "Funded":
            offset = rng.randint(0, (AS_OF - FUNDED_DATE_START).days)
            funding = FUNDED_DATE_START + timedelta(days=offset)
            application = funding - timedelta(days=rng.randint(18, 75))
            funding_date = funding.isoformat()
        else:
            offset = rng.randint(0, (OPEN_APP_END - OPEN_APP_START).days)
            application = OPEN_APP_START + timedelta(days=offset)
            funding_date = None
        eighths = rng.randint(40, 64)
        rows.append(
            {
                "loan_id": loan_id_for(sequence),
                "borrower_name": f"{rng.choice(GIVEN_NAMES)} {rng.choice(SURNAMES)}",
                "property_type": rng.choices(PROPERTY_TYPES, weights=PROPERTY_WEIGHTS, k=1)[0],
                "property_state": rng.choice(PROPERTY_STATES),
                "loan_purpose": rng.choices(LOAN_PURPOSES, weights=PURPOSE_WEIGHTS, k=1)[0],
                "application_date": application.isoformat(),
                "funding_date": funding_date,
                "loan_amount": rng.randint(180, 925) * 1000,
                "interest_rate": f"{eighths / 8:.3f}",
                "status": status,
            }
        )
    frame = pd.DataFrame(rows)
    if frame["loan_id"].duplicated().any():
        raise RuntimeError("source loan ids are not unique")
    if len(frame) != LOAN_COUNT:
        raise RuntimeError(f"expected {LOAN_COUNT} loans, built {len(frame)}")
    return frame


def validate_defect_spec(source: pd.DataFrame) -> None:
    """Fail generation if a planted id is in the wrong status band or overlaps."""
    funded = set(source.loc[source["status"].eq("Funded"), "loan_id"])
    known = set(source["loan_id"])
    groups = {
        "missing": set(MISSING_FROM_REPORTING),
        "duplicate": set(DUPLICATE_EXTRA_COPIES),
        "downgrade": set(STATUS_DOWNGRADES),
        "upgrade": set(STATUS_UPGRADES),
        "amount": set(AMOUNT_DELTAS),
    }
    names = list(groups)
    for index, name in enumerate(names):
        unknown = groups[name] - known
        if unknown:
            raise ValueError(f"{name} ids are not in the source portfolio: {sorted(unknown)}")
        for other in names[index + 1 :]:
            overlap = groups[name] & groups[other]
            if overlap:
                raise ValueError(f"{name} overlaps {other}: {sorted(overlap)}")
    for name in ("missing", "duplicate", "downgrade", "amount"):
        outside = groups[name] - funded
        if outside:
            raise ValueError(f"{name} ids must be funded in source: {sorted(outside)}")
    funded_upgrades = groups["upgrade"] & funded
    if funded_upgrades:
        raise ValueError(f"status upgrades must start unfunded: {sorted(funded_upgrades)}")
    for loan_id, copies in DUPLICATE_EXTRA_COPIES.items():
        if copies < 1:
            raise ValueError(f"{loan_id} needs at least one extra copy")
    amounts = source.set_index("loan_id")["loan_amount"]
    for loan_id, delta in AMOUNT_DELTAS.items():
        if int(amounts.loc[loan_id]) + delta <= 0:
            raise ValueError(f"amount delta wipes out {loan_id}")
        if delta == 0:
            raise ValueError(f"amount delta for {loan_id} does not change the amount")


def build_reporting(source: pd.DataFrame) -> pd.DataFrame:
    """Copy the source portfolio, then apply the planted defects."""
    validate_defect_spec(source)
    missing = set(MISSING_FROM_REPORTING)
    reporting = source.loc[~source["loan_id"].isin(missing)].copy()
    reporting = reporting.sort_values("loan_id").reset_index(drop=True)

    for loan_id, status in {**STATUS_DOWNGRADES, **STATUS_UPGRADES}.items():
        reporting.loc[reporting["loan_id"].eq(loan_id), "status"] = status
    for loan_id, delta in AMOUNT_DELTAS.items():
        mask = reporting["loan_id"].eq(loan_id)
        reporting.loc[mask, "loan_amount"] = (
            reporting.loc[mask, "loan_amount"].astype(int) + delta
        )

    columns = [
        "loan_id",
        "property_type",
        "property_state",
        "funding_date",
        "loan_amount",
        "status",
    ]
    base = reporting[columns].copy()
    extra_frames = []
    for loan_id, copies in DUPLICATE_EXTRA_COPIES.items():
        row = base.loc[base["loan_id"].eq(loan_id)]
        if len(row) != 1:
            raise RuntimeError(f"expected one base row for duplicate {loan_id}")
        extra_frames.extend([row] * copies)
    if extra_frames:
        base = pd.concat([base, *extra_frames], ignore_index=True)

    base.insert(0, "report_row_id", range(1, len(base) + 1))
    base["extract_name"] = EXTRACT_NAME
    base["loan_amount"] = base["loan_amount"].astype(int)
    return base


def build_manifest(source: pd.DataFrame) -> dict:
    """Resolve planted ids to dollar impacts using source amounts only."""
    amounts = source.set_index("loan_id")["loan_amount"].astype(int)
    statuses = source.set_index("loan_id")["status"]
    defects: dict[str, list[dict]] = {}
    totals_by_type: dict[str, dict] = {}
    for discrepancy_type, loan_ids in planted_loan_ids().items():
        cases = []
        for loan_id in loan_ids:
            kind, signed = oracle_signed_impact(loan_id, int(amounts.loc[loan_id]))
            if kind != discrepancy_type:
                raise RuntimeError(f"{loan_id} oracle type {kind} != {discrepancy_type}")
            case = {
                "loan_id": loan_id,
                "source_status": str(statuses.loc[loan_id]),
                "source_amount": int(amounts.loc[loan_id]),
                "signed_impact": int(signed),
            }
            if loan_id in STATUS_DOWNGRADES:
                case["reporting_status"] = STATUS_DOWNGRADES[loan_id]
            elif loan_id in STATUS_UPGRADES:
                case["reporting_status"] = STATUS_UPGRADES[loan_id]
            elif loan_id in AMOUNT_DELTAS:
                case["amount_delta"] = AMOUNT_DELTAS[loan_id]
                case["reporting_amount"] = int(amounts.loc[loan_id]) + AMOUNT_DELTAS[loan_id]
            elif loan_id in DUPLICATE_EXTRA_COPIES:
                case["extra_copies"] = DUPLICATE_EXTRA_COPIES[loan_id]
            cases.append(case)
        defects[discrepancy_type] = cases
        totals_by_type[discrepancy_type] = {
            "count": len(cases),
            "signed_impact": int(sum(item["signed_impact"] for item in cases)),
        }
    source_funded_total = int(amounts.loc[statuses.eq("Funded")].sum())
    net_variance = int(sum(item["signed_impact"] for item in totals_by_type.values()))
    return {
        "seed": SEED,
        "as_of_date": AS_OF_DATE,
        "extract_name": EXTRACT_NAME,
        "loan_count": LOAN_COUNT,
        "property_types": list(PROPERTY_TYPES),
        "statuses": list(STATUSES),
        "status_bands": {
            status: {
                "start": loan_id_for(start),
                "end": loan_id_for(end),
                "count": end - start + 1,
            }
            for status, start, end in STATUS_BANDS
        },
        "rules": _RULES,
        "defects": defects,
        "totals": {
            "source_funded_total": source_funded_total,
            "explained_signed_impact": net_variance,
            "reporting_funded_total": source_funded_total + net_variance,
            "by_type": totals_by_type,
        },
    }


def write_database(source: pd.DataFrame, reporting: pd.DataFrame, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    connection = connect(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.executemany(
            """
            INSERT INTO loans (
                loan_id, borrower_name, property_type, property_state, loan_purpose,
                application_date, funding_date, loan_amount, interest_rate, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            list(source.itertuples(index=False, name=None)),
        )
        connection.executemany(
            """
            INSERT INTO reporting_extract (
                report_row_id, loan_id, property_type, property_state,
                funding_date, loan_amount, status, extract_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            list(reporting.itertuples(index=False, name=None)),
        )
        connection.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [
                ("seed", str(SEED)),
                ("as_of_date", AS_OF_DATE),
                ("extract_name", EXTRACT_NAME),
                ("loan_count", str(LOAN_COUNT)),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def build_database(db_path: Path | None = None, *, write_manifest: bool | None = None) -> Path:
    """Regenerate SQLite. The default path also refreshes the defect manifest."""
    path = Path(db_path) if db_path else DB_PATH
    if write_manifest is None:
        write_manifest = path.resolve() == DB_PATH.resolve()
    source = build_source(SEED)
    reporting = build_reporting(source)
    write_database(source, reporting, path)
    if write_manifest:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest(source)
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    path = build_database(DB_PATH, write_manifest=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    totals = manifest["totals"]
    print(f"Wrote {path}")
    print(f"Wrote {MANIFEST_PATH}")
    print(f"Source funded total:     {money(totals['source_funded_total'])}")
    print(f"Reporting funded total:  {money(totals['reporting_funded_total'])}")
    print(f"Explained variance:      {money(totals['explained_signed_impact'])}")
    for name, item in totals["by_type"].items():
        print(f"  {name}: count={item['count']} signed={money(item['signed_impact'])}")


if __name__ == "__main__":
    main()
