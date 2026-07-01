"""Fetches and caches market data from external providers (yfinance, etc.)."""

import logging

import requests_cache
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

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


def _ticker_info_valid(info: dict) -> bool:
    """Return True when a yfinance info dict indicates a real, tradeable instrument.

    yfinance returns an empty or near-empty dict for tickers that don't exist.
    """
    return bool(info) and (
        "regularMarketPrice" in info
        or "currentPrice" in info
        or "previousClose" in info
        or "shortName" in info
        or "longName" in info
    )


_CURRENCY_MAP = {"INR": "INR", "USD": "USD"}


def _bare_ticker_likely_indian(ticker: str) -> bool:
    """Heuristic: common Indian tickers are 1-4 uppercase letters, no dot/suffix."""
    return (
        "." not in ticker
        and ticker.isascii()
        and ticker.isalpha()
        and ticker.isupper()
        and len(ticker) <= 15
    )


def resolve_ticker_metadata(ticker: str) -> dict:
    """Single source of truth for ticker existence + currency/exchange/asset-class.

    For bare tickers without a suffix (e.g. "RELIANCE", "ICICIBANK") the .NS
    suffix is tried FIRST because yfinance often returns a wrong/similar-named
    entity for bare Indian tickers (e.g. "ICICIBANK" resolves to a USD-traded
    stub).  If the .NS suffix fails, the bare ticker is tried as a fallback,
    which correctly resolves US tickers like "AAPL".

    Returns:
        {
            "valid": bool,
            "ticker": str,          # possibly suffix-corrected, e.g. "RELIANCE.NS"
            "name": str,
            "currency": "INR" | "USD" | "OTHER",
            "exchange": str | None,
            "country": str | None,
            "asset_class": "Equity" | "ETF" | "Crypto",
        }
    """
    def _build(t: str, info: dict) -> dict:
        quote_type = info.get("quoteType", "")
        if quote_type == "ETF":
            asset_class = "ETF"
        elif quote_type == "CRYPTOCURRENCY":
            asset_class = "Crypto"
        else:
            asset_class = "Equity"

        currency = _CURRENCY_MAP.get(info.get("currency"), "OTHER")

        return {
            "valid": True,
            "ticker": t,
            "name": info.get("shortName") or info.get("longName") or t,
            "currency": currency,
            "exchange": info.get("exchange"),
            "country": info.get("country"),
            "asset_class": asset_class,
        }

    # For bare tickers (no dot suffix), try .NS first — yfinance often returns
    # a wrong unrelated entity for bare Indian tickers
    if _bare_ticker_likely_indian(ticker):
        ns_ticker = ticker + ".NS"
        try:
            ns_info = yf.Ticker(ns_ticker).info
        except Exception:
            logger.warning("yfinance lookup failed for %s", ns_ticker, exc_info=True)
            ns_info = {}
        if _ticker_info_valid(ns_info) and ns_info.get("currency") == "INR":
            return _build(ns_ticker, ns_info)

    try:
        info = yf.Ticker(ticker).info
    except Exception:
        logger.warning("yfinance lookup failed for %s", ticker, exc_info=True)
        info = {}

    if _ticker_info_valid(info):
        return _build(ticker, info)

    # Fallback: try .NS for any remaining bare ticker that didn't match above
    if not ticker.endswith(".NS"):
        ns_ticker = ticker + ".NS"
        try:
            ns_info = yf.Ticker(ns_ticker).info
        except Exception:
            logger.warning("yfinance lookup failed for %s", ns_ticker, exc_info=True)
            ns_info = {}
        if _ticker_info_valid(ns_info):
            return _build(ns_ticker, ns_info)

    return {
        "valid": False,
        "ticker": ticker,
        "name": "",
        "currency": "OTHER",
        "exchange": None,
        "country": None,
        "asset_class": None,
    }


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
