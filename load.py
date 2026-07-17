"""Idempotent loader: JSON-lines of journal entries -> Postgres.

Idempotency lives in the DB, not here: `on conflict (external_event_id) do nothing`. If an
event was already loaded we skip it and its postings entirely, so replays cost nothing and can
never double-post. The whole load commits once at the end -- that's when the deferred
double-entry check runs, so an unbalanced entry aborts the load rather than landing half-written.
"""
import argparse
import glob
import json
import os

import psycopg2

DSN = os.environ.get(
    "LEDGER_DSN", "host=localhost port=5432 dbname=ledger user=ledger password=ledger"
)


def load_file(cur, path):
    loaded = skipped = 0
    with open(path) as f:
        for line in f:
            e = json.loads(line)
            cur.execute(
                """insert into journal_entry
                       (external_event_id, description, valid_time, recorded_at, reverses_event_id)
                   values (%s, %s, %s, %s, %s)
                   on conflict (external_event_id) do nothing
                   returning entry_id""",
                (e["external_event_id"], e["description"], e["valid_time"],
                 e["recorded_at"], e["reverses_event_id"]),
            )
            row = cur.fetchone()
            if row is None:      # already seen this event -> idempotent skip
                skipped += 1
                continue
            entry_id = row[0]
            for p in e["postings"]:
                cur.execute(
                    "insert into posting (entry_id, account_id, amount_signed) values (%s, %s, %s)",
                    (entry_id, p["account_id"], p["amount_signed"]),
                )
            loaded += 1
    return loaded, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", default=os.environ.get("LANDING_DIR", "landing"))
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    total_l = total_s = 0
    with conn.cursor() as cur:
        for path in sorted(glob.glob(os.path.join(args.input_dir, "*.json"))):
            l, s = load_file(cur, path)
            total_l += l
            total_s += s
            print(f"{os.path.basename(path)}: loaded {l}, skipped {s} (already seen)")
    conn.commit()   # deferred double-entry check fires here
    conn.close()
    print(f"Done. loaded {total_l}, skipped {total_s}.")


if __name__ == "__main__":
    main()
