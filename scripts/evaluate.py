#!/usr/bin/env python3
"""Full evaluation suite for AI Research Atlas."""

import sys, os, time, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
from etl.db import get_connection

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was",
    "not", "have", "has", "its", "via", "using", "based", "into", "been",
    "which", "their", "also", "more", "than", "over", "such", "each",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _tokenize(title: str) -> frozenset[str]:
    words = set()
    for w in title.lower().split():
        w = w.strip(".,;:()[]{}\"'")
        if len(w) > 3 and w not in _STOPWORDS and w.isalpha():
            words.add(w)
    return frozenset(words)


def _works_topic_year(con, year_range=None) -> pd.DataFrame:
    q = """
        SELECT wt.topic_id, wt.topic_name, w.publication_year AS year,
               COUNT(DISTINCT w.work_id) AS work_count
        FROM work_topics wt JOIN works w ON wt.work_id = w.work_id
    """
    if year_range:
        q += f" WHERE w.publication_year BETWEEN {year_range[0]} AND {year_range[1]}"
    q += " GROUP BY wt.topic_id, wt.topic_name, w.publication_year"
    return con.execute(q).df()


# ── 1. NPMI topic coherence ───────────────────────────────────────────────────

def npmi_coherence(top_n_words: int = 10, top_n_topics: int = 20) -> dict:
    con = get_connection(read_only=True)
    if con.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0:
        con.close()
        return {"status": "skipped"}

    top_topic_ids = [r[0] for r in con.execute("""
        SELECT topic_id FROM (
            SELECT topic_id, COUNT(*) AS cnt
            FROM work_topics GROUP BY topic_id ORDER BY cnt DESC LIMIT ?
        )
    """, [top_n_topics]).fetchall()]

    rows = con.execute("""
        SELECT wt.topic_id, wt.topic_name, wt.work_id, w.title
        FROM work_topics wt JOIN works w ON wt.work_id = w.work_id
        WHERE wt.topic_id IN (SELECT UNNEST(?))
    """, [top_topic_ids]).df()
    con.close()

    if rows.empty:
        return {"status": "no rows"}

    rows["words"] = rows["title"].apply(_tokenize)
    all_doc_words = rows.drop_duplicates("work_id")["words"].tolist()
    D = len(all_doc_words)
    topic_npmi: dict[str, float] = {}

    for topic_id, group in rows.groupby("topic_id"):
        topic_name = group["topic_name"].iloc[0]
        topic_words_list = group["words"].tolist()
        word_freq: dict[str, int] = {}
        for ws in topic_words_list:
            for w in ws:
                word_freq[w] = word_freq.get(w, 0) + 1
        top_words = sorted(word_freq, key=word_freq.__getitem__, reverse=True)[:top_n_words]
        if len(top_words) < 2:
            continue
        doc_freq = {w: sum(1 for doc in all_doc_words if w in doc) for w in top_words}
        scores = []
        for i in range(len(top_words)):
            for j in range(i + 1, len(top_words)):
                w1, w2 = top_words[i], top_words[j]
                co = sum(1 for doc in topic_words_list if w1 in doc and w2 in doc)
                if co == 0:
                    continue
                p_co = co / D
                p_w1 = doc_freq[w1] / D
                p_w2 = doc_freq[w2] / D
                pmi = math.log(p_co / (p_w1 * p_w2 + 1e-12) + 1e-12)
                npmi = pmi / (-math.log(p_co + 1e-12))
                scores.append(npmi)
        if scores:
            topic_npmi[topic_name] = sum(scores) / len(scores)

    if not topic_npmi:
        return {"status": "no scores"}

    avg = sum(topic_npmi.values()) / len(topic_npmi)
    best  = max(topic_npmi, key=topic_npmi.__getitem__)
    worst = min(topic_npmi, key=topic_npmi.__getitem__)
    return {
        "avg_npmi": round(avg, 4),
        "n_topics_evaluated": len(topic_npmi),
        "best_topic":  {"name": best,  "npmi": round(topic_npmi[best], 4)},
        "worst_topic": {"name": worst, "npmi": round(topic_npmi[worst], 4)},
    }


