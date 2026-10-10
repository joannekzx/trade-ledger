# Point-in-time SEC fundamentals: a bitemporal store

**Question:** on any past date D, what did the market *actually know* about a company's reported
numbers, given that companies restate them later?

A backtest that joins fundamentals on "period that had ended by D" silently uses numbers that
were not public on D, or were later revised. This project models SEC XBRL filings with two time
axes so that question is a SQL query, and measures how wrong the naive answer is on real filings.

**Stack:** Postgres · SQL · Python (pandas, psycopg2) · Jupyter · Docker
**Data:** SEC EDGAR `companyfacts` (public XBRL data). No synthetic data anywhere.

> Repo name is historical (`trade-ledger`). It started as a double-entry ledger on generated
> data and was rebuilt around real filings; the bitemporal core is the part worth keeping.

---

## Read it in this order

| Notebook | What it shows |
|---|---|
| [`01_what_is_in_the_data`](notebooks/01_what_is_in_the_data.ipynb) | Profile the raw JSON before modelling anything: repeated reports, restatements, what `fy` really means, tag drift, odd rows. Ends with the design decisions that follow. |
| [`02_bitemporal_model`](notebooks/02_bitemporal_model.ipynb) | The schema, one restatement end to end, `facts_as_of(date)`, and the guarantees (append-only, idempotent load) demonstrated rather than asserted. |
| [`03_restatements_and_leakage`](notebooks/03_restatements_and_leakage.ipynb) | Reporting lag, restatement rates, and how much look-ahead bias you get by ignoring transaction time. Plus the data-quality monitor. |

## What the data showed (Boeing, committed notebook outputs)

* **Restatements are real.** 112 of 1,250 company-periods (9.0%) carry more than one value across
  filings. Boeing's 2017 stockholders' equity was reported as $355M in the 10-K and as $1,656M in
  the next 10-Q.
* **`fy`/`fp` label the filing, not the period.** For annual figures in 10-Ks, `fy` equals the
  period's year in only about a third of rows (2,637 of 7,383), because each 10-K re-reports prior
  years under its own fiscal year. Selecting "the FY2016 number" by `fy` mixes vintages.
* **Not every revision is a restatement.** Ten `CostOfRevenue` revisions only flip the sign
  (same magnitude); they carry no new information and should be filtered before counting restatements.
* **A valid-time-only join leaks.** On several backtest dates the naive query returns an annual
  period whose 10-K had not been filed yet, or a value that was restated afterwards (notebook 03).
* **Reporting lag is tight but not zero.** Median 39 days from fiscal year-end to first filing.

These come from a single company's file. The notebooks are written for many; re-run them after
fetching more tickers (below) and the outputs, including the figures above, will change.

## Data model

```
company(cik, entity_name)

fact  -- one immutable row per REPORT of a fact
  cik, taxonomy, tag, unit
  period_start, period_end      -- valid time: the period the number describes
  filed                         -- transaction time: when it first became public
  value, accn, form, ...        -- accn = the filing that carried it
  unique (cik, taxonomy, tag, unit, period_start, period_end, accn)
```

* **Append-only, enforced by triggers.** `UPDATE`, `DELETE` and `TRUNCATE` raise. A correction is a
  new filing, never an edit.
* **Idempotent load.** The unique key plus `on conflict do nothing`: re-loading, or loading an
  overlapping download, only adds new filings.
* **`facts_as_of(date)`** returns, per period, the value from the latest filing on or before
  that date. Periods not yet filed on that date are absent.
* **`fact_revisions`** lists every change between consecutive filings of the same period.
* **`sql/checks.sql`** is a data-quality monitor: one row per check. These are monitored, not
  enforced, because real filings trip some of them for legitimate reasons.

## Run it

```bash
docker compose up -d                       # Postgres 16; applies sql/01 and sql/02 on first boot
pip install -e ".[notebooks,test]"

export SEC_USER_AGENT="Your Name you@example.com"   # the SEC requires a contact
python -m edgar_bitemporal.fetch                    # default tickers, or: --tickers BA GE AAPL
python -m edgar_bitemporal.load --raw data/raw      # add --all-tags for every us-gaap tag

jupyter lab notebooks/                              # notebooks read ../data/raw (override: EDGAR_RAW_DIR)
```

Tests run against a scratch database (it is wiped, so the name must end in `_test`):

```bash
export LEDGER_TEST_DSN="host=localhost dbname=ledger_test user=ledger password=ledger"
pytest
```

The test fixture is eight rows copied verbatim from Boeing's real filings (a balance sheet and a
net income figure, each restated once), so the tests assert on real restatements.

## Limitations

* **History starts with XBRL (2009).** Earlier periods appear only as comparatives in later
  filings, so for them `filed` is when the number first appears in the data, not the original
  publication date. Notebook 03 excludes them from lag and backtest numbers; notebook 01 section 7 measures them.
* **Date granularity.** `filed` is a date, not a timestamp. A filing made after the close counts
  as that day's information.
* **Survivorship.** Ticker to CIK uses the SEC's current listings, so delisted companies are absent.
* **Core tags only by default.** Revenue is spread across several tags over time (notebook 01
  section 5); stitching them into one series is left explicit rather than hidden in the loader.
