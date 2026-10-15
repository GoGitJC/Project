"""Plotly figures for the funding tie-out and the operations workspace."""

import pandas as pd
import plotly.graph_objects as go

from loanops.formatting import money
from loanops.presentation import SEVERITY_TONE
from loanops.theme import AMBER, BLUE, EMERALD, INK, LINE, NAVY, RED, SLATE

SHORT_STEPS = {
    "Source funded total": "Source funded",
    "Missing from reporting": "Missing",
    "Reported as not funded": "Not funded",
    "Reported as funded in error": "Funded in error",
    "Amount differences": "Amount deltas",
    "Duplicate extra copies": "Duplicate copies",
    "Reporting funded total": "Reporting funded",
}
SEVERITY_COLORS = {
    "critical": RED,
    "warning": AMBER,
    "attention": BLUE,
}


def _base_layout(figure: go.Figure, *, height: int, bottom: int = 40, top: int = 36) -> None:
    figure.update_layout(
        height=height,
        margin={"t": top, "b": bottom, "l": 8, "r": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif", "color": INK, "size": 13},
        hoverlabel={"bgcolor": NAVY, "font_color": "#F8FAFC", "bordercolor": NAVY},
        showlegend=False,
    )


def waterfall_figure(bridge: pd.DataFrame) -> go.Figure:
    full = bridge["step"].tolist()
    labels = [SHORT_STEPS.get(step, step) for step in full]
    values = [int(value) for value in bridge["amount"]]
    measures = bridge["measure"].tolist()
    figure = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            customdata=full,
            increasing={"marker": {"color": EMERALD}},
            decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": NAVY}},
            connector={"line": {"color": "#94A3B8", "width": 1}},
            textposition="outside",
            hovertemplate="%{customdata}<br>%{y:$,.0f}<extra></extra>",
        )
    )
    _base_layout(figure, height=480, bottom=120, top=28)
    figure.update_layout(
        waterfallgap=0.35,
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": LINE,
            "zerolinecolor": LINE,
            "title": "Funded volume (USD)",
            "automargin": True,
        },
        xaxis={"tickangle": -32, "title": "Tie-out step", "automargin": True},
    )
    return figure


def status_figure(breakdown: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_bar(
        name="Source system",
        x=breakdown["status"],
        y=breakdown["source_amount"],
        marker_color=NAVY,
        hovertemplate="%{x}<br>Source %{y:$,.0f}<extra></extra>",
    )
    figure.add_bar(
        name="Reporting extract",
        x=breakdown["status"],
        y=breakdown["reporting_amount"],
        marker_color=BLUE,
        hovertemplate="%{x}<br>Reporting %{y:$,.0f}<extra></extra>",
    )
    _base_layout(figure, height=380, bottom=36, top=48)
    figure.update_layout(
        barmode="group",
        showlegend=True,
        legend={"orientation": "h", "y": 1.12, "x": 0},
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": LINE,
            "title": "Loan amount (USD)",
            "automargin": True,
        },
        xaxis={"title": "Loan status", "automargin": True},
    )
    return figure


def funding_trend_figure(trend: pd.DataFrame) -> go.Figure:
    figure = go.Figure(
        go.Bar(
            x=trend["month"],
            y=trend["funded_volume"],
            marker_color=BLUE,
            customdata=trend["funded_loans"],
            hovertemplate="%{x}<br>%{y:$,.0f}<br>%{customdata} loans<extra></extra>",
        )
    )
    _base_layout(figure, height=340, bottom=48)
    figure.update_layout(
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": LINE,
            "title": "Funded volume (USD)",
            "automargin": True,
        },
        xaxis={"title": "Funding month", "automargin": True},
    )
    return figure


def portfolio_figure(mix: pd.DataFrame, *, category: str) -> go.Figure:
    ordered = mix.sort_values("volume", ascending=True)
    figure = go.Figure(
        go.Bar(
            x=ordered["volume"],
            y=ordered[category],
            orientation="h",
            marker_color=NAVY,
            customdata=ordered["loans"],
            hovertemplate="%{y}<br>%{x:$,.0f}<br>%{customdata} loans<extra></extra>",
        )
    )
    _base_layout(figure, height=max(280, 42 * max(len(ordered), 1)), bottom=36, top=16)
    figure.update_layout(
        xaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": LINE,
            "title": "Funded volume (USD)",
            "automargin": True,
        },
        yaxis={"title": "", "automargin": True},
    )
    return figure


def impact_by_type_figure(summary: pd.DataFrame) -> go.Figure:
    colors = [SEVERITY_COLORS[SEVERITY_TONE[severity]] for severity in summary["severity"]]
    figure = go.Figure(
        go.Bar(
            x=summary["label"],
            y=summary["absolute_impact"],
            marker_color=colors,
            customdata=list(zip(summary["loans"], summary["signed_impact"])),
            hovertemplate="%{x}<br>Absolute %{y:$,.0f}<br>%{customdata[0]} loans<extra></extra>",
        )
    )
    _base_layout(figure, height=360, bottom=90, top=16)
    figure.update_layout(
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": LINE,
            "title": "Absolute signed impact (USD)",
            "automargin": True,
        },
        xaxis={"title": "Discrepancy type", "tickangle": -20, "automargin": True},
    )
    return figure


def severity_figure(summary: pd.DataFrame) -> go.Figure:
    colors = [SEVERITY_COLORS[SEVERITY_TONE[severity]] for severity in summary["severity"]]
    figure = go.Figure(
        go.Bar(
            x=summary["loans"],
            y=summary["severity"],
            orientation="h",
            marker_color=colors,
            hovertemplate="%{y}<br>%{x} exceptions<extra></extra>",
        )
    )
    _base_layout(figure, height=260, bottom=36, top=16)
    figure.update_layout(
        xaxis={"title": "Open exceptions", "gridcolor": LINE, "dtick": 1, "automargin": True},
        yaxis={"title": "Display severity", "automargin": True},
    )
    return figure


def state_impact_figure(by_state: pd.DataFrame) -> go.Figure:
    ordered = by_state.sort_values("absolute_impact", ascending=True)
    figure = go.Figure(
        go.Bar(
            x=ordered["absolute_impact"],
            y=ordered["property_state"],
            orientation="h",
            marker_color=SLATE,
            customdata=ordered["loans"],
            hovertemplate="%{y}<br>Absolute %{x:$,.0f}<br>%{customdata} exceptions<extra></extra>",
        )
    )
    _base_layout(figure, height=max(280, 28 * max(len(ordered), 1)), bottom=36, top=16)
    figure.update_layout(
        xaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": LINE,
            "title": "Absolute signed impact (USD)",
            "automargin": True,
        },
        yaxis={"title": "Property state", "automargin": True},
    )
    return figure


def bridge_display(bridge: pd.DataFrame) -> pd.DataFrame:
    """Presentation copy of the tie-out. Amounts stay whole dollars."""
    display = bridge.copy()
    display["Amount"] = display["amount"].map(lambda value: money(int(value)))
    display["Running total"] = display["running_total"].map(lambda value: money(int(value)))
    return display[["step", "Amount", "Running total"]].rename(columns={"step": "Step"})
