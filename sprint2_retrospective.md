# Sprint 2 Retrospective: Profitability & Cash Flow KPIs

## Objective
Sprint 2 focused on transforming raw financial data (P&L, Balance Sheet, Cash Flow) into a comprehensive suite of 14+ standardized KPIs and ratios in the `financial_ratios` table. This forms the analytical foundation for the Nifty 100 stock screener.

## Key Deliverables & Outcomes
- **Financial Ratios Engine**: Implemented robust computations for NPM, OPM, ROE, ROCE, ROA, D/E, ICR, Net Debt, Asset Turnover, FCF, Capex Intensity, FCF Conversion, and 5-yr CAGRs.
- **Cash Flow Pattern Classifier**: Successfully categorized companies into 8 distinct capital allocation patterns based on their operating, investing, and financing cash flows, outputting to `output/capital_allocation.csv`.
- **Data Quality & Idempotency**: Established a volatile, idempotent execution model for `financial_ratios`. Computations can be cleanly re-run without duplicate accumulation.

## Formula Decisions & Methodologies
1. **Trailing 5-Year CAGR**: CAGRs are anchored dynamically to each row's fiscal year, rather than computing one scalar per company. The logic mandates a strict 5-year window, properly flagging insufficient history, negative bases, and turnaround scenarios.
2. **CFO Quality Score**: Computed as a rolling 5-year average of CFO / PAT, requiring a minimum of 3 valid years in the window to output a score. This mitigates volatility in single-year CFO figures.
3. **Sector Exceptions (Financials)**:
   - High Leverage (`high_leverage_flag`): Explicitly set to `NULL` (not applicable) for companies in the `Financials` sector, as traditional D/E thresholds do not apply to banks and NBFCs.
   - ROCE: Uses a specialized denominator `(equity_capital + reserves + borrowings)` across all sectors for consistency, instead of stripping borrowings for Financials.

## Edge Case Resolutions
- **Denominator Zero/Negative (ROE, D/E)**: Handled gracefully by returning `None` (SQL `NULL`) when equity components are missing or sum to <= 0, preventing division-by-zero errors.
- **CAGR Anomalies**: Handled edge cases such as negative starting bases (`NEG_BASE_TO_POS`, `BOTH_NEGATIVE`) and turnarounds with distinct categorization flags instead of returning misleading numerical values.
- **Fiscal Year Collisions**: Resolved a critical data integrity issue where half-year filings (e.g., `2024-09`) were overwriting full-year filings (e.g., `2024-03`) by ensuring precise lookup keys `(company_id, year_str)` were used for direct data mapping, while maintaining `YYYY-03` prioritization for trailing window analyses.
- **Log Append Duplication**: Ensured `ratio_edge_cases.log` operates idempotently (truncating on each run) to prevent unbounded growth of triaged/un-triaged log entries across pipeline executions.

## Action Items for Sprint 3
- Triage the remaining entries in `ratio_edge_cases.log` regarding cross-check discrepancies (especially ROCE/ROE mismatches against external references) to refine computation rules if necessary.
- Integrate the finalized `financial_ratios` table with the frontend/API layer for screener filtering.
