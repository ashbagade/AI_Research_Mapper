"""Bulk-download OpenAlex work metadata using cursor pagination.

Streams results into DuckDB in batches. Supports checkpointing so
interrupted downloads can resume from the last cursor position.
"""

from __future__ import annotations
import json
import time
import httpx
from pathlib import Path
from tqdm import tqdm

import config
from etl.db import get_connection, init_schema
from etl.ingest import ingest_works_batch

CHECKPOINT_PATH = config.DATA_DIR / "cursor_checkpoint.json"


def _load_checkpoint() -> dict | None:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text())
    return None


def _save_checkpoint(cursor: str, total_fetched: int) -> None:
    CHECKPOINT_PATH.write_text(json.dumps({
        "cursor": cursor,
        "total_fetched": total_fetched,
    }))


def _clear_checkpoint() -> None:
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


def fetch_all_works(max_works: int | None = None) -> None:
    """Download works matching config.WORKS_FILTER into DuckDB.

    Args:
        max_works: Stop after this many works (None = fetch all).
    """
    con = get_connection()
    init_schema(con)

    checkpoint = _load_checkpoint()
    cursor = checkpoint["cursor"] if checkpoint else "*"
    total_fetched = checkpoint["total_fetched"] if checkpoint else 0

    params: dict[str, str | int] = {
        "filter": config.WORKS_FILTER,
        "select": config.WORKS_SELECT,
        "per_page": config.PER_PAGE,
        "cursor": cursor,
        "api_key": config.API_KEY,
    }

    pbar = tqdm(
        initial=total_fetched,
        desc="Downloading works",
        unit=" works",
    )

    with httpx.Client(timeout=120) as client:
        while True:
            try:
                resp = client.get(
                    f"{config.BASE_URL}/works", params=params
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = int(e.response.headers.get("retry-after", "5"))
                    print(f"\n  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                raise

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break

            ingest_works_batch(con, results)
            total_fetched += len(results)
            pbar.update(len(results))

            next_cursor = data.get("meta", {}).get("next_cursor")
            if not next_cursor:
                break

            _save_checkpoint(next_cursor, total_fetched)
            params["cursor"] = next_cursor

            if max_works and total_fetched >= max_works:
                print(f"\n  Reached max_works limit ({max_works})")
                break

    pbar.close()
    con.close()
    _clear_checkpoint()
    print(f"  Done. Total works ingested: {total_fetched}")


def run(max_works: int | None = None) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("=== Bulk-downloading work metadata from OpenAlex ===")
    print(f"  Filter: {config.WORKS_FILTER}")
    fetch_all_works(max_works=max_works)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-works", type=int, default=None,
        help="Stop after N works (for development). Omit for full download.",
    )
    args = parser.parse_args()
    run(max_works=args.max_works)
