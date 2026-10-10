from edgar_bitemporal.flatten import flatten_companyfacts


def test_one_row_per_reported_fact(payload):
    rows = list(flatten_companyfacts(payload, tags=None))
    assert len(rows) == 8                                   # 5 Assets reports + 3 NetIncomeLoss
    assert {r["tag"] for r in rows} == {"Assets", "NetIncomeLoss"}


def test_instant_facts_have_no_period_start(payload):
    rows = list(flatten_companyfacts(payload, tags=None))
    assets = [r for r in rows if r["tag"] == "Assets"]
    assert all(r["period_start"] is None for r in assets)
    income = [r for r in rows if r["tag"] == "NetIncomeLoss"]
    assert all(r["period_start"] == "2016-01-01" for r in income)


def test_tag_filter(payload):
    rows = list(flatten_companyfacts(payload, tags={"Assets"}))
    assert {r["tag"] for r in rows} == {"Assets"}


def test_fiscal_year_describes_the_filing_not_the_period(payload):
    """The 2016 net income, re-reported in the FY2018 10-K, is labelled fy=2018."""
    rows = [r for r in flatten_companyfacts(payload, tags=None) if r["tag"] == "NetIncomeLoss"]
    assert {r["period_end"] for r in rows} == {"2016-12-31"}
    assert {r["fiscal_year"] for r in rows} == {2016, 2017, 2018}
