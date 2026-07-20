# Sprint 1 Exit Checklist

## 1. Environment & Tools
- [x] Python 3.12+ virtual environment (`.venv`) established.
- [x] `requirements.txt` locked (pandas, sqlite3, pytest).
- [x] Makefile with cross-platform (Windows) support for `load`, `test`, `clean`, `clean-db`.

## 2. ETL & Data Foundation
- [x] `DataLoader` module processes all 12 source files from `data/raw` and `data/supporting`.
- [x] Orphan rows safely excluded prior to DB insert (avoids FK violations).
- [x] Duplicates rolled up and logged.
- [x] Audit framework tracks `rows_in`, `rows_out`, `db_rows`, and exact rejection counts per table.

## 3. Schema & Persistence
- [x] 12-table relational schema defined in `db/schema.sql` (Core: 7, Supp: 5).
- [x] Primary Key constraints enforced (composite where necessary).
- [x] Foreign Key constraints enforced (`company_id -> companies(id)`).
- [x] Final Row Counts: 
  - `companies`: 92
  - `profitandloss`: 1164
  - `balancesheet`: 1140
  - `cashflow`: 1056
  - `analysis`: 4
  - `documents`: 1456
  - `sectors`: 92
  - `stock_prices`: 5520
  - `market_cap`: 552
  - `financial_ratios`: 1041
  - `peer_groups`: 56
- [x] `PRAGMA foreign_key_check` returns 0 violations on load completion.

## 4. Data Quality Engine
- [x] DQ-01 to DQ-16 fully implemented and enforced.
- [x] `validation_failures.csv` correctly tags `CRITICAL` (schema blockers) and `WARNING` (business anomalies).
- [x] Component 5 (BFSI Exemption for DQ-05 OPM cross-check) implemented and verified against `broad_sector = 'Financials'`.

## 5. Testing & Validation
- [x] 35+ (Currently 67) Unit Tests covering extract, transform, load, and DQ rules.
- [x] Manual data review confirms accurate multi-year coverage for randomly sampled companies.
- [x] New IPOs (like JIOFIN) correctly handled with < 5 years of P&L data.

**STATUS: SPRINT 1 DATA FOUNDATION DECLARED READY.**
