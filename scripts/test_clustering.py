#!/usr/bin/env python3
"""Quick integration test for paper_clustering.

Creates a small in-memory DuckDB with synthetic papers,
runs the full embed → cluster → project → store pipeline,
and prints the results.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import duckdb
from pathlib import Path


def main():
    # ── 1. Set up an in-memory DB with the schema ───────────────────────
    con = duckdb.connect(":memory:")
    schema_path = Path(__file__).parent / ".." / "etl" / "schema.sql"
    for stmt in schema_path.read_text().split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)

    # ── 2. Insert synthetic papers with real-ish abstracts ──────────────
    papers = [
        ("W001", "Attention Mechanisms in Vision Transformers",     2023, 50, "We study multi-head self-attention layers applied to image patches in vision transformers for classification."),
        ("W002", "Graph Neural Networks for Molecular Modeling",    2023, 30, "Graph neural networks are used to predict molecular properties by learning representations of atoms and bonds."),
        ("W003", "Large Language Model Alignment via RLHF",         2024, 80, "Reinforcement learning from human feedback is used to align language model outputs with human preferences."),
        ("W004", "Diffusion Models for Image Generation",           2023, 60, "Denoising diffusion probabilistic models generate high quality images through iterative noise removal."),
        ("W005", "Federated Learning for Healthcare Data",          2022, 20, "Federated learning enables collaborative model training across hospitals while preserving patient data privacy."),
        ("W006", "Self-Supervised Pretraining for NLP",             2022, 45, "Masked language modeling objectives enable self-supervised pretraining of transformer models for downstream NLP tasks."),
        ("W007", "Transformer Architecture for Time Series",        2024, 25, "Adapting the transformer architecture with positional encodings for multivariate time series forecasting."),
        ("W008", "Prompt Engineering for Few-Shot Learning",        2024, 35, "Carefully designed prompts improve few-shot performance of large language models on downstream classification tasks."),
        ("W009", "Autonomous Driving with Reinforcement Learning",  2023, 40, "Deep reinforcement learning agents learn driving policies in simulated urban environments for autonomous vehicles."),
        ("W010", "Neural Architecture Search with Evolutionary Methods", 2022, 15, "Evolutionary algorithms efficiently search the space of neural network architectures to find optimal designs."),
    ]

    for work_id, title, year, cites, abstract in papers:
        con.execute(
            "INSERT INTO works VALUES (?, ?, ?, ?, ?, NULL)",
            [work_id, title, year, cites, abstract],
        )

    print(f"Inserted {len(papers)} test papers\n")

    # ── 3. Run clustering (with small cluster count for test) ───────────
    from analytics.paper_clustering import compute_paper_clusters

    # Use a small & fast model for testing — fall back gracefully
    compute_paper_clusters(con, n_clusters=3)

    # ── 4. Verify the results ───────────────────────────────────────────
    print("\n=== Results ===")
    rows = con.execute("""
        SELECT pp.work_id, w.title, pp.umap_x, pp.umap_y, pp.cluster_id
        FROM paper_projections pp
        JOIN works w ON pp.work_id = w.work_id
        ORDER BY pp.cluster_id, pp.work_id
    """).fetchall()

    if not rows:
        print("❌ FAIL — paper_projections is empty!")
        con.close()
        sys.exit(1)

    print(f"{'ID':<6} {'Cluster':>7}  {'UMAP_X':>8}  {'UMAP_Y':>8}  Title")
    print("-" * 80)
    for wid, title, ux, uy, cid in rows:
        print(f"{wid:<6} {cid:>7}  {ux:>8.3f}  {uy:>8.3f}  {title[:40]}")

    n_clusters = len(set(r[4] for r in rows))
    print(f"\n✅ PASS — {len(rows)} papers projected into {n_clusters} clusters")

    con.close()


if __name__ == "__main__":
    main()
