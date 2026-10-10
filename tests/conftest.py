"""Test database setup.

The DB tests WIPE the database named by LEDGER_TEST_DSN, so its name must end in `_test`:

    export LEDGER_TEST_DSN="host=localhost dbname=ledger_test user=ledger password=ledger"

Without that variable the DB tests are skipped and only the pure-Python tests run.
The fixture file holds eight rows copied verbatim from Boeing's real SEC companyfacts:
a balance sheet restated once (ASC 606 adoption) and a net income restated once.
"""
import json
import os
import pathlib

import psycopg2
import pytest

from edgar_bitemporal.db import init_schema

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "boeing_real_rows.json"


@pytest.fixture(scope="session")
def payload() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture()
def conn():
    dsn = os.environ.get("LEDGER_TEST_DSN")
    if not dsn:
        pytest.skip("set LEDGER_TEST_DSN to run database tests")
    c = psycopg2.connect(dsn)
    with c.cursor() as cur:
        cur.execute("select current_database()")
        if not cur.fetchone()[0].endswith("_test"):
            pytest.fail("refusing to wipe a database whose name does not end in _test")
        cur.execute("drop schema public cascade; create schema public;")
    c.commit()
    init_schema(c)
    yield c
    c.close()
