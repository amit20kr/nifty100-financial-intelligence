# Nifty 100 Financial Intelligence Platform

> A production-grade quantitative analytics engine for all 92 Nifty 100 companies — computing 50+ financial KPIs, CAGR growth series, cash flow quality scores, and a rules-based stock screener, all backed by a typed SQLite data warehouse built from raw Screener.in exports.

---

## 📊 What This Does

| Module | Description | Status |
|---|---|---|
| **ETL Pipeline** | Loads, normalises, and validates 10 Excel sources into SQLite | ✅ Sprint 1 |
| **Profitability Ratios** | NPM, OPM, ROE, ROCE, ROA — with OPM cross-check logging | ✅ Day 08 |
| **Leverage & Efficiency** | D/E, ICR (at-risk flag), Net Debt, Asset Turnover | ✅ Day 09 |
| **CAGR Engine** | 3/5/10yr Revenue, PAT, EPS CAGR with 7-scenario edge classifier | ✅ Day 10 |
| **Cash Flow KPIs** | FCF, CapEx Intensity, FCF Conversion, 8-pattern classifier | ✅ Sprint 2 |
| **DB Population** | Full `financial_ratios` table population for 92 companies | ✅ Sprint 2 |
| **Screener & Scoring** | Configurable rules-based screener & composite scoring engine | ✅ Sprint 3 |
| **Streamlit Dashboard** | Interactive dashboard with screener, peers, trends & valuation | ✅ Sprint 4 |
| **NLP & PDF Reports** | Auto Pros/Cons generator, PDF Tearsheets & Sector Reports | ✅ Sprint 5 |

---

## 🏗 Architecture

```
nifty100-financial-intelligence/
├── src/
│   ├── etl/              # Loader, normaliser, validator — Sprint 1
│   ├── analytics/
│   │   ├── constants.py  # CagrFlag enum — single source of truth for all flag strings
│   │   ├── ratios.py     # Profitability + Leverage pure functions (Day 08-09)
│   │   ├── cagr.py       # CAGR engine + window extractor (Day 10)
│   │   └── ratio_engine.py
│   ├── screener/         # Composite scoring & filtering engine (Sprint 3)
│   ├── dashboard/        # Streamlit app (Sprint 4)
│   ├── nlp/              # Auto Pros/Cons text generation (Sprint 5)
│   └── reports/          # ReportLab PDF tearsheets & summaries (Sprint 5)
├── db/
│   ├── schema.sql        # Source of truth for DB schema
│   └── migrations/
│       └── migrate.py    # Idempotent Python migration runner
├── tests/
│   ├── etl/
│   └── kpi/              # 32 KPI formula tests — 106 total passing
├── data/                 # Gitignored — shared separately
├── output/               # Gitignored — generated at runtime
├── .env.example          # Template — copy to .env and fill in
├── Makefile              # make load | migrate | test | ratios | coverage
└── requirements.txt
```

---

## ⚡ Quick Start (< 15 minutes)

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/nifty100-financial-intelligence.git
cd nifty100-financial-intelligence

# 2. Environment
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate          # macOS/Linux
pip install -r requirements.txt

# 3. Config
cp .env.example .env
# Edit .env: set DB_PATH, RAW_DATA_DIR, SUPPORTING_DATA_DIR

# 4. Load data (requires Excel source files in data/)
make load

# 5. Apply migrations
make migrate

# 6. Run ratio engine
make ratios

# 7. Test
make test

