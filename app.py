"""LoanOps Intelligence: funding reconciliation dashboard."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from loanops.charts import status_figure, variance_contribution_figure, waterfall_figure
from loanops.constants import AS_OF_DATE, DISCREPANCY_LABELS, SEED
from loanops.database import ensure_database
from loanops.formatting import markdown_safe, money
from loanops.investigate import investigate
from loanops.reconcile import ReconResult, reconcile

TYPE_OPTIONS = ["All", *DISCREPANCY_LABELS.values()]
LABEL_TO_TYPE = {label: key for key, label in DISCREPANCY_LABELS.items()}


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        html, body, [class*="css"] {
            font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }
        .block-container {
            padding-top: 1.15rem;
            padding-bottom: 3rem;
            max-width: 1220px;
        }
        [data-testid="stSidebar"] {
            background-color: #0f3d5e;
            border-right: 1px solid #0b2e46;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdown"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdown"] li,
        [data-testid="stSidebar"] [data-testid="stMarkdown"] strong,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: #e7eef5;
        }
        [data-testid="stSidebar"] hr { border-color: rgba(255, 255, 255, 0.18); }
        .side-brand {
            color: #ffffff;
            font-size: 1.05rem;
            font-weight: 680;
            letter-spacing: -0.02em;
            margin: 0 0 0.15rem;
        }
        .side-kicker {
            color: #d7c4a3;
            font-size: 0.72rem;
            font-weight: 650;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 0 0 0.85rem;
        }
        .eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.75rem;
            font-weight: 650;
            color: #8a5a22;
            margin-bottom: 0.15rem;
        }
        .app-header h1 {
            font-size: 1.7rem;
            line-height: 1.15;
            margin: 0;
            color: #0f3d5e;
            letter-spacing: -0.03em;
            font-weight: 680;
        }
        .page-title {
            font-size: 1.35rem;
            margin: 0.15rem 0 0;
            color: #1c2833;
            letter-spacing: -0.02em;
            font-weight: 650;
        }
        .app-header p { margin: 0.35rem 0 0; color: #3d4c5c; font-size: 1rem; }
        .disclaimer {
            margin-top: 0.55rem;
            color: #5c6b7a;
            font-size: 0.84rem;
        }
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.9rem 0 0.75rem;
        }
        .kpi-card {
            background: #ffffff;
            border: 1px solid #e2e6ec;
            border-top: 3px solid #0f3d5e;
            border-radius: 10px;
            padding: 0.75rem 0.9rem 0.7rem;
            min-width: 0;
        }
        .kpi-card.negative { border-top-color: #9b3a3a; }
        .kpi-card.positive { border-top-color: #1f7a4d; }
        .kpi-label {
            margin: 0;
            color: #5c6b7a;
            font-size: 0.72rem;
            font-weight: 680;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .kpi-value {
            margin: 0.2rem 0 0;
            color: #0f3d5e;
            font-size: 1.55rem;
            line-height: 1.15;
            font-weight: 680;
            letter-spacing: -0.03em;
            font-variant-numeric: tabular-nums;
        }
        .kpi-card.negative .kpi-value { color: #9b3a3a; }
        .kpi-card.positive .kpi-value { color: #1f7a4d; }
        .kpi-note {
            margin: 0.28rem 0 0;
            color: #5c6b7a;
            font-size: 0.78rem;
            line-height: 1.3;
        }
        .status-banner {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: center;
            background: #ffffff;
            border: 1px solid #e2e6ec;
            border-left: 4px solid #1f7a4d;
            border-radius: 10px;
            padding: 0.75rem 1rem;
            margin: 0 0 1.1rem;
        }
        .status-banner.open { border-left-color: #9b3a3a; }
        .status-kicker {
            margin: 0;
            color: #5c6b7a;
            font-size: 0.72rem;
            font-weight: 680;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .status-title {
            margin: 0.12rem 0 0;
            color: #0f3d5e;
            font-size: 1.05rem;
            font-weight: 680;
        }
        .status-banner.open .status-title { color: #9b3a3a; }
        .status-detail { margin: 0.15rem 0 0; color: #3d4c5c; font-size: 0.9rem; }
        .status-figure {
            color: #0f3d5e;
            font-size: 1.25rem;
            font-weight: 680;
            font-variant-numeric: tabular-nums;
            letter-spacing: -0.03em;
            white-space: nowrap;
        }
        .table-scroll {
            overflow-x: auto;
            background: #ffffff;
            border: 1px solid #e2e6ec;
            border-radius: 10px;
            margin: 0.15rem 0 0.35rem;
        }
        table.recon-table {
            width: 100%;
            border-collapse: collapse;
            font-variant-numeric: tabular-nums;
        }
        table.recon-table th {
            text-align: left;
            font-size: 0.72rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: #5c6b7a;
            font-weight: 680;
            padding: 0.7rem 0.85rem;
            border-bottom: 1px solid #e2e6ec;
            white-space: nowrap;
            background: #f8fafc;
        }
        table.recon-table td {
            padding: 0.62rem 0.85rem;
            border-bottom: 1px solid #eef1f5;
            color: #1c2833;
            white-space: nowrap;
            vertical-align: top;
        }
        table.recon-table tr:last-child td { border-bottom: 0; }
        table.recon-table td.num, table.recon-table th.num { text-align: right; }
        table.recon-table td.neg { color: #9b3a3a; font-weight: 650; }
        table.recon-table td.pos { color: #1f7a4d; font-weight: 650; }
        table.recon-table tr.total td { font-weight: 680; color: #0f3d5e; background: #f4f7fb; }
        table.exceptions-table th,
        table.exceptions-table td {
            white-space: normal;
        }
        table.exceptions-table td.num,
        table.exceptions-table th.num {
            white-space: nowrap;
        }
        div[data-testid="stPlotlyChart"] {
            background: #ffffff;
            border: 1px solid #e2e6ec;
            border-radius: 10px;
            padding: 0.2rem 0.35rem 0;
        }
        @media (max-width: 1100px) {
            .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .kpi-value { font-size: 1.35rem; }
            .status-banner { align-items: flex-start; flex-direction: column; }
        }
        @media (max-width: 680px) {
            .kpi-grid { grid-template-columns: 1fr; }
            .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
        }
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


def _kpi_cards(result: ReconResult) -> str:
    net = int(result.net_variance)
    net_class = "negative" if net < 0 else "positive" if net > 0 else ""
    cards = [
        ("Source funded total", money(result.source_funded_total), "Each funded loan once", ""),
        (
            "Reporting funded total",
            money(result.reporting_funded_total),
            "Funded extract rows, extra copies included",
            "",
        ),
        ("Net variance", money(net), "Reporting funded total minus source", net_class),
        (
            "Open exceptions",
            f"{len(result.exceptions)}",
            f"Gross absolute impact {money(result.gross_absolute_impact)}",
            "",
        ),
    ]
    parts = []
    for label, value, note, klass in cards:
        parts.append(
            f"<div class='kpi-card {klass}'>"
            f"<p class='kpi-label'>{html.escape(label)}</p>"
            f"<p class='kpi-value'>{html.escape(value)}</p>"
            f"<p class='kpi-note'>{html.escape(note)}</p>"
            "</div>"
        )
    return f"<div class='kpi-grid'>{''.join(parts)}</div>"


def _status_banner(result: ReconResult) -> str:
    residual = int(result.unexplained)
    balanced = residual == 0
    title = "Tie-out balanced" if balanced else "Tie-out out of balance"
    detail = (
        f"Net variance {money(result.net_variance)} is explained by the bridge. "
        f"Unexplained residual {money(residual)}."
        if balanced
        else (
            f"Net variance {money(result.net_variance)}. "
            f"Unexplained residual {money(residual)}."
        )
    )
    klass = "" if balanced else " open"
    return (
        f"<div class='status-banner{klass}'>"
        "<div>"
        "<p class='status-kicker'>Reconciliation status</p>"
        f"<p class='status-title'>{html.escape(title)}</p>"
        f"<p class='status-detail'>{html.escape(detail)}</p>"
        "</div>"
        f"<div class='status-figure'>{html.escape(money(residual))}</div>"
        "</div>"
    )


def _amount_class(measure: str, amount: int) -> str:
    if measure == "relative" and amount < 0:
        return "num neg"
    if measure == "relative" and amount > 0:
        return "num pos"
    return "num"


def _recon_table(bridge: pd.DataFrame) -> str:
    rows = []
    for record in bridge.itertuples(index=False):
        amount = int(record.amount)
        running = int(record.running_total)
        measure = str(record.measure)
        row_class = " class='total'" if measure in {"absolute", "total"} else ""
        rows.append(
            f"<tr{row_class}>"
            f"<td>{html.escape(str(record.step))}</td>"
            f"<td class='{_amount_class(measure, amount)}'>{html.escape(money(amount))}</td>"
            f"<td class='num'>{html.escape(money(running))}</td>"
            "</tr>"
        )
    header = (
        "<thead><tr>"
        "<th>Step</th>"
        "<th class='num'>Amount</th>"
        "<th class='num'>Running total</th>"
        "</tr></thead>"
    )
    return (
        "<div class='table-scroll'>"
        "<table class='recon-table'>"
        f"{header}<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def _exceptions_table(view: pd.DataFrame) -> str:
    wrap = {"Discrepancy", "Property", "Reporting status"}
    headers = []
    for column in view.columns:
        classes = []
        if column in wrap:
            classes.append("wrap")
        if column in {"Signed impact", "Source amount", "Reporting amount", "Extract rows", "Extra copies"}:
            classes.append("num")
        class_attr = f" class='{' '.join(classes)}'" if classes else ""
        headers.append(f"<th{class_attr}>{html.escape(column)}</th>")
    body = []
    for record in view.itertuples(index=False):
        cells = []
        for column, value in zip(view.columns, record):
            text = html.escape(str(value))
            if column in {"Signed impact", "Source amount", "Reporting amount"}:
                klass = "num"
                if column == "Signed impact" and str(value).startswith("-"):
                    klass = "num neg"
                elif column == "Signed impact" and str(value).startswith("$"):
                    klass = "num pos"
                cells.append(f"<td class='{klass}'>{text}</td>")
            elif column in wrap:
                cells.append(f"<td class='wrap'>{text}</td>")
            else:
                cells.append(f"<td>{text}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return (
        "<div class='table-scroll'>"
        "<table class='recon-table exceptions-table'>"
        f"<thead><tr>{''.join(headers)}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody>"
        "</table></div>"
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
        initial_sidebar_state="expanded",
    )
    _inject_css()
    db_path = ensure_database()
    result = reconcile(db_path)

    with st.sidebar:
        st.markdown(
            "<p class='side-brand'>LoanOps Intelligence</p>"
            "<p class='side-kicker'>Executive overview</p>",
            unsafe_allow_html=True,
        )
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

    st.markdown(
        """
        <div class="app-header">
          <div class="eyebrow">Fictional mortgage lender · Synthetic portfolio</div>
          <h1>LoanOps Intelligence</h1>
          <p class="page-title">Executive Overview</p>
          <p>Funding reconciliation between the loan system of record and the reporting extract.</p>
          <p class="disclaimer">Synthetic data only. Not a production system of record.</p>
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

    st.markdown(_kpi_cards(result), unsafe_allow_html=True)
    st.markdown(_status_banner(result), unsafe_allow_html=True)

    st.subheader("Dollar tie-out")
    st.plotly_chart(
        waterfall_figure(result.bridge),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption("Hover a bar for the amount and the running funded total.")

    st.subheader("Variance contribution")
    st.plotly_chart(
        variance_contribution_figure(result.bridge),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption(
        "Signed dollar impact of each reconciliation category. "
        "Zero is the center line. Green increases the reporting funded total. Red decreases it."
    )

    st.subheader("Reconciliation")
    st.markdown(_recon_table(result.bridge), unsafe_allow_html=True)
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
    if view_source.empty:
        st.info("No exceptions match this filter.")
    else:
        st.markdown(_exceptions_table(_exception_view(view_source)), unsafe_allow_html=True)
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
