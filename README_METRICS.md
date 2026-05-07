AAPL Metrics — README

This folder contains two scripts:
- fetch_aapl_fundamentals.py — downloads AAPL fundamentals (yfinance + Yahoo) and saves aapl_fundamentals.json
- get_aapl_metrics.py — computes derived metrics and writes metrics_aapl.json

Quick start (from Experiments):
1. Create/activate venv:
   python3 -m venv .venv
   source .venv/bin/activate
2. Install deps:
   python -m pip install yfinance pandas requests
3. Run metrics (example):
   python get_aapl_metrics.py --ticker AAPL --out metrics_aapl.json

Metrics (brief):
- marketCap: company size (price × shares).
- trailingPE: price / earnings (TTM).
- pegRatio: P/E adjusted for growth.
- ev_to_ebitda: enterprise value divided by EBITDA.
- price_to_free_cash_flow: market cap / free cash flow.
- dividendYield: annual dividend / price.
- buyback_yield: repurchases / market cap (positive when returning capital).
- total_shareholder_yield: dividendYield + buyback_yield.
- payout_ratio: dividend / EPS (or reported payoutRatio).
- roe: net income / shareholders' equity.
- roic: return on invested capital (fallbacks applied).
- operating_margin, net_profit_margin: profitability ratios.
- debt_to_equity: leverage metric.
- net_debt_to_ebitda: (debt - cash) / EBITDA.
- current_ratio, quick_ratio: liquidity measures.
- revenue_cagr_5yr: compound annual growth rate of revenue over 5 years (calculated from annual statements).

Notes:
- Some metrics may be null if source data is missing. The scripts favour Yahoo "info" fields with fallbacks to parsed statements.
- JSON outputs are ignored by .gitignore by default to avoid committing large data files.