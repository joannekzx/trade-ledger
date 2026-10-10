"""Flatten one SEC `companyfacts` JSON document into one row per reported fact.

Input shape (abridged):
    {"cik": 12927, "entityName": "...",
     "facts": {"us-gaap": {"Assets": {"units": {"USD": [
         {"start": "...", "end": "2017-12-31", "val": 92333000000,
          "accn": "0000012927-18-000007", "fy": 2017, "fp": "FY",
          "form": "10-K", "filed": "2018-02-12", "frame": "CY2017Q4I"}, ...]}}}}}

Every filing that mentions a period re-reports it, so the same (tag, period) appears many
times -- once per filing. That repetition is the transaction-time axis; we keep all of it.
"""
from typing import Iterable, Iterator

# A deliberately small, readable default. Revenue has several competing tags because
# companies changed concepts over time (see notebook 01), so more than one is listed.
CORE_TAGS = frozenset({
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "CostOfRevenue",
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "EarningsPerShareDiluted",
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "LongTermDebtNoncurrent",
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "ResearchAndDevelopmentExpense",
})

COLUMNS = (
    "cik", "taxonomy", "tag", "unit", "period_start", "period_end", "value",
    "accn", "form", "filed", "fiscal_year", "fiscal_period", "frame",
)


def flatten_companyfacts(
    payload: dict,
    tags: Iterable[str] | None = CORE_TAGS,
    taxonomies: Iterable[str] = ("us-gaap",),
) -> Iterator[dict]:
    """Yield one dict per reported fact. tags=None keeps every tag."""
    cik = int(payload["cik"])
    wanted = None if tags is None else set(tags)
    for taxonomy in taxonomies:
        for tag, body in payload.get("facts", {}).get(taxonomy, {}).items():
            if wanted is not None and tag not in wanted:
                continue
            for unit, items in body.get("units", {}).items():
                for it in items:
                    yield {
                        "cik": cik,
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "unit": unit,
                        "period_start": it.get("start"),   # absent for instant concepts
                        "period_end": it["end"],
                        "value": it["val"],
                        "accn": it["accn"],
                        "form": it["form"],
                        "filed": it["filed"],
                        "fiscal_year": it.get("fy"),
                        "fiscal_period": it.get("fp"),
                        "frame": it.get("frame"),
                    }
