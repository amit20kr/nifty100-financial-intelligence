import os
import sqlite3
import pandas as pd
import logging
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s \u2014 %(message)s"
)
logger = logging.getLogger("portfolio_summary")


def _ext_yr(y_str):
    try:
        return int(str(y_str)[:4])
    except:
        return 0


def get_trend_arrow(val_latest, val_prior, is_inverse=False):
    if pd.isna(val_latest) or pd.isna(val_prior):
        return ""  # No data for trend

    diff = val_latest - val_prior
    # flat within 2% absolute or relative? Let's use 2% relative to prior if prior != 0, else absolute 2 units.
    if abs(val_prior) > 0.001:
        pct_change = diff / abs(val_prior)
    else:
        pct_change = diff  # absolute fallback if prior is ~0

    if abs(pct_change) <= 0.02:
        return "<font color='gray'>&#8594;</font>"  # Right arrow (Flat)

    if diff > 0:
        return (
            "<font color='green'>&#8593;</font>"
            if not is_inverse
            else "<font color='red'>&#8593;</font>"
        )
    else:
        return (
            "<font color='red'>&#8595;</font>"
            if not is_inverse
            else "<font color='green'>&#8595;</font>"
        )


def fmt(val, suffix="", dec=2):
    if pd.isna(val) or val is None:
        return "N/A"
    return f"{val:.{dec}f}{suffix}"


def main():
    db_path = "db/nifty100.db"

    with sqlite3.connect(db_path) as conn:
        df_comp = pd.read_sql("SELECT * FROM companies", conn)
        df_fr = pd.read_sql("SELECT * FROM financial_ratios WHERE year != 'TTM'", conn)

    try:
        df_ci = pd.read_excel("output/cashflow_intelligence.xlsx")
    except FileNotFoundError:
        df_ci = pd.DataFrame()

    df_fr["cal_year"] = df_fr["year"].apply(_ext_yr)

    # We need to sort companies alphabetically by ticker (company_id)
    tickers = sorted(df_comp["id"].unique())

    out_dir = "reports/portfolio"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "portfolio_summary.pdf")

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    style_header = ParagraphStyle(
        "HeaderStyle",
        parent=styles["Heading1"],
        textColor=colors.HexColor("#0f2c59"),
        alignment=1,
    )

    elements = []

    # Title Page
    elements.append(Spacer(1, 200))
    elements.append(
        Paragraph(
            "<b>NIFTY 100 Portfolio Summary</b>",
            ParagraphStyle("Title", parent=styles["Title"], fontSize=24),
        )
    )
    elements.append(Spacer(1, 20))
    elements.append(
        Paragraph(
            "Sprint 5 Output",
            ParagraphStyle("Sub", parent=styles["Normal"], fontSize=14, alignment=1),
        )
    )
    elements.append(PageBreak())

    companies_processed = 0

    for ticker in tickers:
        fr_sub = df_fr[df_fr["company_id"] == ticker].sort_values("cal_year")
        if fr_sub.empty or len(fr_sub) < 2:
            continue  # Need at least 2 years for a trend

        latest_fr = fr_sub.iloc[-1]
        prior_fr = fr_sub.iloc[-2]

        cname = df_comp[df_comp["id"] == ticker].iloc[0]["company_name"]
        ci_sub = df_ci[df_ci["company_id"] == ticker]
        sector = (
            ci_sub.iloc[0]["broad_sector"]
            if not ci_sub.empty and "broad_sector" in ci_sub.columns
            else "Unknown"
        )

        # Page Header
        elements.append(Paragraph(f"<b>{cname} ({ticker})</b>", style_header))
        elements.append(
            Paragraph(
                f"Sector: {sector}",
                ParagraphStyle("Sec", parent=styles["Normal"], alignment=1),
            )
        )
        elements.append(Spacer(1, 30))

        # 6 KPIs
        # ROE, ROCE, Net Profit Margin, D/E, Rev CAGR, FCF
        kpi_defs = [
            ("ROE", "return_on_equity_pct", "%", False),
            ("ROCE", "return_on_capital_employed_pct", "%", False),
            ("Net Profit Margin", "net_profit_margin_pct", "%", False),
            ("D/E", "debt_to_equity", "", True),  # Inverse: lower is better
            ("Revenue 5yr CAGR", "revenue_cagr_5yr", "%", False),
            ("Free Cash Flow (Cr)", "free_cash_flow_cr", "", False),
        ]

        table_data = [["Metric", "Latest Year", "Prior Year", "Trend"]]

        for name, col, suf, inv in kpi_defs:
            v_lat = latest_fr.get(col)
            v_pri = prior_fr.get(col)
            trend = get_trend_arrow(v_lat, v_pri, inv)
            table_data.append(
                [
                    name,
                    fmt(v_lat, suf),
                    fmt(v_pri, suf),
                    Paragraph(trend, styles["Normal"]) if trend else "N/A",
                ]
            )

        t = Table(table_data, colWidths=[150, 100, 100, 60])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2c59")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 1, colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )

        elements.append(t)
        elements.append(PageBreak())
        companies_processed += 1

    doc.build(elements)
    logger.info(f"Generated {out_path} covering {companies_processed} companies.")


if __name__ == "__main__":
    main()