# 8. Run Dashboard
make dashboard
# Or directly:
streamlit run src/dashboard/app.py
```

---

## 🧪 Testing

```bash
make test           # Full suite (106 tests, ~38s)
make coverage       # HTML coverage report → reports/htmlcov/
```

**Current test status:** `106 passed, 0 failed`

| Suite | Tests | Coverage |
|---|---|---|
| ETL (loader, validator, normaliser) | 73 | — |
| KPI Formulas (Days 08–10) | 32 | ratios.py ≥ 88%, cagr.py ≥ 92% |
| Smoke | 1 | — |

---

## 🔑 Key Design Decisions

| Decision | Rationale |
|---|---|
| Pure functions throughout `analytics/` | Testable without DB; Day 12 population is a separate persistence layer |
| `NamedTuple` for all multi-value returns | Attribute access is self-documenting; prevents positional argument bugs |
| `CagrFlag(str, Enum)` in `constants.py` | One source of truth for all flag strings written to SQLite TEXT columns |
| `extract_cagr_window()` matches by `int(year[:4])` | Handles ABB (Dec FY), SIEMENS (Sep FY), and fiscal year changes without `iloc[-n]` misalignment |
| Idempotent `migrate.py` | `PRAGMA table_info` + `schema_migrations` tracking — safe to re-run on every deploy |
| All thresholds in `.env` | Zero hardcoded numbers in formula code — consistent with `BS_BALANCE_TOLERANCE_PCT` pattern |

---

## 📋 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DB_PATH` | `db/nifty100.db` | SQLite database path |
| `FINANCIALS_SECTOR_LABEL` | `Financials` | Must match `sectors.broad_sector` exactly |
| `DE_HIGH_LEVERAGE_THRESHOLD` | `5.0` | D/E above this triggers `high_leverage_flag` (non-Financials only) |
| `ICR_AT_RISK_THRESHOLD` | `1.5` | ICR below this triggers `icr_at_risk_flag` |
| `CAGR_ZERO_EPSILON` | `1e-6` | Epsilon for float zero-detection in CAGR base/end checks |
| `OPM_CROSS_CHECK_TOLERANCE_PCT` | `1.0` | OPM source vs computed mismatch threshold for logging |
| `BS_BALANCE_TOLERANCE_PCT` | `1.0` | Balance sheet assets vs liabilities max diff % |

See `.env.example` for the full list.

---

## 📦 Data Sources

Raw data is sourced from [Screener.in](https://www.screener.in) exports for all 92 Nifty 100 constituents. Due to licensing, raw Excel files are **not committed** to this repository. Place them in `data/raw/` and `data/supporting/` before running `make load`.

---

## 🗺 Roadmap

- [x] Sprint 1 — ETL Data Foundation (92 companies, 10 tables, 106 tests)
- [x] Sprint 2 — Ratio Engine, Cash Flow KPIs, DB population, verification
- [x] Sprint 3 — Screener Engine, Composite Scores, Peer Analytics, Radar Charts
- [x] Sprint 4 — Streamlit Financial Dashboard and Valuation Module
- [x] Sprint 5 — NLP Pros/Cons Generator, Cash Flow Intelligence, PDF Reports (Tearsheets, Sector, Portfolio)

---

## 📖 Detailed Walkthrough (Sprint 1 to 5)

This project has been built in 5 systematic sprints to create a complete quantitative and qualitative analytics pipeline.

### Sprint 1: ETL & Data Foundation
- Built a robust ETL pipeline to parse and load raw Excel data from Screener.in for 92 Nifty 100 companies.
- Normalized 10 core tables (Profit & Loss, Balance Sheet, Cash Flow, Market Cap, etc.) into a strictly typed SQLite database.

### Sprint 2: Financial Ratio Engine
- Developed pure Python functions to compute 50+ financial KPIs (ROE, ROCE, D/E, ICR, OPM, NPM).
- Built a complex CAGR engine to calculate 3, 5, and 10-year growth rates (Revenue, PAT, EPS) with edge-case classifiers.
- Implemented Cash Flow Intelligence (FCF, CapEx Intensity, FCF Conversion) and populated the central `financial_ratios` table.

### Sprint 3: Screener & Scoring Engine
- Created a configurable, rules-based stock screener.
- Developed a Composite Scoring system that ranks companies based on Value, Growth, Profitability, and Quality.
- Built Peer Analytics and generated data for Radar Charts to visualize company strengths visually against sector peers.

### Sprint 4: Streamlit Dashboard
- Built a multi-page interactive Streamlit dashboard (`src/dashboard/app.py`).
- Integrated Screener, Peer Comparisons, Trend analysis, Sector insights, and a dedicated Valuation module directly into the UI.

### Sprint 5: NLP & PDF Reporting
- **NLP Text Parser:** Added an automated Pros/Cons generator that translates raw financial data into human-readable insights using 24 objective heuristic rules and confidence scores.
- **Cash Flow Intelligence:** Expanded cash flow analytics to identify distress signals and deleveraging trends.
- **Automated PDF Reports:** Used `ReportLab` to batch-generate 91 company tearsheet PDFs (complete with charts, CF waterfalls, and KPIs), 10 Sector Summary PDFs, and a comprehensive Portfolio Summary.

The pipeline is fully automated and idempotent. Running the master scripts regenerates the database, calculates all ratios, flags edge cases, scores the companies, and compiles the final PDF reports.

---

*Built with Python 3.12 · SQLite · pandas · pytest · Streamlit · ReportLab*
