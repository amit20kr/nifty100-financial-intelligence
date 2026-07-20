-- Sprint 1 · Exploratory Queries · Nifty 100 Financial Intelligence Platform
-- ============================================================================
-- Queries Q01–Q13 for manual data verification and Sprint 1 Demo
-- Run against: db/nifty100.db
-- Generated: Day 07

-- Q01: Company count (exit criterion: must be 92)
SELECT COUNT(*) AS company_count FROM companies;

-- Q02: Coverage distribution — years of P&L per company, ascending (reveals new listings)
SELECT company_id, COUNT(*) AS years
FROM profitandloss
WHERE year NOT IN ('TTM','PARTIAL_YEAR')
GROUP BY company_id ORDER BY years ASC;

-- Q03: P&L latest year per company
SELECT company_id, MAX(year) AS latest_year
FROM profitandloss GROUP BY company_id;

-- Q04: FK integrity check (exit criterion: zero rows)
PRAGMA foreign_key_check;

-- Q05: Full table row counts across all 12 tables
SELECT 'companies'        AS tbl, COUNT(*) AS cnt FROM companies
UNION ALL SELECT 'profitandloss',    COUNT(*) FROM profitandloss
UNION ALL SELECT 'balancesheet',     COUNT(*) FROM balancesheet
UNION ALL SELECT 'cashflow',         COUNT(*) FROM cashflow
UNION ALL SELECT 'analysis',         COUNT(*) FROM analysis
UNION ALL SELECT 'documents',        COUNT(*) FROM documents
UNION ALL SELECT 'prosandcons',      COUNT(*) FROM prosandcons
UNION ALL SELECT 'sectors',          COUNT(*) FROM sectors
UNION ALL SELECT 'stock_prices',     COUNT(*) FROM stock_prices
UNION ALL SELECT 'market_cap',       COUNT(*) FROM market_cap
UNION ALL SELECT 'financial_ratios', COUNT(*) FROM financial_ratios
UNION ALL SELECT 'peer_groups',      COUNT(*) FROM peer_groups;

-- Q06: Companies with <5 years of P&L data (new listings / data gaps)
SELECT company_id, COUNT(*) AS year_count
FROM profitandloss
WHERE year NOT IN ('TTM','PARTIAL_YEAR')
GROUP BY company_id HAVING COUNT(*) < 5
ORDER BY year_count ASC;

-- Q07: TTM rows in P&L (trailing twelve months coverage)
SELECT company_id, year FROM profitandloss WHERE year = 'TTM' ORDER BY company_id;

-- Q08: Sector distribution (broad_sector breakdown)
SELECT broad_sector, COUNT(*) AS company_count
FROM sectors GROUP BY broad_sector ORDER BY company_count DESC;

-- Q09: Top 10 companies by latest market cap
SELECT m.company_id, c.company_name, m.market_cap_crore, m.year
FROM market_cap m
JOIN companies c ON m.company_id = c.id
WHERE m.year = (SELECT MAX(m2.year) FROM market_cap m2 WHERE m2.company_id = m.company_id)
ORDER BY m.market_cap_crore DESC LIMIT 10;

-- Q10: Balance sheet imbalance check (DQ-04 equivalent in SQL)
SELECT company_id, year,
       ROUND(ABS(total_assets - total_liabilities) / NULLIF(total_assets,0) * 100, 2) AS imbalance_pct
FROM balancesheet
WHERE ABS(total_assets - total_liabilities) / NULLIF(total_assets,0) > 0.01
ORDER BY imbalance_pct DESC LIMIT 20;

-- Q11: Financial ratios — PE ratio leaders (latest year)
SELECT fr.company_id, c.company_name, fr.pe_ratio, fr.year
FROM financial_ratios fr
JOIN companies c ON fr.company_id = c.id
WHERE fr.year = (SELECT MAX(fr2.year) FROM financial_ratios fr2 WHERE fr2.company_id = fr.company_id)
  AND fr.pe_ratio IS NOT NULL AND fr.pe_ratio > 0
ORDER BY fr.pe_ratio DESC LIMIT 10;

-- Q12: Peer groups — number of companies per group
SELECT peer_group_name, COUNT(*) AS members
FROM peer_groups GROUP BY peer_group_name ORDER BY members DESC;

-- Q13: Stock price range per company (52-week based)
SELECT company_id,
       MIN(close_price) AS min_close,
       MAX(close_price) AS max_close,
       ROUND(AVG(close_price), 2) AS avg_close,
       COUNT(*) AS trading_days
FROM stock_prices GROUP BY company_id ORDER BY avg_close DESC LIMIT 10;
