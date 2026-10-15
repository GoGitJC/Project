"""Plotly figures for the funding tie-out."""

import pandas as pd
import plotly.graph_objects as go

from loanops.formatting import money

NAVY = "#0f3d5e"
COPPER = "#c47b2b"
RED = "#9b3a3a"
GREEN = "#1f7a4d"
GRID = "#e2e6ec"
INK = "#1c2833"


def waterfall_figure(bridge: pd.DataFrame) -> go.Figure:
    labels = bridge["step"].tolist()
    values = [int(value) for value in bridge["amount"]]
    measures = bridge["measure"].tolist()
    figure = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            increasing={"marker": {"color": GREEN}},
            decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": NAVY}},
            connector={"line": {"color": "#b7c0ca", "width": 1}},
            hovertemplate="%{x}<br>%{y:$,.0f}<extra></extra>",
        )
    )
    figure.update_layout(
        waterfallgap=0.35,
        showlegend=False,
        margin={"t": 24, "b": 100, "l": 8, "r": 8},
        height=460,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"color": INK, "size": 13},
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": GRID,
            "zerolinecolor": GRID,
        },
        xaxis={"tickangle": -25},
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
        marker_color=COPPER,
        hovertemplate="%{x}<br>Reporting %{y:$,.0f}<extra></extra>",
    )
    figure.update_layout(
        barmode="group",
        margin={"t": 24, "b": 8, "l": 8, "r": 8},
        height=380,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"color": INK, "size": 13},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "gridcolor": GRID,
            "title": "Loan amount",
        },
        xaxis={"title": ""},
    )
    return figure


def bridge_display(bridge: pd.DataFrame) -> pd.DataFrame:
    """Presentation copy of the tie-out. Amounts stay whole dollars."""
    display = bridge.copy()
    display["Amount"] = display["amount"].map(lambda value: money(int(value)))
    display["Running total"] = display["running_total"].map(lambda value: money(int(value)))
    return display[["step", "Amount", "Running total"]].rename(columns={"step": "Step"})
