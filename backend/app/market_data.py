"""Fetches and caches market data from external providers.

Ticker resolution and price history go directly against Yahoo Finance's
`v8/finance/chart` endpoint instead of yfinance's `Ticker.info`/`download()`.
`Ticker.info` (and yfinance's `.download()` in recent versions) require a
cookie+crumb CSRF handshake that Yahoo aggressively rate-limits on shared
cloud IPs (Render, AWS, GCP, etc.) -- `v8/finance/chart` is a simpler, older
endpoint that doesn't require that handshake and has proven reliable in
production from cloud environments.

Sector/industry/market-cap data isn't available on that endpoint (the
endpoint that has it, quoteSummary, is the one that's rate-limited), so
get_metadata() reports "Unknown" sector/industry -- this only softens
diversification-chart richness, it never blocks ingestion or price-based math.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
import requests_cache

logger = logging.getLogger(__name__)

_MAX_WORKERS = 10


def _parallel_map(func, items: list):
    """Run func(item) for each item concurrently (I/O-bound network calls,
    independent of each other) and return results in the original order."""
    if len(items) <= 1:
        return [func(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(items))) as pool:
        return list(pool.map(func, items))

# Install HTTP cache at module load time (24-hour TTL, SQLite backend)
requests_cache.install_cache(
    cache_name="http_cache",
    backend="sqlite",
    expire_after=86400,
)

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def _fetch_chart(symbol: str, range_: str = "3y", interval: str = "1d") -> dict | None:
    """Call Yahoo's crumb-free chart endpoint. Returns the raw `result[0]`
    dict (meta + timestamp + indicators), or None on any failure."""
    try:
        resp = requests.get(
            _YAHOO_CHART_URL.format(symbol=symbol),
            params={"interval": interval, "range": range_},
            headers=_YAHOO_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("chart", {}).get("result")
        if not result:
            return None
        return result[0]
    except Exception:
        logger.warning("Yahoo chart lookup failed for %s", symbol, exc_info=True)
        return None


def _chart_to_series(chart: dict) -> pd.Series:
    """Extract a daily close-price Series (DatetimeIndex) from a chart result."""
    timestamps = chart.get("timestamp") or []
    closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    index = pd.to_datetime(timestamps, unit="s").normalize()
    series = pd.Series(closes, index=index, dtype=float)
    return series.dropna()


def fetch_prices(tickers: list[str], period: str = "3y") -> pd.DataFrame:
    """Fetch historical daily closing prices for multiple tickers.

    Returns a DataFrame with a DatetimeIndex and columns equal to the
    requested tickers (tickers that fail to resolve are simply omitted).
    """
    charts = _parallel_map(lambda t: _fetch_chart(t, range_=period), tickers)

    columns = {}
    for t, chart in zip(tickers, charts):
        if chart is None:
            continue
        series = _chart_to_series(chart)
        if not series.empty:
            columns[t] = series

    if not columns:
        return pd.DataFrame(columns=tickers)

    data = pd.DataFrame(columns)
    data = data[[t for t in tickers if t in data.columns]]
    data = data.dropna(how="all")
    return data


def fetch_benchmark(ticker: str = "^NSEI", period: str = "3y") -> pd.Series:
    """Fetch benchmark closing prices as a pd.Series with a DatetimeIndex."""
    chart = _fetch_chart(ticker, range_=period)
    if chart is None:
        return pd.Series(dtype=float, name=ticker)
    series = _chart_to_series(chart)
    series.name = ticker
    return series


_INSTRUMENT_TYPE_MAP = {
    "ETF": "ETF",
    "CRYPTOCURRENCY": "Crypto",
}
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


def _build_metadata_from_chart(t: str, chart: dict) -> dict:
    meta = chart.get("meta", {})
    instrument_type = meta.get("instrumentType", "")
    asset_class = _INSTRUMENT_TYPE_MAP.get(instrument_type, "Equity")
    currency = _CURRENCY_MAP.get(meta.get("currency"), "OTHER")

    return {
        "valid": True,
        "ticker": t,
        "name": meta.get("shortName") or meta.get("longName") or t,
        "currency": currency,
        "exchange": meta.get("exchangeName"),
        "country": None,
        "asset_class": asset_class,
    }


def resolve_ticker_metadata(ticker: str) -> dict:
    """Single source of truth for ticker existence + currency/exchange/asset-class.

    For bare tickers without a suffix (e.g. "RELIANCE", "ICICIBANK") the .NS
    suffix is tried FIRST because Yahoo often returns a wrong/similar-named
    entity for bare Indian tickers. If the .NS suffix fails, the bare ticker
    is tried as a fallback, which correctly resolves US tickers like "AAPL".

    Returns:
        {
            "valid": bool,
            "ticker": str,          # possibly suffix-corrected, e.g. "RELIANCE.NS"
            "name": str,
            "currency": "INR" | "USD" | "OTHER",
            "exchange": str | None,
            "country": None,
            "asset_class": "Equity" | "ETF" | "Crypto",
        }
    """
    # For bare tickers (no dot suffix), try .NS first
    if _bare_ticker_likely_indian(ticker):
        ns_ticker = ticker + ".NS"
        chart = _fetch_chart(ns_ticker, range_="5d")
        if chart and chart.get("meta", {}).get("currency") == "INR":
            return _build_metadata_from_chart(ns_ticker, chart)

    chart = _fetch_chart(ticker, range_="5d")
    if chart:
        return _build_metadata_from_chart(ticker, chart)

    # Fallback: try .NS for any remaining bare ticker that didn't match above
    if not ticker.endswith(".NS"):
        ns_ticker = ticker + ".NS"
        chart = _fetch_chart(ns_ticker, range_="5d")
        if chart:
            return _build_metadata_from_chart(ns_ticker, chart)

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
    """Return sector/industry/market-cap metadata for each ticker.

    Sector/industry aren't available on the crumb-free chart endpoint (the
    endpoint that has them, quoteSummary, is the one that's rate-limited),
    so this reports "Unknown" for both -- it only softens the diversification
    chart, it never blocks ingestion or price-based math.

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
    metas = _parallel_map(resolve_ticker_metadata, tickers)

    result: dict[str, dict] = {}
    for t, meta in zip(tickers, metas):
        result[t] = {
            "sector": "Unknown",
            "industry": "Unknown",
            "market_cap": 0,
            "asset_class": meta.get("asset_class") or "Equity",
        }

    return result
