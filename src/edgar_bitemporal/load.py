"""Idempotent load of companyfacts JSON into Postgres.

Idempotency lives in the database: the unique key on `fact` plus `on conflict do nothing`.
Re-running a load, or loading a newer download that overlaps an older one, only adds the
filings that are genuinely new.
"""
import argparse
import csv
import io
import json
import pathlib

from .db import connect, init_schema
from .flatten import COLUMNS, CORE_TAGS, flatten_companyfacts

_COLS = ", ".join(COLUMNS)

_STAGE_DDL = """
create temp table if not exists stage (
    cik bigint, taxonomy text, tag text, unit text, period_start date, period_end date,
    value numeric, accn text, form text, filed date,
    fiscal_year int, fiscal_period text, frame text
) on commit delete rows
"""


def load_payload(cur, payload: dict, tags=CORE_TAGS, taxonomies=("us-gaap",)) -> tuple[int, int]:
    """Load one company's document. Returns (inserted, skipped_as_already_present)."""
    rows = [tuple(r[c] for c in COLUMNS) for r in flatten_companyfacts(payload, tags, taxonomies)]
    cur.execute(
        """insert into company (cik, entity_name) values (%s, %s)
           on conflict (cik) do update set entity_name = excluded.entity_name""",
        (int(payload["cik"]), payload["entityName"]),
    )
    if not rows:
        return 0, 0

    buf = io.StringIO()
    csv.writer(buf).writerows(rows)          # None -> empty field -> NULL below
    buf.seek(0)
    cur.execute(_STAGE_DDL)
    cur.execute("truncate stage")
    cur.copy_expert(f"copy stage ({_COLS}) from stdin with (format csv, null '')", buf)
    cur.execute(
        f"""insert into fact ({_COLS}) select {_COLS} from stage
            on conflict on constraint fact_natural_key do nothing"""
    )
    inserted = cur.rowcount
    return inserted, len(rows) - inserted


def load_dir(raw_dir: pathlib.Path, tags=CORE_TAGS) -> None:
    conn = connect()
    try:
        init_if_missing(conn)
        total_in = total_skip = 0
        for path in sorted(raw_dir.glob("CIK*.json")):
            payload = json.loads(path.read_text())
            with conn.cursor() as cur:
                ins, skip = load_payload(cur, payload, tags)
            conn.commit()
            total_in += ins
            total_skip += skip
            print(f"{payload['entityName']:<40} inserted {ins:>7,}  already present {skip:>7,}")
        print(f"done: inserted {total_in:,}, skipped {total_skip:,}")
    finally:
        conn.close()


def init_if_missing(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("select to_regclass('public.fact')")
        exists = cur.fetchone()[0] is not None
    if not exists:
        init_schema(conn)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", default="data/raw", type=pathlib.Path, help="folder of CIK*.json files")
    ap.add_argument("--all-tags", action="store_true", help="load every us-gaap tag, not just the core set")
    args = ap.parse_args()
    load_dir(args.raw, tags=None if args.all_tags else CORE_TAGS)
