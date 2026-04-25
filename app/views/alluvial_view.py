"""Alluvial / Sankey view — topic volume flow with merge/split ribbons."""

from __future__ import annotations
import plotly.graph_objects as go
import pandas as pd

_PALETTE = [
    "#4cc9f0", "#f72585", "#7209b7", "#3a0ca3", "#4361ee",
    "#43aa8b", "#90be6d", "#f9c74f", "#f8961e", "#ef233c",
    "#06d6a0", "#118ab2", "#ffd166", "#e76f51", "#264653",
]

_TYPE_ALPHA = {"split": 0.55, "merge": 0.55, "transfer": 0.30}


def build_alluvial_figure(
    df: pd.DataFrame,
    transitions: pd.DataFrame | None = None,
    top_n: int = 10,
    selected_topics: list | None = None,
) -> go.Figure:
    """Sankey diagram showing how topic paper-volume flows year-to-year.

    Same-topic ribbons represent continuity; cross-topic ribbons (colored
    differently) represent detected merges, splits, or transfers.
    """
    if df.empty:
        return _empty_figure("No topic data available")

    if selected_topics:
        ordered = (
            df[df["topic_id"].isin(selected_topics)]
            .groupby("topic_id")["work_count"].sum()
            .sort_values(ascending=False)
            .index.tolist()
        )
        plot_topics = ordered[:top_n]
    else:
        plot_topics = (
            df.groupby("topic_id")["work_count"]
            .sum().nlargest(top_n).index.tolist()
        )

    plot_df = df[df["topic_id"].isin(plot_topics)].copy()
    years = sorted(plot_df["year"].unique())

    if len(years) < 2:
        return _empty_figure("Need at least 2 years of data")

    topic_color = {tid: _PALETTE[i % len(_PALETTE)] for i, tid in enumerate(plot_topics)}
    lookup = plot_df.set_index(["topic_id", "year"])["work_count"].to_dict()
    name_lookup = (
        plot_df.drop_duplicates("topic_id")
        .set_index("topic_id")["topic_name"].to_dict()
    )

    # ── Nodes ────────────────────────────────────────────────────────────────
    node_labels: list[str] = []
    node_colors: list[str] = []
    node_idx: dict[tuple, int] = {}

    for year in years:
        for tid in plot_topics:
            if (tid, year) in lookup:
                node_idx[(tid, year)] = len(node_labels)
                node_labels.append(
                    f"{_shorten(name_lookup.get(tid, str(tid)), 28)} '{str(year)[2:]}"
                )
                node_colors.append(topic_color[tid])

    # ── Links ─────────────────────────────────────────────────────────────────
    src, tgt, val, link_colors, link_labels = [], [], [], [], []

    # Same-topic continuity ribbons
    for i, year in enumerate(years[:-1]):
        next_year = years[i + 1]
        for tid in plot_topics:
            s_key, t_key = (tid, year), (tid, next_year)
            if s_key in node_idx and t_key in node_idx:
                flow = min(lookup[s_key], lookup[t_key])
                if flow > 0:
                    src.append(node_idx[s_key])
                    tgt.append(node_idx[t_key])
                    val.append(flow)
                    link_colors.append(_rgba(topic_color[tid], 0.30))
                    link_labels.append("continues")

    # Cross-topic transition ribbons (merge / split / transfer)
    if transitions is not None and not transitions.empty:
        trans_filtered = transitions[
            transitions["src_topic_id"].isin(plot_topics) &
            transitions["tgt_topic_id"].isin(plot_topics)
        ]
        for _, row in trans_filtered.iterrows():
            s_key = (row["src_topic_id"], int(row["year"]))
            t_key = (row["tgt_topic_id"], int(row["next_year"]))
            if s_key not in node_idx or t_key not in node_idx:
                continue
            flow = int(row["overlap_count"])
            if flow == 0:
                continue
            t_type = row["transition_type"]
            alpha = _TYPE_ALPHA.get(t_type, 0.40)
            # Cross-topic links use white-ish tint to stand out
            src.append(node_idx[s_key])
            tgt.append(node_idx[t_key])
            val.append(flow)
            link_colors.append(_rgba("#ffffff", alpha))
            link_labels.append(t_type)

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=12,
            thickness=18,
            line=dict(color="#2a2a4a", width=0.5),
            label=node_labels,
            color=node_colors,
            hovertemplate="<b>%{label}</b><br>Papers: %{value:,}<extra></extra>",
        ),
        link=dict(
            source=src,
            target=tgt,
            value=val,
            color=link_colors,
            customdata=link_labels,
            hovertemplate=(
                "%{source.label} → %{target.label}<br>"
                "Type: %{customdata}<br>"
                "Papers: %{value:,}<extra></extra>"
            ),
        ),
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        font=dict(color="#c0c0d0", size=10),
        height=360,
    )
    return fig


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _shorten(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _empty_figure(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=14, color="#888"))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=360,
    )
    return fig