# ── 2. Trend sanity + related-topic correlation ───────────────────────────────

def trend_sanity_check() -> dict:
    con = get_connection(read_only=True)
    df = con.execute("""
        SELECT topic_name, year, work_count
        FROM topic_year_stats
        WHERE LOWER(topic_name) LIKE '%natural language%'
           OR LOWER(topic_name) LIKE '%neural network%'
           OR LOWER(topic_name) LIKE '%graph neural%'
           OR LOWER(topic_name) LIKE '%large language%'
           OR LOWER(topic_name) LIKE '%transformer%'
        ORDER BY topic_name, year
    """).df()
    con.close()

    if df.empty:
        return {"status": "skipped"}

    results = {}
    for name, group in df.groupby("topic_name"):
        group = group.sort_values("year")
        pre  = group[group["year"] <= 2020]["work_count"].mean()
        post = group[group["year"] > 2020]["work_count"].mean()
        results[name] = {
            "pre_2020_avg":   round(float(pre),  1) if pd.notna(pre)  else 0,
            "post_2020_avg":  round(float(post), 1) if pd.notna(post) else 0,
            "growth_detected": bool(post > pre) if pd.notna(pre) and pd.notna(post) else None,
        }
    return results


def related_topic_trend_correlation() -> dict:
    con = get_connection(read_only=True)
    tys = _works_topic_year(con)
    con.close()

    if tys.empty:
        return {"status": "skipped"}

    top_topics = (
        tys.groupby("topic_id")["work_count"].sum()
        .nlargest(30).index.tolist()
    )
    tys = tys[tys["topic_id"].isin(top_topics)]

    pivot = tys.pivot_table(
        index="year", columns="topic_name", values="work_count", fill_value=0
    )
    if pivot.shape[1] < 2:
        return {"status": "insufficient topics"}

    corr = pivot.corr()
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs.append((cols[i], cols[j], float(corr.iloc[i, j])))

    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    avg_abs = sum(abs(p[2]) for p in pairs) / len(pairs)

    return {
        "avg_pairwise_trend_correlation": round(avg_abs, 4),
        "top_correlated_pairs": [
            {"topic_1": p[0][:45], "topic_2": p[1][:45], "correlation": round(p[2], 3)}
            for p in pairs[:5]
        ],
    }


# ── 3. Collaboration: intra vs inter-community ────────────────────────────────

def collaboration_community_analysis() -> dict:
    con = get_connection(read_only=True)
    df = con.execute("""
        SELECT e.source_author_id, e.target_author_id, e.weight,
               a1.community_id AS src_comm, a2.community_id AS tgt_comm
        FROM community_edges e
        JOIN author_communities a1 ON e.source_author_id = a1.author_id
        JOIN author_communities a2 ON e.target_author_id = a2.author_id
    """).df()
    con.close()

    if df.empty:
        return {"status": "skipped"}

    intra = df[df["src_comm"] == df["tgt_comm"]]
    inter = df[df["src_comm"] != df["tgt_comm"]]
    total_weight = df["weight"].sum()

    return {
        "total_edges": int(len(df)),
        "intra_community_edges": int(len(intra)),
        "inter_community_edges": int(len(inter)),
        "intra_edge_fraction":   round(len(intra) / len(df), 4),
        "intra_weight_fraction": round(float(intra["weight"].sum() / total_weight), 4),
    }


# ── 4. Graph robustness under author-threshold changes ────────────────────────

