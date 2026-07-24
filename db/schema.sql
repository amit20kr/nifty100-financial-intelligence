-- schema.sql
-- Relational schema for Nifty 100 Database
-- Sprint 1, Day 4

-- Note: PRAGMA foreign_keys = OFF should be executed in python before this script runs, 
-- and then PRAGMA foreign_keys = ON afterwards, to allow DROP TABLE in any order.

DROP TABLE IF EXISTS peer_groups;
DROP TABLE IF EXISTS financial_ratios;
DROP TABLE IF EXISTS stock_prices;
DROP TABLE IF EXISTS market_cap;
DROP TABLE IF EXISTS sectors;
DROP TABLE IF EXISTS prosandcons;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS analysis;
DROP TABLE IF EXISTS cashflow;
DROP TABLE IF EXISTS balancesheet;
DROP TABLE IF EXISTS profitandloss;
DROP TABLE IF EXISTS companies;

-- 1. companies (Parent Table)
CREATE TABLE companies (
    id TEXT PRIMARY KEY,
    company_logo TEXT,
    company_name TEXT,
    chart_link TEXT,
    about_company TEXT,
    website TEXT,
    nse_profile TEXT,
    bse_profile TEXT,
    face_value REAL,
    book_value REAL,
    roce_percentage REAL,
    roe_percentage REAL
);

-- 2. profitandloss
CREATE TABLE profitandloss (
    id TEXT,
    company_id TEXT,
    year TEXT,
    sales REAL,
    expenses REAL,
    operating_profit REAL,
    opm_percentage REAL,
    other_income REAL,
    interest REAL,
    depreciation REAL,
    profit_before_tax REAL,
    tax_percentage REAL,
    net_profit REAL,
    eps REAL,
    dividend_payout REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 3. balancesheet
CREATE TABLE balancesheet (
    id TEXT,
    company_id TEXT,
    year TEXT,
    equity_capital REAL,
    reserves REAL,
    borrowings REAL,
    other_liabilities REAL,
    total_liabilities REAL,
    fixed_assets REAL,
    cwip REAL,
    investments REAL,
    other_asset REAL,
    total_assets REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 4. cashflow
CREATE TABLE cashflow (
    id TEXT,
    company_id TEXT,
    year TEXT,
    operating_activity REAL,
    investing_activity REAL,
    financing_activity REAL,
    net_cash_flow REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 5. analysis
CREATE TABLE analysis (
    id TEXT,
    company_id TEXT PRIMARY KEY,
    compounded_sales_growth TEXT,
    compounded_profit_growth TEXT,
    stock_price_cagr TEXT,
    roe TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 6. documents
CREATE TABLE documents (
    id TEXT,
    company_id TEXT,
    year TEXT,
    Annual_Report TEXT,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 7. prosandcons
CREATE TABLE prosandcons (
    id TEXT PRIMARY KEY,
    company_id TEXT,
    pros TEXT,
    cons TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 8. sectors
CREATE TABLE sectors (
    id TEXT,
    company_id TEXT PRIMARY KEY,
    broad_sector TEXT,
    sub_sector TEXT,
    index_weight_pct REAL,
    market_cap_category TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 9. market_cap
CREATE TABLE market_cap (
    id TEXT,
    company_id TEXT,
    year TEXT,
    market_cap_crore REAL,
    enterprise_value_crore REAL,
    pe_ratio REAL,
    pb_ratio REAL,
    ev_ebitda REAL,
    dividend_yield_pct REAL,
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 10. stock_prices
CREATE TABLE stock_prices (
    id TEXT,
    company_id TEXT,
    date TEXT,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    close_price REAL,
    volume REAL,
    adjusted_close REAL,
    PRIMARY KEY (company_id, date),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 11. financial_ratios
-- Sprint 1 columns: pre-seeded from Screener.in financial_ratios.xlsx
-- Sprint 2 columns: computed by ratio engine (Days 08-11), populated by Day 12 script
CREATE TABLE financial_ratios (
    id TEXT,
    company_id TEXT,
    year TEXT,
    -- Sprint 1 pre-seeded (may be overwritten by engine in Day 12)
    net_profit_margin_pct REAL,
    operating_profit_margin_pct REAL,
    return_on_equity_pct REAL,
    debt_to_equity REAL,
    interest_coverage REAL,
    asset_turnover REAL,
    free_cash_flow_cr REAL,
    capex_cr REAL,
    earnings_per_share REAL,
    book_value_per_share REAL,
    dividend_payout_ratio_pct REAL,
    total_debt_cr REAL,
    cash_from_operations_cr REAL,
    -- Sprint 2 Day 08: profitability
    return_on_capital_employed_pct REAL,
    return_on_assets_pct REAL,
    -- Sprint 2 Day 09: leverage & efficiency
    net_debt_cr REAL,
    icr_label TEXT,
    icr_at_risk_flag INTEGER,      -- NULL=debt-free, 0=safe, 1=at risk
    high_leverage_flag INTEGER,    -- NULL=Financials sector, 0=false, 1=true
    -- Sprint 2 Day 10: CAGR
    revenue_cagr_5yr REAL,
    pat_cagr_5yr REAL,
    eps_cagr_5yr REAL,
    revenue_cagr_5yr_flag TEXT,
    pat_cagr_5yr_flag TEXT,
    eps_cagr_5yr_flag TEXT,
    -- Sprint 2 Day 11: CFO quality & cashflow patterns
    composite_quality_score REAL,          -- CFO/PAT trailing-5yr rolling avg
    composite_quality_score_flag TEXT,     -- INSUFFICIENT_YEARS if < 3 valid years
    cfo_quality_label TEXT,                -- High Quality / Moderate / Accrual Risk
    cashflow_pattern_code TEXT,            -- e.g. "+--", "---"
    cashflow_pattern_label TEXT,           -- Reinvestor, Shareholder Returns, etc.
    pattern_flag TEXT,                     -- UNDEFINED_COMBINATION for (-,+,-)
    capex_intensity_label TEXT,            -- Asset Light / Moderate / Capital Intensive
    capex_intensity_pct REAL,              -- abs(investing_activity)/sales*100
    fcf_conversion_flag TEXT,              -- edge-case flag for FCF/OP calculation
    fcf_conversion_pct REAL,               -- FCF/operating_profit*100
    PRIMARY KEY (company_id, year),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);

-- 12. peer_groups
CREATE TABLE peer_groups (
    id TEXT PRIMARY KEY,
    peer_group_name TEXT,
    company_id TEXT,
    is_benchmark INTEGER,
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
