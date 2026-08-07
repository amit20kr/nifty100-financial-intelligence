import pandas as pd
from src.nlp.pros_cons_generator import (
    _extract_year,
    _is_contiguous_streak,
    _confidence,
    pro_rule_01,
    pro_rule_02,
    pro_rule_08,
    con_rule_11,
    con_rule_01,
)


def test_extract_year():
    assert _extract_year("2023-03") == 2023
    assert _extract_year("2024-12") == 2024
    assert _extract_year("TTM") == 0
    assert _extract_year(None) == 0


def test_is_contiguous_streak():
    assert _is_contiguous_streak([2021, 2022, 2023], 3) is True
    assert _is_contiguous_streak([2020, 2022, 2023], 3) is False
    assert _is_contiguous_streak([2023, 2024], 3) is False
    assert _is_contiguous_streak([2019, 2020, 2021, 2022, 2023], 5) is True
    assert _is_contiguous_streak([2018, 2020, 2021, 2022, 2023], 5) is False


def test_confidence_boundary():
    # Boundary exact trigger
    # ROE = 20.0, threshold = 20.0
    score = _confidence(20.0, 20.0, "magnitude")
    assert abs(score - 60.0) < 0.01


def test_pro_rule_01():
    # ROE sustained 3 years
    df = pd.DataFrame(
        {"year": [2021, 2022, 2023], "return_on_equity_pct": [21.0, 22.0, 25.0]}
    )
    res = pro_rule_01(df, "TEST")
    assert len(res) == 1
    assert res[0]["confidence_pct"] >= 60.0

    # Non contiguous
    df2 = pd.DataFrame(
        {"year": [2020, 2022, 2023], "return_on_equity_pct": [21.0, 22.0, 25.0]}
    )
    assert len(pro_rule_01(df2, "TEST")) == 0

    # Boundary exact
    df3 = pd.DataFrame(
        {"year": [2021, 2022, 2023], "return_on_equity_pct": [25.0, 22.0, 20.0]}
    )
    res3 = pro_rule_01(df3, "TEST")
    assert len(res3) == 1
    assert abs(res3[0]["confidence_pct"] - 60.0) < 0.01


def test_pro_rule_08_mismatched_years():
    # Div Yield + FCF mismatch
    df_fr = pd.DataFrame({"year": [2022], "free_cash_flow_cr": [100.0]})
    df_mc = pd.DataFrame({"year": [2023], "dividend_yield_pct": [3.0]})
    # Different years, should discard
    assert len(pro_rule_08(df_fr, df_mc, "TEST")) == 0

    # Match years
    df_fr2 = pd.DataFrame({"year": [2023], "free_cash_flow_cr": [100.0]})
    assert len(pro_rule_08(df_fr2, df_mc, "TEST")) == 1


def test_con_rule_11_net_cash():
    # Net debt < 0 (net cash) should cleanly skip
    df_fr = pd.DataFrame({"year": [2023], "net_debt_cr": [-500.0]})
    df_pl = pd.DataFrame(
        {"year": [2023], "operating_profit": [100.0], "depreciation": [50.0]}
    )
    assert len(con_rule_11(df_fr, df_pl, "TEST")) == 0


def test_con_rule_01_financials():
    df = pd.DataFrame({"debt_to_equity": [5.0]})
    # Should skip
    assert len(con_rule_01(df, "Financials", "TEST")) == 0
    # Should flag
    assert len(con_rule_01(df, "IT", "TEST")) == 1


def test_jiofin_graceful_skip():
    # 5 yr streak rule with 3 yrs data
    df = pd.DataFrame(
        {"year": [2021, 2022, 2023], "free_cash_flow_cr": [100.0, 200.0, 300.0]}
    )
    assert len(pro_rule_02(df, "TEST")) == 0
