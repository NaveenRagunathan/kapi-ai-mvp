"""Fetches and caches market data from external providers (yfinance, etc.)."""

import requests_cache
import yfinance as yf
import pandas as pd

# Install HTTP cache at module load time (24-hour TTL, SQLite backend)
requests_cache.install_cache(
    cache_name="http_cache",
    backend="sqlite",
    expire_after=86400,
)


def fetch_prices(tickers: list[str], period: str = "3y") -> pd.DataFrame:
    """Fetch historical daily adjusted closing prices.

    Returns a DataFrame with a DatetimeIndex and columns equal to the
    requested tickers.  Rows where every value is NaN are dropped.
    """
    data = yf.download(tickers, period=period, auto_adjust=True)["Close"]

    # yf.download returns a Series when only one ticker is requested; normalise
    # to a DataFrame so callers always receive consistent output.
    if isinstance(data, pd.Series):
        data = data.to_frame(name=tickers[0] if tickers else "Close")

    # Ensure requested column order (download may reorder or add extras)
    existing = [t for t in tickers if t in data.columns]
    data = data[existing]

    # Drop rows where all values are NaN
    data = data.dropna(how="all")

    return data


def fetch_benchmark(ticker: str = "^NSEI", period: str = "3y") -> pd.Series:
    """Fetch benchmark closing prices.

    Returns a pd.Series with a DatetimeIndex.
    """
    data = yf.download(ticker, period=period, auto_adjust=True)["Close"]

    # Normalise to a Series regardless of what yfinance returns
    if isinstance(data, pd.DataFrame):
        if ticker in data.columns:
            data = data[ticker]
        else:
            data = data.iloc[:, 0]

    data = data.dropna()
    data.name = ticker
    return data


def get_metadata(tickers: list[str]) -> dict[str, dict]:
    """Return metadata for each ticker.

    Structure::

        {
            "<ticker>": {
                "sector":     str,
                "industry":   str,
                "market_cap": int,
                "asset_class": str,   # "ETF" | "Crypto" | "Equity"
            },
            ...
        }
    """
    result: dict[str, dict] = {}

    for t in tickers:
        info = yf.Ticker(t).info

        quote_type = info.get("quoteType", "")
        if quote_type == "ETF":
            asset_class = "ETF"
        elif quote_type == "CRYPTOCURRENCY":
            asset_class = "Crypto"
        else:
            asset_class = "Equity"

        result[t] = {
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "asset_class": asset_class,
        }

    return result
