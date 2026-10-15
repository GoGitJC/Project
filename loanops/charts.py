"""Plotly figures for the funding tie-out.

Figures read the reconciliation bridge and status breakdown. They do not
recalculate impacts.
"""

import pandas as pd
import plotly.graph_objects as go

from loanops.formatting import money

NAVY = "#0f3d5e"
COPPER = "#c47b2b"
RED = "#9b3a3a"
GREEN = "#1f7a4d"
GRID = "#e6ebf1"
INK = "#1c2833"
MUTED = "#5c6b7a"
FONT = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'

# Display labels only. The bridge step names stay unchanged for the tie-out.
_TICKS = {
    "Source funded total": "Source<br>funded",
    "Missing from reporting": "Missing",
    "Reported as not funded": "Not<br>funded",
    "Reported as funded in error": "Funded<br>in error",
    "Amount differences": "Amount<br>difference",
    "Duplicate extra copies": "Extra<br>copies",
    "Reporting funded total": "Reporting<br>funded",
}


def _font(size: int) -> dict:
    return {"family": FONT, "size": size, "color": INK}


def waterfall_figure(bridge: pd.DataFrame) -> go.Figure:
    """Source-to-reporting waterfall. Bar values are the bridge amounts."""
    labels = [str(step) for step in bridge["step"]]
    values = [int(value) for value in bridge["amount"]]
    measures = [str(measure) for measure in bridge["measure"]]
    running = [int(value) for value in bridge["running_total"]]
    ticktext = [_TICKS.get(label, label) for label in labels]
    customdata = [
        [label, money(amount), money(total)]
        for label, amount, total in zip(labels, values, running)
    ]
    figure = go.Figure(
        go.Waterfall(
            x=labels,
            y=values,
            measure=measures,
            customdata=customdata,
            increasing={"marker": {"color": GREEN, "line": {"color": GREEN, "width": 0}}},
            decreasing={"marker": {"color": RED, "line": {"color": RED, "width": 0}}},
            totals={"marker": {"color": NAVY, "line": {"color": NAVY, "width": 0}}},
            connector={"line": {"color": "#9aa8b5", "width": 1, "dash": "dot"}},
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Amount %{customdata[1]}<br>"
                "Running total %{customdata[2]}<extra></extra>"
            ),
            hoverlabel={"font": _font(13), "bgcolor": "white", "bordercolor": GRID},
        )
    )
    figure.update_layout(
        waterfallgap=0.42,
        showlegend=False,
        margin={"t": 28, "b": 16, "l": 16, "r": 16},
        height=440,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=_font(13),
        hovermode="closest",
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "separatethousands": True,
            "gridcolor": GRID,
            "zeroline": False,
            "automargin": True,
            "tickfont": _font(12),
            "title": {"text": "Funded dollars", "font": _font(12)},
        },
        xaxis={
            "tickmode": "array",
            "tickvals": labels,
            "ticktext": ticktext,
            "tickangle": 0,
            "tickfont": _font(11),
            "automargin": True,
            "showgrid": False,
        },
    )
    return figure


def variance_contribution_figure(bridge: pd.DataFrame) -> go.Figure:
    """Horizontal signed impact of each bridge category, centered on zero.

    Only relative bridge rows are contributions. Totals are the waterfall anchors.
    """
    relative = bridge.loc[bridge["measure"].eq("relative")]
    labels = [str(step) for step in relative["step"]]
    values = [int(value) for value in relative["amount"]]
    colors = [GREEN if value > 0 else RED if value < 0 else MUTED for value in values]
    customdata = [[money(value)] for value in values]
    # Values sit in a column to the right of the plot so they never cover
    # the category names or the bars. The numbers still come from the bridge.
    annotations = [
        {
            "x": 1.02,
            "xref": "x domain",
            "xanchor": "left",
            "y": label,
            "yref": "y",
            "text": money(value),
            "showarrow": False,
            "font": {"family": FONT, "size": 12, "color": color},
            "align": "left",
        }
        for label, value, color in zip(labels, values, colors)
    ]
    figure = go.Figure(
        go.Bar(
            y=labels,
            x=values,
            orientation="h",
            marker={"color": colors, "line": {"width": 0}},
            customdata=customdata,
            hovertemplate="<b>%{y}</b><br>Signed impact %{customdata[0]}<extra></extra>",
            hoverlabel={"font": _font(13), "bgcolor": "white", "bordercolor": GRID},
        )
    )
    figure.update_layout(
        margin={"t": 8, "b": 28, "l": 8, "r": 128},
        height=380,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=_font(13),
        bargap=0.38,
        showlegend=False,
        annotations=annotations,
        xaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "separatethousands": True,
            "gridcolor": GRID,
            "zeroline": True,
            "zerolinecolor": NAVY,
            "zerolinewidth": 2,
            "automargin": True,
            "tickfont": _font(12),
            "title": {"text": "Signed impact", "font": _font(12)},
        },
        yaxis={
            "autorange": "reversed",
            "automargin": True,
            "tickfont": _font(13),
            "showgrid": False,
        },
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
        margin={"t": 36, "b": 16, "l": 16, "r": 16},
        height=380,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=_font(13),
        legend={"orientation": "h", "y": 1.14, "x": 0, "font": _font(12)},
        yaxis={
            "tickprefix": "$",
            "tickformat": ",",
            "separatethousands": True,
            "gridcolor": GRID,
            "title": {"text": "Loan amount", "font": _font(12)},
            "automargin": True,
            "tickfont": _font(12),
        },
        xaxis={"title": "", "tickfont": _font(12), "automargin": True},
        hoverlabel={"font": _font(13), "bgcolor": "white", "bordercolor": GRID},
    )
    return figure


def bridge_display(bridge: pd.DataFrame) -> pd.DataFrame:
    """Presentation copy of the tie-out. Amounts stay whole dollars."""
    display = bridge.copy()
    display["Amount"] = display["amount"].map(lambda value: money(int(value)))
    display["Running total"] = display["running_total"].map(lambda value: money(int(value)))
    return display[["step", "Amount", "Running total"]].rename(columns={"step": "Step"})
