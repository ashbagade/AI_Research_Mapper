"""Emerging Topic Detector — Innovation 2.

Identifies topics likely to grow based on early signals:
  1. Growth acceleration (second derivative of work count)
  2. New-author influx (fraction of authors new to this topic)
  3. Cross-topic connections (authors bridging from other topics)

Unlike the trend timeline which shows historical popularity, this module
surfaces topics that are not yet dominant but exhibit characteristics
of future expansion.
"""

from __future__ import annotations
import duckdb
from etl.db import get_connection

# Weights for composite emerging score
W_ACCELERATION = 0.4
W_NEW_AUTHORS = 0.3
W_CROSS_TOPIC = 0.3

TOP_K_PAPERS = 5


def compute_emerging_signals(con: duckdb.DuckDBPyConnection | None = None) -> None:
    close_after = con is None
    if con is None:
        con = get_connection()

    con.execute("DELETE FROM emerging_topic_signals")
    con.execute("DELETE FROM emerging_topic_papers")

    _compute_acceleration(con)
    _compute_new_author_fraction(con)
    _compute_cross_topic_score(con)
    _compute_composite_and_classify(con)
    _link_representative_papers(con)

    if close_after:
        con.close()


def _compute_acceleration(con: duckdb.DuckDBPyConnection) -> None:
    """Second derivative of work_count: growth_rate(t) - growth_rate(t-1)."""
    con.execute("""
        INSERT INTO emerging_topic_signals
            (topic_id, topic_name, year, acceleration,
             new_author_fraction, cross_topic_score, composite_score, classification)
        SELECT
            cur.topic_id,
            cur.topic_name,
            cur.year,
            COALESCE(cur.growth_rate - prev.growth_rate, 0) AS acceleration,
            0, 0, 0, 'pending'
        FROM topic_year_stats cur
        LEFT JOIN topic_year_stats prev
            ON cur.topic_id = prev.topic_id AND cur.year = prev.year + 1
        WHERE cur.work_count > 0
    """)


def _compute_new_author_fraction(con: duckdb.DuckDBPyConnection) -> None:
    """Fraction of authors in topic-year who did NOT publish in that topic
    in any prior year. Requires the authorships + work_topics tables."""
    has_data = con.execute("SELECT COUNT(*) FROM authorships").fetchone()[0]
    if has_data == 0:
        return

    con.execute("""
        WITH topic_author_year AS (
            SELECT DISTINCT wt.topic_id, a.author_id, w.publication_year AS year
            FROM work_topics wt
            JOIN works w ON wt.work_id = w.work_id
            JOIN authorships a ON wt.work_id = a.work_id
            WHERE a.author_id != ''
        ),
        first_year AS (
            SELECT topic_id, author_id, MIN(year) AS first_yr
            FROM topic_author_year
            GROUP BY topic_id, author_id
        ),
        fractions AS (
            SELECT
                tay.topic_id,
                tay.year,
                COUNT(DISTINCT CASE WHEN fy.first_yr = tay.year
                                    THEN tay.author_id END) * 1.0
                / NULLIF(COUNT(DISTINCT tay.author_id), 0) AS new_frac
            FROM topic_author_year tay
            JOIN first_year fy
                ON tay.topic_id = fy.topic_id AND tay.author_id = fy.author_id
            GROUP BY tay.topic_id, tay.year
        )
        UPDATE emerging_topic_signals AS e
        SET new_author_fraction = COALESCE(f.new_frac, 0)
        FROM fractions f
        WHERE e.topic_id = f.topic_id AND e.year = f.year
    """)


def _compute_cross_topic_score(con: duckdb.DuckDBPyConnection) -> None:
    """Measures how many authors publishing in this topic also published
    in OTHER topics in the same year — a signal of convergence/bridging."""
    has_data = con.execute("SELECT COUNT(*) FROM authorships").fetchone()[0]
    if has_data == 0:
        return

    con.execute("""
        WITH author_topic_year AS (
            SELECT DISTINCT a.author_id, wt.topic_id, w.publication_year AS year
            FROM authorships a
            JOIN work_topics wt ON a.work_id = wt.work_id
            JOIN works w ON a.work_id = w.work_id
            WHERE a.author_id != ''
        ),
        author_topic_count AS (
            SELECT author_id, year, COUNT(DISTINCT topic_id) AS n_topics
            FROM author_topic_year
            GROUP BY author_id, year
        ),
        bridging AS (
            SELECT
                aty.topic_id,
                aty.year,
                AVG(CASE WHEN atc.n_topics > 1 THEN 1.0 ELSE 0.0 END) AS bridge_frac
            FROM author_topic_year aty
            JOIN author_topic_count atc
                ON aty.author_id = atc.author_id AND aty.year = atc.year
            GROUP BY aty.topic_id, aty.year
        )
        UPDATE emerging_topic_signals AS e
        SET cross_topic_score = COALESCE(b.bridge_frac, 0)
        FROM bridging b
        WHERE e.topic_id = b.topic_id AND e.year = b.year
    """)


