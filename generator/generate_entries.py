"""Generate synthetic balanced journal entries for the trade ledger.

Every emitted entry's postings sum to zero -- unbalanced data can only ever come from a bug,
never from here. Anomalies are injected on purpose so the ledger's guarantees have something
to prove: replayed events (idempotency), backdated valid_time (bitemporality), and corrections
(reversing entries).
"""
import argparse
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

# fixed chart of accounts; must match the seeds in schema.sql
ACCOUNTS = ["cash", "settlement", "equity_position", "counterparty_payable", "fees_expense", "revenue"]


def new_id():
    return "evt-" + uuid.uuid4().hex[:12]


def make_entry(now):
    """One balanced entry: move `amount` between two accounts, sometimes skimming a fee (3rd leg)."""
    src, dst = random.sample(ACCOUNTS, 2)
    amount = round(random.uniform(100, 10000), 2)
    valid = now - timedelta(minutes=random.randint(0, 600))
    postings = [
        {"account_id": src, "amount_signed": -amount},
        {"account_id": dst, "amount_signed": amount},
    ]
    # occasionally split a fee off so entries aren't all two legs; still nets to zero
    if random.random() < 0.2:
        fee = round(amount * 0.01, 2)
        postings[1]["amount_signed"] = round(amount - fee, 2)
        postings.append({"account_id": "fees_expense", "amount_signed": fee})
    return {
        "external_event_id": new_id(),
        "description": f"{src}->{dst}",
        "valid_time": valid.isoformat(),
        "recorded_at": now.isoformat(),
        "reverses_event_id": None,
        "postings": postings,
    }


def reverse_of(entry, now):
    """A correction: negate every posting of `entry`, recorded later than the original."""
    return {
        "external_event_id": new_id(),
        "description": "reversal of " + entry["external_event_id"],
        "valid_time": entry["valid_time"],
        "recorded_at": (now + timedelta(minutes=random.randint(1, 120))).isoformat(),
        "reverses_event_id": entry["external_event_id"],
        "postings": [
            {"account_id": p["account_id"], "amount_signed": -p["amount_signed"]}
            for p in entry["postings"]
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1000, help="base entries to generate")
    ap.add_argument("--replay-rate", type=float, default=0.05, help="idempotency: re-emit same event")
    ap.add_argument("--backdate-rate", type=float, default=0.08, help="bitemporal: valid_time days ago")
    ap.add_argument("--reversal-rate", type=float, default=0.05, help="corrections via reversing entries")
    ap.add_argument("--output-dir", default=os.environ.get("LANDING_DIR", "landing"))
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    records = []
    for _ in range(args.count):
        e = make_entry(now)
        # backdate: the movement really happened days ago, only recorded now
        if random.random() < args.backdate_rate:
            days = random.randint(1, 10)
            e["valid_time"] = (now - timedelta(days=days, minutes=random.randint(0, 600))).isoformat()
        records.append(e)
        # replay the same event -> the loader must treat it as a no-op
        if random.random() < args.replay_rate:
            records.append(dict(e))
        # correct a prior entry with a reversal recorded later
        if random.random() < args.reversal_rate:
            records.append(reverse_of(e, now))

    os.makedirs(args.output_dir, exist_ok=True)
    path = os.path.join(args.output_dir, "entries_" + now.strftime("%Y%m%d%H%M%S") + ".json")
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(records)} records ({args.count} base + {len(records) - args.count} injected) to {path}")


if __name__ == "__main__":
    main()
