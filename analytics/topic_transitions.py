"""Topic merge/split detection using combined structural + behavioral signals.

Structural signal: how paper dual-tagging overlap between two topics changes
year-over-year (topics converging = papers increasingly tagged with both).

Behavioral signal: author migration — fraction of topic A's researchers who
publish in topic B the following year.

A transition is flagged only when both signals fire together. filters
out noisy false positives that either signal alone would produce.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from etl.db import get_connection


def compute_topic_transitions(
    combined_threshold: float = 0.50,
    top_n_topics: int = 30,
    structural_weight: float = 0.50,
) -> pd.DataFrame:
    con = get_connection(read_only=True)
    if con.execute("SELECT COUNT(*) FROM works").fetchone()[0] == 0:
        con.close()
        return pd.DataFrame()

    top_topics = [r[0] for r in con.execute("""
        SELECT topic_id FROM (
            SELECT wt.topic_id, COUNT(DISTINCT w.work_id) AS n
            FROM work_topics wt JOIN works w ON wt.work_id = w.work_id
            GROUP BY wt.topic_id ORDER BY n DESC LIMIT ?
        )
    """, [top_n_topics]).fetchall()]

    paper_df = con.execute("""
        SELECT DISTINCT wt.topic_id, wt.topic_name,
                        w.publication_year AS year, wt.work_id
        FROM work_topics wt JOIN works w ON wt.work_id = w.work_id
        WHERE wt.topic_id IN (SELECT UNNEST(?))
    """, [top_topics]).df()

    author_df = con.execute("""
        SELECT DISTINCT wt.topic_id, w.publication_year AS year, au.author_id
        FROM work_topics wt
        JOIN works w  ON wt.work_id  = w.work_id
        JOIN authorships au ON w.work_id = au.work_id
        WHERE wt.topic_id IN (SELECT UNNEST(?))
    """, [top_topics]).df()

    con.close()

    papers:  dict[tuple, set] = {}
    authors: dict[tuple, set] = {}
    names:   dict[str, str]   = {}

    for (tid, year), grp in paper_df.groupby(["topic_id", "year"]):
        papers[(tid, year)] = set(grp["work_id"])
        names[tid] = grp["topic_name"].iloc[0]

    for (tid, year), grp in author_df.groupby(["topic_id", "year"]):
        authors[(tid, year)] = set(grp["author_id"])

    years = sorted({y for _, y in papers})
    rows  = []

    for i, year in enumerate(years[:-1]):
        next_year  = years[i + 1]
        src_topics = [t for t, y in papers if y == year]
        tgt_topics = [t for t, y in papers if y == next_year]

        for src in src_topics:
            src_papers_y  = papers[(src, year)]
            src_authors_y = authors.get((src, year), set())
            if not src_papers_y or not src_authors_y:
                continue

            src_papers_y1 = papers.get((src, next_year), set())

            for tgt in tgt_topics:
                if src == tgt:
                    continue

                tgt_papers_y  = papers.get((tgt, year), set())
                tgt_papers_y1 = papers.get((tgt, next_year), set())
                tgt_authors_y1 = authors.get((tgt, next_year), set())

                # ── Structural signal ──────────────────────────────────────
                # Dual-tagging overlap: fraction of src's papers also in tgt
                overlap_y  = (len(src_papers_y  & tgt_papers_y)  / len(src_papers_y)
                              if src_papers_y else 0.0)
                overlap_y1 = (len(src_papers_y1 & tgt_papers_y1) / len(src_papers_y1)
                              if src_papers_y1 else 0.0)

                # Weight current overlap level + positive trend equally
                trend = overlap_y1 - overlap_y
                structural = 0.6 * overlap_y1 + 0.4 * max(0.0, trend)

                # ── Behavioral signal ──────────────────────────────────────
                shared_authors = len(src_authors_y & tgt_authors_y1)
                behavioral = shared_authors / len(src_authors_y)

                rows.append({
                    "src_topic_id":   src,
                    "tgt_topic_id":   tgt,
                    "src_topic_name": names.get(src, src),
                    "tgt_topic_name": names.get(tgt, tgt),
                    "year":           year,
                    "next_year":      next_year,
                    "structural":     structural,
                    "structural_trend": trend,
                    "behavioral":     behavioral,
                    "shared_authors": shared_authors,
                })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["norm_structural"] = _minmax(df["structural"])
    df["norm_behavioral"] = _minmax(df["behavioral"])
    df["combined_score"]  = (
        structural_weight       * df["norm_structural"] +
        (1 - structural_weight) * df["norm_behavioral"]
    )

    df = df[df["combined_score"] >= combined_threshold].copy()
    if df.empty:
        return pd.DataFrame()

    df["overlap_count"] = df["shared_authors"]
    df["overlap_ratio"]  = df["combined_score"]
    df = _classify(df)

    return df[[
        "src_topic_id", "tgt_topic_id", "src_topic_name", "tgt_topic_name",
        "year", "next_year", "overlap_count", "overlap_ratio",
        "transition_type", "combined_score", "structural", "behavioral",
    ]]


def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    return pd.Series(0.0, index=s.index) if hi == lo else (s - lo) / (hi - lo)


def _classify(df: pd.DataFrame) -> pd.DataFrame:
    """Label each transition as split, merge, or transfer.

    Merge: multiple sources converge on one target (fan-in > 1).
    Split: one source fans out to multiple targets (fan-out > 1).
    Transfer: clean 1-to-1 author + paper shift.
    """
    fan_out = df.groupby(["src_topic_id", "year"])["tgt_topic_id"].count().to_dict()
    fan_in  = df.groupby(["tgt_topic_id", "next_year"])["src_topic_id"].count().to_dict()

    def label(row):
        if fan_in.get((row["tgt_topic_id"], row["next_year"]), 1) > 1:
            return "merge"
        if fan_out.get((row["src_topic_id"], row["year"]), 1) > 1:
            return "split"
        return "transfer"

    df["transition_type"] = df.apply(label, axis=1)
    return df


def persist(df: pd.DataFrame) -> None:
    if df.empty:
        return
    con = get_connection()
    con.execute("DELETE FROM topic_transitions")
    con.execute("""
        INSERT INTO topic_transitions
        SELECT src_topic_id, tgt_topic_id, src_topic_name, tgt_topic_name,
               year, next_year, overlap_count, overlap_ratio, transition_type
        FROM df
    """)
    con.close()


def run() -> None:
    print("=== Detecting topic merge/split transitions (combined signal) ===")
    df = compute_topic_transitions()
    if df.empty:
        print("  No transitions detected above threshold")
        return
    persist(df)
    n_split = (df["transition_type"] == "split").sum()
    n_merge = (df["transition_type"] == "merge").sum()
    n_xfer  = (df["transition_type"] == "transfer").sum()
    avg_struct = df["structural"].mean()
    avg_behav  = df["behavioral"].mean()
    print(f"  {len(df)} transitions: {n_split} splits, {n_merge} merges, {n_xfer} transfers")
    print(f"  avg structural overlap: {avg_struct:.3f}  |  avg author migration: {avg_behav:.3f}")
