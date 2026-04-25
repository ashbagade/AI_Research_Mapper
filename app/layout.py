"""Dash application layout — multi-view grid with global controls."""

from __future__ import annotations
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from app.views.network_view import CYTOSCAPE_STYLESHEET


def build_layout(year_min: int, year_max: int, topic_options: list[dict]) -> html.Div:
    return html.Div([
        # Header
        html.Div([
            html.H1("AI Research Evolution Atlas"),
            html.P("Interactive topic trends, emerging signals, and collaboration networks from OpenAlex"),
        ], className="main-header"),

        # Global controls
        html.Div([
            html.Div([
                html.Label("Year Range", style={"fontSize": "0.8rem", "color": "#8888aa"}),
                dcc.RangeSlider(
                    id="year-slider",
                    min=year_min, max=year_max,
                    value=[year_min, year_max],
                    marks={y: str(y) for y in range(year_min, year_max + 1)},
                    step=1,
                ),
            ], style={"flex": "1", "minWidth": "300px"}),

            html.Div([
                html.Label("Filter Topics", style={"fontSize": "0.8rem", "color": "#8888aa"}),
                dcc.Dropdown(
                    id="topic-filter",
                    options=topic_options,
                    multi=True,
                    placeholder="All topics",
                    style={"backgroundColor": "#1a1a2e", "color": "#e0e0e0"},
                ),
            ], style={"flex": "1", "minWidth": "300px"}),

            html.Div([
                html.Label("Y-Axis Metric", style={"fontSize": "0.8rem", "color": "#8888aa"}),
                dcc.Dropdown(
                    id="y-axis-select",
                    options=[
                        {"label": "Work Count", "value": "work_count"},
                        {"label": "Relative Share", "value": "relative_share"},
                        {"label": "Momentum (3yr avg)", "value": "momentum"},
                    ],
                    value="work_count",
                    clearable=False,
                    style={"backgroundColor": "#1a1a2e", "color": "#e0e0e0"},
                ),
            ], style={"width": "200px"}),

            html.Div([
                html.Label("Search Papers", style={"fontSize": "0.8rem", "color": "#8888aa"}),
                dcc.Input(
                    id="search-input",
                    type="text",
                    placeholder="Search by title…",
                    debounce=True,
                    style={
                        "backgroundColor": "#1a1a2e", "color": "#e0e0e0",
                        "border": "1px solid #2a2a4a", "borderRadius": "4px",
                        "padding": "6px 10px", "width": "100%",
                    },
                ),
            ], style={"width": "220px"}),
        ], className="controls-bar"),

        # Main grid
        dbc.Container([
            dbc.Row([
                # Left column: Trend Timeline
                dbc.Col([
                    html.Div([
                        html.H3("Topic Trend Timeline"),
                        dcc.Graph(id="trend-chart", config={"displayModeBar": False}),
                    ], className="view-card"),
                ], md=7),

                # Right column: Emerging Topic Detector
                dbc.Col([
                    html.Div([
                        html.H3("Emerging Topic Detector"),
                        dcc.Graph(id="emerging-heatmap", config={"displayModeBar": False}),
                    ], className="view-card"),
                ], md=5),
            ], className="g-2 mt-2"),

            dbc.Row([
                # Left column: Collaboration Network
                dbc.Col([
                    html.Div([
                        html.H3("Collaboration Network"),
                        html.Div([
                            html.Label("Community:", style={"fontSize": "0.75rem", "color": "#8888aa", "marginRight": "8px"}),
                            dcc.Dropdown(
                                id="community-filter",
                                placeholder="All communities",
                                style={"backgroundColor": "#1a1a2e", "color": "#e0e0e0", "width": "280px", "display": "inline-block"},
                            ),
                        ], style={"marginBottom": "6px", "display": "flex", "alignItems": "center"}),
                        cyto.Cytoscape(
                            id="network-graph",
                            layout={"name": "cose", "animate": False, "nodeRepulsion": 8000},
                            stylesheet=CYTOSCAPE_STYLESHEET,
                            style={"width": "100%", "height": "360px"},
                            elements=[],
                        ),
                    ], className="view-card"),
                ], md=7),

                # Right column: Emerging Topics Ranked Table
                dbc.Col([
                    html.Div([
                        html.H3("Emerging Signals — Ranked"),
                        dash_table.DataTable(
                            id="emerging-table",
                            columns=[
                                {"name": "Topic", "id": "Topic"},
                                {"name": "Status", "id": "Status"},
                                {"name": "Score", "id": "Composite Score", "type": "numeric",
                                 "format": {"specifier": ".3f"}},
                                {"name": "Accel", "id": "Acceleration", "type": "numeric",
                                 "format": {"specifier": ".3f"}},
                                {"name": "New Auth %", "id": "New Author %", "type": "numeric",
                                 "format": {"specifier": ".1%"}},
                                {"name": "Cross-Topic", "id": "Cross-Topic Score", "type": "numeric",
                                 "format": {"specifier": ".3f"}},
                            ],
                            page_size=12,
                            sort_action="native",
                            style_table={"overflowX": "auto"},
                            style_header={
                                "backgroundColor": "#16213e", "color": "#a0a0cc",
                                "fontWeight": "600", "fontSize": "0.75rem",
                                "borderBottom": "1px solid #2a2a4a",
                            },
                            style_cell={
                                "backgroundColor": "#1a1a2e", "color": "#e0e0e0",
                                "borderBottom": "1px solid #222240",
                                "fontSize": "0.8rem", "padding": "6px 10px",
                                "textAlign": "left",
                            },
                            style_data_conditional=[
                                {"if": {"filter_query": '{Status} = "emerging"'},
                                 "backgroundColor": "#1a3a2e", "color": "#51cf66"},
                                {"if": {"filter_query": '{Status} = "declining"'},
                                 "backgroundColor": "#3a1a1a", "color": "#ff6b6b"},
                            ],
                        ),
                    ], className="view-card"),
                ], md=5),
            ], className="g-2 mt-2"),

            # Alluvial / topic flow panel
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H3("Topic Flow — Alluvial View"),
                        dcc.Graph(id="alluvial-chart", config={"displayModeBar": False}),
                    ], className="view-card"),
                ], md=12),
            ], className="g-2 mt-2"),

            # Evidence panel
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.H3("Evidence — Representative Papers"),
                        dash_table.DataTable(
                            id="evidence-table",
                            columns=[
                                {"name": "Title", "id": "title"},
                                {"name": "Year", "id": "year", "type": "numeric"},
                                {"name": "Citations", "id": "citations", "type": "numeric"},
                                {"name": "Topics", "id": "topics"},
                                {"name": "Authors", "id": "authors"},
                            ],
                            page_size=10,
                            sort_action="native",
                            filter_action="native",
                            style_table={"overflowX": "auto"},
                            style_header={
                                "backgroundColor": "#16213e", "color": "#a0a0cc",
                                "fontWeight": "600", "fontSize": "0.75rem",
                                "borderBottom": "1px solid #2a2a4a",
                            },
                            style_cell={
                                "backgroundColor": "#1a1a2e", "color": "#e0e0e0",
                                "borderBottom": "1px solid #222240",
                                "fontSize": "0.8rem", "padding": "6px 10px",
                                "textAlign": "left", "maxWidth": "350px",
                                "overflow": "hidden", "textOverflow": "ellipsis",
                            },
                        ),
                    ], className="view-card"),
                ], md=12),
            ], className="g-2 mt-2 mb-3"),
        ], fluid=True),
    ])