def _compute_composite_and_classify(con: duckdb.DuckDBPyConnection) -> None:
    """Combine signals into composite score and classify topics."""
    con.execute(f"""
        WITH minmax AS (
            SELECT
                MIN(acceleration) AS min_a, MAX(acceleration) AS max_a,
                MIN(new_author_fraction) AS min_n, MAX(new_author_fraction) AS max_n,
                MIN(cross_topic_score) AS min_c, MAX(cross_topic_score) AS max_c
            FROM emerging_topic_signals
        ),
        normed AS (
            SELECT
                e.topic_id, e.year,
                CASE WHEN (m.max_a - m.min_a) > 0
                     THEN (e.acceleration - m.min_a) / (m.max_a - m.min_a)
                     ELSE 0 END AS norm_accel,
                CASE WHEN (m.max_n - m.min_n) > 0
                     THEN (e.new_author_fraction - m.min_n) / (m.max_n - m.min_n)
                     ELSE 0 END AS norm_new,
                CASE WHEN (m.max_c - m.min_c) > 0
                     THEN (e.cross_topic_score - m.min_c) / (m.max_c - m.min_c)
                     ELSE 0 END AS norm_cross
            FROM emerging_topic_signals e, minmax m
        )
        UPDATE emerging_topic_signals AS e
        SET composite_score = (
            {W_ACCELERATION} * n.norm_accel
            + {W_NEW_AUTHORS} * n.norm_new
            + {W_CROSS_TOPIC} * n.norm_cross
        )
        FROM normed n
        WHERE e.topic_id = n.topic_id AND e.year = n.year
    """)

    con.execute("""
        WITH thresholds AS (
            SELECT
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY composite_score) AS p75,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY composite_score) AS p25
            FROM emerging_topic_signals
        )
        UPDATE emerging_topic_signals AS e
        SET classification = CASE
            WHEN e.composite_score >= th.p75 THEN 'emerging'
            WHEN e.composite_score <= th.p25 THEN 'declining'
            ELSE 'established'
        END
        FROM thresholds th
    """)

    con.execute("""
        UPDATE topic_year_stats AS tys
        SET is_emerging = (ets.classification = 'emerging')
        FROM emerging_topic_signals ets
        WHERE tys.topic_id = ets.topic_id AND tys.year = ets.year
    """)


def _link_representative_papers(con: duckdb.DuckDBPyConnection) -> None:
    """For each emerging topic-year, find top-K papers by citation count."""
    has_works = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    if has_works == 0:
        return

    con.execute(f"""
        INSERT INTO emerging_topic_papers
        SELECT sub.topic_id, sub.year, sub.work_id, sub.title,
               sub.cited_by_count, sub.rn AS rank
        FROM (
            SELECT
                ets.topic_id, ets.year,
                w.work_id, w.title, w.cited_by_count,
                ROW_NUMBER() OVER (
                    PARTITION BY ets.topic_id, ets.year
                    ORDER BY w.cited_by_count DESC
                ) AS rn
            FROM emerging_topic_signals ets
            JOIN work_topics wt ON ets.topic_id = wt.topic_id
            JOIN works w ON wt.work_id = w.work_id
                AND w.publication_year = ets.year
            WHERE ets.classification = 'emerging'
        ) sub
        WHERE sub.rn <= {TOP_K_PAPERS}
    """)


def run() -> None:
    print("=== Running Emerging Topic Detector ===")
    con = get_connection()
    compute_emerging_signals(con)

    n_emerging = con.execute("""
        SELECT COUNT(DISTINCT topic_id)
        FROM emerging_topic_signals
        WHERE classification = 'emerging'
    """).fetchone()[0]
    n_papers = con.execute("SELECT COUNT(*) FROM emerging_topic_papers").fetchone()[0]
    print(f"  Detected {n_emerging} distinct emerging topics")
    print(f"  Linked {n_papers} representative papers")
    con.close()


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    run()
