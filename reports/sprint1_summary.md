# Sprint 1 Retrospective & Summary: Data Foundation

## Sprint Goal Achieved
By the end of Sprint 1, the team successfully established a fully loaded and validated SQLite database (`nifty100.db`) containing all 12 tables (7 core + 5 supplementary) derived from the 12 source files. All 16 Data Quality (DQ) rules were executed, with all `CRITICAL` failures resolved and `WARNING`s correctly logged for downstream processing. The foundation for all subsequent analytic and API modules is firmly in place.

## Final Metrics & Exit Criteria
- **Total Tables Populated:** 12 (Target: 10+, achieved 12).
- **`companies` Table Count:** 92 (Target: 92).
- **Foreign Key Violations:** 0 (Orphan rows dropped safely pre-insert).
- **Automated Tests:** 69 passing, 0 failures.
- **Code Coverage:** 84% (Target: >80%).
- **Manual DQ Review:** 5 random companies inspected; year coverage spans from 2013-03 to TTM, adjusting correctly for newly listed entities (e.g., JIOFIN with 3 years).

## Key Technical Decisions & Resolutions
1. **Idempotency & Load Order:** The `DataLoader` implements strict transactional control (`BEGIN TRANSACTION`... `COMMIT`/`ROLLBACK`) and enforces correct insert ordering (Parent `companies` first, child tables next).
2. **Orphan Ticker Resolution:** 9 known orphan tickers (e.g., WIPRO, ZOMATO) that lacked parent `companies` records were programmatically detected and removed prior to DB insertion, satisfying `PRAGMA foreign_key_check` and guaranteeing referential integrity.
3. **Data Quality Engine:** A comprehensive `validator.py` executes 16 DQ rules. Notable refinements include **DQ-05 (OPM Cross-Check)**, where BFSI entities (defined as `broad_sector = 'Financials'`) are safely exempted from standard operating margin calculations.
4. **Audit Logging:** The `load_audit.csv` precisely records `rows_in`, `rows_rejected`, `duplicates_removed`, and the final DB sync status (`LOADED_OK`) per table.

## Next Steps (Sprint 2 Prep)
- **KPI Engine:** `RatioEngine` stub created. Ready to ingest `nifty100.db` and output structured financial metrics.
- **API Foundation:** FastAPI stub created. `tests/api/test_api_smoke.py` passes.
- **Dashboarding:** Streamlit environment validated.

**Sign-off Status:** APPROVED & MERGED.
