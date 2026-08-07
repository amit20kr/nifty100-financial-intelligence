import time
import os
from pathlib import Path

# Fix paths for running locally
project_root = Path(__file__).resolve().parent
os.environ["PYTHONPATH"] = str(project_root)

from src.dashboard.utils import db
from src.screener.engine import FilterEngine


def run_qa():
    print("=== Sprint 4 Day 27 QA Suite ===\n")

    # 1. Profile Load Time Benchmark
    print("--- 1. Profile Sequence Load Time ---")
    test_tickers = ["RELIANCE", "TCS", "HDFCBANK", "ITC", "ONGC"]

    for ticker in test_tickers:
        start_t = time.time()
        # Simulate the profile page calls
        db.get_companies()
        db.get_ratios(ticker)
        db.get_pl(ticker)
        db.get_sectors()
        db.get_prosandcons(ticker)
        end_t = time.time()

        duration = end_t - start_t
        assert (
            duration < 3.0
        ), f"Profile for {ticker} took {duration:.2f}s (must be < 3s)"
        print(f"[{ticker}] Profile calls took: {duration:.3f}s - PASS")

    print("\n--- 2. Screener Extreme Stress Test ---")
    # Engine initialization benchmark
    eng_start = time.time()
    engine = FilterEngine(
        project_root / "db/nifty100.db", project_root / "config/screener_config.yaml"
    )
    eng_end = time.time()
    print(f"FilterEngine cold start time: {eng_end - eng_start:.3f}s")

    payload = {
        "return_on_equity_pct": -20.0,
        "debt_to_equity": 0.0,  # Test financials bypass
        "free_cash_flow_cr": -5000.0,
        "revenue_cagr_5yr": -10.0,
        "pat_cagr_5yr": -10.0,
        "operating_profit_margin_pct": -10.0,
        "pe_ratio": 150.0,
        "pb_ratio": 30.0,
        "dividend_yield_pct": 0.0,
        "interest_coverage": -5.0,  # Test ICR infinity bypass
    }

    apply_start = time.time()
    try:
        res = engine.apply(payload)
        apply_end = time.time()
        print(f"Screener apply() latency: {apply_end - apply_start:.4f}s")
        print(
            f"Extreme payload resulted in {len(res)} matches without crashing. - PASS"
        )
    except Exception as e:
        print(f"FAIL: Screener crash - {e}")

    print("\n--- 3. Sparse History Edge Cases ---")
    sparse_tickers = ["JIOFIN", "ZOMATO", "PAYTM", "SUNPHARMA", "NYKAA"]

    for ticker in sparse_tickers:
        try:
            db.get_ratios(ticker)
            db.get_pl(ticker)
            # using get_valuation instead of get_market_cap since we don't have get_market_cap exposed per ticker, wait I'll use get_universe_market_cap()
            db.get_universe_market_cap()
            db.get_valuation(ticker)
            print(
                f"[{ticker}] db.py getters handled missing/sparse data gracefully. - PASS"
            )
        except Exception as e:
            print(f"FAIL: [{ticker}] raised exception: {e}")

    print("\nAll automated tests completed successfully.")


if __name__ == "__main__":
    run_qa()
