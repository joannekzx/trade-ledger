"""Behavioural tests for the database layer, run against real Boeing filings."""
import datetime as dt

import psycopg2
import pytest

from edgar_bitemporal.load import load_payload

ASSETS_PERIOD = dt.date(2017, 12, 31)
ORIGINAL, RESTATED = 92_333_000_000, 112_362_000_000     # filed 2018-02-12, then 2018-04-25


def _load(conn, payload):
    with conn.cursor() as cur:
        result = load_payload(cur, payload, tags=None)
    conn.commit()
    return result


def _asof_assets(conn, known: str):
    with conn.cursor() as cur:
        cur.execute(
            "select value from facts_as_of(%s) where tag = 'Assets' and period_end = %s",
            (known, ASSETS_PERIOD),
        )
        return [r[0] for r in cur.fetchall()]


def test_as_of_returns_what_was_known_at_the_time(conn, payload):
    _load(conn, payload)
    assert _asof_assets(conn, "2018-01-01") == []                  # not filed yet
    assert _asof_assets(conn, "2018-03-01") == [ORIGINAL]          # the 10-K's number
    assert _asof_assets(conn, "2018-05-01") == [RESTATED]          # after the first 10-Q restates it
    assert _asof_assets(conn, "2026-01-01") == [RESTATED]          # and it stays restated


def test_valid_time_filter_alone_leaks_the_future(conn, payload):
    """The bug bitemporality prevents: filtering only on period_end returns the *latest* value,
    which on 2018-03-01 was not yet public."""
    _load(conn, payload)
    with conn.cursor() as cur:
        cur.execute(
            """select value from fact where tag = 'Assets' and period_end = %s
               order by filed desc limit 1""", (ASSETS_PERIOD,))
        naive = cur.fetchone()[0]
    assert naive == RESTATED
    assert _asof_assets(conn, "2018-03-01") == [ORIGINAL] != [naive]


def test_revisions_view_lists_each_restatement_once(conn, payload):
    _load(conn, payload)
    with conn.cursor() as cur:
        cur.execute("select tag, prev_value, value from fact_revisions order by tag")
        got = cur.fetchall()
    assert got == [
        ("Assets", ORIGINAL, RESTATED),
        ("NetIncomeLoss", 4_895_000_000, 5_034_000_000),
    ]


def test_load_is_idempotent(conn, payload):
    assert _load(conn, payload) == (8, 0)
    assert _load(conn, payload) == (0, 8)                          # replay adds nothing
    with conn.cursor() as cur:
        cur.execute("select count(*) from fact")
        assert cur.fetchone()[0] == 8


@pytest.mark.parametrize("stmt", [
    "update fact set value = 0",
    "delete from fact",
    "truncate fact",
])
def test_fact_is_append_only(conn, payload, stmt):
    _load(conn, payload)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.RaiseException, match="append-only"):
            cur.execute(stmt)
    conn.rollback()


def test_quality_checks_run_clean_on_fixture(conn, payload):
    _load(conn, payload)
    from edgar_bitemporal.db import SQL_DIR
    with conn.cursor() as cur:
        cur.execute((SQL_DIR / "checks.sql").read_text())
        results = {name: n for name, n, _ in cur.fetchall()}
    assert set(results.values()) == {0}
    assert "filed_before_period_end" in results
