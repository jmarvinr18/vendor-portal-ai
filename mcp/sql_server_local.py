"""MCP server exposing read-only PostgreSQL tools, for a containerized Postgres.

Differences from the RDS/IAM version:
  * password auth (env var or Secrets Manager) instead of short-lived IAM tokens,
    so a real connection pool pays off;
  * DSN assembled from PG* env vars or taken whole from DATABASE_URL;
  * startup retry, because the DB container is often still booting;
  * sslmode defaults to "prefer" (same host/network) instead of "require".

Env vars
--------
DATABASE_URL        full libpq URL; overrides the PG* vars below
PGHOST              default "postgres" (the compose service name)
PGPORT              default 5432
PGDATABASE          required unless DATABASE_URL is set
PGUSER              required unless DATABASE_URL is set
PGPASSWORD          password, if DB_SECRET_ARN is not set
DB_SECRET_ARN       Secrets Manager secret holding {"username","password",...}
PGSSLMODE           default "prefer"; use "require"/"verify-full" across networks
ALLOWED_SCHEMAS     comma-separated, default "public"
MAX_ROWS            hard row cap, default 200
STATEMENT_TIMEOUT_MS  default 5000
POOL_MIN/POOL_MAX   default 1 / 8
MCP_PORT            default 8000
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from dotenv import load_dotenv

load_dotenv()

import sqlparse
from fastmcp import FastMCP
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from fastmcp.utilities.http import find_available_port
port = find_available_port('127.0.0.1')

print(f"PORT: {port}")

log = logging.getLogger("pg_tools")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

ALLOWED_SCHEMAS = {s.strip() for s in os.getenv("ALLOWED_SCHEMAS", "public").split(",") if s.strip()}
MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
STATEMENT_TIMEOUT_MS = int(os.getenv("STATEMENT_TIMEOUT_MS", "5000"))

mcp = FastMCP("pg-tools")


# --------------------------------------------------------------------------- #
# connection
# --------------------------------------------------------------------------- #
def _password() -> str:
    """Password from Secrets Manager when DB_SECRET_ARN is set, else PGPASSWORD."""
    arn = os.getenv("DB_SECRET_ARN")
    if not arn:
        return os.environ["PGPASSWORD"]
    import boto3  # imported lazily so local runs need no AWS deps

    client = boto3.client("secretsmanager", region_name=os.environ["AWS_REGION"])
    secret = json.loads(client.get_secret_value(SecretId=arn)["SecretString"])
    return secret["password"]


def _conninfo() -> str:
    if url := os.getenv("DATABASE_URL"):
        return url
    return psycopg.conninfo.make_conninfo(
        host=os.getenv("PGHOST", "postgres"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=_password(),
        sslmode=os.getenv("PGSSLMODE", "prefer"),
        connect_timeout=5,
        application_name="agent-mcp",
    )


# Session-level guards: every connection in the pool is read-only and time-limited,
# so a tool that forgets to check something still cannot write or hang the DB.
SESSION_OPTIONS = (
    f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
    f"-c idle_in_transaction_session_timeout={STATEMENT_TIMEOUT_MS} "
    "-c default_transaction_read_only=on"
)

pool = ConnectionPool(
    conninfo=_conninfo(),
    kwargs={"row_factory": dict_row, "options": SESSION_OPTIONS},
    min_size=int(os.getenv("POOL_MIN", "1")),
    max_size=int(os.getenv("POOL_MAX", "8")),
    max_idle=300,
    open=False,  # opened in wait_for_db() below
    name="pg-tools",
)


def wait_for_db(attempts: int = 30, delay: float = 2.0) -> None:
    """Block until the database container accepts connections."""
    pool.open()
    for i in range(1, attempts + 1):
        try:
            with pool.connection(timeout=5) as conn:
                conn.execute("SELECT 1")
            log.info("database reachable")
            return
        except Exception as exc:  # noqa: BLE001 - startup probe
            log.warning("waiting for database (%s/%s): %s", i, attempts, exc)
            time.sleep(delay)
    raise RuntimeError("database not reachable")


# --------------------------------------------------------------------------- #
# SQL guard
# --------------------------------------------------------------------------- #
BANNED = {
    "insert", "update", "delete", "drop", "alter", "create", "grant", "revoke",
    "truncate", "copy", "call", "do", "vacuum", "analyze", "set", "reset",
    "merge", "listen", "notify", "lock", "prepare", "execute", "refresh",
}
BANNED_FUNCTIONS = ("pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_sleep", "dblink", "lo_import", "lo_export")


def assert_read_only(query: str) -> None:
    """Reject anything that is not a single SELECT/WITH statement.

    This is a cheap filter, not the security boundary: the read-only role and
    default_transaction_read_only are what actually stop writes.
    """
    statements = [s for s in sqlparse.parse(query) if str(s).strip(" ;\n\t")]
    if len(statements) != 1:
        raise ValueError("exactly one statement allowed")

    tokens = [t.value.lower() for t in statements[0].flatten() if not t.is_whitespace]
    keywords = {t.value.lower() for t in statements[0].flatten() if t.ttype in sqlparse.tokens.Keyword}
    words = [t for t in tokens if t not in {"(", ")"}]
    if not words or words[0] not in ("select", "with"):
        raise ValueError("only SELECT or WITH queries are allowed")
    if banned := BANNED & keywords:
        raise ValueError(f"disallowed keyword: {sorted(banned)[0]}")
    lowered = query.lower()
    for fn in BANNED_FUNCTIONS:
        if fn in lowered:
            raise ValueError(f"disallowed function: {fn}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (UUID, memoryview, bytes)):
        return str(value)
    return value


def _rows(cursor) -> list[dict]:
    return [{k: _jsonable(v) for k, v in row.items()} for row in cursor.fetchall()]


def _check_schema(schema: str) -> None:
    if schema not in ALLOWED_SCHEMAS:
        raise ValueError(f"schema not allowed: {schema} (allowed: {sorted(ALLOWED_SCHEMAS)})")


# --------------------------------------------------------------------------- #
# tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_tables(schema: str = "public") -> list[dict]:
    """List tables and views in a schema with row-count estimates.

    Call this before writing SQL so table names are never guessed.
    """
    _check_schema(schema)
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname AS table_name,
                   CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view'
                                  WHEN 'm' THEN 'materialized view' WHEN 'p' THEN 'partitioned table' END AS kind,
                   GREATEST(c.reltuples, 0)::bigint AS approx_rows
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = %s
               AND c.relkind IN ('r', 'v', 'm', 'p')
               AND has_table_privilege(c.oid, 'SELECT')
             ORDER BY 1
            """,
            (schema,),
        )
        return _rows(cur)


