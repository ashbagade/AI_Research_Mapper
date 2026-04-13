# AI Research Atlas - TODOs & Next Steps

Based on the team progress report, the core architecture (ETL, DuckDB, baseline Dash UI) is complete. The following items currently need to be implemented to match the project timeline described in the report.

## 1. Machine Learning & Embeddings Pipeline
**Script Location:** `analytics/`

- [x] Select and load a document-level embedding model (e.g., `SPECTER` or `SciBERT` via HuggingFace `sentence-transformers`).
- [x] Generate embeddings for the abstract/content data of the papers.
- [x] Implement k-means clustering on the generated embeddings.
- [x] Implement a baseline Latent Dirichlet Allocation (LDA) model to compare against.
- [x] Integrate embedding and clustering outputs back into the DuckDB database (note: `schema.sql` already has `umap_x` and `umap_y` columns prepared).

## 2. Alluvial View & Merge/Split Detection
**Script Locations:** `analytics/topic_evolution.py` & `app/views/`

- [ ] **Data Model:** Update the analytics pipeline to detect when topics merge or split over time.
- [ ] **Visualization:** Create `app/views/alluvial_view.py`.
- [ ] **Integration:** Build a Plotly Sankey diagram (Alluvial diagram) mapping the flow of topics merging and splitting over time and register the new view in `app/main.py`/`app/layout.py`.

## 3. Evaluation Metrics
**Script Location:** `scripts/evaluate.py`
  
- [ ] Evaluate LDA/K-Means topic clusters using NPMI (Normalized Pointwise Mutual Information) coherence tests.
- [ ] Validate the emerging trend detection logic.
- [ ] Test the modularity of the Leiden community network graph.
- [ ] Conduct dashboard UI latency tests and evaluate with sample user tasks.

## 4. Local Setup Checklist (For New Contributors)
- [ ] Create a virtual environment and run `pip install -r requirements.txt`.
- [ ] Create a `.env` file containing `OPENALEX_API_KEY=your_key_here`. 
- [ ] Fetch OpenAlex data by running `python scripts/run_etl.py --max-works 5000` (for a starter batch).
- [ ] Precompute data by running `python scripts/run_analytics.py`.
- [ ] Launch application with `python app/main.py`.
