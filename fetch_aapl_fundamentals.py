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

    # pick common key metrics (safe .get)
    keys = [
        "marketCap",
        "fiftyTwoWeekHigh",
        "fiftyTwoWeekLow",
        "trailingPE",
        "trailingEps",
        "pegRatio",
        "priceToSalesTrailing12Months",
        "priceToBook",
        "enterpriseValue",
        "enterpriseToRevenue",
        "enterpriseToEbitda",
        "profitMargins",
        "returnOnAssets",
        "returnOnEquity",
        "totalRevenue",
        "netIncomeToCommon",
        "freeCashflow",
        "totalCash",
        "debtToEquity",
        "dividendRate",
        "dividendYield",
    ]
    metrics = {k: info.get(k) for k in keys}
    data["key_metrics"] = metrics

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


