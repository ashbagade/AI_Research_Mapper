"""Shared DuckDB connection and schema bootstrapping."""

import duckdb
from pathlib import Path
import config

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.DB_PATH), read_only=read_only)


def init_schema(con: duckdb.DuckDBPyConnection | None = None) -> None:
    close_after = con is None
    if con is None:
        con = get_connection()
    ddl = _SCHEMA_PATH.read_text()
    for statement in ddl.split(";"):
        stmt = statement.strip()
        if stmt:
            con.execute(stmt)
    if close_after:
        con.close()
