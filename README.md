# LoanOps Intelligence

Funding reconciliation proof of concept for a fictional mortgage lender. The loan system of record is SQLite. A separate reporting extract is wrong on purpose. The dashboard ties source funded dollars to reporting funded dollars and names the loans that explain the gap.

Synthetic data only. No paid APIs. No customer data.

## Quick start

The SQLite database is already in `data/loanops.db`. After installing dependencies, start the dashboard. You do not need to generate data first.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows, activate with `.venv\Scripts\activate`.

Regenerate the database and the defect manifest from the fixed seed:

```bash
python -m loanops.generate
```

Run the tests:

```bash
pytest
```

Open [http://localhost:8501](http://localhost:8501).

## Architecture

```
app.py                      Streamlit entry. KPIs, tie-out, exceptions, investigation.
loanops/generate.py         Seeded source portfolio and defective reporting extract.
loanops/defects.py          Exact planted loan ids. The reconciler does not import this.
loanops/database.py         SQLite schema. Builds the file on startup if it is missing.
loanops/reconcile.py        SQL join plus Pandas classification and the dollar bridge.
loanops/investigate.py      Root-cause note filled from one reconciliation row.
loanops/charts.py           Plotly waterfall and status breakdown.
data/loanops.db             Committed source of truth and reporting extract.
data/planted_defects.json   Resolved dollar impacts for the planted ids.
tests/                      Counts, signed impacts, tie-out, and investigation evidence.
```

`loans` is the system of record: 500 unique loan ids. `reporting_extract` is the simulated downstream file `RPT-2026-03-15`. Reconciliation reads those two tables. It does not read the defect list. `loanops/defects.py` is the answer key for generation and tests.

Signed impacts are the bridge from source funded total to reporting funded total:

```
reporting funded total
    = source funded total
    + missing from reporting          (negative)
    + reported as not funded          (negative)
    + reported as funded in error     (positive)
    + amount differences              (reporting − source)
    + duplicate extra copies          (extra rows only)
```

If that sum does not match the reporting funded total, `reconcile()` raises. The dashboard prints the unexplained residual, which is `$0` for this portfolio.

## Reconciliation rules

Compare the source funded population (`status = 'Funded'`, one row per loan) with the reporting extract (every row whose status is `Funded`, so a second copy counts).

| Discrepancy | Rule | Signed impact |
| --- | --- | --- |
| Missing from reporting | Funded in source, no reporting row | −source amount, once |
| Duplicate in reporting | Same loan id more than once | Extra copies only. The earliest `report_row_id` is the legitimate copy and is not an error. |
| Incorrect funding status | Present in both, and the status crosses the funded boundary | Signed change in funded dollars on the first extract row, once |
| Incorrect loan amount | Funded on both sides, amounts differ | Reporting amount − source amount, once. The true balance stays in both totals. |

The legitimate first copy of a duplicate is still inside both funded totals. It is not also booked as missing. A status or amount break is not also booked as the full loan balance.

## Synthetic portfolio

Seed `42`. As-of date `2026-03-15`. Amounts are whole dollars. Status is assigned by loan id so the planted cases stay put. Property type, purpose, state, amount, rate, name, and dates are drawn from that seed.

| Status | Loan ids | Count |
| --- | --- | --- |
| Funded | LN-000001–LN-000320 | 320 |
| Approved | LN-000321–LN-000380 | 60 |
| In Process | LN-000381–LN-000440 | 60 |
| Denied | LN-000441–LN-000475 | 35 |
| Withdrawn | LN-000476–LN-000500 | 25 |

Property types: Single Family, Condo, Multi-Family, Townhouse, Manufactured.

Loan purposes: Purchase, Refinance, Cash-Out Refinance.

Borrower names are combinations from a fixed fictional list. They are not customers.

Source columns: `loan_id`, `borrower_name`, `property_type`, `property_state`, `loan_purpose`, `application_date`, `funding_date`, `loan_amount`, `interest_rate`, `status`.

Reporting columns: `report_row_id`, `loan_id`, `property_type`, `property_state`, `funding_date`, `loan_amount`, `status`, `extract_name`.

Non-funded loans have no funding date. A loan reported as Funded with a null funding date is evidence the status was mapped incorrectly, not a separate defect type.

## Planted defects

27 loans. Categories do not overlap, so each loan has one cause. Dollar impacts below are the seeded amounts.

**Tie-out**

| Step | Amount | Running total |
| --- | ---: | ---: |
| Source funded total | $181,433,000 | $181,433,000 |
| Missing from reporting | −$5,530,000 | $175,903,000 |
| Reported as not funded | −$3,104,000 | $172,799,000 |
| Reported as funded in error | +$2,275,000 | $175,074,000 |
| Amount differences | +$20,000 | $175,094,000 |
| Duplicate extra copies | +$2,855,000 | $177,949,000 |
| Reporting funded total | $177,949,000 | $177,949,000 |

Net variance (reporting − source): **−$3,484,000**. Unexplained residual: **$0**. Gross absolute impact, the sum of the absolute signed impacts, is $13,844,000. Offsetting status errors are why the gross figure is larger than the net.

| Type | Loans | Signed impact |
| --- | ---: | ---: |
| Missing from reporting | 8 | −$5,530,000 |
| Duplicate in reporting | 6 | +$2,855,000 |
| Incorrect funding status | 9 | −$829,000 |
| Incorrect loan amount | 4 | +$20,000 |

### Missing from reporting

Funded in source, omitted from the extract. Impact is the source amount once.

| Loan | Source amount | Signed impact |
| --- | ---: | ---: |
| LN-000012 | $778,000 | −$778,000 |
| LN-000048 | $855,000 | −$855,000 |
| LN-000103 | $769,000 | −$769,000 |
| LN-000156 | $286,000 | −$286,000 |
| LN-000210 | $886,000 | −$886,000 |
| LN-000244 | $666,000 | −$666,000 |
| LN-000287 | $606,000 | −$606,000 |
| LN-000319 | $684,000 | −$684,000 |

### Duplicates

One extra funded copy of the same amount. Impact is that extra copy, not two times the balance.

| Loan | Source amount | Extra copies | Signed impact |
| --- | ---: | ---: | ---: |
| LN-000007 | $569,000 | 1 | +$569,000 |
| LN-000033 | $700,000 | 1 | +$700,000 |
| LN-000091 | $192,000 | 1 | +$192,000 |
| LN-000140 | $466,000 | 1 | +$466,000 |
| LN-000198 | $196,000 | 1 | +$196,000 |
| LN-000276 | $732,000 | 1 | +$732,000 |

### Incorrect funding status

Five funded loans are reported as something else (−$3,104,000). Four loans that are not funded are reported as Funded (+$2,275,000).

| Loan | Source status | Source amount | Reporting status | Signed impact |
| --- | --- | ---: | --- | ---: |
| LN-000021 | Funded | $613,000 | Approved | −$613,000 |
| LN-000067 | Funded | $769,000 | In Process | −$769,000 |
| LN-000122 | Funded | $282,000 | Approved | −$282,000 |
| LN-000189 | Funded | $660,000 | Withdrawn | −$660,000 |
| LN-000255 | Funded | $780,000 | Denied | −$780,000 |
| LN-000330 | Approved | $729,000 | Funded | +$729,000 |
| LN-000350 | Approved | $634,000 | Funded | +$634,000 |
| LN-000400 | In Process | $380,000 | Funded | +$380,000 |
| LN-000460 | Denied | $532,000 | Funded | +$532,000 |

### Incorrect loan amount

Both sides Funded. Impact is the delta only.

| Loan | Source amount | Reporting amount | Signed impact |
| --- | ---: | ---: | ---: |
| LN-000015 | $297,000 | $272,000 | −$25,000 |
| LN-000080 | $714,000 | $724,000 | +$10,000 |
| LN-000175 | $490,000 | $485,000 | −$5,000 |
| LN-000300 | $811,000 | $851,000 | +$40,000 |

## Two-minute demo

1. Start the app and read the KPI row. Source funded is `$181,433,000`. Reporting funded is `$177,949,000`. Net variance is `−$3,484,000` across 27 exceptions.
2. Walk the waterfall left to right. Each bar is one rule above. The last bar equals the reporting KPI, and the residual under the bridge is `$0`.
3. Use the status chart to show that Funded dollars moved, and that Approved, In Process, Denied, and Withdrawn moved with them because of the status map.
4. Filter exceptions to **Missing from reporting**. Select `LN-000012` and click **Investigate Discrepancy**. The note shows Funded `$778,000` in source, no extract row, and a signed impact of `−$778,000` counted once. The next step is to backfill that loan.
5. Filter to **Duplicate in reporting** and investigate `LN-000007`. Source has one Funded loan for `$569,000`. The extract has two rows. The impact is `$569,000`, the extra copy. The next step is to dedupe on loan id and keep the earliest report row.
6. Investigate `LN-000021` (Funded `$613,000` in source, Approved in the extract, impact `−$613,000`) and `LN-000330` (Approved `$729,000` in source, Funded in the extract, no funding date, impact `+$729,000`). The next step is to correct the status crosswalk.
7. Investigate `LN-000015`. Both sides are Funded. Source `$297,000`, reporting `$272,000`, impact `−$25,000` only. The true balance is not removed from the tie-out.
8. Point at `pytest`. The tests recompute these counts and impacts from the source amounts and fail if a loan is counted twice.

## Assumptions

- Funded means the status string `Funded`. No other status is in the funded population.
- Source `loan_id` is unique. The reporting extract may repeat it.
- The legitimate copy is the lowest `report_row_id`.
- Whole dollars, integer arithmetic. No cents and no floating point in the tie-out.
- Loans that are not funded, and that are also absent from the extract, are not exceptions.
- A status change that stays on the non-funded side would not change funded totals, so it is not flagged. This dataset does not plant that case.
- The extract is a full portfolio snapshot, not a funded-only file. That is what makes a wrong status visible as a status break instead of a missing loan.
- The investigation text is a template filled from the reconciliation row. It is not a model guess, and it does not claim a failure in a system this demo does not contain.

## Tests

`pytest` covers:

- 500 unique source ids and the status bands
- Deterministic regeneration, and that `data/loanops.db` matches a fresh build
- Each planted loan's reporting rows (absent, duplicated, remapped, or re-amounted)
- Signed impact for every planted loan, including extra-copy-only duplicates and delta-only amount breaks
- The bridge identity `source funded + signed impacts = reporting funded`
- Dashboard status totals for Funded match those two populations
- Investigation notes quote the loan id, both sides, the signed impact, and the matching next step
