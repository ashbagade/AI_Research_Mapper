"""Evidence Panel — paper drilldown table that reacts to all other views."""

from __future__ import annotations
import pandas as pd


def filter_evidence(
    works_df: pd.DataFrame,
    work_topics_df: pd.DataFrame,
    authorships_df: pd.DataFrame,
    selected_topic_ids: list[str] | None = None,
    selected_author_ids: list[str] | None = None,
    year_range: tuple[int, int] | None = None,
    search_query: str = "",
    max_rows: int = 100,
) -> pd.DataFrame:
    """Filter and join works data for the evidence table.

    Returns a DataFrame with columns suitable for display:
    [work_id, title, year, citations, topics, authors].
    """
    if works_df.empty:
        return pd.DataFrame(columns=[
            "work_id", "title", "year", "citations", "topics", "authors"
        ])

    df = works_df.copy()

    if year_range:
        df = df[
            (df["publication_year"] >= year_range[0])
            & (df["publication_year"] <= year_range[1])
        ]

    if selected_topic_ids and not work_topics_df.empty:
        matching_wids = work_topics_df[
            work_topics_df["topic_id"].isin(selected_topic_ids)
        ]["work_id"].unique()
        df = df[df["work_id"].isin(matching_wids)]

    if selected_author_ids and not authorships_df.empty:
        matching_wids = authorships_df[
            authorships_df["author_id"].isin(selected_author_ids)
        ]["work_id"].unique()
        df = df[df["work_id"].isin(matching_wids)]

    if search_query:
        mask = df["title"].str.contains(search_query, case=False, na=False)
        df = df[mask]

    df = df.nlargest(max_rows, "cited_by_count")

    if not work_topics_df.empty:
        topics_agg = (
            work_topics_df[work_topics_df["work_id"].isin(df["work_id"])]
            .groupby("work_id")["topic_name"]
            .apply(lambda x: "; ".join(x.head(3)))
            .reset_index()
            .rename(columns={"topic_name": "topics"})
        )
        df = df.merge(topics_agg, on="work_id", how="left")
    else:
        df["topics"] = ""

    if not authorships_df.empty:
        authors_agg = (
            authorships_df[authorships_df["work_id"].isin(df["work_id"])]
            .groupby("work_id")["author_name"]
            .apply(lambda x: "; ".join(x.head(5)))
            .reset_index()
            .rename(columns={"author_name": "authors"})
        )
        df = df.merge(authors_agg, on="work_id", how="left")
    else:
        df["authors"] = ""

    result = df[["work_id", "title", "publication_year", "cited_by_count", "topics", "authors"]].copy()
    result.columns = ["work_id", "title", "year", "citations", "topics", "authors"]
    return result.sort_values("citations", ascending=False).reset_index(drop=True)
