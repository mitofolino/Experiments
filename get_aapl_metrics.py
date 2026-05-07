#!/usr/bin/env python3
"""
get_aapl_metrics.py

Fetches AAPL fundamentals (Yahoo via yfinance + quoteSummary fallback) and computes derived metrics.

Metrics (what they mean and how they're calculated):

- marketCap
  Purpose: Size of the company; used for valuation comparisons.
  Source/Calc: Taken directly from Yahoo ('marketCap') = share price * shares outstanding.

- trailingPE (P/E)
  Purpose: Valuation multiple showing price paid per dollar of trailing earnings.
  Source/Calc: Yahoo 'trailingPE' (Price / EPS (TTM)).

- pegRatio
  Purpose: Adjusts P/E for expected earnings growth (lower may indicate better value).
  Source/Calc: Yahoo 'pegRatio' (P/E divided by expected growth rate).

- ev_to_ebitda (EV/EBITDA)
  Purpose: Enterprise-value based multiple that accounts for capital structure.
  Source/Calc: Yahoo 'enterpriseToEbitda'. EV/EBITDA = (Enterprise Value) / EBITDA.

- price_to_free_cash_flow (Price/FCF)
  Purpose: Valuation relative to cash generation; alternative to P/E.
  Source/Calc: marketCap / freeCashflow (both from Yahoo when available).

- dividendYield
  Purpose: Cash yield to shareholders from dividends.
  Source/Calc: Yahoo 'dividendYield' (annual dividend / current price).

- buyback_yield
  Purpose: Returns to shareholders via share repurchases.
  Source/Calc: -(Repurchase Of Capital Stock) / marketCap (repurchases typically negative cash outflow).

- total_shareholder_yield
  Purpose: Combined cash yield (dividend + buybacks) to shareholders.
  Source/Calc: dividendYield + buyback_yield (when available).

- payout_ratio
  Purpose: Share of earnings paid as dividends; shows sustainability of dividend.
  Source/Calc: Yahoo 'payoutRatio' or dividendRate / trailingEps when payoutRatio missing.

- roe (Return on Equity)
  Purpose: Profitability relative to shareholders' equity.
  Source/Calc: Yahoo 'returnOnEquity' (Net Income / Shareholders' Equity).

- roic (Return on Invested Capital)
  Purpose: How efficiently a company turns capital into profits.
  Source/Calc: Prefer 'returnOnInvestment' or 'returnOnInvestedCapital' from Yahoo; fallback to 'returnOnAssets' if missing.

- operating_margin
  Purpose: Operating efficiency (operating income as % of revenue).
  Source/Calc: Yahoo 'operatingMargins' (Operating Income / Revenue).

- net_profit_margin
  Purpose: Net profitability (net income as % of revenue).
  Source/Calc: Yahoo 'profitMargins' (Net Income / Revenue).

- debt_to_equity
  Purpose: Capital structure/leverage measure.
  Source/Calc: Yahoo 'debtToEquity' = Total Debt / Shareholders' Equity.

- net_debt_to_ebitda
  Purpose: Leverage adjusted for cash; shows how many years of EBITDA needed to pay net debt.
  Source/Calc: (Total Debt - Total Cash) / EBITDA (using Yahoo fields).

- current_ratio
  Purpose: Short-term liquidity (ability to cover current liabilities).
  Source/Calc: Yahoo 'currentRatio' = Current Assets / Current Liabilities.

- quick_ratio
  Purpose: Liquidity minus inventory; stricter short-term liquidity.
  Source/Calc: Yahoo 'quickRatio' (or (Current Assets - Inventory) / Current Liabilities).

- revenue_cagr_5yr
  Purpose: Growth rate of revenue over 5 years.
  Source/Calc: Calculated from annual income statements: CAGR = (rev_end / rev_start)^(1/years) - 1.

Notes:
- All fields try to use Yahoo-provided keys first (t.info), with fallbacks to parsed financial statements when necessary.
- Repurchases are read from cashflow statements and treated as negative outflows; buyback yield is expressed as a positive fraction of market cap.
- Some metrics may be null when source data is missing; check JSON output for nulls.

Writes JSON to metrics_aapl.json and prints it.

Requires: yfinance, pandas, requests
"""

import json
import math
from typing import Any, Dict, Optional
import pandas as pd
import yfinance as yf


def safe_num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return float(v)
        return float(v)
    except Exception:
        return None


def df_to_revs(ann: pd.DataFrame) -> list:
    if ann is None or ann.empty:
        return []
    revs = []
    # columns are dates; pick 'Total Revenue' or 'TotalRevenue' row
    for col in ann.columns:
        val = None
        for key in ('Total Revenue', 'totalRevenue', 'TotalRevenue', 'TotalRevenue'):
            if key in ann.index:
                val = ann.at[key, col]
                break
        # fallback: try 'Total Revenue' in column if ann is a transposed format
        if val is None:
            try:
                # try to find a row that contains 'Revenue' in its name
                for idx in ann.index:
                    if 'reven' in str(idx).lower():
                        maybe = ann.at[idx, col]
                        if pd.notna(maybe):
                            val = maybe
                            break
            except Exception:
                pass
        if pd.isna(val) if val is not None else True:
            continue
        revs.append(float(val))
    return revs


