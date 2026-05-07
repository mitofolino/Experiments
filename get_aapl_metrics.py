#!/usr/bin/env python3
"""
get_aapl_metrics.py

Fetches AAPL fundamentals (Yahoo via yfinance + quoteSummary fallback) and computes derived metrics:
- Market Cap, P/E, PEG, EV/EBITDA
- Price / Free Cash Flow
- Return on Equity (ROE), ROIC (fallback)
- Operating & Net Profit Margins
- Debt/Equity, Net Debt/EBITDA
- Current & Quick Ratios
- Revenue CAGR (5yr)
- Dividend Yield, Total Shareholder Yield, Payout Ratio

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
    t = yf.Ticker(ticker)
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
