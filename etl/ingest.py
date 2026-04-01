"""Parse OpenAlex work records and insert into DuckDB."""

from __future__ import annotations
import duckdb


def reconstruct_abstract(inverted_index: dict | None) -> str:
    """Rebuild plain text from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort(key=lambda p: p[0])
    return " ".join(w for _, w in positions)


def _extract_id(url: str) -> str:
    """'https://openalex.org/W123' -> 'W123'"""
    return url.rsplit("/", 1)[-1] if url else ""


def ingest_works_batch(
    con: duckdb.DuckDBPyConnection, works: list[dict]
) -> None:
    work_rows = []
    topic_rows = []
    author_rows = []
    cite_rows = []

    for w in works:
        wid = _extract_id(w.get("id", ""))
        if not wid:
            continue

        abstract = reconstruct_abstract(w.get("abstract_inverted_index"))
        topics = w.get("topics") or []
        primary_tid = _extract_id(topics[0]["id"]) if topics else None

        work_rows.append((
            wid,
            w.get("display_name", ""),
            w.get("publication_year"),
            w.get("cited_by_count", 0),
            abstract,
            primary_tid,
        ))

        for t in topics:
            sf = t.get("subfield") or {}
            topic_rows.append((
                wid,
                _extract_id(t["id"]),
                t.get("display_name", ""),
                t.get("score", 0.0),
                _extract_id(sf.get("id", "")),
            ))

        for a in w.get("authorships") or []:
            author = a.get("author") or {}
            insts = a.get("institutions") or []
            inst = insts[0] if insts else {}
            author_rows.append((
                wid,
                _extract_id(author.get("id", "")),
                author.get("display_name", ""),
                a.get("author_position", ""),
                _extract_id(inst.get("id", "")) if inst else "",
                inst.get("display_name", "") if inst else "",
            ))

        for ref in w.get("referenced_works") or []:
            cite_rows.append((wid, _extract_id(ref)))

    if work_rows:
        con.executemany(
            "INSERT OR IGNORE INTO works VALUES (?, ?, ?, ?, ?, ?)",
            work_rows,
        )
    if topic_rows:
        con.executemany(
            "INSERT INTO work_topics VALUES (?, ?, ?, ?, ?)", topic_rows
        )
    if author_rows:
        con.executemany(
            "INSERT INTO authorships VALUES (?, ?, ?, ?, ?, ?)", author_rows
        )
    if cite_rows:
        con.executemany(
            "INSERT INTO citations VALUES (?, ?)", cite_rows
        )