def graph_robustness_check() -> dict:
    con = get_connection(read_only=True)
    nodes = con.execute("SELECT author_id, community_id, paper_count FROM author_communities").df()
    edges = con.execute("SELECT source_author_id, target_author_id, weight FROM community_edges").df()
    con.close()

    results = {}
    for threshold in [1, 2, 5, 10, 20]:
        qualified = set(nodes[nodes["paper_count"] >= threshold]["author_id"])
        filtered_edges = edges[
            edges["source_author_id"].isin(qualified) &
            edges["target_author_id"].isin(qualified)
        ]
        filtered_nodes = nodes[nodes["paper_count"] >= threshold]

        try:
            import igraph as ig, leidenalg
            g = ig.Graph()
            g.add_vertices(list(qualified))
            vmap = {v: i for i, v in enumerate(qualified)}
            edge_list = [
                (vmap[r.source_author_id], vmap[r.target_author_id])
                for _, r in filtered_edges.iterrows()
                if r.source_author_id in vmap and r.target_author_id in vmap
            ]
            g.add_edges(edge_list)
            partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)
            modularity = round(partition.modularity, 4)
            n_comm = len(partition)
        except Exception:
            modularity = None
            n_comm = filtered_nodes["community_id"].nunique()

        results[f"min_papers_{threshold}"] = {
            "n_authors":     int(len(qualified)),
            "n_edges":       int(len(filtered_edges)),
            "n_communities": int(n_comm),
            "modularity":    modularity,
        }

    return results


# ── 5. Emerging topic backtest ────────────────────────────────────────────────

def emerging_topic_backtest() -> dict:
    con = get_connection(read_only=True)
    signals = con.execute("SELECT * FROM emerging_topic_signals ORDER BY year").df()
    tys     = _works_topic_year(con)
    con.close()

    if signals.empty or tys.empty:
        return {"status": "skipped"}

    tys = tys.sort_values(["topic_id", "year"])
    tys["next_wc"] = tys.groupby("topic_id")["work_count"].shift(-1)
    tys["actual_growth"] = (tys["next_wc"] - tys["work_count"]) / (tys["work_count"] + 1)

    years = sorted(signals["year"].unique())
    results = {}

    for test_year in [y for y in years if y + 1 in years]:
        predicted = set(
            signals[(signals["year"] == test_year) & (signals["classification"] == "emerging")]["topic_id"]
        )
        if not predicted:
            continue

        actual_df = tys[tys["year"] == test_year].dropna(subset=["actual_growth"])
        if actual_df.empty:
            continue

        n = len(predicted)
        actual_top = set(actual_df.nlargest(n, "actual_growth")["topic_id"])

        tp = len(predicted & actual_top)
        precision = tp / len(predicted) if predicted else 0
        recall    = tp / len(actual_top) if actual_top else 0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0)

        results[str(test_year + 1)] = {
            "n_predicted": n,
            "precision":   round(precision, 3),
            "recall":      round(recall, 3),
            "f1":          round(f1, 3),
        }

    if results:
        avg_f1 = round(sum(v["f1"] for v in results.values()) / len(results), 3)
        results["avg_f1"] = avg_f1

    return results


# ── 6. Signal importance ──────────────────────────────────────────────────────

def signal_importance() -> dict:
    con = get_connection(read_only=True)
    signals = con.execute("SELECT * FROM emerging_topic_signals").df()
    tys     = _works_topic_year(con)
    con.close()

    if signals.empty or tys.empty:
        return {"status": "skipped"}

    tys = tys.sort_values(["topic_id", "year"])
    tys["next_growth"] = tys.groupby("topic_id")["work_count"].pct_change().shift(-1)

    merged = signals.merge(
        tys[["topic_id", "year", "next_growth"]], on=["topic_id", "year"]
    ).dropna(subset=["next_growth"])

    if merged.empty:
        return {"status": "no overlap"}

    signal_cols = ["acceleration", "new_author_fraction", "cross_topic_score", "composite_score"]
    correlations = {}
    for col in signal_cols:
        if col in merged.columns:
            corr = merged[col].corr(merged["next_growth"], method="spearman")
            correlations[col] = round(float(corr), 4)

    ranked = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)
    return {
        "spearman_correlations": correlations,
        "strongest_signal": ranked[0][0] if ranked else None,
    }


# ── 7. Emerging topic stability ───────────────────────────────────────────────

