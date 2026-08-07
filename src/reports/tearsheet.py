import os
import io
import pandas as pd
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
    ListFlowable,
    ListItem,
)


class InsufficientDataError(ValueError):
    pass


class TearsheetGenerator:
    def __init__(
        self,
        df_comp,
        df_fr,
        df_cf,
        df_pl,
        df_bs,
        df_pc,
        df_ci,
        df_comp_score,
        df_mc=None,
    ):
        """
        Pre-loaded DataFrames to avoid repeated DB/File IO.
        df_comp: companies (id, company_name)
        df_fr: financial_ratios
        df_cf: cashflow
        df_pl: profitandloss
        df_bs: balancesheet
        df_pc: pros_cons_generated.csv
        df_ci: cashflow_intelligence.xlsx
        df_comp_score: composite_scores_all.csv
        df_mc: market_cap
        """
        self.df_comp = df_comp
        self.df_fr = df_fr
        self.df_cf = df_cf
        self.df_pl = df_pl
        self.df_bs = df_bs
        self.df_pc = df_pc
        self.df_ci = df_ci
        self.df_comp_score = df_comp_score
        self.df_mc = pd.DataFrame() if df_mc is None else df_mc

        self.min_years = int(os.getenv("TEARSHEET_MIN_YEARS", "3"))

        # ReportLab styles
        self.styles = getSampleStyleSheet()
        self.navy_color = colors.HexColor("#0f2c59")

        # Custom Paragraph Styles for wrapping
        self.style_normal = self.styles["Normal"]
        self.style_header = ParagraphStyle(
            "HeaderStyle",
            parent=self.styles["Heading1"],
            textColor=colors.white,
            alignment=1,
        )
        self.style_kpi_title = ParagraphStyle(
            "KPITitle",
            parent=self.styles["Normal"],
            fontSize=10,
            textColor=colors.gray,
            alignment=1,
        )
        self.style_kpi_val = ParagraphStyle(
            "KPIVal", parent=self.styles["Heading2"], alignment=1
        )

        self.style_pro = ParagraphStyle(
            "ProStyle",
            parent=self.styles["Normal"],
            textColor=colors.darkgreen,
            spaceAfter=6,
        )
        self.style_con = ParagraphStyle(
            "ConStyle",
            parent=self.styles["Normal"],
            textColor=colors.darkred,
            spaceAfter=6,
        )
        self.style_neutral = ParagraphStyle(
            "NeutralStyle",
            parent=self.styles["Normal"],
            textColor=colors.black,
            spaceAfter=6,
        )

    def _extract_year(self, y_str: str) -> int:
        try:
            return int(str(y_str)[:4])
        except:
            return 0

    def generate(self, company_id: str, output_path: str):
        # 1. Filter data
        comp = self.df_comp[self.df_comp["id"] == company_id]
        if comp.empty:
            raise ValueError(f"Company {company_id} not found in companies data.")
        comp_name = comp.iloc[0]["company_name"]

        fr = self.df_fr[
            (self.df_fr["company_id"] == company_id) & (self.df_fr["year"] != "TTM")
        ].copy()
        cf = self.df_cf[
            (self.df_cf["company_id"] == company_id) & (self.df_cf["year"] != "TTM")
        ].copy()
        pl = self.df_pl[
            (self.df_pl["company_id"] == company_id) & (self.df_pl["year"] != "TTM")
        ].copy()
        bs = self.df_bs[
            (self.df_bs["company_id"] == company_id) & (self.df_bs["year"] != "TTM")
        ].copy()
        pc = (
            self.df_pc[self.df_pc["company_id"] == company_id].copy()
            if not self.df_pc.empty
            else pd.DataFrame()
        )
        ci = (
            self.df_ci[self.df_ci["company_id"] == company_id].copy()
            if not self.df_ci.empty
            else pd.DataFrame()
        )
        score = (
            self.df_comp_score[self.df_comp_score["company_id"] == company_id]
            if not self.df_comp_score.empty
            else pd.DataFrame()
        )

        if len(fr) < self.min_years:
            raise InsufficientDataError(
                f"{company_id} has only {len(fr)} years of data. Minimum is {self.min_years}."
            )

        # Add cal_year for sorting charts properly
        for df in [fr, cf, pl, bs]:
            if not df.empty:
                df["cal_year"] = df["year"].apply(self._extract_year)
                df.sort_values("cal_year", inplace=True)

        # 2. Build PDF Document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30,
        )
        elements = []

        # --- PAGE 1 ---
        # A. Navy Header
        sector = (
            ci.iloc[0]["broad_sector"]
            if not ci.empty and "broad_sector" in ci.columns
            else "Unknown Sector"
        )
        # Extract market cap from df_mc latest non-TTM row
        full_mc = self.df_mc[
            (self.df_mc["company_id"] == company_id) & (self.df_mc["year"] != "TTM")
        ].copy()
        if not full_mc.empty:
            full_mc["cal_year"] = full_mc["year"].apply(self._extract_year)
            full_mc.sort_values("cal_year", inplace=True)
            mcap = full_mc.iloc[-1].get("market_cap_crore")
            mcap_str = f"{mcap:,.0f} Cr" if pd.notna(mcap) else "N/A"
        else:
            mcap_str = "N/A"

        comp_score = (
            score.iloc[0]["screener_composite_score"] if not score.empty else 0.0
        )
        comp_score_str = f"{comp_score:.1f}/100" if pd.notna(comp_score) else "N/A"

        header_data = [
            [Paragraph(f"<b>{comp_name} ({company_id})</b>", self.style_header)],
            [
                Paragraph(
                    f"<font color='white'>Sector: {sector} | Market Cap: {mcap_str} | Composite Score: {comp_score_str}</font>",
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

        # B. 6 KPI Tiles
        latest_fr = fr.iloc[-1]
        latest_cf = cf.iloc[-1] if not cf.empty else None

        def fmt(val, suffix="", dec=2):
            if pd.isna(val) or val is None:
                return "N/A"
            return f"{val:.{dec}f}{suffix}"

        kpis = [
            ("ROE", fmt(latest_fr.get("return_on_equity_pct"), "%")),
            ("ROCE", fmt(latest_fr.get("return_on_capital_employed_pct"), "%")),
            ("Net Profit Margin", fmt(latest_fr.get("net_profit_margin_pct"), "%")),
            ("D/E", fmt(latest_fr.get("debt_to_equity"))),
            (
                "Revenue CAGR 5yr",
                (
                    fmt(latest_fr.get("revenue_cagr_5yr"), "%")
                    if "revenue_cagr_5yr" in latest_fr
                    else "N/A"
                ),
            ),
            (
                "FCF (latest)",
                (
                    fmt(latest_fr.get("free_cash_flow_cr"), " Cr")
                    if "free_cash_flow_cr" in latest_fr
                    else "N/A"
                ),
            ),
        ]

        kpi_data = [
            [
                Paragraph(kpis[0][0], self.style_kpi_title),
                Paragraph(kpis[1][0], self.style_kpi_title),
                Paragraph(kpis[2][0], self.style_kpi_title),
            ],
            [
                Paragraph(kpis[0][1], self.style_kpi_val),
                Paragraph(kpis[1][1], self.style_kpi_val),
                Paragraph(kpis[2][1], self.style_kpi_val),
            ],
            [
                Paragraph(kpis[3][0], self.style_kpi_title),
                Paragraph(kpis[4][0], self.style_kpi_title),
                Paragraph(kpis[5][0], self.style_kpi_title),
            ],
            [
                Paragraph(kpis[3][1], self.style_kpi_val),
                Paragraph(kpis[4][1], self.style_kpi_val),
                Paragraph(kpis[5][1], self.style_kpi_val),
            ],
        ]

        kpi_table = Table(kpi_data, colWidths=[166, 166, 166])
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 1, colors.lightgrey),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(kpi_table)
        elements.append(Spacer(1, 20))

        # C. Charts Page 1 (1x2 Table)
        rev_pat_buf = self._draw_revenue_profit_bar(pl)
        roe_roce_buf = self._draw_roe_roce_line(fr)

        chart_data_p1 = [
            [
                Image(rev_pat_buf, width=250, height=200),
                Image(roe_roce_buf, width=250, height=200),
            ]
        ]
        elements.append(Table(chart_data_p1, colWidths=[260, 260]))

        # --- PAGE 2 ---
        elements.append(PageBreak())

        # A. Capital Allocation Badge & Charts (1x2 Table)
        cap_alloc = (
            ci.iloc[0]["capital_allocation_label"]
            if not ci.empty and pd.notna(ci.iloc[0]["capital_allocation_label"])
            else "Unclassified/No Data"
        )

        elements.append(
            Paragraph(
                f"<b>Capital Allocation Pattern:</b> {cap_alloc}",
                self.styles["Heading2"],
            )
        )
        elements.append(Spacer(1, 10))

        bs_buf = self._draw_balance_sheet_stacked(bs)
        cf_buf = self._draw_cashflow_waterfall(cf)

        chart_data_p2 = [
            [Image(bs_buf, width=250, height=200), Image(cf_buf, width=250, height=200)]
        ]
        elements.append(Table(chart_data_p2, colWidths=[260, 260]))
        elements.append(Spacer(1, 20))

        # B. Pros and Cons
        elements.append(Paragraph("<b>Pros & Cons</b>", self.styles["Heading2"]))
        elements.append(Spacer(1, 10))

        if not pc.empty:
            pros = (
                pc[pc["type"] == "PRO"]
                .sort_values("confidence_pct", ascending=False)
                .head(6)
            )
            cons = (
                pc[pc["type"] == "CON"]
                .sort_values("confidence_pct", ascending=False)
                .head(6)
            )
        else:
            pros = pd.DataFrame()
            cons = pd.DataFrame()

        pro_list = [
            ListItem(Paragraph(row["insight"], self.style_pro))
            for _, row in pros.iterrows()
        ]
        con_list = [
            ListItem(Paragraph(row["insight"], self.style_con))
            for _, row in cons.iterrows()
        ]

        if len(con_list) == 0:
            con_list = [
                ListItem(Paragraph("No major red flags detected.", self.style_neutral))
            ]

        if len(pro_list) == 0:
            pro_list = [
                ListItem(
                    Paragraph("No major positive signals detected.", self.style_neutral)
                )
            ]

        pc_data = [
            [
                Paragraph("<b>Strengths</b>", self.style_pro),
                Paragraph("<b>Risks</b>", self.style_con),
            ],
            [
                ListFlowable(
                    pro_list, bulletType="bullet", bulletColor=colors.darkgreen
                ),
                ListFlowable(con_list, bulletType="bullet", bulletColor=colors.darkred),
            ],
        ]

        pc_table = Table(pc_data, colWidths=[250, 250])
        pc_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, 1),
                        colors.HexColor("#f0fdf4"),
                    ),  # light green
                    (
                        "BACKGROUND",
                        (1, 0),
                        (1, 1),
                        colors.HexColor("#fef2f2"),
                    ),  # light red
                    ("BOX", (0, 0), (0, 1), 1, colors.HexColor("#bbf7d0")),
                    ("BOX", (1, 0), (1, 1), 1, colors.HexColor("#fecdd3")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elements.append(pc_table)

        # Build PDF
        doc.build(elements)
        plt.close("all")  # Clear matplotlib memory

    def _draw_revenue_profit_bar(self, pl):
        plt.figure(figsize=(5, 4))
        if not pl.empty:
            years = pl["year"].tolist()
            rev = pl["sales"].tolist()
            pat = pl["net_profit"].tolist()

            x = range(len(years))
            width = 0.35

            fig, ax1 = plt.subplots(figsize=(5, 4))
            ax1.bar(
                [i - width / 2 for i in x], rev, width, label="Revenue", color="#3b82f6"
            )
            ax1.set_ylabel("Revenue (Cr)")
            ax1.set_xticks(x)
            ax1.set_xticklabels(years, rotation=45)

            ax2 = ax1.twinx()
            ax2.bar(
                [i + width / 2 for i in x],
                pat,
                width,
                label="Net Profit",
                color="#10b981",
            )
            ax2.set_ylabel("Net Profit (Cr)")

            plt.title("Revenue & Net Profit")
            fig.legend(loc="upper left", bbox_to_anchor=(0.1, 0.9))
            plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        plt.close()
        return buf

    def _draw_roe_roce_line(self, fr):
        plt.figure(figsize=(5, 4))
        if not fr.empty:
            years = fr["year"].tolist()
            roe = fr["return_on_equity_pct"].tolist()
            roce = fr["return_on_capital_employed_pct"].tolist()

            plt.plot(years, roe, marker="o", label="ROE (%)", color="#ef4444")
            plt.plot(years, roce, marker="s", label="ROCE (%)", color="#8b5cf6")

            plt.title("ROE vs ROCE")
            plt.xticks(rotation=45)
            plt.ylabel("%")
            plt.legend()
            plt.grid(True, linestyle="--", alpha=0.5)
            plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        plt.close()
        return buf

    def _draw_balance_sheet_stacked(self, bs):
        plt.figure(figsize=(5, 4))
        if not bs.empty:
            years = bs["year"].tolist()
            eq = bs["equity_capital"].fillna(0) + bs["reserves"].fillna(0)
            debt = bs["borrowings"].fillna(0)
            ol = bs["other_liabilities"].fillna(0)

            plt.bar(years, eq, label="Equity", color="#0f2c59")
            plt.bar(years, debt, bottom=eq, label="Borrowings", color="#ef4444")
            plt.bar(years, ol, bottom=eq + debt, label="Other Liab", color="#94a3b8")

            plt.title("Capital Structure")
            plt.xticks(rotation=45)
            plt.ylabel("Cr")
            plt.legend()
            plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        plt.close()
        return buf

    def _draw_cashflow_waterfall(self, cf):
        plt.figure(figsize=(5, 4))
        if not cf.empty:
            # Waterfall for latest year only to keep it readable, or grouped bar?
            # Spec: "CFO/CFI/CFF waterfall chart". Let's do a grouped bar for all years.
            years = cf["year"].tolist()
            cfo = cf["operating_activity"].fillna(0).tolist()
            cfi = cf["investing_activity"].fillna(0).tolist()
            cff = cf["financing_activity"].fillna(0).tolist()

            x = range(len(years))
            width = 0.25

            plt.bar([i - width for i in x], cfo, width, label="CFO", color="#10b981")
            plt.bar([i for i in x], cfi, width, label="CFI", color="#ef4444")
            plt.bar([i + width for i in x], cff, width, label="CFF", color="#3b82f6")

            plt.title("Cash Flows (Operating, Investing, Financing)")
            plt.xticks(x, years, rotation=45)
            plt.ylabel("Cr")
            plt.legend()
            plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150)
        buf.seek(0)
        plt.close()
        return buf
