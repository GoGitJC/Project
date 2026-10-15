"""LoanOps Intelligence workspace.

The page reads ReconResult and investigate(). It does not classify loans
or replace the dollar bridge.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from loanops.charts import (
    bridge_display,
    funding_trend_figure,
    impact_by_type_figure,
    portfolio_figure,
    severity_figure,
    state_impact_figure,
    status_figure,
    waterfall_figure,
)
from loanops.constants import AS_OF_DATE, DISCREPANCY_LABELS, MISSING, SEED
from loanops.database import ensure_database
from loanops.formatting import markdown_safe, money
from loanops.investigate import investigate
from loanops.presentation import (
    SEVERITY_BY_TYPE,
    SEVERITY_TONE,
    exception_display,
    exception_export,
    exception_summary,
    filter_exceptions,
    funding_trend,
    impact_by_state,
    load_source_loans,
    mix_by,
    preferred_loan,
    rank_exceptions,
    severity_summary,
    status_display,
    tie_out_status,
)
from loanops.reconcile import reconcile
from loanops.theme import THEME_CSS

PAGES = (
    "Executive overview",
    "Reconciliation",
    "Investigate",
    "Data quality",
)
TYPE_OPTIONS = ["All", *DISCREPANCY_LABELS.values()]
LABEL_TO_TYPE = {label: key for key, label in DISCREPANCY_LABELS.items()}
SEVERITY_OPTIONS = ["All", "Critical", "Warning", "Attention"]
PLOTLY = {"displayModeBar": False}
ALL_OPEN = "All open exceptions"
ALL_TYPE = "All in this type"

GUIDE = (
    {
        "page": "Executive overview",
        "kicker": "01 · Position",
        "title": "Read the funded position, then the bridge",
        "body": (
            "Source funded volume counts each Funded loan once. "
            "Reporting funded volume sums every Funded extract row, so an extra copy adds dollars. "
            "Net variance is reporting minus source. "
            "Health reads Explained only when the unexplained residual is zero. "
            "The waterfall below is that bridge."
        ),
    },
    {
        "page": "Reconciliation",
        "kicker": "02 · Population",
        "title": "The variance is a list of loans, not a plug number",
        "body": (
            "The status table is the source population beside the extract. "
            "The bridge lists each rule in order. "
            "Open exceptions below are the rows behind those steps."
        ),
        "filter_type": "All",
    },
    {
        "page": "Reconciliation",
        "kicker": "03 · Missing loans",
        "title": "Funded in source, absent from the extract",
        "body": (
            "This filter keeps one discrepancy type. "
            "Each signed impact is the source amount once. "
            "Select a row and continue, or stay here and open the dossier from the table."
        ),
        "filter_type": "Missing from reporting",
    },
    {
        "page": "Investigate",
        "kicker": "04 · Dossier",
        "title": "Open the loan the tie-out already named",
        "body": (
            "The loan is selected. Click Investigate Discrepancy. "
            "The dossier shows the detected break, the contributing record, "
            "the source and reporting evidence, the signed impact, and the corrective action. "
            "The wording is filled from that reconciliation row."
        ),
        "discrepancy_type": MISSING,
        "preferred": "LN-000012",
    },
    {
        "page": "Data quality",
        "kicker": "05 · Quality",
        "title": "Same exceptions, read as a quality picture",
        "body": (
            "Duplicates, missing records, amount deltas, and status errors are counts "
            "and signed impacts from the exception frame. "
            "Freshness is the portfolio as-of date and the time this session ran the tie-out. "
            "This snapshot is synthetic."
        ),
    },
)


def _html(fragment: str) -> None:
    # Dollar signs inside HTML become entities so Streamlit does not parse them as math.
    st.markdown(fragment.replace("$", "&#36;"), unsafe_allow_html=True)


def _init_state() -> None:
    st.session_state.setdefault("page", PAGES[0])
    st.session_state.setdefault("guide_step", None)
    st.session_state.setdefault("reviewed_loans", [])
    st.session_state.setdefault("filter_type", "All")
    st.session_state.setdefault("filter_state", "All")
    st.session_state.setdefault("filter_property", "All")
    st.session_state.setdefault("filter_severity", "All")
    st.session_state.setdefault("filter_query", "")
    st.session_state.setdefault("inv_type", "All")
    st.session_state.setdefault("inv_loan_select", ALL_OPEN)


def _clock(iso_stamp: str) -> str:
    moment = datetime.fromisoformat(iso_stamp)
    return moment.strftime("%d %b %Y · %H:%M UTC")


def _selected_rows(event) -> list[int]:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return []
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows", [])
    return list(rows or [])


def _mark_reviewed(loan_ids: list[str]) -> None:
    reviewed: list[str] = st.session_state["reviewed_loans"]
    for loan_id in loan_ids:
        if loan_id not in reviewed:
            reviewed.append(loan_id)


def _enter_guide(step: int, exceptions: pd.DataFrame) -> None:
    spec = GUIDE[step]
    st.session_state["guide_step"] = step
    st.session_state["page"] = spec["page"]
    if "filter_type" in spec:
        st.session_state["filter_type"] = spec["filter_type"]
        st.session_state["filter_state"] = "All"
        st.session_state["filter_property"] = "All"
        st.session_state["filter_severity"] = "All"
        st.session_state["filter_query"] = ""
    if "discrepancy_type" in spec:
        loan_id = preferred_loan(exceptions, spec["discrepancy_type"], spec["preferred"])
        st.session_state["inv_type"] = DISCREPANCY_LABELS[spec["discrepancy_type"]]
        if loan_id:
            st.session_state["inv_loan_select"] = loan_id


def _clear_filters() -> None:
    st.session_state["filter_type"] = "All"
    st.session_state["filter_state"] = "All"
    st.session_state["filter_property"] = "All"
    st.session_state["filter_severity"] = "All"
    st.session_state["filter_query"] = ""


def _open_investigation(exceptions: pd.DataFrame, loan_id: str, discrepancy_type: str) -> None:
    st.session_state["inv_type"] = DISCREPANCY_LABELS[discrepancy_type]
    st.session_state["inv_loan_select"] = loan_id
    st.session_state["investigation"] = investigate(
        exceptions,
        loan_id=loan_id,
        discrepancy_type=discrepancy_type,
    )
    _mark_reviewed(st.session_state["investigation"]["loan_ids"])
    st.session_state["page"] = "Investigate"


def _page_head(kicker: str, title: str, summary: str) -> None:
    _html(
        f'<div class="page-head">'
        f'<div class="page-kicker">{kicker}</div>'
        f"<h1>{title}</h1>"
        f"<p>{summary}</p>"
        f'<div class="synth">Synthetic portfolio · Not a production system of record</div>'
        f"</div>"
    )


def _section(title: str, summary: str) -> None:
    _html(f'<div class="section-head"><h2>{title}</h2><p>{summary}</p></div>')


def _kpi(label: str, value: str, hint: str, tone: str) -> str:
    return (
        f'<article class="kpi {tone}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="hint">{hint}</div>'
        f"</article>"
    )


def _render_guide(exceptions: pd.DataFrame) -> None:
    step = st.session_state["guide_step"]
    if step is None:
        return
    spec = GUIDE[step]
    _html(
        f'<div class="guide">'
        f'<div class="step">{spec["kicker"]} · Two-minute briefing</div>'
        f'<h3>{spec["title"]}</h3>'
        f'<p>{spec["body"]}</p>'
        f"</div>"
    )
    back, nxt, _rest = st.columns([1, 1.2, 4])
    if step > 0 and back.button("Back", key="guide-back"):
        _enter_guide(step - 1, exceptions)
        st.rerun()
    finish = step == len(GUIDE) - 1
    if nxt.button("Finish briefing" if finish else "Next", key="guide-next", type="primary"):
        if finish:
            st.session_state["guide_step"] = None
        else:
            _enter_guide(step + 1, exceptions)
        st.rerun()


def _select_page(page: str) -> None:
    st.session_state["page"] = page
    st.session_state["guide_step"] = None


def _start_briefing() -> None:
    st.session_state["guide_step"] = 0
    st.session_state["page"] = GUIDE[0]["page"]


def _exit_briefing() -> None:
    st.session_state["guide_step"] = None


def _render_sidebar(result, db_name: str) -> None:
    label, _tone, hint = tie_out_status(result.unexplained, len(result.exceptions))
    with st.sidebar:
        _html(
            '<div class="brand">'
            '<div class="brand-mark">LO</div>'
            "<div><div class=\"brand-name\">LoanOps</div>"
            '<div class="brand-sub">Intelligence</div></div>'
            "</div>"
        )
        st.caption("Fictional mortgage lender. Synthetic loans only.")
        for page in PAGES:
            active = st.session_state["page"] == page
            st.button(
                page,
                key=f"nav-{page.lower().replace(' ', '-')}",
                width="stretch",
                type="primary" if active else "secondary",
                on_click=_select_page,
                args=(page,),
            )
        st.divider()
        st.button(
            "Start two-minute briefing",
            key="start-briefing",
            width="stretch",
            on_click=_start_briefing,
        )
        if st.session_state["guide_step"] is not None:
            st.button(
                "Exit briefing",
                key="exit-briefing",
                width="stretch",
                on_click=_exit_briefing,
            )
        _html(
            f'<div class="side-note">'
            f'<div class="label">Reconciliation health</div>'
            f'<div class="value">{label}</div>'
            f'<div class="hint">{hint}</div>'
            f"</div>"
        )
        st.caption(
            markdown_safe(
                f"As of {AS_OF_DATE} · Seed {SEED} · {result.extract_name} · File {db_name}"
            )
        )


def _render_kpis(result, summary: pd.DataFrame, reconciled_at: str) -> None:
    health, health_tone, health_hint = tie_out_status(result.unexplained, len(result.exceptions))
    critical = int(summary.loc[summary["severity"].eq("Critical"), "loans"].sum())
    open_count = int(summary["loans"].sum())
    if critical:
        open_tone = "critical"
    elif open_count:
        open_tone = "warning"
    else:
        open_tone = "success"
    variance_tone = "success" if result.net_variance == 0 else "warning"
    if result.unexplained != 0:
        variance_tone = "critical"
    type_count = int((summary["loans"] > 0).sum())
    cards = [
        _kpi(
            "Source funded volume",
            money(result.source_funded_total),
            f"{result.source_funded_count} funded loans, each counted once.",
            "neutral",
        ),
        _kpi(
            "Reporting funded volume",
            money(result.reporting_funded_total),
            f"{result.reporting_funded_row_count} funded extract rows, extra copies included.",
            "neutral",
        ),
        _kpi(
            "Financial discrepancy",
            money(result.net_variance),
            f"Reporting minus source. Gross absolute impact {money(result.gross_absolute_impact)}.",
            variance_tone,
        ),
        _kpi("Reconciliation health", health, health_hint, health_tone),
        _kpi(
            "Open exceptions",
            str(open_count),
            f"{critical} critical · {type_count} discrepancy types with at least one row.",
            open_tone,
        ),
        _kpi(
            "Last reconciliation",
            _clock(reconciled_at),
            f"Portfolio as of {AS_OF_DATE}. Extract {result.extract_name}. Computed this session.",
            "neutral",
        ),
    ]
    _html(f'<div class="kpi-grid">{"".join(cards)}</div>')


def _render_executive(result, loans: pd.DataFrame, summary: pd.DataFrame, reconciled_at: str) -> None:
    _page_head(
        "Executive dashboard",
        "Funding position",
        "Source funded volume against the reporting extract, the explained gap, and the open book of exceptions.",
    )
    st.caption(
        markdown_safe(
            f"{result.source_loan_count} source loans · "
            f"{result.reporting_row_count} reporting rows · "
            f"Reconciled {_clock(reconciled_at)}."
        )
    )
    _render_kpis(result, summary, reconciled_at)
    _section(
        "Dollar tie-out",
        "Each bar is one reconciliation rule. The last total is the reporting funded volume.",
    )
    chart_col, bridge_col = st.columns((1.25, 1), gap="large")
    with chart_col:
        st.plotly_chart(waterfall_figure(result.bridge), width="stretch", config=PLOTLY)
    with bridge_col:
        st.dataframe(bridge_display(result.bridge), hide_index=True, width="stretch")
        st.caption(markdown_safe(f"Unexplained residual: {money(result.unexplained)}."))
    _section(
        "Funding trend",
        "Source loans with status Funded, summed by funding month. This is portfolio mix, not a second tie-out.",
    )
    st.plotly_chart(funding_trend_figure(funding_trend(loans)), width="stretch", config=PLOTLY)
    property_col, purpose_col = st.columns(2, gap="large")
    with property_col:
        _section("Funded volume by property type", "Source funded loans only.")
        st.plotly_chart(
            portfolio_figure(mix_by(loans, "property_type"), category="property_type"),
            width="stretch",
            config=PLOTLY,
        )
    with purpose_col:
        _section("Funded volume by purpose", "Source funded loans only.")
        st.plotly_chart(
            portfolio_figure(mix_by(loans, "loan_purpose"), category="loan_purpose"),
            width="stretch",
            config=PLOTLY,
        )
    _section(
        "Status breakdown",
        "Source dollars beside the extract. Reporting Funded includes extra duplicate rows and excludes source-funded loans mapped to another status.",
    )
    st.plotly_chart(status_figure(result.status_breakdown), width="stretch", config=PLOTLY)


def _render_workspace(result) -> None:
    _page_head(
        "Reconciliation workspace",
        "Source versus reporting",
        "Compare the two populations, then filter the loan-level exceptions that explain the funded gap.",
    )
    _section(
        "Population comparison",
        "Control totals stay on the full portfolio. Filters below do not change this table.",
    )
    st.dataframe(status_display(result.status_breakdown), hide_index=True, width="stretch")
    _section(
        "Variance breakdown",
        "Signed steps from source funded volume to reporting funded volume.",
    )
    bridge_col, note_col = st.columns((3, 2), gap="large")
    with bridge_col:
        st.dataframe(bridge_display(result.bridge), hide_index=True, width="stretch")
    with note_col:
        _html(
            _kpi(
                "Net variance",
                money(result.net_variance),
                f"Unexplained residual {money(result.unexplained)}. Gross absolute impact {money(result.gross_absolute_impact)}.",
                "warning" if result.net_variance else "success",
            )
        )
        st.caption(
            "Missing loans reduce reporting by the source amount once. "
            "Duplicates add extra copies only. Status and amount breaks book the signed difference once."
        )
    summary = exception_summary(result.exceptions)
    _section(
        "Exception alerts",
        "Display severity groups the four discrepancy types. The dollar figure is the signed impact already on those rows.",
    )
    alerts = []
    for row in summary.itertuples(index=False):
        if int(row.loans) == 0:
            continue
        tone = SEVERITY_TONE[row.severity]
        alerts.append(
            f'<div class="alert {tone}"><div class="dot"></div><div>'
            f'<div class="title">{row.label}</div>'
            f'<div class="meta">{row.severity} · {int(row.loans)} loans · '
            f"signed impact {money(int(row.signed_impact))}</div>"
            f"</div></div>"
        )
    if alerts:
        _html("".join(alerts))
    else:
        _html(
            '<div class="empty"><div class="page-kicker">Clear</div>'
            "<h3>No open exceptions</h3>"
            "<p>The tie-out did not return any discrepancy rows.</p></div>"
        )

    _section("Loan-level exceptions", "Search and filter the open book. Export follows the rows in view.")
    states = ["All", *sorted(result.exceptions["property_state"].dropna().astype(str).unique())]
    properties = ["All", *sorted(result.exceptions["property_type"].dropna().astype(str).unique())]
    if st.session_state["filter_state"] not in states:
        st.session_state["filter_state"] = "All"
    if st.session_state["filter_property"] not in properties:
        st.session_state["filter_property"] = "All"
    if st.session_state["filter_type"] not in TYPE_OPTIONS:
        st.session_state["filter_type"] = "All"
    if st.session_state["filter_severity"] not in SEVERITY_OPTIONS:
        st.session_state["filter_severity"] = "All"

    type_col, severity_col, state_col, property_col = st.columns(4)
    type_label = type_col.selectbox("Discrepancy", TYPE_OPTIONS, key="filter_type")
    severity = severity_col.selectbox("Display severity", SEVERITY_OPTIONS, key="filter_severity")
    state = state_col.selectbox("State", states, key="filter_state")
    property_type = property_col.selectbox("Property type", properties, key="filter_property")
    search_col, clear_col = st.columns([4, 1])
    query = search_col.text_input("Loan id contains", key="filter_query", placeholder="LN-000012")
    clear_col.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
    clear_col.button("Clear filters", on_click=_clear_filters, width="stretch")

    filtered = filter_exceptions(
        result.exceptions,
        type_label=type_label,
        state=state,
        property_type=property_type,
        severity=severity,
        query=query,
        label_to_type=LABEL_TO_TYPE,
    )
    ranked = rank_exceptions(filtered)
    filtered_impact = int(ranked["signed_impact"].sum()) if not ranked.empty else 0
    _html(
        '<div class="kpi-grid">'
        + _kpi("Rows in view", str(len(ranked)), "After the filters above.", "neutral")
        + _kpi(
            "Filtered signed impact",
            money(filtered_impact),
            f"Sum of signed impact on these rows. Control net variance remains {money(result.net_variance)}.",
            "neutral",
        )
        + "</div>"
    )
    if ranked.empty:
        _html(
            '<div class="empty"><div class="page-kicker">No rows</div>'
            "<h3>Nothing matches these filters</h3>"
            "<p>The tie-out still has its open population. Clear a filter to return to it.</p></div>"
        )
        return

    event = st.dataframe(
        exception_display(ranked),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="exception-table",
    )
    st.caption(
        "Select a row, then investigate it. "
        "The CSV keeps whole-dollar amounts. The table shows the same amounts in accounting format."
    )
    export_col, investigate_col = st.columns([1, 1])
    export_col.download_button(
        "Export CSV",
        data=exception_export(ranked),
        file_name=f"loanops-exceptions-{AS_OF_DATE}.csv",
        mime="text/csv",
        width="stretch",
    )
    rows = _selected_rows(event)
    if investigate_col.button("Investigate Discrepancy", type="primary", width="stretch"):
        if not rows:
            st.warning("Select an exception row first.")
        else:
            chosen = ranked.iloc[int(rows[0])]
            _open_investigation(result.exceptions, str(chosen["loan_id"]), str(chosen["discrepancy_type"]))
            st.rerun()


def _investigation_is_current(
    report: dict,
    selected: str,
    all_label: str,
    type_label: str,
    exceptions: pd.DataFrame,
) -> bool:
    loan_ids = [str(value) for value in report["loan_ids"]]
    if selected != all_label:
        return loan_ids == [selected]
    pool = exceptions
    if type_label != "All":
        pool = pool.loc[pool["discrepancy_type"].eq(LABEL_TO_TYPE[type_label])]
    return set(loan_ids) == set(pool["loan_id"].astype(str))


def _loan_options(exceptions: pd.DataFrame, type_label: str) -> tuple[str, list[str]]:
    pool = exceptions
    if type_label != "All":
        pool = pool.loc[pool["discrepancy_type"].eq(LABEL_TO_TYPE[type_label])]
    all_label = ALL_OPEN if type_label == "All" else ALL_TYPE
    options = [all_label, *pool["loan_id"].astype(str).tolist()]
    return all_label, options


def _render_dossier(report: dict) -> None:
    reviewed = set(st.session_state["reviewed_loans"])
    loan_ids = report["loan_ids"]
    if not loan_ids:
        status_label, status_class = "No match", "none"
    elif set(loan_ids).issubset(reviewed):
        status_label, status_class = "Open · reviewed this session", "open"
    else:
        status_label, status_class = "Open · evidence assembled", "open"
    severity = ""
    if len(loan_ids) == 1 and report["comparison"]:
        kind = next(
            (key for key, label in DISCREPANCY_LABELS.items() if report["title"].startswith(label)),
            None,
        )
        if kind:
            severity_name = SEVERITY_BY_TYPE.get(kind, "")
            if severity_name:
                severity = (
                    f'<span class="pill {SEVERITY_TONE[severity_name]}">{severity_name}</span>'
                )
    if not loan_ids:
        loans_text = "None"
    elif len(loan_ids) > 4:
        loans_text = "Loan ids are listed in the evidence below."
    else:
        loans_text = ", ".join(loan_ids)
    impact = int(report["signed_impact"])
    if impact < 0:
        impact_tone = "critical"
    elif impact > 0:
        impact_tone = "warning"
    else:
        impact_tone = "neutral"
    _html(
        f'<div class="dossier-top">'
        f"<div><div class=\"page-kicker\">Detected discrepancy</div>"
        f"<h2 style=\"margin:0.15rem 0 0;color:#0F172A;letter-spacing:-0.02em;\">{report['title']}</h2>"
        f'<div style="margin-top:0.45rem">{severity} '
        f'<span class="pill {status_class}">{status_label}</span></div></div>'
        f"</div>"
    )
    _html(
        '<div class="kpi-grid">'
        + _kpi(
            "Financial impact",
            money(impact),
            "Signed impact from the tie-out for this selection.",
            impact_tone,
        )
        + _kpi(
            "Contributing loan records",
            str(len(loan_ids)),
            loans_text,
            "neutral",
        )
        + _kpi(
            "Investigation status",
            "Open" if loan_ids else "No match",
            "Reviewing a dossier does not clear the exception or post a correction.",
            "warning" if loan_ids else "neutral",
        )
        + "</div>"
    )
    st.markdown("**Root cause findings**")
    st.markdown(markdown_safe(report["summary"]))
    st.markdown("**Reconciliation evidence**")
    if report["comparison"]:
        evidence = pd.DataFrame(report["comparison"])
        for column in ("source", "reporting"):
            evidence[column] = evidence[column].map(
                lambda value: "—" if str(value) in {"nan", "None"} else value
            )
        st.dataframe(
            evidence,
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
    else:
        _html(
            '<div class="empty"><h3>No evidence rows</h3>'
            "<p>No exception matched this selection.</p></div>"
        )
    _html(
        f'<div class="action"><div class="label">Recommended corrective action</div>'
        f"<p>{report['next_step']}</p></div>"
    )


def _render_investigate(result) -> None:
    _page_head(
        "Investigate discrepancy",
        "Evidence dossier",
        "Pick a loan or a discrepancy type. The note cites source values, reporting values, and the signed impact.",
    )
    if st.session_state["inv_type"] not in TYPE_OPTIONS:
        st.session_state["inv_type"] = "All"
    all_label, options = _loan_options(result.exceptions, st.session_state["inv_type"])
    if st.session_state["inv_loan_select"] not in options:
        st.session_state["inv_loan_select"] = all_label

    control_col, dossier_col = st.columns([1, 2], gap="large")
    with control_col:
        type_label = st.selectbox("Discrepancy", TYPE_OPTIONS, key="inv_type")
        all_label, options = _loan_options(result.exceptions, type_label)
        if st.session_state["inv_loan_select"] not in options:
            st.session_state["inv_loan_select"] = all_label
        selected = st.selectbox("Loan", options, key="inv_loan_select")
        run = st.button("Investigate Discrepancy", type="primary", width="stretch")
        if run:
            loan_arg = None if selected == all_label else selected
            type_arg = None if type_label == "All" else LABEL_TO_TYPE[type_label]
            opened = investigate(result.exceptions, loan_id=loan_arg, discrepancy_type=type_arg)
            st.session_state["investigation"] = opened
            _mark_reviewed(opened["loan_ids"])
        reviewed = st.session_state["reviewed_loans"]
        if reviewed:
            shown = ", ".join(reviewed[:8])
            extra = f" +{len(reviewed) - 8} more" if len(reviewed) > 8 else ""
            st.caption(f"Reviewed this session: {shown}{extra}")
        else:
            st.caption("No loan has been opened in this session.")
        st.caption(
            "A reviewed loan stays open. This workspace does not write back to the source system or the extract."
        )
    report = st.session_state.get("investigation")
    with dossier_col:
        if not report:
            _html(
                '<div class="empty"><div class="page-kicker">Waiting</div>'
                "<h3>No investigation yet</h3>"
                "<p>Select a loan and click Investigate Discrepancy. "
                "The findings are filled from the reconciliation row.</p></div>"
            )
            return
        if not _investigation_is_current(report, selected, all_label, type_label, result.exceptions):
            st.caption(
                "This dossier is the previous investigation. "
                "Click Investigate Discrepancy to open the current selection."
            )
        with st.container(border=True):
            _render_dossier(report)


def _render_quality(result, reconciled_at: str) -> None:
    _page_head(
        "Data quality center",
        "Exception composition",
        "The same open exceptions, grouped so duplicates, missing records, bad amounts, and wrong statuses can be read at a glance.",
    )
    summary = exception_summary(result.exceptions)
    cards = []
    tones = {"Critical": "critical", "Warning": "warning", "Attention": "attention"}
    for row in summary.itertuples(index=False):
        cards.append(
            _kpi(
                row.label,
                str(int(row.loans)),
                f"{row.severity} · signed impact {money(int(row.signed_impact))}.",
                tones[row.severity],
            )
        )
    _html(f'<div class="kpi-grid quarters">{"".join(cards)}</div>')
    impact_col, severity_col = st.columns(2, gap="large")
    with impact_col:
        _section("Absolute impact by type", "Absolute value of the signed impact on each discrepancy type.")
        st.plotly_chart(impact_by_type_figure(summary), width="stretch", config=PLOTLY)
    with severity_col:
        _section("Exception severity", "Critical, warning, and attention counts from the display grouping.")
        st.plotly_chart(severity_figure(severity_summary(summary)), width="stretch", config=PLOTLY)
    by_state = impact_by_state(result.exceptions)
    _section(
        "Absolute impact by state",
        "Where the open exception dollars sit. Absolute impact keeps offsetting breaks visible.",
    )
    if by_state.empty:
        _html('<div class="empty"><h3>No state concentration</h3><p>No exception rows are open.</p></div>')
    else:
        st.plotly_chart(state_impact_figure(by_state), width="stretch", config=PLOTLY)

    _section(
        "Data freshness",
        "This demo has no source watermark and no downstream feed. The clocks below are the portfolio as-of date and this session.",
    )
    row_delta = result.reporting_row_count - result.source_loan_count
    _html(
        '<div class="kpi-grid">'
        + _kpi("Portfolio as of", AS_OF_DATE, "Business date on the synthetic portfolio.", "neutral")
        + _kpi("Reporting extract", result.extract_name, "Name stored with the extract rows.", "neutral")
        + _kpi("Reconciled this session", _clock(reconciled_at), "When this browser session ran the tie-out.", "neutral")
        + _kpi(
            "Source loans",
            str(result.source_loan_count),
            f"{result.source_funded_count} of them are Funded.",
            "neutral",
        )
        + _kpi(
            "Reporting rows",
            str(result.reporting_row_count),
            f"{result.reporting_funded_row_count} rows have status Funded.",
            "neutral",
        )
        + _kpi(
            "Row difference",
            f"{row_delta:+d}",
            "Reporting rows minus source loans. Missing loans and extra copies both move this count.",
            "warning" if row_delta else "success",
        )
        + "</div>"
    )
    _section("Quality table", "Whole dollars, ready to export. Display severity is not a separate control result.")
    quality = summary.copy()
    quality["Signed impact"] = quality["signed_impact"].map(lambda value: money(int(value)))
    quality["Absolute impact"] = quality["absolute_impact"].map(lambda value: money(int(value)))
    st.dataframe(
        quality[["label", "severity", "loans", "Signed impact", "Absolute impact"]].rename(
            columns={"label": "Discrepancy", "severity": "Display severity", "loans": "Loans"}
        ),
        hide_index=True,
        width="stretch",
    )
    quality_csv = summary[
        ["label", "severity", "loans", "signed_impact", "absolute_impact"]
    ].to_csv(index=False).encode("utf-8")
    first, second = st.columns(2)
    first.download_button(
        "Export quality summary",
        data=quality_csv,
        file_name=f"loanops-data-quality-{AS_OF_DATE}.csv",
        mime="text/csv",
        width="stretch",
    )
    second.download_button(
        "Export all exceptions",
        data=exception_export(rank_exceptions(result.exceptions)),
        file_name=f"loanops-exceptions-{AS_OF_DATE}.csv",
        mime="text/csv",
        width="stretch",
    )


def main() -> None:
    st.set_page_config(
        page_title="LoanOps Intelligence",
        page_icon=":material/account_balance:",
        layout="wide",
        initial_sidebar_state="auto",
    )
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    _init_state()
    db_path = ensure_database()
    with st.spinner("Reconciling the source ledger to the reporting extract…"):
        result = reconcile(db_path)
    st.session_state.setdefault(
        "reconciled_at",
        datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    loans = load_source_loans(db_path)
    summary = exception_summary(result.exceptions)
    _render_sidebar(result, db_path.name)
    _render_guide(result.exceptions)
    page = st.session_state["page"]
    if page == "Executive overview":
        _render_executive(result, loans, summary, st.session_state["reconciled_at"])
    elif page == "Reconciliation":
        _render_workspace(result)
    elif page == "Investigate":
        _render_investigate(result)
    else:
        _render_quality(result, st.session_state["reconciled_at"])


if __name__ == "__main__":
    main()