def emerging_topic_stability() -> dict:
    con = get_connection(read_only=True)
    signals = con.execute("""
        SELECT * FROM emerging_topic_signals
        WHERE year = (SELECT MAX(year) FROM emerging_topic_signals)
    """).df()
    con.close()

    if signals.empty:
        return {"status": "skipped"}

    baseline_top = set(signals.nlargest(10, "composite_score")["topic_id"])

    configs = {
        "accel_heavy":   (0.6, 0.2, 0.2),
        "author_heavy":  (0.2, 0.6, 0.2),
        "bridging_heavy":(0.2, 0.2, 0.6),
        "equal":         (0.33, 0.33, 0.34),
    }

    results = {}
    for name, (w1, w2, w3) in configs.items():
        s = signals.copy()
        def norm(c): return (s[c] - s[c].min()) / (s[c].max() - s[c].min() + 1e-12)
        s["reweighted"] = w1 * norm("acceleration") + w2 * norm("new_author_fraction") + w3 * norm("cross_topic_score")
        alt_top = set(s.nlargest(10, "reweighted")["topic_id"])
        overlap = len(baseline_top & alt_top)
        results[name] = {"top10_overlap": overlap, "stability": round(overlap / 10, 2)}

    return results


# ── 8. Community modularity ───────────────────────────────────────────────────

def community_modularity() -> dict:
    con = get_connection(read_only=True)
    n_comm    = con.execute("SELECT COUNT(DISTINCT community_id) FROM author_communities").fetchone()[0]
    n_authors = con.execute("SELECT COUNT(*) FROM author_communities").fetchone()[0]
    n_edges   = con.execute("SELECT COUNT(*) FROM community_edges").fetchone()[0]
    con.close()
    return {"n_communities": n_comm, "n_authors": n_authors, "n_edges": n_edges}


# ── 9. Query latency ──────────────────────────────────────────────────────────

def query_latency_benchmark() -> dict:
    con = get_connection(read_only=True)
    queries = {
        "topic_year_stats": "SELECT * FROM topic_year_stats",
        "emerging_signals": "SELECT * FROM emerging_topic_signals",
        "network_nodes":    "SELECT * FROM author_communities",
        "network_edges":    "SELECT * FROM community_edges",
    }
    results = {}
    for name, q in queries.items():
        t0 = time.perf_counter()
        try:
            con.execute(q).df()
            results[name] = f"{(time.perf_counter() - t0) * 1000:.1f}ms"
        except Exception as e:
            results[name] = f"error: {e}"
    con.close()
    return results


# ── runner ────────────────────────────────────────────────────────────────────

def run():
    print("=== AI Research Atlas — Full Evaluation ===\n")

    print("1. NPMI Topic Coherence:")
    for k, v in npmi_coherence().items():
        print(f"   {k}: {v}")

    print("\n2. Trend Sanity Check (known AI topics post-2020):")
    for topic, info in trend_sanity_check().items():
        print(f"   {topic}: {info}")

    print("\n3. Related Topic Trend Correlation:")
    res = related_topic_trend_correlation()
    print(f"   avg_pairwise_trend_correlation: {res.get('avg_pairwise_trend_correlation')}")
    for p in res.get("top_correlated_pairs", []):
        print(f"   {p['topic_1'][:40]} <-> {p['topic_2'][:40]}: r={p['correlation']}")

    print("\n4. Collaboration — Intra vs Inter-Community:")
    for k, v in collaboration_community_analysis().items():
        print(f"   {k}: {v}")

    print("\n5. Graph Robustness (varying author threshold):")
    for thresh, info in graph_robustness_check().items():
        print(f"   {thresh}: {info}")

    print("\n6. Emerging Topic Backtest:")
    for k, v in emerging_topic_backtest().items():
        print(f"   predict_{k}: {v}")

    print("\n7. Signal Importance (Spearman correlation with next-year growth):")
    for k, v in signal_importance().items():
        print(f"   {k}: {v}")

    print("\n8. Emerging Topic Stability (weight perturbation):")
    for config, info in emerging_topic_stability().items():
        print(f"   {config}: {info}")

    print("\n9. Community Modularity:")
    for k, v in community_modularity().items():
        print(f"   {k}: {v}")

    print("\n10. Query Latency Benchmark:")
    for k, v in query_latency_benchmark().items():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    run()
