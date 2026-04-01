"""Emerging Topic Detector view — heatmap + ranked table of early signals."""

from __future__ import annotations
import plotly.graph_objects as go
import pandas as pd


def build_emerging_heatmap(df: pd.DataFrame) -> go.Figure:
    """Build a heatmap of composite emerging scores (topic x year).

    Args:
        df: DataFrame from emerging_topic_signals with columns
            [topic_id, topic_name, year, composite_score, classification].
    """
    if df.empty:
        return _empty_figure("No emerging-topic signals computed yet")

    recent = df[df["year"] >= df["year"].max() - 4]
    top_topics = (
        recent.groupby("topic_id")["composite_score"]
        .mean()
        .nlargest(20)
        .index
    )
    plot_df = recent[recent["topic_id"].isin(top_topics)]

    pivot = plot_df.pivot_table(
        index="topic_name", columns="year",
        values="composite_score", aggfunc="first",
    )
    pivot = pivot.sort_index(ascending=True)

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(c) for c in pivot.columns],
        y=pivot.index.tolist(),
        colorscale=[
            [0, "#1a1a2e"],
            [0.5, "#4a6cf7"],
            [1.0, "#ff6b6b"],
        ],
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Year: %{x}<br>"
            "Score: %{z:.3f}"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=200, r=20, t=10, b=40),
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(autorange="reversed"),
        height=420,
    )
    return fig


def build_emerging_table_data(
    signals_df: pd.DataFrame,
    papers_df: pd.DataFrame,
    year: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare data for the emerging-topics ranked table.

    Returns:
        (ranked_topics_df, evidence_papers_df)
    """
    if signals_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    target_year = year or signals_df["year"].max()
    latest = signals_df[signals_df["year"] == target_year].copy()
    latest = latest.sort_values("composite_score", ascending=False)

    cols = [
        "topic_name", "classification", "composite_score",
        "acceleration", "new_author_fraction", "cross_topic_score",
    ]
    ranked = latest[[c for c in cols if c in latest.columns]].copy()
    ranked.columns = [
        "Topic", "Status", "Composite Score",
        "Acceleration", "New Author %", "Cross-Topic Score",
    ]

    if not papers_df.empty:
        evidence = papers_df[papers_df["year"] == target_year].copy()
    else:
        evidence = pd.DataFrame()

    return ranked, evidence


def _empty_figure(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=14, color="#888"))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", height=420,
    )
    return fig
