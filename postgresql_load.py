"""
Fetch recent SEC EDGAR filings for every company in the S&P 500
and store the results in a PostgreSQL database.

Requires: requests, pandas, sqlalchemy, psycopg2-binary
    pip install requests pandas sqlalchemy psycopg2-binary
"""

import time
import requests
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()


# IMPORTANT: replace with your real name/email - SEC blocks generic User-Agents
HEADERS = {
    "User-Agent": "kevinlzhang129@gmail.com"
}

# Update these to match your local PostgreSQL setup
DB_USER = "kevin"
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "chatbot_db"

DB_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def get_sp500_tickers() -> list[str]:
    """Scrape the current S&P 500 ticker list from Wikipedia."""
    from io import StringIO

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    wiki_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; sp500-fetcher/1.0)"
    }
    response = requests.get(url, headers=wiki_headers)
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    sp500_table = tables[0]
    tickers = sp500_table["Symbol"].tolist()
    tickers = [t.replace(".", "-") for t in tickers]
    return tickers


def get_ticker_to_cik_map() -> dict[str, str]:
    """Download SEC's full ticker -> CIK mapping."""
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()

    return {
        entry["ticker"]: str(entry["cik_str"]).zfill(10)
        for entry in data.values()
    }


def get_company_filings(cik: str) -> dict:
    """Fetch a company's filing history from EDGAR."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def main():
    print("Fetching S&P 500 ticker list...")
    sp500_tickers = get_sp500_tickers()
    print(f"Found {len(sp500_tickers)} tickers.")

    print("Fetching SEC ticker -> CIK map...")
    ticker_to_cik = get_ticker_to_cik_map()

    results = []

    for i, ticker in enumerate(sp500_tickers, start=1):
        cik = ticker_to_cik.get(ticker)
        if not cik:
            print(f"[{i}/{len(sp500_tickers)}] {ticker}: no CIK found, skipping")
            continue

        try:
            company_data = get_company_filings(cik)
            recent = company_data["filings"]["recent"]

            results.append({
                "ticker": ticker,
                "cik": cik,
                "name": company_data.get("name"),
                "latest_form": recent["form"][0] if recent["form"] else None,
                "latest_filing_date": recent["filingDate"][0] if recent["filingDate"] else None,
                "sic_description": company_data.get("sicDescription"),
            })
            print(f"[{i}/{len(sp500_tickers)}] {ticker}: OK")

        except Exception as e:
            print(f"[{i}/{len(sp500_tickers)}] {ticker}: ERROR - {e}")

        # SEC rate limit is 10 requests/second - this keeps us well under that
        time.sleep(0.15)

    df = pd.DataFrame(results)

    # Also keep a CSV as a local backup/inspection copy
    df.to_csv("sp500_edgar_filings.csv", index=False)

    # Write to PostgreSQL
    engine = create_engine(DB_URL)
    df.to_sql(
        "sp500_filings",
        engine,
        if_exists="replace",  # use "append" instead if you want to keep history across runs
        index=False,
    )

    print(f"\nDone. Saved {len(df)} rows to sp500_edgar_filings.csv and the 'sp500_filings' table in PostgreSQL.")


if __name__ == "__main__":
    main()