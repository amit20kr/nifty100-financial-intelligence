"""
validate_urls.py
================
Standalone script to validate URLs in the documents dataset (DQ-13).
Uses ThreadPoolExecutor for concurrent validation, completely decoupled
from the core deterministic ETL pipeline.

Author  : Bluestock Data Analytics Team
Sprint  : 1 — Day 3
"""

import concurrent.futures
import logging
import sys
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger(__name__)

DOCS_PATH = Path("data/raw/documents.xlsx")
FAILURES_PATH = Path("output/url_validation_failures.csv")


def check_url(url: str) -> tuple[str, str, int]:
    """Check a single URL. Returns (url, status, status_code)."""
    if not isinstance(url, str) or not url.startswith("http"):
        return (str(url), "INVALID_FORMAT", 0)

    # Only allow BSE/NSE domains as per security best practices
    allowed_domains = ["bseindia.com", "nseindia.com"]
    if not any(d in url for d in allowed_domains):
        return (url, "DOMAIN_NOT_ALLOWED", 0)

    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        return (
            url,
            "OK" if response.status_code == 200 else "HTTP_ERROR",
            response.status_code,
        )
    except requests.exceptions.RequestException as e:
        return (url, f"EXCEPTION: {type(e).__name__}", 0)


def main():
    if not DOCS_PATH.exists():
        logger.error("Documents file not found at %s", DOCS_PATH)
        sys.exit(1)

    logger.info("Loading documents from %s", DOCS_PATH)
    df = pd.read_excel(DOCS_PATH, header=1, engine="openpyxl")

    if "Annual_Report" not in df.columns:
        logger.error("Column 'Annual_Report' missing.")
        sys.exit(1)

    urls = df["Annual_Report"].dropna().unique().tolist()
    logger.info("Validating %d unique URLs concurrently...", len(urls))

    failures = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(check_url, url): url for url in urls}

        for i, future in enumerate(concurrent.futures.as_completed(future_to_url), 1):
            url = future_to_url[future]
            try:
                _, status, code = future.result()
                if status != "OK":
                    failures.append({"url": url, "status": status, "code": code})
            except Exception:
                failures.append(
                    {"url": url, "status": "UNHANDLED_EXCEPTION", "code": 0}
                )

            if i % 100 == 0:
                logger.info("Processed %d/%d URLs...", i, len(urls))

    if failures:
        FAILURES_PATH.parent.mkdir(exist_ok=True, parents=True)
        pd.DataFrame(failures).to_csv(FAILURES_PATH, index=False)
        logger.warning(
            "Found %d URL failures. Logged to %s", len(failures), FAILURES_PATH
        )
    else:
        logger.info("All %d URLs are valid and reachable.", len(urls))


if __name__ == "__main__":
    main()
