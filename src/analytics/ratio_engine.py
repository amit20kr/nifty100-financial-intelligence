import logging
from src.analytics.ratios import (
    net_profit_margin,
    operating_profit_margin,
    return_on_equity,
    return_on_capital_employed,
    return_on_assets,
)

logger = logging.getLogger(__name__)


class RatioEngine:
    def __init__(self):
        pass

    def run(self):
        logger.info("RatioEngine run started.")
        # Sample row to confirm the module is wired (Day 8 smoke-testing)
        sales = 240893.0
        operating_profit = 64296.0
        profit_before_tax = 61997.0
        interest = 778.0
        net_profit = 46099.0
        equity_capital = 362.0
        reserves = 90127.0
        borrowings = 8021.0
        total_assets = 145472.0

        npm = net_profit_margin(net_profit, sales)
        opm = operating_profit_margin(operating_profit, sales, opm_pct_source=27.0)
        roe = return_on_equity(net_profit, equity_capital, reserves)
        roce_dict = return_on_capital_employed(
            profit_before_tax,
            interest,
            equity_capital,
            reserves,
            borrowings,
            "Technology",
        )
        roa = return_on_assets(net_profit, total_assets)

        logger.info(
            f"Sample Ratios - NPM: {npm:.2f}%, OPM: {opm:.2f}%, ROE: {roe:.2f}%, ROCE: {roce_dict['roce']:.2f}%, ROA: {roa:.2f}%"
        )
        logger.info("RatioEngine run completed.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = RatioEngine()
    engine.run()
