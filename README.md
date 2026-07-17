# Trade Ledger (bitemporal, double-entry)

An append-only accounting ledger where **balances are never stored** — they're reconstructed by
replaying immutable postings *as of any point in time*. Built to make the data-modeling decisions
the headline: double-entry integrity, immutability, and bitemporality.

The throughline across my projects is *data integrity* — this one puts it in the schema itself:
the database refuses to hold money that doesn't balance, and refuses to let history be rewritten.

**Stack:** Postgres · SQL (constraints, triggers, bitemporal functions) · Python (synthetic data + loader) · Docker

---

## The three data-design ideas

1. **Double-entry, enforced by the DB.** Every event is a *journal entry* of ≥2 *postings* that
   sum to zero. A deferred constraint trigger rejects any entry that doesn't balance — money can't
   be created or destroyed by a bug or a bad load.
2. **Append-only.** Journal entries and postings are never updated or deleted (a trigger blocks
   it). A mistake is fixed by posting a **reversing entry**, so the full history survives.
3. **Bitemporal.** Two time axes — *valid time* (when it's effective) and *transaction time* (when
   we recorded it) — let you ask *"what did we believe the balance was on June 30, as known on
   July 5?"* That's the question that separates a ledger from a running total.

---

## Quick start

```bash
docker compose up -d                              # Postgres + schema + seeded accounts
pip install -r requirements.txt
python generator/generate_entries.py --count 1000 # synthetic balanced entries -> landing/
python load.py                                    # idempotent load into Postgres

# inspect
psql "host=localhost dbname=ledger user=ledger password=ledger" -f queries.sql   # define views/functions
psql "host=localhost dbname=ledger user=ledger password=ledger" -f tests.sql     # all checks -> 0 violations
```
