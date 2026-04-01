"""Fetch lightweight aggregate counts from OpenAlex group_by API.

This populates topic_year_stats with raw counts without downloading
individual work records -- extremely cheap and fast.
"""

from __future__ import annotations
import httpx
from tqdm import tqdm

import config
from etl.db import get_connection, init_schema


def _api_params(extra_filter: str = "", group_by: str = "topics.id") -> dict:
    base_filter = (
        f"topics.subfield.id:{config.AI_SUBFIELD_ID},"
        f"type:{config.WORK_TYPE}"
    )
    if extra_filter:
        base_filter += f",{extra_filter}"
    params: dict[str, str | int] = {
        "filter": base_filter,
        "group_by": group_by,
        "per_page": 200,
        "api_key": config.API_KEY,
    }
    return params


def fetch_topic_year_counts() -> list[dict]:
    """Get work counts per topic per year via group_by queries."""
    rows: list[dict] = []
    start, end = config.YEAR_RANGE

    with httpx.Client(timeout=60) as client:
        for year in tqdm(range(start, end + 1), desc="Fetching aggregates"):
            params = _api_params(
                extra_filter=f"publication_year:{year},cited_by_count:>{config.MIN_CITATIONS}",
                group_by="topics.id",
            )
            resp = client.get(f"{config.BASE_URL}/works", params=params)
            resp.raise_for_status()
            data = resp.json()

            for group in data.get("group_by", []):
                topic_url = group["key"]
                tid = topic_url.rsplit("/", 1)[-1] if "/" in topic_url else topic_url
                rows.append({
                    "topic_id": tid,
                    "topic_name": group.get("key_display_name", ""),
                    "year": year,
                    "work_count": group["count"],
                })

    return rows


def fetch_topic_citation_sums() -> dict[tuple[str, int], int]:
    """Get citation sums per topic-year via a second pass of group_by.

    OpenAlex group_by doesn't return citation sums directly, so we
    approximate via the total count and rely on detailed data for
    accurate sums once bulk ETL completes.
    """
    return {}


def store_raw_aggregates(rows: list[dict]) -> None:
    """Write raw aggregate counts into topic_year_stats."""
    con = get_connection()
    init_schema(con)

    con.execute("DELETE FROM topic_year_stats")

    for r in rows:
        con.execute(
            """INSERT INTO topic_year_stats
               (topic_id, topic_name, year, work_count,
                citation_sum, growth_rate, relative_share, momentum, is_emerging)
               VALUES (?, ?, ?, ?, 0, 0, 0, 0, false)
            """,
            [r["topic_id"], r["topic_name"], r["year"], r["work_count"]],
        )
    con.close()


def run() -> None:
    print("=== Fetching topic-year aggregates from OpenAlex ===")
    rows = fetch_topic_year_counts()
    print(f"  Retrieved {len(rows)} topic-year rows")
    store_raw_aggregates(rows)
    print("  Stored in DuckDB topic_year_stats")


if __name__ == "__main__":
    run()
