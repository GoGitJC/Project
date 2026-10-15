"""Portfolio constants for the fictional LoanOps lender."""

from pathlib import Path

SEED = 42
LOAN_COUNT = 500
AS_OF_DATE = "2026-03-15"
EXTRACT_NAME = "RPT-2026-03-15"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "loanops.db"
MANIFEST_PATH = DATA_DIR / "planted_defects.json"

# Assigned by loan sequence so planted loan IDs stay valid.
# Other attributes (amount, property, dates, names) use SEED.
STATUS_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Funded", 1, 320),
    ("Approved", 321, 380),
    ("In Process", 381, 440),
    ("Denied", 441, 475),
    ("Withdrawn", 476, 500),
)

STATUSES: tuple[str, ...] = tuple(status for status, _, _ in STATUS_BANDS)

PROPERTY_TYPES: tuple[str, ...] = (
    "Single Family",
    "Condo",
    "Multi-Family",
    "Townhouse",
    "Manufactured",
)
PROPERTY_WEIGHTS: tuple[float, ...] = (0.55, 0.18, 0.10, 0.12, 0.05)

LOAN_PURPOSES: tuple[str, ...] = (
    "Purchase",
    "Refinance",
    "Cash-Out Refinance",
)
PURPOSE_WEIGHTS: tuple[float, ...] = (0.62, 0.25, 0.13)

PROPERTY_STATES: tuple[str, ...] = (
    "AZ",
    "CA",
    "CO",
    "FL",
    "GA",
    "IL",
    "NC",
    "NY",
    "OH",
    "PA",
    "TX",
    "WA",
)

GIVEN_NAMES: tuple[str, ...] = (
    "Avery",
    "Blake",
    "Cameron",
    "Drew",
    "Ellis",
    "Finley",
    "Gray",
    "Harper",
    "Indigo",
    "Jules",
    "Kendall",
    "Logan",
    "Marlow",
    "Nico",
    "Oakley",
    "Parker",
    "Quinn",
    "Reese",
    "Shay",
    "Taylor",
)
SURNAMES: tuple[str, ...] = (
    "Alden",
    "Brooks",
    "Callahan",
    "Dalton",
    "Ellison",
    "Ferris",
    "Godfrey",
    "Hollis",
    "Iverson",
    "Jessup",
    "Keene",
    "Langley",
    "Mercer",
    "North",
    "Osgood",
    "Phelps",
    "Quincy",
    "Redding",
    "Sutter",
    "Talbott",
)

# Discrepancy types produced by reconciliation. The planter and the
# reconciler share these labels so tests can name the same cases.
MISSING = "missing_from_reporting"
DUPLICATE = "duplicate_in_reporting"
INCORRECT_STATUS = "incorrect_status"
INCORRECT_AMOUNT = "incorrect_amount"

DISCREPANCY_LABELS: dict[str, str] = {
    MISSING: "Missing from reporting",
    DUPLICATE: "Duplicate in reporting",
    INCORRECT_STATUS: "Incorrect funding status",
    INCORRECT_AMOUNT: "Incorrect loan amount",
}


def loan_id_for(sequence: int) -> str:
    """Stable source loan id. Sequence 1 is LN-000001."""
    if not 1 <= sequence <= LOAN_COUNT:
        raise ValueError(f"loan sequence {sequence} is outside 1..{LOAN_COUNT}")
    return f"LN-{sequence:06d}"


def status_for_sequence(sequence: int) -> str:
    for status, start, end in STATUS_BANDS:
        if start <= sequence <= end:
            return status
    raise ValueError(f"loan sequence {sequence} has no status band")