def compute_metrics(ticker: str = 'AAPL') -> Dict[str, Any]:
    tyes = yf.Ticker(ticker)
    info = {}
    try:
        info = t.info if hasattr(t, 'info') else t.get_info()
    except Exception:
        info = {}

    # basic numeric helpers
    market_cap = safe_num(info.get('marketCap'))
    trailing_pe = safe_num(info.get('trailingPE') or info.get('trailingPE'))
    peg = safe_num(info.get('pegRatio'))
    ev_to_ebitda = safe_num(info.get('enterpriseToEbitda') or info.get('enterpriseToEbitda'))
    dividend_yield = safe_num(info.get('dividendYield') or info.get('trailingAnnualDividendYield'))
    payout_ratio = safe_num(info.get('payoutRatio'))

    # financial statements
    try:
        income = t.financials
        balance = t.balance_sheet
        cashflow = t.cashflow
    except Exception:
        income = balance = cashflow = pd.DataFrame()

    # Price / Free Cash Flow
    free_cf = safe_num(info.get('freeCashflow') or info.get('freeCashFlow') or (None))
    price_to_fcf = None
    if market_cap and free_cf and free_cf != 0:
        price_to_fcf = market_cap / free_cf

    # Debt and liquidity
    total_debt = safe_num(info.get('totalDebt'))
    total_cash = safe_num(info.get('totalCash') or info.get('cash'))
    ebitda = safe_num(info.get('ebitda'))
    net_debt_to_ebitda = None
    if total_debt is not None and total_cash is not None and ebitda:
        net_debt = total_debt - total_cash
        if ebitda != 0:
            net_debt_to_ebitda = net_debt / ebitda

    # margins and returns
    operating_margin = safe_num(info.get('operatingMargins'))
    net_profit_margin = safe_num(info.get('profitMargins'))
    roe = safe_num(info.get('returnOnEquity'))
    roic = safe_num(info.get('returnOnInvestment') or info.get('returnOnInvestedCapital') or info.get('returnOnAssets'))

    # ratios
    debt_to_equity = safe_num(info.get('debtToEquity'))
    current_ratio = safe_num(info.get('currentRatio'))
    quick_ratio = safe_num(info.get('quickRatio'))

    # Revenue CAGR 5yr
    revs = df_to_revs(income)
    revenue_cagr_5yr = None
    try:
        if len(revs) >= 6:
            # revs are in descending date order from yfinance; reverse to chronological
            last5 = revs[0:5]
            first = last5[-1]
            last = last5[0]
            years = len(last5) - 1
            if first and last and first > 0:
                revenue_cagr_5yr = (last / first) ** (1.0 / years) - 1.0
    except Exception:
        revenue_cagr_5yr = None

    # Total Shareholder Yield (dividend + buyback)
    buyback_yield = None
    try:
        if isinstance(cashflow, pd.DataFrame) and not cashflow.empty:
            # pick latest column
            latest_col = cashflow.columns[0]
            repurchase = None
            for key in ('Repurchase Of Capital Stock', 'Repurchase Of Common Stock', 'Repurchase of Common Stock'):
                if key in cashflow.index:
                    repurchase = cashflow.at[key, latest_col]
                    break
            if repurchase is None:
                # try common names
                for idx in cashflow.index:
                    if 'repurch' in str(idx).lower():
                        repurchase = cashflow.at[idx, latest_col]
                        break
            if repurchase is not None and market_cap:
                buyback_yield = (-float(repurchase)) / market_cap
    except Exception:
        buyback_yield = None

    total_shareholder_yield = None
    if dividend_yield is not None:
        total_shareholder_yield = dividend_yield + (buyback_yield or 0.0)
    else:
        total_shareholder_yield = buyback_yield

    # Payout ratio fallback
    if payout_ratio is None:
        try:
            div_rate = safe_num(info.get('dividendRate'))
            eps = safe_num(info.get('trailingEps') or info.get('epsTrailingTwelveMonths'))
            if div_rate is not None and eps:
                payout_ratio = div_rate / eps
        except Exception:
            payout_ratio = None

    metrics = {
        'ticker': ticker,
        'marketCap': market_cap,
        'trailingPE': trailing_pe,
        'pegRatio': peg,
        'ev_to_ebitda': ev_to_ebitda,
        'price_to_free_cash_flow': price_to_fcf,
        'dividendYield': dividend_yield,
        'total_shareholder_yield': total_shareholder_yield,
        'buyback_yield': buyback_yield,
        'payout_ratio': payout_ratio,
        'roe': roe,
        'roic': roic,
        'operating_margin': operating_margin,
        'net_profit_margin': net_profit_margin,
        'debt_to_equity': debt_to_equity,
        'net_debt_to_ebitda': net_debt_to_ebitda,
        'current_ratio': current_ratio,
        'quick_ratio': quick_ratio,
        'revenue_cagr_5yr': revenue_cagr_5yr,
    }

    return metrics


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', default='AAPL')
    parser.add_argument('--out', default='metrics_aapl.json')
    args = parser.parse_args()

    m = compute_metrics(args.ticker)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    print(json.dumps(m, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
