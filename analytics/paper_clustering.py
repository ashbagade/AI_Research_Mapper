"""Paper Clustering — SPECTER embeddings + K-Means + UMAP projection.

Generates document-level embeddings for paper abstracts using a SPECTER-style
model (via sentence-transformers), clusters them with K-Means, and projects
the embeddings into 2D via UMAP.  Results are stored in the paper_projections
table.
"""

from __future__ import annotations

import numpy as np
import duckdb
from etl.db import get_connection

# ── Configurable defaults ────────────────────────────────────────────────────
DEFAULT_MODEL_NAME = "allenai/specter2_base"
DEFAULT_N_CLUSTERS = 15
EMBEDDING_BATCH_SIZE = 64
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1
UMAP_METRIC = "cosine"
UMAP_RANDOM_STATE = 42


# ── Public API ───────────────────────────────────────────────────────────────

def compute_paper_clusters(
    con: duckdb.DuckDBPyConnection | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    n_clusters: int = DEFAULT_N_CLUSTERS,
) -> None:
    """End-to-end pipeline: embed → cluster → project → store."""
    close_after = con is None
    if con is None:
        con = get_connection()

    # 1. Fetch papers with non-empty abstracts
    papers = _fetch_papers(con)
    if not papers:
        print("  No papers with abstracts found. Skipping clustering.")
        if close_after:
            con.close()
        return

    work_ids, abstracts = zip(*papers)
    print(f"  Loaded {len(work_ids)} papers with abstracts")

    # 2. Generate embeddings
    embeddings = _embed_abstracts(list(abstracts), model_name)
    print(f"  Embeddings shape: {embeddings.shape}")

    # 3. K-Means clustering
    labels = _kmeans_cluster(embeddings, n_clusters)
    print(f"  K-Means assigned {len(set(labels))} clusters")

    # 4. UMAP 2D projection
    coords = _umap_project(embeddings)
    print(f"  UMAP projection done ({coords.shape})")

    # 5. Store results in DuckDB
    _store_projections(con, list(work_ids), coords, labels)
    print(f"  Stored {len(work_ids)} rows into paper_projections")

    if close_after:
        con.close()


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fetch_papers(
    con: duckdb.DuckDBPyConnection,
    max_papers: int = 50_000,
) -> list[tuple[str, str]]:
    """Return (work_id, abstract_text) for top papers by citation count."""
    rows = con.execute("""
        SELECT work_id, abstract_text
        FROM works
        WHERE abstract_text IS NOT NULL
          AND LENGTH(TRIM(abstract_text)) > 0
        ORDER BY cited_by_count DESC
        LIMIT ?
    """, [max_papers]).fetchall()
    return rows


def _embed_abstracts(
    abstracts: list[str],
    model_name: str,
) -> np.ndarray:
    """Generate dense embeddings using a sentence-transformers model."""
    from sentence_transformers import SentenceTransformer

    import torch
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    print(f"  Loading embedding model: {model_name} (device={device})")
    model = SentenceTransformer(model_name, device=device)

    batch_size = 32 if device == "mps" else EMBEDDING_BATCH_SIZE
    print(f"  Encoding {len(abstracts)} abstracts (batch_size={batch_size})...")
    embeddings = model.encode(
        abstracts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings


def _kmeans_cluster(
    embeddings: np.ndarray,
    n_clusters: int,
) -> np.ndarray:
    """Run K-Means on the embedding matrix and return cluster labels."""
    from sklearn.cluster import KMeans

    # Ensure n_clusters <= n_samples
    n_clusters = min(n_clusters, embeddings.shape[0])
    km = KMeans(
        n_clusters=n_clusters,
        n_init=10,
        max_iter=300,
        random_state=42,
    )
    labels = km.fit_predict(embeddings)
    return labels


def _umap_project(
    embeddings: np.ndarray,
) -> np.ndarray:
    """Project high-dimensional embeddings to 2D via UMAP."""
    import umap

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=UMAP_N_NEIGHBORS,
        min_dist=UMAP_MIN_DIST,
        metric=UMAP_METRIC,
        random_state=UMAP_RANDOM_STATE,
    )
    coords = reducer.fit_transform(embeddings)
    return coords


def _store_projections(
    con: duckdb.DuckDBPyConnection,
    work_ids: list[str],
    coords: np.ndarray,
    labels: np.ndarray,
) -> None:
    """Write UMAP (x, y) and cluster_id into the paper_projections table."""
    con.execute("DELETE FROM paper_projections")
    rows = [
        (wid, float(coords[i, 0]), float(coords[i, 1]), int(labels[i]))
        for i, wid in enumerate(work_ids)
    ]
    con.executemany(
        "INSERT INTO paper_projections (work_id, umap_x, umap_y, cluster_id) VALUES (?, ?, ?, ?)",
        rows,
    )


# ── Standalone runner ────────────────────────────────────────────────────────

def run() -> None:
    print("=== Running Paper Clustering (SPECTER + K-Means + UMAP) ===")
    con = get_connection()
    compute_paper_clusters(con)
    n = con.execute("SELECT COUNT(*) FROM paper_projections").fetchone()[0]
    n_clusters = con.execute(
        "SELECT COUNT(DISTINCT cluster_id) FROM paper_projections"
    ).fetchone()[0]
    print(f"  Total projections: {n}, distinct clusters: {n_clusters}")
    con.close()


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    run()
