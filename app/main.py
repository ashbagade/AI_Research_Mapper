#!/usr/bin/env python3
"""Dash application entry point."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import dash
import dash_bootstrap_components as dbc
from etl.db import get_connection, init_schema
from app.layout import build_layout
from app.callbacks import register_callbacks
import config


def _get_topic_options() -> list[dict]:
    con = get_connection(read_only=True)
    try:
        df = con.execute("""
            SELECT DISTINCT topic_id, topic_name
            FROM topic_year_stats
            ORDER BY topic_name
        """).df()
    except Exception:
        df = None
    con.close()

    if df is None or df.empty:
        return []
    return [
        {"label": row["topic_name"], "value": row["topic_id"]}
        for _, row in df.iterrows()
    ]


def create_app() -> dash.Dash:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = get_connection()
    init_schema(con)
    con.close()

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        assets_folder=os.path.join(os.path.dirname(__file__), "assets"),
        suppress_callback_exceptions=True,
    )

    topic_options = _get_topic_options()
    year_min, year_max = config.YEAR_RANGE
    app.layout = build_layout(year_min, year_max, topic_options)
    register_callbacks(app)

    return app


if __name__ == "__main__":
    app = create_app()
    print("Starting AI Research Evolution Atlas on http://127.0.0.1:8050")
    app.run(debug=True, port=8050)
