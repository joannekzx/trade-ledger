"""Connection helpers shared by the loader, the tests and the notebooks."""
import argparse
import os
import pathlib

import pandas as pd
import psycopg2

SQL_DIR = pathlib.Path(__file__).resolve().parents[2] / "sql"


def dsn() -> str:
    return os.environ.get(
        "LEDGER_DSN", "host=localhost port=5432 dbname=ledger user=ledger password=ledger"
    )


def connect():
    return psycopg2.connect(dsn())


def q(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a query and return a DataFrame. Use %(name)s placeholders for parameters."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()


def init_schema(conn) -> None:
    """Apply sql/01_schema.sql and sql/02_asof.sql (docker-compose does this on first boot)."""
    with conn.cursor() as cur:
        for name in ("01_schema.sql", "02_asof.sql"):
            cur.execute((SQL_DIR / name).read_text())
    conn.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Create the schema in the database named by LEDGER_DSN.")
    ap.add_argument("command", choices=["init"])
    ap.parse_args()
    c = connect()
    init_schema(c)
    c.close()
    print("schema applied")
