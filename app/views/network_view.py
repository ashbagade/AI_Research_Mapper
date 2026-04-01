"""Collaboration Network view — Cytoscape graph of co-authorship communities."""

from __future__ import annotations
import pandas as pd

COMMUNITY_COLORS = [
    "#4a6cf7", "#ff6b6b", "#51cf66", "#fcc419", "#cc5de8",
    "#20c997", "#ff922b", "#339af0", "#f06595", "#a9e34b",
    "#845ef7", "#22b8cf", "#ff8787", "#69db7c", "#fab005",
]

MAX_DISPLAY_NODES = 300
MAX_DISPLAY_EDGES = 1000


def build_cytoscape_elements(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    selected_community: int | None = None,
    selected_topic: str | None = None,
) -> list[dict]:
    """Convert author_communities + community_edges DataFrames to Cytoscape elements.

    Args:
        nodes_df: DataFrame with [author_id, author_name, community_id,
                  community_label, paper_count].
        edges_df: DataFrame with [source_author_id, target_author_id, weight].
        selected_community: Show only this community.
        selected_topic: Filter to authors publishing on this topic label.
    """
    if nodes_df.empty:
        return []

    if selected_community is not None:
        nodes_df = nodes_df[nodes_df["community_id"] == selected_community]
    elif selected_topic:
        nodes_df = nodes_df[
            nodes_df["community_label"].str.contains(selected_topic, case=False, na=False)
        ]

    top_nodes = nodes_df.nlargest(MAX_DISPLAY_NODES, "paper_count")
    node_ids = set(top_nodes["author_id"])

    elements = []
    for _, row in top_nodes.iterrows():
        comm = int(row["community_id"])
        color = COMMUNITY_COLORS[comm % len(COMMUNITY_COLORS)]
        elements.append({
            "data": {
                "id": row["author_id"],
                "label": row["author_name"],
                "community": comm,
                "community_label": row["community_label"],
                "paper_count": int(row["paper_count"]),
                "color": color,
                "size": min(10 + int(row["paper_count"]) * 2, 60),
            },
        })

    if not edges_df.empty:
        filtered_edges = edges_df[
            edges_df["source_author_id"].isin(node_ids)
            & edges_df["target_author_id"].isin(node_ids)
        ].nlargest(MAX_DISPLAY_EDGES, "weight")

        for _, row in filtered_edges.iterrows():
            elements.append({
                "data": {
                    "source": row["source_author_id"],
                    "target": row["target_author_id"],
                    "weight": int(row["weight"]),
                },
            })

    return elements


CYTOSCAPE_STYLESHEET = [
    {
        "selector": "node",
        "style": {
            "label": "data(label)",
            "background-color": "data(color)",
            "width": "data(size)",
            "height": "data(size)",
            "font-size": "8px",
            "color": "#ccc",
            "text-valign": "bottom",
            "text-margin-y": "5px",
        },
    },
    {
        "selector": "edge",
        "style": {
            "width": "mapData(weight, 1, 20, 0.5, 4)",
            "line-color": "#3a3a5a",
            "opacity": 0.5,
            "curve-style": "bezier",
        },
    },
    {
        "selector": "node:selected",
        "style": {
            "border-color": "#fff",
            "border-width": 3,
        },
    },
]
