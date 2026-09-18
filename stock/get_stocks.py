#!/usr/bin/env python3
"""Fetch stock index performance using yfinance."""

import sys
import math
import yfinance as yf

INDICES = {
    "sp500": "^GSPC",
    "dax": "^GDAXI",
    "omx30": "^OMX",
}

PERIODS = {
    "1y": "1y",
    "6m": "6mo",
    "1m": "1mo",
    "1w": "5d",
}

def get_performance(symbol, period="1y"):
    """Calculate performance percentage for a symbol over a given period."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            return None

        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None

        old_price = float(closes.iloc[0])
        current_price = float(closes.iloc[-1])

        if not math.isfinite(old_price) or not math.isfinite(current_price) or old_price <= 0:
            return None

        performance = ((current_price - old_price) / old_price) * 100
        if not math.isfinite(performance):
            return None

        return performance
    except Exception:
        return None

def format_with_color(perf):
    """Format performance with conky color codes."""
    if perf is None or not math.isfinite(perf):
        return "N/A"
    color = "green" if perf >= 0 else "red"
    return f"${{color {color}}}{perf:+.2f}%${{color}}"

def main():
    if len(sys.argv) < 2:
        print("Usage: get_stocks.py <index|all> [period]")
        print("Indices: sp500, dax, omx30")
        print("Periods: 1y, 6m, 1m, 1w (default: 1y)")
        sys.exit(1)

    arg = sys.argv[1].lower()
    period_arg = sys.argv[2].lower() if len(sys.argv) > 2 else "1y"
    period = PERIODS.get(period_arg, "1y")

    if arg == "all":
        for name, symbol in INDICES.items():
            perf = get_performance(symbol, period)
            print(f"{name}:{format_with_color(perf)}")
    elif arg in INDICES:
        perf = get_performance(INDICES[arg], period)
        print(format_with_color(perf))
    else:
        print(f"Unknown index: {arg}")
        sys.exit(1)

if __name__ == "__main__":
    main()
