"""Collaboration Network + Community Detection — Innovation 3.

Builds a weighted co-authorship graph from the authorships table,
runs the Leiden algorithm for community detection, and labels
communities by their dominant topic.
"""

from __future__ import annotations
import duckdb
import igraph as ig
import leidenalg
from collections import Counter
from etl.db import get_connection

MIN_PAPERS_PER_AUTHOR = 3
MAX_AUTHORS_FOR_GRAPH = 20_000  # cap for responsiveness


def build_coauthorship_graph(
    con: duckdb.DuckDBPyConnection,
) -> tuple[ig.Graph, dict[str, int]]:
    """Build an igraph co-authorship graph from DuckDB authorships.

    Returns (graph, author_id_to_vertex_index).
    """
    author_papers = con.execute(f"""
        SELECT author_id, author_name, COUNT(DISTINCT work_id) AS paper_count
        FROM authorships
        WHERE author_id != ''
        GROUP BY author_id, author_name
        HAVING paper_count >= {MIN_PAPERS_PER_AUTHOR}
        ORDER BY paper_count DESC
        LIMIT {MAX_AUTHORS_FOR_GRAPH}
    """).fetchall()

    aid_to_idx: dict[str, int] = {}
    names: list[str] = []
    pcounts: list[int] = []
    for aid, aname, pc in author_papers:
        aid_to_idx[aid] = len(aid_to_idx)
        names.append(aname)
        pcounts.append(pc)

    if not aid_to_idx:
        g = ig.Graph()
        return g, aid_to_idx

    aid_set_sql = ",".join(f"'{a}'" for a in aid_to_idx)
    edges_raw = con.execute(f"""
        SELECT a1.author_id, a2.author_id, COUNT(DISTINCT a1.work_id) AS weight
        FROM authorships a1
        JOIN authorships a2
            ON a1.work_id = a2.work_id
            AND a1.author_id < a2.author_id
        WHERE a1.author_id IN ({aid_set_sql})
          AND a2.author_id IN ({aid_set_sql})
        GROUP BY a1.author_id, a2.author_id
    """).fetchall()

    edges = []
    weights = []
    for a1, a2, w in edges_raw:
        if a1 in aid_to_idx and a2 in aid_to_idx:
            edges.append((aid_to_idx[a1], aid_to_idx[a2]))
            weights.append(w)

    g = ig.Graph(n=len(aid_to_idx), edges=edges, directed=False)
    g.vs["author_id"] = list(aid_to_idx.keys())
    g.vs["name"] = names
    g.vs["paper_count"] = pcounts
    g.es["weight"] = weights

    return g, aid_to_idx


def detect_communities(g: ig.Graph) -> list[int]:
    """Run Leiden algorithm and return community membership list."""
    if g.vcount() == 0:
        return []
    partition = leidenalg.find_partition(
        g,
        leidenalg.ModularityVertexPartition,
        weights="weight",
        seed=42,
    )
    return partition.membership


def label_communities(
    con: duckdb.DuckDBPyConnection,
    g: ig.Graph,
    membership: list[int],
) -> dict[int, str]:
    """Label each community by the most frequent topic among its members."""
    community_authors: dict[int, list[str]] = {}
    for v_idx, comm_id in enumerate(membership):
        community_authors.setdefault(comm_id, []).append(
            g.vs[v_idx]["author_id"]
        )

    labels: dict[int, str] = {}
    for comm_id, author_ids in community_authors.items():
        if not author_ids:
            labels[comm_id] = f"Community {comm_id}"
            continue

        batch_size = 500
        topic_counter: Counter[str] = Counter()
        for i in range(0, len(author_ids), batch_size):
            batch = author_ids[i : i + batch_size]
            aids_sql = ",".join(f"'{a}'" for a in batch)
            rows = con.execute(f"""
                SELECT wt.topic_name, COUNT(*) AS cnt
                FROM authorships a
                JOIN work_topics wt ON a.work_id = wt.work_id
                WHERE a.author_id IN ({aids_sql})
                GROUP BY wt.topic_name
                ORDER BY cnt DESC
                LIMIT 3
            """).fetchall()
            for tname, cnt in rows:
                topic_counter[tname] += cnt

        if topic_counter:
            labels[comm_id] = topic_counter.most_common(1)[0][0]
        else:
            labels[comm_id] = f"Community {comm_id}"

    return labels


def store_communities(
    con: duckdb.DuckDBPyConnection,
    g: ig.Graph,
    membership: list[int],
    labels: dict[int, str],
) -> None:
    """Persist community assignments and edges to DuckDB."""
    con.execute("DELETE FROM author_communities")
    con.execute("DELETE FROM community_edges")

    rows = []
    for v_idx in range(g.vcount()):
        comm = membership[v_idx]
        rows.append((
            g.vs[v_idx]["author_id"],
            g.vs[v_idx]["name"],
            comm,
            labels.get(comm, ""),
            g.vs[v_idx]["paper_count"],
        ))

    if rows:
        con.executemany(
            "INSERT INTO author_communities VALUES (?, ?, ?, ?, ?)", rows
        )

    edge_rows = []
    for e in g.es:
        edge_rows.append((
            g.vs[e.source]["author_id"],
            g.vs[e.target]["author_id"],
            e["weight"],
        ))
    if edge_rows:
        con.executemany(
            "INSERT INTO community_edges VALUES (?, ?, ?)", edge_rows
        )


def run() -> None:
    print("=== Building collaboration network + detecting communities ===")
    con = get_connection()

    print("  Building co-authorship graph...")
    g, aid_to_idx = build_coauthorship_graph(con)
    print(f"  Graph: {g.vcount()} authors, {g.ecount()} co-authorship edges")

    if g.vcount() == 0:
        print("  No authors found. Skipping community detection.")
        con.close()
        return

    print("  Running Leiden community detection...")
    membership = detect_communities(g)
    n_communities = len(set(membership))
    print(f"  Found {n_communities} communities")

    print("  Labeling communities by dominant topic...")
    labels = label_communities(con, g, membership)

    print("  Storing results...")
    store_communities(con, g, membership, labels)
    con.close()
    print("  Done.")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    run()
