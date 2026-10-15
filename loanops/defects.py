"""Deterministic defects planted in the reporting extract.

The source portfolio is the system of record. This module lists the exact
loan ids that the generator changes when it builds the reporting extract.
Reconciliation does not read this module. It only compares the two tables.

Status bands (inclusive), from loanops.constants.STATUS_BANDS:
  LN-000001–LN-000320  Funded
  LN-000321–LN-000380  Approved
  LN-000381–LN-000440  In Process
  LN-000441–LN-000475  Denied
  LN-000476–LN-000500  Withdrawn

Impacts below are defined against the source amount. They are the oracle
the tests use. Dollar amounts depend on seed 42 and are resolved when the
database is built.
"""

from loanops.constants import (
    DUPLICATE,
    INCORRECT_AMOUNT,
    INCORRECT_STATUS,
    MISSING,
)

# Funded in source, omitted entirely from the reporting extract.
# Signed impact = -source amount, once.
MISSING_FROM_REPORTING: tuple[str, ...] = (
    "LN-000012",
    "LN-000048",
    "LN-000103",
    "LN-000156",
    "LN-000210",
    "LN-000244",
    "LN-000287",
    "LN-000319",
)

# Funded in source. The extract keeps one matching row and appends this
# many extra copies of that same funded row.
# Signed impact = extra copies × source amount. The first copy is not an error.
DUPLICATE_EXTRA_COPIES: dict[str, int] = {
    "LN-000007": 1,
    "LN-000033": 1,
    "LN-000091": 1,
    "LN-000140": 1,
    "LN-000198": 1,
    "LN-000276": 1,
}

# Funded in source, one reporting row, status overwritten.
# Signed impact = -source amount, once (the row leaves the funded total).
STATUS_DOWNGRADES: dict[str, str] = {
    "LN-000021": "Approved",
    "LN-000067": "In Process",
    "LN-000122": "Approved",
    "LN-000189": "Withdrawn",
    "LN-000255": "Denied",
}

# Not funded in source, one reporting row, status overwritten to Funded.
# Amount is left unchanged. Signed impact = +source amount, once.
STATUS_UPGRADES: dict[str, str] = {
    "LN-000330": "Funded",
    "LN-000350": "Funded",
    "LN-000400": "Funded",
    "LN-000460": "Funded",
}

# Funded on both sides, one reporting row, amount shifted by this delta.
# Signed impact = delta, once. The loan's true balance is not removed.
AMOUNT_DELTAS: dict[str, int] = {
    "LN-000015": -25_000,
    "LN-000080": 10_000,
    "LN-000175": -5_000,
    "LN-000300": 40_000,
}


def planted_loan_ids() -> dict[str, tuple[str, ...]]:
    """Loan ids by discrepancy type, in spec order."""
    return {
        MISSING: MISSING_FROM_REPORTING,
        DUPLICATE: tuple(DUPLICATE_EXTRA_COPIES),
        INCORRECT_STATUS: tuple(STATUS_DOWNGRADES) + tuple(STATUS_UPGRADES),
        INCORRECT_AMOUNT: tuple(AMOUNT_DELTAS),
    }


def oracle_signed_impact(loan_id: str, source_amount: int) -> tuple[str, int]:
    """Return the planted discrepancy type and signed dollar impact.

    This is arithmetic from the spec and the source amount. It does not
    look at the reporting table or the reconciler.
    """
    amount = int(source_amount)
    if loan_id in MISSING_FROM_REPORTING:
        return MISSING, -amount
    if loan_id in DUPLICATE_EXTRA_COPIES:
        return DUPLICATE, DUPLICATE_EXTRA_COPIES[loan_id] * amount
    if loan_id in STATUS_DOWNGRADES:
        return INCORRECT_STATUS, -amount
    if loan_id in STATUS_UPGRADES:
        return INCORRECT_STATUS, amount
    if loan_id in AMOUNT_DELTAS:
        return INCORRECT_AMOUNT, AMOUNT_DELTAS[loan_id]
    raise KeyError(f"{loan_id} is not a planted defect")
