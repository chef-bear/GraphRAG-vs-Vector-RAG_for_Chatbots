
import os
import time
from io import StringIO
from datetime import datetime, timedelta

import requests
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

HEADERS = {
    "User-Agent": "Kevin Zhang kevinlzhang129@gmail.com"
}

DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

DB_URL = (
    f"postgresql+psycopg2://"
    f"{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

ALLOWED_FORMS = {"10-K", "10-Q"}

YEARS_BACK = 5

REQUEST_DELAY_SECONDS = 0.2


def get_sp500_tickers() -> list[str]:
    """
    Scrape the current S&P 500 ticker list from Wikipedia.
    """

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; sp500-fetcher/1.0)"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))

    sp500_table = tables[0]

    tickers = sp500_table["Symbol"].tolist()

    tickers = [
        ticker.replace(".", "-")
        for ticker in tickers
    ]

    return tickers


def get_ticker_to_cik_map() -> dict[str, str]:
    """
    Download SEC's ticker -> CIK mapping.
    """

    url = "https://www.sec.gov/files/company_tickers.json"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return {
        entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
        for entry in data.values()
    }

def get_company_filings(cik: str) -> dict:
    """
    Fetch a company's SEC filing history metadata.
    """

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.json()

def build_filing_url(
    cik: str,
    accession_number: str,
    primary_document: str
) -> str:
    """
    Construct the direct SEC EDGAR URL for a filing document.
    """

    cik_without_leading_zeros = str(int(cik))

    accession_without_dashes = accession_number.replace("-", "")

    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_without_leading_zeros}/"
        f"{accession_without_dashes}/"
        f"{primary_document}"
    )


def download_filing_html(url: str) -> str:
    """
    Download the raw HTML for a filing.
    """

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    return response.text


def html_to_text(html: str) -> str:
    """
    Convert SEC filing HTML to cleaned plain text.
    """

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    for tag in soup(
        [
            "script",
            "style",
            "noscript"
        ]
    ):
        tag.decompose()

    text_content = soup.get_text(
        separator=" ",
        strip=True
    )

    cleaned_text = " ".join(
        text_content.split()
    )

    return cleaned_text

