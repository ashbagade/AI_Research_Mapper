"""Topic Trend Timeline view — line chart of topic growth over years."""

from __future__ import annotations
import plotly.graph_objects as go
import pandas as pd


def build_trend_figure(
    df: pd.DataFrame,
    y_col: str = "work_count",
    selected_topics: list[str] | None = None,
    top_n: int = 15,
) -> go.Figure:
    """Build a multi-line chart of topic trends.

    Args:
        df: DataFrame with columns [topic_id, topic_name, year, work_count,
            relative_share, momentum, is_emerging].
        y_col: Which column to plot on y-axis.
        selected_topics: If set, show only these topic_ids.
        top_n: If no selection, show top N topics by total work count.
    """
    if df.empty:
        return _empty_figure("No topic data available")

    if selected_topics:
        plot_df = df[df["topic_id"].isin(selected_topics)]
    else:
        totals = df.groupby("topic_id")["work_count"].sum().nlargest(top_n)
        plot_df = df[df["topic_id"].isin(totals.index)]

    fig = go.Figure()

    for tid, group in plot_df.groupby("topic_id"):
        group = group.sort_values("year")
        name = group["topic_name"].iloc[0]
        is_emerging_any = group["is_emerging"].any()

        fig.add_trace(go.Scatter(
            x=group["year"],
            y=group[y_col],
            mode="lines+markers",
            name=_shorten(name, 35),
            customdata=group[["topic_id", "topic_name", "growth_rate", "momentum"]].values,
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "Year: %{x}<br>"
                f"{y_col}: " + "%{y:,.0f}<br>"
                "Growth: %{customdata[2]:.1%}<br>"
                "Momentum: %{customdata[3]:.1%}"
                "<extra></extra>"
            ),
            line=dict(width=3 if is_emerging_any else 1.5),
            marker=dict(size=7 if is_emerging_any else 4),
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=50, r=20, t=10, b=40),
        xaxis=dict(title="Year", dtick=1, gridcolor="#2a2a4a"),
        yaxis=dict(title=y_col.replace("_", " ").title(), gridcolor="#2a2a4a"),
        legend=dict(
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
            yanchor="top", y=1, xanchor="left", x=1.02,
        ),
        hovermode="x unified",
        height=370,
    )
    return fig


def _shorten(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _empty_figure(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=14, color="#888"))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", height=370,
    )
    return fig
