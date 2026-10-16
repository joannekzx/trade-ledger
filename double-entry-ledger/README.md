# Trade Ledger (bitemporal, double-entry)

An append-only ledger in Postgres. **Balances are never stored.** They are calculated by adding up
immutable postings, as of any point in time. The database itself refuses to hold money that does not
balance and refuses to let history be rewritten.

**Stack:** Postgres, SQL (constraints, triggers, functions), Python, Docker. Data is synthetic.

## Three ideas

1. **Double-entry, enforced by the database.** Every event is a *journal entry* with 2+ *postings* that
   must add up to zero (+ debit, - credit). A deferrable constraint trigger checks this at commit and
   rejects any entry that does not balance.
2. **Append-only.** `before update or delete` triggers block any change to entries and postings. A mistake
   is fixed by posting a **reversing entry**, so the history is kept.
3. **Bitemporal.** Two timestamps on every entry: `valid_time` (when the money movement is effective) and
   `recorded_at` (when we wrote it down). `balance_as_of(account, valid, known)` answers "what was the
   balance on June 30, *as we knew it on July 5*?"

Loading is **idempotent**: `external_event_id` is unique and the loader uses `on conflict do nothing`, so
replaying an event is a no-op.

## Files

| File | What it is |
|---|---|
| `schema.sql` | Tables, the balance trigger, the append-only triggers, a small chart of accounts |
| `queries.sql` | `balance_as_of()`, `current_balances`, `account_statement` |
| `tests.sql` | Four checks that should all report 0 violations: unbalanced entries, ledger total, duplicate event ids, orphan postings |
| `generator/generate_entries.py` | Makes balanced entries and injects replays (5%), back-dated entries (8%) and reversals (5%) |
| `load.py` | Idempotent loader. Commits once at the end, which is when the balance check runs |

## Run it

```bash
docker compose up -d                                 # Postgres, schema loaded on first start
pip install -r requirements.txt
python generator/generate_entries.py --count 1000
python load.py
psql "host=localhost dbname=ledger user=ledger password=ledger" -f queries.sql
psql "host=localhost dbname=ledger user=ledger password=ledger" -f tests.sql   # every row: 0
```

This uses port 5432, same as the SEC project one folder up. Run only one at a time.
