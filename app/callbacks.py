"""Coordinated callbacks — wires all views to shared global state."""

from __future__ import annotations
import pandas as pd
from dash import Input, Output, State, callback, no_update
from etl.db import get_connection
from app.views.trend_view import build_trend_figure
from app.views.emerging_view import build_emerging_heatmap, build_emerging_table_data
from app.views.network_view import build_cytoscape_elements
from app.views.evidence_view import filter_evidence
from app.views.alluvial_view import build_alluvial_figure


def _load_topic_year_stats(year_range: tuple[int, int] | None = None) -> pd.DataFrame:
    con = get_connection(read_only=True)
    q = "SELECT * FROM topic_year_stats"
    if year_range:
        q += f" WHERE year BETWEEN {year_range[0]} AND {year_range[1]}"
    df = con.execute(q).df()
    con.close()
    return df


def _load_emerging_signals() -> pd.DataFrame:
    con = get_connection(read_only=True)
    df = con.execute("SELECT * FROM emerging_topic_signals").df()
    con.close()
    return df


def _load_emerging_papers() -> pd.DataFrame:
    con = get_connection(read_only=True)
    df = con.execute("SELECT * FROM emerging_topic_papers").df()
    con.close()
    return df


def _load_network_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = get_connection(read_only=True)
    nodes = con.execute("SELECT * FROM author_communities").df()
    edges = con.execute("SELECT * FROM community_edges").df()
    con.close()
    return nodes, edges


def _load_works_topic_year_stats(year_range: tuple[int, int] | None = None) -> pd.DataFrame:
    """Compute topic-year work counts from actual ingested papers (not aggregates)."""
    con = get_connection(read_only=True)
    q = """
        SELECT wt.topic_id, wt.topic_name,
               w.publication_year AS year,
               COUNT(DISTINCT w.work_id) AS work_count
        FROM work_topics wt
        JOIN works w ON wt.work_id = w.work_id
    """
    if year_range:
        q += f" WHERE w.publication_year BETWEEN {year_range[0]} AND {year_range[1]}"
    q += " GROUP BY wt.topic_id, wt.topic_name, w.publication_year"
    df = con.execute(q).df()
    con.close()
    return df


def _load_transitions() -> pd.DataFrame:
    con = get_connection(read_only=True)
    try:
        df = con.execute("SELECT * FROM topic_transitions").df()
    except Exception:
        df = pd.DataFrame()
    con.close()
    return df


def _load_works() -> pd.DataFrame:
    con = get_connection(read_only=True)
    df = con.execute(
        "SELECT work_id, title, publication_year, cited_by_count FROM works"
    ).df()
    con.close()
    return df


def _load_work_topics() -> pd.DataFrame:
    con = get_connection(read_only=True)
    df = con.execute("SELECT work_id, topic_id, topic_name FROM work_topics").df()
    con.close()
    return df


def _load_authorships() -> pd.DataFrame:
    con = get_connection(read_only=True)
    df = con.execute("SELECT work_id, author_id, author_name FROM authorships").df()
    con.close()
    return df


def register_callbacks(app):
    @app.callback(
        Output("trend-chart", "figure"),
        Input("year-slider", "value"),
        Input("topic-filter", "value"),
        Input("y-axis-select", "value"),
    )
    def update_trend(year_range, selected_topics, y_col):
        df = _load_topic_year_stats(tuple(year_range))
        return build_trend_figure(df, y_col=y_col, selected_topics=selected_topics)

    @app.callback(
        Output("emerging-heatmap", "figure"),
        Output("emerging-table", "data"),
        Input("year-slider", "value"),
    )
    def update_emerging(year_range):
        signals = _load_emerging_signals()
        papers = _load_emerging_papers()

        if not signals.empty:
            signals = signals[
                (signals["year"] >= year_range[0])
                & (signals["year"] <= year_range[1])
            ]
        heatmap = build_emerging_heatmap(signals)

        ranked, _ = build_emerging_table_data(signals, papers, year=year_range[1])
        table_data = ranked.to_dict("records") if not ranked.empty else []

        return heatmap, table_data

    @app.callback(
        Output("network-graph", "elements"),
        Output("community-filter", "options"),
        Input("community-filter", "value"),
        Input("topic-filter", "value"),
    )
    def update_network(selected_community, selected_topics):
        nodes_df, edges_df = _load_network_data()

        comm_options = []
        if not nodes_df.empty:
            for _, row in (
                nodes_df.groupby("community_id")
                .agg({"community_label": "first", "author_id": "count"})
                .reset_index()
                .sort_values("author_id", ascending=False)
                .head(20)
                .iterrows()
            ):
                comm_options.append({
                    "label": f"{row['community_label']} ({row['author_id']} authors)",
                    "value": int(row["community_id"]),
                })

        topic_label = None
        if selected_topics and len(selected_topics) == 1:
            tys = _load_topic_year_stats()
            match = tys[tys["topic_id"] == selected_topics[0]]
            if not match.empty:
                topic_label = match["topic_name"].iloc[0]

        elements = build_cytoscape_elements(
            nodes_df, edges_df,
            selected_community=selected_community,
            selected_topic=topic_label,
        )
        return elements, comm_options

    @app.callback(
        Output("alluvial-chart", "figure"),
        Input("year-slider", "value"),
        Input("topic-filter", "value"),
    )
    def update_alluvial(year_range, selected_topics):
        df = _load_works_topic_year_stats(tuple(year_range))
        transitions = _load_transitions()
        return build_alluvial_figure(df, transitions=transitions, selected_topics=selected_topics)

    @app.callback(
        Output("evidence-table", "data"),
        Input("trend-chart", "clickData"),
        Input("network-graph", "tapNodeData"),
        Input("year-slider", "value"),
        Input("topic-filter", "value"),
        Input("search-input", "value"),
    )
    def update_evidence(trend_click, node_tap, year_range, selected_topics, search):
        works = _load_works()
        wt = _load_work_topics()
        auth = _load_authorships()

        topic_ids = list(selected_topics) if selected_topics else None
        author_ids = None

        if trend_click and trend_click.get("points"):
            pt = trend_click["points"][0]
            cd = pt.get("customdata")
            if cd and len(cd) > 0:
                clicked_tid = cd[0]
                topic_ids = [clicked_tid]

        if node_tap:
            author_ids = [node_tap.get("id", "")]

        evidence = filter_evidence(
            works, wt, auth,
            selected_topic_ids=topic_ids,
            selected_author_ids=author_ids,
            year_range=tuple(year_range),
            search_query=search or "",
        )
        return evidence.to_dict("records")