def create_filings_table(engine):
    """
    Create the PostgreSQL table if it does not already exist.

    accession_number is UNIQUE so rerunning the scraper
    does not create duplicate filings.
    """

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS sp500_filings (
        id BIGSERIAL PRIMARY KEY,

        ticker TEXT NOT NULL,
        cik TEXT NOT NULL,
        company_name TEXT,

        form TEXT NOT NULL,
        filing_date DATE,
        report_date DATE,

        accession_number TEXT UNIQUE NOT NULL,
        primary_document TEXT,

        filing_url TEXT,
        filing_text TEXT,

        sic_description TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    with engine.begin() as connection:
        connection.execute(
            text(create_table_sql)
        )


def insert_filing(
    engine,
    filing: dict
):
    """
    Insert a filing into PostgreSQL.

    If accession_number already exists,
    skip the filing.
    """

    insert_sql = """
    INSERT INTO sp500_filings (
        ticker,
        cik,
        company_name,
        form,
        filing_date,
        report_date,
        accession_number,
        primary_document,
        filing_url,
        filing_text,
        sic_description
    )
    VALUES (
        :ticker,
        :cik,
        :company_name,
        :form,
        :filing_date,
        :report_date,
        :accession_number,
        :primary_document,
        :filing_url,
        :filing_text,
        :sic_description
    )
    ON CONFLICT (accession_number)
    DO NOTHING;
    """

    with engine.begin() as connection:
        connection.execute(
            text(insert_sql),
            filing
        )

def filing_exists(engine, accession_number: str) -> bool:
    query = """
    SELECT 1
    FROM sp500_filings
    WHERE accession_number = :accession_number
    LIMIT 1;
    """

    with engine.connect() as connection:
        result = connection.execute(
            text(query),
            {"accession_number": accession_number}
        ).first()

    return result is not None

def main():

    print(
        "Connecting to PostgreSQL..."
    )

    engine = create_engine(
        DB_URL
    )

    create_filings_table(
        engine
    )

    print(
        "Fetching S&P 500 ticker list..."
    )

    sp500_tickers = get_sp500_tickers()

    print(
        f"Found {len(sp500_tickers)} companies."
    )

    print(
        "Fetching SEC ticker -> CIK map..."
    )

    ticker_to_cik = get_ticker_to_cik_map()

    cutoff_date = (
        datetime.now()
        - timedelta(days=YEARS_BACK * 365)
    ).date()

    print(
        f"Downloading filings since {cutoff_date}"
    )

    csv_results = []

    total_filings_downloaded = 0

    for company_index, ticker in enumerate(
        sp500_tickers,
        start=1
    ):

        cik = ticker_to_cik.get(
            ticker.upper()
        )

        if not cik:

            print(
                f"[{company_index}/{len(sp500_tickers)}] "
                f"{ticker}: no CIK found"
            )

            continue

        try:

            company_data = get_company_filings(
                cik
            )

            recent = company_data[
                "filings"
            ][
                "recent"
            ]

            company_name = company_data.get(
                "name"
            )

            sic_description = company_data.get(
                "sicDescription"
            )

            company_filings_count = 0

            number_of_filings = len(
                recent["form"]
            )

            for filing_index in range(
                number_of_filings
            ):

                form = recent[
                    "form"
                ][filing_index]

                if form not in ALLOWED_FORMS:
                    continue

                filing_date_string = recent[
                    "filingDate"
                ][filing_index]

                filing_date = datetime.strptime(
                    filing_date_string,
                    "%Y-%m-%d"
                ).date()

                if filing_date < cutoff_date:
                    continue

                accession_number = recent[
                    "accessionNumber"
                ][filing_index]

                if filing_exists(engine, accession_number):
                    print(
                            f"{ticker} {form} {filing_date}: already downloaded, skipping"
                    )
                    continue
                
                primary_document = recent[
                    "primaryDocument"
                ][filing_index]

                report_date_string = recent[
                    "reportDate"
                ][filing_index]

                report_date = None

                if report_date_string:

                    try:

                        report_date = datetime.strptime(
                            report_date_string,
                            "%Y-%m-%d"
                        ).date()

                    except ValueError:

                        report_date = None

                filing_url = build_filing_url(
                    cik,
                    accession_number,
                    primary_document
                )

                try:

                    filing_html = download_filing_html(
                        filing_url
                    )

                    filing_text = html_to_text(
                        filing_html
                    )

                except Exception as filing_error:

                    print(
                        f"    ERROR downloading "
                        f"{ticker} {form} "
                        f"{filing_date}: "
                        f"{filing_error}"
                    )

                    continue

                filing_record = {

                    "ticker": ticker,

                    "cik": cik,

                    "company_name": company_name,

                    "form": form,

                    "filing_date": filing_date,

                    "report_date": report_date,

                    "accession_number":
                        accession_number,

                    "primary_document":
                        primary_document,

                    "filing_url":
                        filing_url,

                    "filing_text":
                        filing_text,

                    "sic_description":
                        sic_description,
                }

                insert_filing(
                    engine,
                    filing_record
                )

                csv_results.append(
                    {
                        "ticker": ticker,
                        "cik": cik,
                        "company_name": company_name,
                        "form": form,
                        "filing_date": filing_date,
                        "report_date": report_date,
                        "accession_number":
                            accession_number,
                        "primary_document":
                            primary_document,
                        "filing_url":
                            filing_url,
                        "sic_description":
                            sic_description,
                        "text_length":
                            len(filing_text),
                    }
                )

                company_filings_count += 1

                total_filings_downloaded += 1

                print(
                    f"    {ticker} "
                    f"{form} "
                    f"{filing_date} "
                    f"({len(filing_text):,} chars)"
                )

                time.sleep(
                    REQUEST_DELAY_SECONDS
                )

            print(
                f"[{company_index}/{len(sp500_tickers)}] "
                f"{ticker}: "
                f"{company_filings_count} filings"
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

        except Exception as error:

            print(
                f"[{company_index}/{len(sp500_tickers)}] "
                f"{ticker}: ERROR - {error}"
            )


    if csv_results:

        df = pd.DataFrame(
            csv_results
        )

        df.to_csv(
            "sp500_edgar_filings.csv",
            index=False
        )

    print()
    print(
        "Done."
    )
    print(
        f"Downloaded/processed "
        f"{total_filings_downloaded} filings."
    )
    print(
        "Saved filings to PostgreSQL table:"
    )
    print(
        "sp500_filings"
    )


if __name__ == "__main__":
    main()