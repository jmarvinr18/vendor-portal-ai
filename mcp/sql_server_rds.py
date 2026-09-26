# pg_tools.py
import json, os
import boto3
# import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()
mcp = FastMCP("pg-tools")

HOST, PORT = os.environ["PGHOST"], int(os.getenv("PGPORT", "5432"))
DB, USER = os.environ["PGDATABASE"], os.environ["PGUSER"]
REGION = os.environ["AWS_REGION"]
MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
ALLOWED_SCHEMAS = set(os.getenv("ALLOWED_SCHEMAS", "public").split(","))

_rds = boto3.client("rds", region_name=REGION)


def _password() -> str:
    # IAM auth: 15-minute token, fetched per connection
    return _rds.generate_db_auth_token(DBHostname=HOST, Port=PORT, DBUsername=USER, Region=REGION)


pool = ConnectionPool(
    conninfo=f"host={HOST} port={PORT} dbname={DB} user={USER} sslmode=require",
    kwargs={"row_factory": dict_row, "options": "-c statement_timeout=5000 -c default_transaction_read_only=on"},
    min_size=0, max_size=4, open=True,
    configure=lambda conn: conn.execute("SET application_name = 'agent-mcp'"),
    connection_class=psycopg.Connection,
)


def _connect():
    # password callback keeps the IAM token fresh
    return psycopg.connect(
        host=HOST, port=PORT, dbname=DB, user=USER, password=_password(), sslmode="require",
        row_factory=dict_row, options="-c statement_timeout=5000 -c default_transaction_read_only=on",
    )


@mcp.tool()
def list_tables(schema: str = "public") -> list[dict]:
    """List tables and their row-count estimates in a schema. Use before writing SQL."""
    if schema not in ALLOWED_SCHEMAS:
        raise ValueError(f"schema not allowed: {schema}")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT c.relname AS table, c.reltuples::bigint AS approx_rows
                 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relkind IN ('r','v','m')
                ORDER BY 1""",
            (schema,),
        )
        return cur.fetchall()


@mcp.tool()
def describe_table(table: str, schema: str = "public") -> list[dict]:
    """Return column names, types and nullability for one table."""
    if schema not in ALLOWED_SCHEMAS:
        raise ValueError(f"schema not allowed: {schema}")
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT column_name, data_type, is_nullable, column_default
                 FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position""",
            (schema, table),
        )
        rows = cur.fetchall()
    if not rows:
        raise ValueError(f"no such table: {schema}.{table}")
    return rows


@mcp.tool()
def run_query(query: str, params: list | None = None, limit: int = 50) -> dict:
    """Run one read-only SELECT and return rows.

    query: a single SELECT/WITH statement; use %s placeholders for values, never string concatenation.
    params: values for the placeholders, in order.
    limit: max rows to return (hard cap 200).
    """
    assert_read_only(query)                      # see the next section
    limit = max(1, min(limit, MAX_ROWS))
    wrapped = sql.SQL("SELECT * FROM ({}) AS agent_q LIMIT {}").format(
        sql.SQL(query), sql.Literal(limit)
    )
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(wrapped, params or [])
        rows = cur.fetchall()
    return {"row_count": len(rows), "truncated": len(rows) == limit, "rows": rows}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")