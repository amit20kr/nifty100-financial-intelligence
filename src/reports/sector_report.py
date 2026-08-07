import os
import re
import pandas as pd
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


class SectorReportGenerator:
    def __init__(self, df_comp, df_fr, df_ci, df_comp_score, df_mc=None):
        self.df_comp = df_comp
        self.df_fr = df_fr
        self.df_ci = df_ci
        self.df_comp_score = df_comp_score
        self.df_mc = pd.DataFrame() if df_mc is None else df_mc

        self.styles = getSampleStyleSheet()
        self.navy_color = colors.HexColor("#0f2c59")
        self.style_header = ParagraphStyle(
            "HeaderStyle",
            parent=self.styles["Heading1"],
            textColor=colors.white,
            alignment=1,
        )

    def _sanitize_filename(self, name: str) -> str:
        # Replace non-alphanumeric with underscore
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", name)
        return clean.strip("_")

    def generate_all(self, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)

        # Merge basic data for the latest non-TTM year
        # Get latest non-TTM fr
        fr_non_ttm = self.df_fr[self.df_fr["year"] != "TTM"].copy()

        # safely extract year
        def _ext_yr(y_str):
            try:
                return int(str(y_str)[:4])
            except:
                return 0

        fr_non_ttm["cal_year"] = fr_non_ttm["year"].apply(_ext_yr)
        latest_fr = (
            fr_non_ttm.sort_values("cal_year")
            .groupby("company_id")
            .last()
            .reset_index()
        )

        # Merge with ci for sector, comp for name, score for composite_score
        merged = pd.merge(
            latest_fr,
            self.df_comp[["id", "company_name"]],
            left_on="company_id",
            right_on="id",
            how="left",
        )
        merged = pd.merge(
            merged,
            self.df_ci[["company_id", "broad_sector"]],
            on="company_id",
            how="left",
        )

        # Merge market cap
        if not self.df_mc.empty:
            mc_non_ttm = self.df_mc[self.df_mc["year"] != "TTM"].copy()
            mc_non_ttm["cal_year"] = mc_non_ttm["year"].apply(_ext_yr)
            latest_mc = (
                mc_non_ttm.sort_values("cal_year")
                .groupby("company_id")
                .last()
                .reset_index()
            )
            merged = pd.merge(
                merged,
                latest_mc[["company_id", "market_cap_crore"]],
                on="company_id",
                how="left",
            )
        else:
            merged["market_cap_crore"] = pd.NA

        if not self.df_comp_score.empty:
            merged = pd.merge(
                merged,
                self.df_comp_score[["company_id", "screener_composite_score"]],
                on="company_id",
                how="left",
            )
        else:
            merged["screener_composite_score"] = pd.NA

        sectors = merged["broad_sector"].dropna().unique()

        for sector in sectors:
            sec_df = merged[merged["broad_sector"] == sector].copy()
            n_companies = len(sec_df)
            if n_companies == 0:
                continue

            safe_name = self._sanitize_filename(sector)
            out_path = os.path.join(output_dir, f"{safe_name}_report.pdf")

            try:
                self._generate_single(sector, sec_df, n_companies, out_path)
                print(f"Generated {out_path} ({n_companies} companies)")
            except Exception as e:
                print(f"Failed to generate sector report for {sector}: {e}")

    def _fmt(self, val, dec=2, suffix=""):
        if pd.isna(val) or val is None:
            return "N/A"
        return f"{val:.{dec}f}{suffix}"

    def _generate_single(self, sector_name, df, n, out_path):
        doc = SimpleDocTemplate(
            out_path,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30,
        )
        elements = []

        # --- PAGE 1: Summary ---
        title_suffix = " (Small Sample Size)" if n < 5 else ""
        header_data = [
            [
                Paragraph(
                    f"<b>{sector_name} Sector Report{title_suffix}</b>",
                    self.style_header,
                )
            ],
            [
                Paragraph(
                    f"<font color='white'>Total Companies: {n}</font>",
                    ParagraphStyle(
                        "SubHeader", parent=self.styles["Normal"], alignment=1
                    ),
                )
            ],
        ]

        header_table = Table(header_data, colWidths=[500])
        header_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), self.navy_color),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        elements.append(header_table)
        elements.append(Spacer(1, 20))

        elements.append(Paragraph("<b>Sector Medians</b>", self.styles["Heading2"]))
        elements.append(Spacer(1, 10))

        # Calculate medians
        metrics = {
            "Market Cap (Cr)": (df["market_cap_crore"].median(), 0, ""),
            "ROE (%)": (df["return_on_equity_pct"].median(), 2, "%"),
            "ROCE (%)": (df["return_on_capital_employed_pct"].median(), 2, "%"),
            "Net Profit Margin (%)": (df["net_profit_margin_pct"].median(), 2, "%"),
            "D/E": (df["debt_to_equity"].median(), 2, ""),
            "Revenue 5yr CAGR (%)": (
                df.get("revenue_cagr_5yr", pd.Series([pd.NA])).median(),
                2,
                "%",
            ),
            "PAT 5yr CAGR (%)": (
                df.get("pat_cagr_5yr", pd.Series([pd.NA])).median(),
                2,
                "%",
            ),
            "Composite Score": (
                df.get("screener_composite_score", pd.Series([pd.NA])).median(),
                1,
                "/100",
            ),
        }

        med_data = []
        for k, (val, dec, suf) in metrics.items():
            med_data.append([k, self._fmt(val, dec, suf)])

        med_table = Table(med_data, colWidths=[250, 150])
        med_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 1, colors.lightgrey),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(med_table)

        # --- PAGE 2+: Company List ---
        elements.append(PageBreak())
        elements.append(Paragraph("<b>Company Listing</b>", self.styles["Heading2"]))
        elements.append(Spacer(1, 10))

        col_headers = [
            "Company",
            "Ticker",
            "Mkt Cap",
            "ROE",
            "ROCE",
            "NPM",
            "D/E",
            "Rev CAGR",
            "PAT CAGR",
            "Score",
        ]

        # Ensure 'revenue_cagr_5yr' and 'pat_cagr_5yr' exist
        if "revenue_cagr_5yr" not in df.columns:
            df["revenue_cagr_5yr"] = pd.NA
        if "pat_cagr_5yr" not in df.columns:
            df["pat_cagr_5yr"] = pd.NA

        # Sort by Market Cap desc
        df = df.sort_values("market_cap_crore", ascending=False)

        list_data = [col_headers]
        for _, row in df.iterrows():
            list_data.append(
                [
                    Paragraph(
                        str(row.get("company_name", "N/A")), self.styles["Normal"]
                    ),
                    row.get("company_id", "N/A"),
                    self._fmt(row.get("market_cap_crore"), 0),
                    self._fmt(row.get("return_on_equity_pct"), 1, "%"),
                    self._fmt(row.get("return_on_capital_employed_pct"), 1, "%"),
                    self._fmt(row.get("net_profit_margin_pct"), 1, "%"),
                    self._fmt(row.get("debt_to_equity"), 2),
                    self._fmt(row.get("revenue_cagr_5yr"), 1, "%"),
                    self._fmt(row.get("pat_cagr_5yr"), 1, "%"),
                    self._fmt(row.get("screener_composite_score"), 1),
                ]
            )

        list_table = Table(
            list_data, colWidths=[120, 50, 50, 40, 40, 40, 35, 50, 50, 40], repeatRows=1
        )
        list_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.navy_color),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (0, 1), (0, -1), "LEFT"),  # Left align company name
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 1, colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        elements.append(list_table)
        doc.build(elements)
