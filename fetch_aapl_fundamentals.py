#!/usr/bin/env python3
"""
fetch_aapl_fundamentals.py

Fetch AAPL fundamentals using yfinance and (optionally) Yahoo's quoteSummary JSON.
Writes a JSON file `aapl_fundamentals.json` in the current directory.

Dependencies:
  pip install yfinance pandas requests

Usage:
  python fetch_aapl_fundamentals.py
"""

import json
import datetime
import pandas as pd
import yfinance as yf
import numpy as np


def series_to_native(val):
    if pd.isna(val):
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        return float(val)
    return val


def df_to_list(df, max_cols=5):
    """Convert a DataFrame with date columns to a list of dicts (one per column)."""
    if df is None or df.empty:
        return []
    # Ensure consistent indexing and fillna handling
    df = df.copy()
    df = df.where(pd.notnull(df), None)
    cols = list(df.columns)[:max_cols]
    out = []
    for col in cols:
        entry = {"date": str(col)}
        for idx in df.index:
            try:
                entry[str(idx)] = series_to_native(df.at[idx, col])
            except Exception:
                entry[str(idx)] = None
        out.append(entry)
    return out


def get_ticker(ticker="AAPL"):
    t = yf.Ticker(ticker)

    # safe info retrieval
    try:
        info = t.info if hasattr(t, "info") else t.get_info()
    except Exception:
        info = {}

    # latest price (1-day history)
    price = None
    try:
        hist = t.history(period="1d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
    except Exception:
        price = None

    data = {
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        "ticker": ticker,
        "price": price,
        "info": info,
    }

    # extract basic key metrics from info
    data["key_metrics"] = {
        "marketCap": info.get("marketCap"),
        "trailingPE": info.get("trailingPE"),
        "pegRatio": info.get("pegRatio"),
        "ev_to_ebitda": info.get("enterpriseToEbitda"),
        "priceToSalesTrailing12Months": info.get("priceToSalesTrailing12Months"),
        "priceToBook": info.get("priceToBook"),
        "profitMargins": info.get("profitMargins"),
        "operatingMargins": info.get("operatingMargins"),
        "returnOnAssets": info.get("returnOnAssets"),
        "returnOnEquity": info.get("returnOnEquity"),
        "totalRevenue": info.get("totalRevenue"),
        "netIncomeToCommon": info.get("netIncomeToCommon"),
        "freeCashflow": info.get("freeCashflow"),
        "totalCash": info.get("totalCash"),
        "debtToEquity": info.get("debtToEquity"),
        "dividendRate": info.get("dividendRate"),
        "dividendYield": info.get("dividendYield"),
        "currentRatio": info.get("currentRatio"),
        "quickRatio": info.get("quickRatio"),
        "ebitda": info.get("ebitda"),
        "totalDebt": info.get("totalDebt"),
    }

    # financial statements (annual and quarterly)
    try:
        income = t.financials
        bal = t.balance_sheet
        cash = t.cashflow
        q_income = t.quarterly_financials
        q_bal = t.quarterly_balance_sheet
        q_cash = t.quarterly_cashflow
    except Exception:
        income = bal = cash = q_income = q_bal = q_cash = pd.DataFrame()

    data["financials"] = {
        "income_annual": df_to_list(income, max_cols=5),
        "balance_annual": df_to_list(bal, max_cols=5),
        "cashflow_annual": df_to_list(cash, max_cols=5),
        "income_quarterly": df_to_list(q_income, max_cols=8),
        "balance_quarterly": df_to_list(q_bal, max_cols=8),
        "cashflow_quarterly": df_to_list(q_cash, max_cols=8),
    }

    data["financials"] = {
        "income_annual": df_to_list(income, max_cols=5),
        "balance_annual": df_to_list(bal, max_cols=5),
        "cashflow_annual": df_to_list(cash, max_cols=5),
        "income_quarterly": df_to_list(q_income, max_cols=8),
        "balance_quarterly": df_to_list(q_bal, max_cols=8),
        "cashflow_quarterly": df_to_list(q_cash, max_cols=8),
    }

    # compute derived metrics where possible
    try:
        km = data.get("key_metrics", {})
        market_cap = km.get("marketCap")
        free_cashflow = km.get("freeCashflow") or km.get("freeCashflow")
        # price-to-free-cash-flow (Market Cap / Free Cash Flow)
        price_to_free_cash_flow = None
        try:
            if market_cap and free_cashflow:
                price_to_free_cash_flow = market_cap / free_cashflow
        except Exception:
            price_to_free_cash_flow = None
        km["price_to_free_cash_flow"] = price_to_free_cash_flow

        # Net debt to EBITDA
        total_debt = km.get("totalDebt") or info.get("totalDebt")
        total_cash = km.get("totalCash") or info.get("totalCash")
        ebitda = km.get("ebitda") or info.get("ebitda")
        net_debt_to_ebitda = None
        try:
            if total_debt is not None and total_cash is not None and ebitda:
                net_debt = total_debt - total_cash
                if ebitda != 0:
                    net_debt_to_ebitda = net_debt / ebitda
        except Exception:
            net_debt_to_ebitda = None
        km["net_debt_to_ebitda"] = net_debt_to_ebitda

        # Revenue CAGR (5yr) from annual income statements
        rev_cagr_5yr = None
        try:
            ann = data.get("financials", {}).get("income_annual", [])
            revs = []
            for entry in ann:
                for key in ("Total Revenue", "TotalRevenue", "totalRevenue"):
                    if key in entry and entry[key] is not None:
                        revs.append(entry[key])
                        break
            if len(revs) >= 5:
                window = list(reversed(revs[:5]))
                start = window[0]
                end = window[-1]
                if start and end and start > 0:
                    years = len(window) - 1
                    rev_cagr_5yr = (end / start) ** (1.0 / years) - 1.0
        except Exception:
            rev_cagr_5yr = None
        km["revenue_cagr_5yr"] = rev_cagr_5yr

        # Total Shareholder Yield = Dividend Yield + Buyback Yield (using latest annual repurchases)
        dividend_yield = km.get("dividendYield") or info.get("dividendYield") or info.get("trailingAnnualDividendYield")
        buyback_yield = None
        try:
            cf_ann = data.get("financials", {}).get("cashflow_annual", [])
            if cf_ann:
                repurchase = cf_ann[0].get("Repurchase Of Capital Stock")
                if repurchase is None:
                    repurchase = cf_ann[0].get("Repurchase Of Common Stock") or cf_ann[0].get("Repurchase Of Capital Stock, Common Stock")
                if repurchase is not None and market_cap:
                    buyback_yield = (-repurchase) / market_cap
        except Exception:
            buyback_yield = None
        km["buyback_yield"] = buyback_yield
        if dividend_yield is not None:
            try:
                km["total_shareholder_yield"] = dividend_yield + (buyback_yield or 0)
            except Exception:
                km["total_shareholder_yield"] = None
        else:
            km["total_shareholder_yield"] = buyback_yield

        # Payout ratio (fallback to dividend / EPS)
        payout_ratio = info.get("payoutRatio")
        if payout_ratio is None:
            div_rate = info.get("dividendRate")
            eps = info.get("trailingEps")
            try:
                if div_rate is not None and eps:
                    payout_ratio = div_rate / eps
            except Exception:
                payout_ratio = None
        km["payout_ratio"] = payout_ratio

        # ROIC fallback
        roic = info.get("returnOnInvestment") or info.get("returnOnInvestedCapital") or info.get("returnOnAssets")
        km["roic"] = roic

        data["key_metrics"] = km
    except Exception:
        pass

    # attempt to fetch Yahoo's quoteSummary JSON for additional structured fields
    try:
        import requests
        url = (
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
            "?modules=assetProfile,financialData,defaultKeyStatistics,price,summaryDetail"
        )
        resp = requests.get(url, timeout=10)
        if resp.ok:
            data["yahoo_quoteSummary"] = resp.json()
        else:
            data["yahoo_quoteSummary"] = {"error": resp.status_code}
    except Exception as e:
        data["yahoo_quoteSummary"] = {"error": str(e)}

    return data


def main():
    out_filename = "aapl_fundamentals.json"
    data = get_ticker("AAPL")
    with open(out_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved fundamentals to {out_filename}")


if __name__ == "__main__":
    main()
