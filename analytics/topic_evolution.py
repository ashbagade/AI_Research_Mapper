"""Topic Trend Timeline — Innovation 1.

Computes per-topic growth rates, momentum (3-year rolling average),
and relative share for the Topic Trend Timeline view.
"""

from __future__ import annotations
import duckdb
from etl.db import get_connection


def compute_topic_year_stats(con: duckdb.DuckDBPyConnection | None = None) -> None:
    """Compute growth_rate, relative_share, and momentum from raw counts.

    Expects topic_year_stats to already contain work_count per topic-year
    (populated by fetch_aggregates or by aggregating from the works table).
    """
    close_after = con is None
    if con is None:
        con = get_connection()

    _backfill_from_works_table(con)

    con.execute("""
        UPDATE topic_year_stats AS t
        SET relative_share = t.work_count * 1.0 / totals.total
        FROM (
            SELECT year, SUM(work_count) AS total
            FROM topic_year_stats
            GROUP BY year
        ) AS totals
        WHERE t.year = totals.year AND totals.total > 0
    """)

    con.execute("""
        UPDATE topic_year_stats AS cur
        SET growth_rate = CASE
            WHEN prev.work_count > 0
            THEN (cur.work_count - prev.work_count) * 1.0 / prev.work_count
            ELSE 0
        END
        FROM topic_year_stats AS prev
        WHERE cur.topic_id = prev.topic_id
          AND cur.year = prev.year + 1
    """)

    con.execute("""
        UPDATE topic_year_stats AS cur
        SET momentum = (
            SELECT AVG(sub.growth_rate)
            FROM topic_year_stats AS sub
            WHERE sub.topic_id = cur.topic_id
              AND sub.year BETWEEN cur.year - 2 AND cur.year
        )
    """)

    _update_citation_sums(con)

    if close_after:
        con.close()


def _backfill_from_works_table(con: duckdb.DuckDBPyConnection) -> None:
    """If bulk works have been loaded, recompute counts from work_topics."""
    has_works = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='works'"
    ).fetchone()[0]
    if not has_works:
        return

    work_count = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    if work_count == 0:
        return

    con.execute("""
        INSERT OR REPLACE INTO topic_year_stats (
            topic_id, topic_name, year, work_count,
            citation_sum, growth_rate, relative_share, momentum, is_emerging
        )
        SELECT
            wt.topic_id,
            wt.topic_name,
            w.publication_year AS year,
            COUNT(DISTINCT w.work_id) AS work_count,
            0 AS citation_sum,
            0 AS growth_rate,
            0 AS relative_share,
            0 AS momentum,
            false AS is_emerging
        FROM work_topics wt
        JOIN works w ON wt.work_id = w.work_id
        GROUP BY wt.topic_id, wt.topic_name, w.publication_year
    """)


def _update_citation_sums(con: duckdb.DuckDBPyConnection) -> None:
    """Update citation_sum from the works table if available."""
    work_count = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    if work_count == 0:
        return

    con.execute("""
        UPDATE topic_year_stats AS tys
        SET citation_sum = sub.csum
        FROM (
            SELECT wt.topic_id, w.publication_year AS year,
                   SUM(w.cited_by_count) AS csum
            FROM work_topics wt
            JOIN works w ON wt.work_id = w.work_id
            GROUP BY wt.topic_id, w.publication_year
        ) AS sub
        WHERE tys.topic_id = sub.topic_id AND tys.year = sub.year
    """)


def run() -> None:
    print("=== Computing topic evolution statistics ===")
    con = get_connection()
    compute_topic_year_stats(con)
    n = con.execute("SELECT COUNT(*) FROM topic_year_stats WHERE growth_rate != 0").fetchone()[0]
    print(f"  Updated {n} topic-year rows with growth/momentum stats")
    con.close()


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    run()
