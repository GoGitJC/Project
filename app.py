"""LoanOps Intelligence: funding reconciliation dashboard."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from loanops.charts import bridge_display, status_figure, waterfall_figure
from loanops.constants import AS_OF_DATE, DISCREPANCY_LABELS, SEED
from loanops.database import ensure_database
from loanops.formatting import markdown_safe, money
from loanops.investigate import investigate
from loanops.reconcile import reconcile

TYPE_OPTIONS = ["All", *DISCREPANCY_LABELS.values()]
LABEL_TO_TYPE = {label: key for key, label in DISCREPANCY_LABELS.items()}


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1180px; }
        .eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.75rem;
            font-weight: 650;
            color: #8a5a22;
            margin-bottom: 0.15rem;
        }
        .app-header h1 {
            font-size: 1.85rem;
            line-height: 1.15;
            margin: 0;
            color: #0f3d5e;
            letter-spacing: -0.02em;
        }
        .app-header p { margin: 0.35rem 0 0; color: #3d4c5c; font-size: 1.02rem; }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e2e6ec;
            border-top: 3px solid #0f3d5e;
            padding: 0.55rem 0.75rem 0.35rem;
            border-radius: 8px;
        }
        div[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _amount_cell(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return money(int(value))


def _exception_view(frame: pd.DataFrame) -> pd.DataFrame:
    reporting_status = frame["reporting_status"].where(frame["reporting_status"].notna(), "Not in extract")
    funding_date = frame["funding_date"].where(frame["funding_date"].notna(), "—")
    return pd.DataFrame(
        {
            "Loan": frame["loan_id"],
            "Discrepancy": frame["discrepancy_type"].map(DISCREPANCY_LABELS),
            "Signed impact": frame["signed_impact"].map(lambda value: money(int(value))),
            "Source status": frame["source_status"],
            "Reporting status": reporting_status,
            "Source amount": frame["source_amount"].map(lambda value: money(int(value))),
            "Reporting amount": frame["reporting_amount"].map(_amount_cell),
            "Property": frame["property_type"],
            "State": frame["property_state"],
            "Funding date": funding_date,
            "Extract rows": frame["reporting_copies"].astype(int),
            "Extra copies": frame["extra_copies"].astype(int),
        }
    )


def _render_investigation(report: dict) -> None:
    st.markdown(f"**{markdown_safe(report['title'])}**")
    st.markdown(markdown_safe(report["summary"]))
    if report["comparison"]:
        st.dataframe(
            pd.DataFrame(report["comparison"]),
            hide_index=True,
            width="stretch",
            column_config={
                "field": st.column_config.TextColumn("Field"),
                "source": st.column_config.TextColumn("Source system"),
                "reporting": st.column_config.TextColumn("Reporting extract"),
            },
        )
    elif report["lines"]:
        st.dataframe(
            pd.DataFrame({"Evidence": report["lines"]}),
            hide_index=True,
            width="stretch",
        )
    st.markdown(f"**Recommended next step.** {markdown_safe(report['next_step'])}")
    st.caption(
        f"Signed impact from the tie-out: {money(report['signed_impact'])}. "
        "This note restates the reconciliation evidence for the selection."
    )


def main() -> None:
    st.set_page_config(
        page_title="LoanOps Intelligence",
        page_icon=":material/account_balance:",
        layout="wide",
    )
    _inject_css()
    db_path = ensure_database()
    result = reconcile(db_path)

    st.markdown(
        """
        <div class="app-header">
          <div class="eyebrow">Fictional mortgage lender · Synthetic portfolio</div>
          <h1>LoanOps Intelligence</h1>
          <p>Funding reconciliation between the loan system of record and the reporting extract.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"As of {AS_OF_DATE} · Seed {SEED} · Extract {result.extract_name} · "
        f"{result.source_loan_count} source loans · "
        f"{result.source_funded_count} funded in source · "
        f"{result.reporting_row_count} reporting rows "
        f"({result.reporting_funded_row_count} funded rows, extra copies included)"
    )

    with st.sidebar:
        st.markdown("**How the tie-out works**")
        st.markdown(
            "Source funded total is the sum of loan amounts where status is Funded, one row per loan."
        )
        st.markdown(
            "Reporting funded total sums every extract row with status Funded, so a second copy adds dollars."
        )
        st.markdown(
            "Missing loans reduce the reporting total by the source amount once. "
            "Duplicates add only the extra copies. "
            "Status and amount breaks book the signed difference once."
        )
        st.caption(f"Database: `{db_path.name}`")

    source_col, reporting_col, variance_col, exception_col = st.columns(4)
    source_col.metric(
        "Source funded total",
        money(result.source_funded_total),
        help="Sum of source loan amounts with status Funded. Each loan is counted once.",
    )
    reporting_col.metric(
        "Reporting funded total",
        money(result.reporting_funded_total),
        help="Sum of reporting rows with status Funded, including extra duplicate rows.",
    )
    variance_col.metric(
        "Net variance",
        money(result.net_variance),
        help="Reporting funded total minus source funded total. The bridge explains this figure.",
    )
    exception_col.metric(
        "Open exceptions",
        f"{len(result.exceptions)}",
        help=(
            f"Gross absolute impact {money(result.gross_absolute_impact)}. "
            "Signed impacts are what the bridge uses, so offsetting breaks stay visible."
        ),
    )

    chart_col, bridge_col = st.columns((3, 2), gap="large")
    with chart_col:
        st.subheader("Dollar tie-out")
        st.plotly_chart(
            waterfall_figure(result.bridge),
            width="stretch",
            config={"displayModeBar": False},
        )
    with bridge_col:
        st.subheader("Bridge")
        st.dataframe(
            bridge_display(result.bridge),
            hide_index=True,
            width="stretch",
        )
        st.caption(f"Unexplained residual: {money(result.unexplained)}.")

    st.subheader("Status breakdown")
    st.plotly_chart(
        status_figure(result.status_breakdown),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption(
        "Dollars by status. The reporting Funded bar includes extra duplicate rows and "
        "excludes source-funded loans that the extract mapped to another status."
    )

    st.subheader("Exceptions")
    type_label = st.radio(
        "Discrepancy type",
        TYPE_OPTIONS,
        horizontal=True,
        label_visibility="visible",
    )
    query = st.text_input("Loan id contains", placeholder="LN-000012")
    view_source = result.exceptions
    if type_label != "All":
        view_source = view_source.loc[
            view_source["discrepancy_type"].eq(LABEL_TO_TYPE[type_label])
        ]
    if query.strip():
        view_source = view_source.loc[
            view_source["loan_id"].str.contains(query.strip(), case=False, na=False)
        ]
    view_source = view_source.reset_index(drop=True)
    st.dataframe(
        _exception_view(view_source),
        hide_index=True,
        width="stretch",
    )
    st.caption(f"{len(view_source)} exception row{'s' if len(view_source) != 1 else ''} shown.")

    st.subheader("Investigate discrepancy")
    st.markdown(
        "Pick a loan, or review every row in the current filter. "
        "The note uses the source values, the reporting values, and the signed impact from the tie-out."
    )
    choices = ["All shown exceptions", *view_source["loan_id"].tolist()]
    selected = st.selectbox("Loan", choices)
    if st.button("Investigate Discrepancy", type="primary"):
        loan_arg = None if selected == "All shown exceptions" else selected
        type_arg = None if type_label == "All" else LABEL_TO_TYPE[type_label]
        st.session_state["investigation"] = investigate(
            result.exceptions,
            loan_id=loan_arg,
            discrepancy_type=type_arg,
        )
    report = st.session_state.get("investigation")
    if report:
        with st.container(border=True):
            _render_investigation(report)


if __name__ == "__main__":
    main()
