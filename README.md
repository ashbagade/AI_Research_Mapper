# AI Research Evolution Atlas

Interactive system for exploring how AI research evolves over time, built on [OpenAlex](https://openalex.org) metadata. Surfaces topic trends, emerging research signals, and collaboration communities through a coordinated multi-view dashboard.

## Three Core Innovations

### 1. Topic Trend Timeline
Per-topic growth rates, momentum (3-year rolling average), and relative share computed from OpenAlex topic assignments across 2018–2025. Powers an interactive line chart where clicking a topic filters all other views.

### 2. Emerging Topic Detector (Early Signal Model)
Identifies topics likely to grow based on three signals:
- **Growth acceleration** — second derivative of publication count
- **New-author influx** — fraction of authors new to this topic in a given year
- **Cross-topic connections** — fraction of authors bridging multiple topics

A weighted composite score classifies each topic-year as *emerging*, *established*, or *declining*. Each emerging detection links to its top-K representative papers.

### 3. Collaboration Network
Weighted co-authorship graph with Leiden community detection. Communities are labeled by their dominant research topic. Visualized as an interactive network where node color = community, size = paper count, edge thickness = co-authorship weight.

## Architecture

```
OpenAlex API → ETL (metadata only, free) → DuckDB → Analytics Pipeline → Dash UI
```

- **ETL**: Tier 1 (group_by aggregates, ~free) + Tier 2 (cursor-paginated bulk download, metadata only)
- **Storage**: DuckDB — single-file columnar database, sub-2ms query latency
- **Analytics**: All heavy computation precomputed offline, stored in DuckDB
- **UI**: Dash + Plotly + dash-cytoscape, coordinated callbacks across views

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAlex API key in .env
echo "OPENALEX_API_KEY=your_key_here" > .env

# Run ETL (aggregates + bulk metadata download)
python3 scripts/run_etl.py --max-works 5000   # start small
python3 scripts/run_etl.py                     # or fetch all ~540K

# Run analytics pipeline
python3 scripts/run_analytics.py

# Run evaluation
python3 scripts/evaluate.py

# Launch the interactive dashboard
python3 app/main.py
# → Open http://127.0.0.1:8050
```

## Project Structure

```
config.py                          # API key, filters, paths
etl/
  fetch_aggregates.py              # Cheap group_by counts
  fetch_works.py                   # Bulk metadata download with checkpointing
  ingest.py                        # Parse OpenAlex JSON → DuckDB
  db.py                            # DuckDB connection + schema init
  schema.sql                       # Table DDL
analytics/
  topic_evolution.py               # Growth rates, momentum, relative share
  emerging_topics.py               # 3-signal emerging detector
  collaboration_network.py         # Co-authorship graph + Leiden communities
app/
  main.py                          # Dash entry point
  layout.py                        # Multi-view grid layout
  callbacks.py                     # Coordinated view callbacks
  views/
    trend_view.py                  # Topic trend line chart
    emerging_view.py               # Emerging heatmap + ranked table
    network_view.py                # Cytoscape collaboration graph
    evidence_view.py               # Paper drilldown table
scripts/
  run_etl.py                       # End-to-end ETL runner
  run_analytics.py                 # End-to-end analytics runner
  evaluate.py                      # Topic coherence, trend sanity, latency
```

## Cost

All data downloads are **free metadata only** — no PDF or full-text content is fetched. The OpenAlex API charges $0.0001 per list query; with a free API key ($1/day credit), the full 540K-work download costs ~$0.54 total.
