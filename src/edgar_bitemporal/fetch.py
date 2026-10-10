"""Download SEC companyfacts JSON for a list of tickers into data/raw/.

The SEC requires a descriptive User-Agent with a contact address and asks for <= 10 requests/s.
Set it once:   export SEC_USER_AGENT="Your Name your.email@example.com"
"""
import argparse
import os
import pathlib
import sys
import time

import requests

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# A mix of steady reporters and companies with notable restatements.
DEFAULT_TICKERS = ["BA", "GE", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA",
                   "JPM", "GS", "XOM", "WMT", "JNJ", "KO", "INTC"]


def _session() -> requests.Session:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        sys.exit('Set SEC_USER_AGENT first, e.g.  export SEC_USER_AGENT="Your Name you@example.com"')
    s = requests.Session()
    s.headers["User-Agent"] = ua
    return s


def _get(s: requests.Session, url: str, tries: int = 4) -> requests.Response:
    for attempt in range(tries):
        r = s.get(url, timeout=60)
        if r.status_code == 200:
            return r
        time.sleep(2 ** attempt)           # back off on 429/5xx
    r.raise_for_status()
    return r


def resolve_ciks(s: requests.Session, tickers: list[str]) -> dict[str, int]:
    """Ticker -> CIK using the SEC's own mapping (current listings only)."""
    table = _get(s, TICKERS_URL).json()
    by_ticker = {row["ticker"].upper(): int(row["cik_str"]) for row in table.values()}
    missing = [t for t in tickers if t.upper() not in by_ticker]
    if missing:
        print(f"warning: no CIK found for {missing}", file=sys.stderr)
    return {t.upper(): by_ticker[t.upper()] for t in tickers if t.upper() in by_ticker}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("data/raw"))
    ap.add_argument("--refresh", action="store_true", help="re-download files that already exist")
    args = ap.parse_args()

    s = _session()
    args.out.mkdir(parents=True, exist_ok=True)
    for ticker, cik in resolve_ciks(s, args.tickers).items():
        dest = args.out / f"CIK{cik:010d}.json"
        if dest.exists() and not args.refresh:
            print(f"{ticker:<6} cached  {dest.name}")
            continue
        dest.write_bytes(_get(s, FACTS_URL.format(cik=cik)).content)
        print(f"{ticker:<6} fetched {dest.name}  ({dest.stat().st_size / 1e6:.1f} MB)")
        time.sleep(0.2)


if __name__ == "__main__":
    main()
