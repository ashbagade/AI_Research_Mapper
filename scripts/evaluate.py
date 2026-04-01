#!/usr/bin/env python3
"""Evaluation metrics: topic coherence, trend sanity, latency, modularity."""

import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from etl.db import get_connection


def topic_coherence_check() -> dict:
    """Check that topics have meaningful vocabulary overlap (proxy for NPMI).

    Uses title word overlap within vs across topics as a simple coherence proxy.
    """
    con = get_connection(read_only=True)
    work_count = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    if work_count == 0:
        con.close()
        return {"status": "skipped", "reason": "no works data"}

    intra = con.execute("""
        WITH split AS (
            SELECT wt.topic_id, w.work_id,
                   string_split(LOWER(w.title), ' ') AS words
            FROM work_topics wt
            JOIN works w ON wt.work_id = w.work_id
        ),
        topic_words AS (
            SELECT topic_id, UNNEST(words) AS word
            FROM split
        ),
        filtered AS (
            SELECT topic_id, word
            FROM topic_words
            WHERE LENGTH(word) > 3
        )
        SELECT AVG(cnt) AS avg_shared FROM (
            SELECT topic_id, word, COUNT(*) AS cnt
            FROM filtered
            GROUP BY topic_id, word
            HAVING cnt > 5
        )
    """).fetchone()
    con.close()

    return {"avg_intra_topic_word_frequency": intra[0] if intra[0] else 0}


def trend_sanity_check() -> dict:
    """Verify known trends: LLM/NLP topics should grow post-2020."""
    con = get_connection(read_only=True)
    df = con.execute("""
        SELECT topic_name, year, work_count
        FROM topic_year_stats
        WHERE LOWER(topic_name) LIKE '%natural language%'
           OR LOWER(topic_name) LIKE '%neural network%'
           OR LOWER(topic_name) LIKE '%graph neural%'
        ORDER BY topic_name, year
    """).df()
    con.close()

    results = {}
    if df.empty:
        return {"status": "skipped", "reason": "no matching topics"}

    for name, group in df.groupby("topic_name"):
        group = group.sort_values("year")
        pre = group[group["year"] <= 2020]["work_count"].mean()
        post = group[group["year"] > 2020]["work_count"].mean()
        results[name] = {
            "pre_2020_avg": round(pre, 1) if pd.notna(pre) else 0,
            "post_2020_avg": round(post, 1) if pd.notna(post) else 0,
            "growth_detected": bool(post > pre) if pd.notna(pre) and pd.notna(post) else None,
        }
    return results


def community_modularity() -> dict:
    """Compute modularity of the Leiden partition from stored data."""
    con = get_connection(read_only=True)
    n_communities = con.execute(
        "SELECT COUNT(DISTINCT community_id) FROM author_communities"
    ).fetchone()[0]
    n_authors = con.execute(
        "SELECT COUNT(*) FROM author_communities"
    ).fetchone()[0]
    n_edges = con.execute(
        "SELECT COUNT(*) FROM community_edges"
    ).fetchone()[0]
    con.close()

    return {
        "n_communities": n_communities,
        "n_authors": n_authors,
        "n_edges": n_edges,
    }


def query_latency_benchmark() -> dict:
    """Measure typical query latencies for dashboard data loading."""
    con = get_connection(read_only=True)
    queries = {
        "topic_year_stats": "SELECT * FROM topic_year_stats",
        "emerging_signals": "SELECT * FROM emerging_topic_signals",
        "network_nodes": "SELECT * FROM author_communities",
        "network_edges": "SELECT * FROM community_edges",
    }

    results = {}
    for name, q in queries.items():
        t0 = time.perf_counter()
        try:
            con.execute(q).df()
            elapsed = (time.perf_counter() - t0) * 1000
            results[name] = f"{elapsed:.1f}ms"
        except Exception as e:
            results[name] = f"error: {e}"

    con.close()
    return results


def run():
    print("=== Evaluation ===\n")

    print("1. Topic Coherence Check:")
    for k, v in topic_coherence_check().items():
        print(f"   {k}: {v}")

    print("\n2. Trend Sanity Check:")
    sanity = trend_sanity_check()
    for topic, info in sanity.items():
        print(f"   {topic}: {info}")

    print("\n3. Community Modularity:")
    for k, v in community_modularity().items():
        print(f"   {k}: {v}")

    print("\n4. Query Latency Benchmark:")
    for k, v in query_latency_benchmark().items():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    run()