@mcp.tool()
def describe_table(table: str, schema: str = "public") -> dict:
    """Return the columns, types, nullability and primary key of one table."""
    _check_schema(schema)
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
              FROM information_schema.columns
             WHERE table_schema = %s AND table_name = %s
             ORDER BY ordinal_position
            """,
            (schema, table),
        )
        columns = _rows(cur)
        if not columns:
            raise ValueError(f"no such table (or no SELECT privilege): {schema}.{table}")

        cur.execute(
            """
            SELECT a.attname AS column_name
              FROM pg_index i
              JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
             WHERE i.indrelid = to_regclass(%s)::oid AND i.indisprimary
            """,
            (f"{schema}.{table}",),
        )
        primary_key = [r["column_name"] for r in _rows(cur)]

    return {"schema": schema, "table": table, "columns": columns, "primary_key": primary_key}


@mcp.tool()
def run_query(query: str, params: list | None = None, limit: int = 50) -> dict:
    """Run one read-only SELECT and return the rows.

    query:  a single SELECT or WITH statement. Use %s placeholders for values --
            never concatenate values into the SQL text.
    params: values for those placeholders, in order.
    limit:  maximum rows to return (capped server-side).

    Returns {"row_count", "truncated", "columns", "rows"}. Writes, multiple
    statements and non-SELECT statements are rejected.
    """
    assert_read_only(query)
    limit = max(1, min(int(limit), MAX_ROWS))
    wrapped = sql.SQL("SELECT * FROM ({}) AS agent_q LIMIT {}").format(
        sql.SQL(query), sql.Literal(limit)  # noqa: S608 - query is guard-checked and run read-only
    )
    started = time.perf_counter()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(wrapped, params or [])
        rows = _rows(cur)
        columns = [d.name for d in cur.description or []]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    log.info("run_query rows=%s ms=%s sql=%s", len(rows), elapsed_ms, " ".join(query.split())[:200])
    return {
        "row_count": len(rows),
        "truncated": len(rows) == limit,
        "elapsed_ms": elapsed_ms,
        "columns": columns,
        "rows": rows,
    }


@mcp.tool()
def health() -> dict:
    """Report database connectivity, server version and pool stats."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT version() AS version, current_database() AS database, current_user AS user")
        info = _rows(cur)[0]
    stats = pool.get_stats()
    info["pool"] = {k: stats.get(k) for k in ("pool_size", "pool_available", "requests_waiting")}
    return info


if __name__ == "__main__":
    wait_for_db()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)