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
    """Compute metrics for `ticker` with robust fallbacks.

    Strategy:
    - Prefer yfinance t.get_info() (or t.info).
    - If that yields few fields, attempt Yahoo quoteSummary JSON as a fallback.
    - Always parse financial statements from yfinance for repurchases and revenue history.
    - Return a metrics dict and include a "_source" key showing which source was used.
    """
    t = yf.Ticker(ticker)
    info = {}
    source = "none"

    # 1) Try yfinance high-level info
    try:
        if hasattr(t, "get_info"):
            info = t.get_info() or {}
        else:
            info = getattr(t, "info", {}) or {}
        if info:
            source = "yfinance"
    except Exception:
        info = {}

    # 2) If info seems empty, try Yahoo quoteSummary JSON as fallback
    yahoo_q = {}
    if not info:
        try:
            import requests
            qs_url = (
                f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
                "?modules=financialData,defaultKeyStatistics,price,summaryDetail"
            )
            r = requests.get(qs_url, timeout=10)
            j = r.json()
            if j and isinstance(j, dict):
                res = j.get("quoteSummary", {}).get("result")
                if res and len(res) > 0:
                    yahoo_q = res[0]
                    source = "yahoo_json"
        except Exception:
            yahoo_q = {}

    # financial statements (annual/quarterly) from yfinance
    try:
        income = t.financials
        balance = t.balance_sheet
        cashflow = t.cashflow
    except Exception:
        income = balance = cashflow = pd.DataFrame()

    # helper to read raw value from yahoo quoteSummary module
    def _raw(q, *path):
        try:
            cur = q
            for p in path:
                if cur is None:
                    return None
                cur = cur.get(p)
            if isinstance(cur, dict):
                return safe_num(cur.get("raw") if "raw" in cur else cur)
            return safe_num(cur)
        except Exception:
            return None

    # gather values (prefer info, then yahoo_q)
    market_cap = safe_num(info.get("marketCap") or _raw(yahoo_q, "price", "marketCap"))
    # Price and EPS values for P/E fallbacks
    price = safe_num(info.get("currentPrice") or info.get("regularMarketPrice") or _raw(yahoo_q, "price", "regularMarketPrice") or _raw(yahoo_q, "price", "regularMarketPreviousClose"))
    ttm_eps = safe_num(info.get("trailingEps") or info.get("epsTrailingTwelveMonths") or _raw(yahoo_q, "defaultKeyStatistics", "trailingEps") or _raw(yahoo_q, "financialData", "trailingEps"))
    forward_eps = safe_num(info.get("forwardEps") or _raw(yahoo_q, "financialData", "forwardEps"))

    trailing_pe = safe_num(info.get("trailingPE") or _raw(yahoo_q, "summaryDetail", "trailingPE") or _raw(yahoo_q, "defaultKeyStatistics", "trailingPE"))
    # fallback: compute trailing P/E from price and trailing EPS when available
    if trailing_pe is None and price and ttm_eps and ttm_eps != 0:
        try:
            trailing_pe = float(price) / float(ttm_eps)
        except Exception:
            trailing_pe = None

    forward_pe = safe_num(info.get("forwardPE") or _raw(yahoo_q, "financialData", "forwardPE"))
    # fallback: compute forward P/E from price and forward EPS
    if forward_pe is None and price and forward_eps and forward_eps != 0:
        try:
            forward_pe = float(price) / float(forward_eps)
        except Exception:
            forward_pe = None

    peg = safe_num(info.get("pegRatio") or _raw(yahoo_q, "defaultKeyStatistics", "pegRatio") or _raw(yahoo_q, "financialData", "pegRatio"))
    ev_to_ebitda = safe_num(info.get("enterpriseToEbitda") or _raw(yahoo_q, "financialData", "enterpriseToEbitda"))
    dividend_yield = safe_num(info.get("dividendYield") or _raw(yahoo_q, "summaryDetail", "dividendYield") or _raw(yahoo_q, "financialData", "dividendYield"))
    payout_ratio = safe_num(info.get("payoutRatio") or _raw(yahoo_q, "financialData", "payoutRatio"))
    free_cf = safe_num(info.get("freeCashflow") or _raw(yahoo_q, "financialData", "freeCashflow"))

    # Price/FCF
    price_to_fcf = None
    if market_cap and free_cf and free_cf != 0:
        price_to_fcf = market_cap / free_cf

    # debt and cash
    total_debt = safe_num(info.get("totalDebt") or _raw(yahoo_q, "financialData", "totalDebt"))
    total_cash = safe_num(info.get("totalCash") or _raw(yahoo_q, "financialData", "totalCash"))
    ebitda = safe_num(info.get("ebitda") or _raw(yahoo_q, "financialData", "ebitda"))

    net_debt_to_ebitda = None
    if total_debt is not None and total_cash is not None and ebitda:
        try:
            net_debt = total_debt - total_cash
            if ebitda != 0:
                net_debt_to_ebitda = net_debt / ebitda
        except Exception:
            net_debt_to_ebitda = None

    # margins and returns
    operating_margin = safe_num(info.get("operatingMargins") or _raw(yahoo_q, "financialData", "operatingMargins"))
    net_profit_margin = safe_num(info.get("profitMargins") or _raw(yahoo_q, "financialData", "profitMargins"))
    roe = safe_num(info.get("returnOnEquity") or _raw(yahoo_q, "financialData", "returnOnEquity"))
    roic = safe_num(info.get("returnOnInvestment") or info.get("returnOnInvestedCapital") or _raw(yahoo_q, "financialData", "returnOnEquity") or info.get("returnOnAssets"))

    # liquidity
    debt_to_equity = safe_num(info.get("debtToEquity") or _raw(yahoo_q, "financialData", "debtToEquity"))
    current_ratio = safe_num(info.get("currentRatio") or _raw(yahoo_q, "financialData", "currentRatio"))
    quick_ratio = safe_num(info.get("quickRatio") or _raw(yahoo_q, "financialData", "quickRatio"))

    # revenue cagr using income statement
    revs = df_to_revs(income)
    revenue_cagr_5yr = None
    try:
        if len(revs) >= 5:
            # revs from yfinance are in descending order (newest first)
            last5 = revs[:5]
            newest = last5[0]
            oldest = last5[-1]
            years = len(last5) - 1
            if oldest and newest and oldest > 0:
                revenue_cagr_5yr = (newest / oldest) ** (1.0 / years) - 1.0
    except Exception:
        revenue_cagr_5yr = None

    # buyback yield from cashflow statement (repurchases)
    buyback_yield = None
    try:
        if isinstance(cashflow, pd.DataFrame) and not cashflow.empty and market_cap:
            latest_col = cashflow.columns[0]
            repurchase = None
            for key in ("Repurchase Of Capital Stock", "Repurchase Of Common Stock", "Repurchase of Common Stock"):
                if key in cashflow.index:
                    repurchase = cashflow.at[key, latest_col]
                    break
            if repurchase is None:
                for idx in cashflow.index:
                    if "repurch" in str(idx).lower():
                        repurchase = cashflow.at[idx, latest_col]
                        break
            if repurchase is not None:
                buyback_yield = (-float(repurchase)) / market_cap
    except Exception:
        buyback_yield = None

    total_shareholder_yield = None
    if dividend_yield is not None:
        total_shareholder_yield = dividend_yield + (buyback_yield or 0.0)
    else:
        total_shareholder_yield = buyback_yield

    # payout ratio fallback
    if payout_ratio is None:
        try:
            div_rate = safe_num(info.get("dividendRate") or _raw(yahoo_q, "summaryDetail", "dividendRate"))
            eps = safe_num(info.get("trailingEps") or info.get("epsTrailingTwelveMonths") or _raw(yahoo_q, "defaultKeyStatistics", "trailingEps"))
            if div_rate is not None and eps:
                payout_ratio = div_rate / eps
        except Exception:
            payout_ratio = None

    metrics = {
        "ticker": ticker,
        "marketCap": market_cap,
        "trailingPE": trailing_pe,
        "forwardPE": forward_pe,
        "pegRatio": peg,
        "ev_to_ebitda": ev_to_ebitda,
        "price_to_free_cash_flow": price_to_fcf,
        "dividendYield": dividend_yield,
        "total_shareholder_yield": total_shareholder_yield,
        "buyback_yield": buyback_yield,
        "payout_ratio": payout_ratio,
        "roe": roe,
        "roic": roic,
        "operating_margin": operating_margin,
        "net_profit_margin": net_profit_margin,
        "debt_to_equity": debt_to_equity,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "revenue_cagr_5yr": revenue_cagr_5yr,
        # Expose EPS fields used for P/E calculations
        "ttmEPS": ttm_eps,
        "forwardEPS": forward_eps,
        "_source": source,
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
