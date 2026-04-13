"""LDA Baseline Topic Model.

Runs Latent Dirichlet Allocation on paper abstracts using TF-IDF
vectorisation.  Serves as a comparison baseline against the SPECTER
+ K-Means clustering approach.

Stores:
  - lda_topic_words  — top keywords per LDA topic
  - paper_lda        — per-paper dominant topic assignment + probability
"""

from __future__ import annotations

import numpy as np
import duckdb
from etl.db import get_connection

# ── Configurable defaults ────────────────────────────────────────────────────
DEFAULT_N_TOPICS = 10
TOP_N_WORDS = 15           # words stored per topic in lda_topic_words
MAX_DF = 0.85              # ignore terms appearing in >85% of documents
MIN_DF = 3                 # ignore terms appearing in fewer than 3 documents
MAX_FEATURES = 10_000      # vocabulary cap
LDA_MAX_ITER = 25
LDA_RANDOM_STATE = 42


# ── Public API ───────────────────────────────────────────────────────────────

def compute_lda_topics(
    con: duckdb.DuckDBPyConnection | None = None,
    n_topics: int = DEFAULT_N_TOPICS,
) -> None:
    """End-to-end pipeline: vectorise → LDA → store topics & assignments."""
    close_after = con is None
    if con is None:
        con = get_connection()

    # 1. Fetch papers with non-empty abstracts
    papers = _fetch_papers(con)
    if not papers:
        print("  No papers with abstracts found. Skipping LDA.")
        if close_after:
            con.close()
        return

    work_ids, abstracts = zip(*papers)
    print(f"  Loaded {len(work_ids)} papers with abstracts")

    # 2. TF-IDF vectorisation
    tfidf_matrix, feature_names = _vectorise(list(abstracts))
    print(f"  TF-IDF matrix: {tfidf_matrix.shape[0]} docs × {tfidf_matrix.shape[1]} terms")

    # 3. Fit LDA
    lda_model, doc_topic_matrix = _fit_lda(tfidf_matrix, n_topics)
    print(f"  LDA fitted with {n_topics} topics (perplexity: {lda_model.perplexity(tfidf_matrix):.2f})")

    # 4. Extract top words per topic
    topic_words = _extract_topic_words(lda_model, feature_names)

    # 5. Store results
    _store_results(con, list(work_ids), doc_topic_matrix, topic_words)
    print(f"  Stored {len(topic_words)} topics and {len(work_ids)} paper assignments")

    if close_after:
        con.close()


# ── Internal helpers ─────────────────────────────────────────────────────────

def _fetch_papers(
    con: duckdb.DuckDBPyConnection,
) -> list[tuple[str, str]]:
    """Return (work_id, abstract_text) for papers that have an abstract."""
    rows = con.execute("""
        SELECT work_id, abstract_text
        FROM works
        WHERE abstract_text IS NOT NULL
          AND LENGTH(TRIM(abstract_text)) > 0
        ORDER BY work_id
    """).fetchall()
    return rows


def _vectorise(
    abstracts: list[str],
) -> tuple[object, list[str]]:
    """Convert abstracts to a TF-IDF matrix."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    # Dynamically adjust min_df if corpus is tiny (e.g. tests)
    effective_min_df = min(MIN_DF, max(1, len(abstracts) // 3))

    vectoriser = TfidfVectorizer(
        max_df=MAX_DF,
        min_df=effective_min_df,
        max_features=MAX_FEATURES,
        stop_words="english",
        sublinear_tf=True,
    )
    tfidf_matrix = vectoriser.fit_transform(abstracts)
    feature_names = vectoriser.get_feature_names_out().tolist()
    return tfidf_matrix, feature_names


def _fit_lda(
    tfidf_matrix,
    n_topics: int,
) -> tuple[object, np.ndarray]:
    """Fit an LDA model and return (model, doc_topic_distribution)."""
    from sklearn.decomposition import LatentDirichletAllocation

    # Ensure n_topics <= n_samples
    n_topics = min(n_topics, tfidf_matrix.shape[0])

    lda = LatentDirichletAllocation(
        n_components=n_topics,
        max_iter=LDA_MAX_ITER,
        learning_method="online",
        random_state=LDA_RANDOM_STATE,
        n_jobs=-1,
    )
    doc_topic_matrix = lda.fit_transform(tfidf_matrix)
    return lda, doc_topic_matrix


def _extract_topic_words(
    lda_model,
    feature_names: list[str],
) -> list[tuple[int, str, str]]:
    """Extract the top-N words per topic.

    Returns list of (topic_id, top_words_csv, auto_label).
    """
    topics = []
    for idx, component in enumerate(lda_model.components_):
        top_indices = component.argsort()[-TOP_N_WORDS:][::-1]
        top_words = [feature_names[i] for i in top_indices]
        # Auto-label = first 3 keywords
        label = " / ".join(top_words[:3])
        topics.append((idx, ", ".join(top_words), label))
    return topics


def _store_results(
    con: duckdb.DuckDBPyConnection,
    work_ids: list[str],
    doc_topic_matrix: np.ndarray,
    topic_words: list[tuple[int, str, str]],
) -> None:
    """Write LDA results to DuckDB."""
    con.execute("DELETE FROM lda_topic_words")
    con.execute("DELETE FROM paper_lda")

    # Topic keyword table
    con.executemany(
        "INSERT INTO lda_topic_words (topic_id, top_words, label) VALUES (?, ?, ?)",
        topic_words,
    )

    # Per-paper dominant topic assignment
    rows = []
    for i, wid in enumerate(work_ids):
        dominant = int(np.argmax(doc_topic_matrix[i]))
        prob = float(doc_topic_matrix[i, dominant])
        rows.append((wid, dominant, prob))

    con.executemany(
        "INSERT INTO paper_lda (work_id, lda_topic_id, probability) VALUES (?, ?, ?)",
        rows,
    )


# ── Standalone runner ────────────────────────────────────────────────────────

def run() -> None:
    print("=== Running LDA Baseline Topic Model ===")
    con = get_connection()
    compute_lda_topics(con)
    n_topics = con.execute("SELECT COUNT(*) FROM lda_topic_words").fetchone()[0]
    n_papers = con.execute("SELECT COUNT(*) FROM paper_lda").fetchone()[0]
    print(f"  Total LDA topics: {n_topics}, papers assigned: {n_papers}")

    # Print topic summaries
    print("\n  LDA Topic Summaries:")
    for tid, _, label in con.execute(
        "SELECT topic_id, top_words, label FROM lda_topic_words ORDER BY topic_id"
    ).fetchall():
        print(f"    Topic {tid}: {label}")

    con.close()


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    run()
