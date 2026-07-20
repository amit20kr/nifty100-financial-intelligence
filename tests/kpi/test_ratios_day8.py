import logging
from src.analytics.ratios import (
    net_profit_margin,
    operating_profit_margin,
    return_on_equity,
    return_on_capital_employed,
    return_on_assets,
)


def test_npm_normal():
    # TCS-like normal: 46099 / 240893 × 100 ≈ 19.14
    val = net_profit_margin(net_profit=46099.0, sales=240893.0)
    assert val is not None
    assert round(val, 2) == 19.14


def test_npm_sales_zero():
    val = net_profit_margin(net_profit=100.0, sales=0)
    assert val is None


def test_opm_normal_no_log():
    # Normal + cross-check diff = 0.31% < 1% tolerance
    val = operating_profit_margin(
        operating_profit=64296.0, sales=240893.0, opm_pct_source=27.0
    )
    assert val is not None
    assert round(val, 2) == 26.69


def test_opm_mismatch_log(caplog):
    # opm_pct_source=35.0 (diff > 1%) -> returns computed value AND logs mismatch
    caplog.set_level(logging.INFO, logger="ratio_edge_cases")

    val = operating_profit_margin(
        operating_profit=64296.0,
        sales=240893.0,
        opm_pct_source=35.0,
        company_id="TCS",
        year="2024-03",
    )
    assert val is not None
    assert round(val, 2) == 26.69

    assert "OPM Mismatch" in caplog.text
    assert "35.00%" in caplog.text
    assert "TCS" in caplog.text


def test_roe_normal():
    # Normal: 46099 / (362 + 90127) × 100 ≈ 50.94
    val = return_on_equity(net_profit=46099.0, equity_capital=362.0, reserves=90127.0)
    assert val is not None
    assert round(val, 2) == 50.94


def test_roe_denom_zero_or_nan():
    # equity_capital=None -> None
    val1 = return_on_equity(net_profit=100.0, equity_capital=None, reserves=-500.0)
    assert val1 is None

    # Denom <= 0 -> None
    val2 = return_on_equity(net_profit=100.0, equity_capital=100.0, reserves=-200.0)
    assert val2 is None


def test_roce_normal():
    # Normal non-Financials: EBIT=62775, denom=98510 → ≈ 63.72%
    # Uses NamedTuple attribute access (retrofitted from dict in Day 08)
    res = return_on_capital_employed(
        profit_before_tax=61997.0,
        interest=778.0,
        equity_capital=362.0,
        reserves=90127.0,
        borrowings=8021.0,
        broad_sector="Technology",
    )
    assert res.sector_category == "Non-Financials"
    assert res.value is not None
    assert round(res.value, 2) == 63.72


def test_roa_assets_zero():
    val = return_on_assets(net_profit=100.0, total_assets=0)
    assert val is None
