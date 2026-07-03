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
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
import requests_cache

logger = logging.getLogger(__name__)

_FMP_BASE_URL = "https://financialmodelingprep.com/stable"

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


def _fetch_fmp_profile(ticker: str) -> dict | None:
    """Fetch sector/industry/market-cap/P-E from Financial Modeling Prep's
    /stable/profile endpoint. Yahoo's crumb-free chart endpoint (used
    elsewhere in this module) doesn't expose this data -- the Yahoo endpoint
    that does (quoteSummary) is exactly the one that gets rate-limited/
    blocked on cloud IPs, which is why this module avoids it entirely (see
    module docstring). FMP's free tier covers both US and NSE-suffixed
    tickers on /profile; P-E (via /ratios-ttm) is premium-gated for non-US
    symbols on the free tier, so it's attempted best-effort and left None
    on failure rather than guessed.

    Returns None if FMP_API_KEY isn't set or the request fails/returns
    nothing -- callers must treat that as "no data available", not an error.
    """
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{_FMP_BASE_URL}/profile",
            params={"symbol": ticker, "apikey": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data or not isinstance(data, list):
            return None
        profile = data[0]

        pe_ratio = None
        try:
            ratios_resp = requests.get(
                f"{_FMP_BASE_URL}/ratios-ttm",
                params={"symbol": ticker, "apikey": api_key},
                timeout=10,
            )
            if ratios_resp.ok:
                ratios_data = ratios_resp.json()
                if isinstance(ratios_data, list) and ratios_data:
                    pe_ratio = ratios_data[0].get("priceToEarningsRatioTTM")
        except Exception:
            pass  # P-E is best-effort; premium-gated for many non-US tickers on the free tier

        return {
            "sector": profile.get("sector") or "Unknown",
            "industry": profile.get("industry") or "Unknown",
            "market_cap": profile.get("marketCap") or 0,
            "pe_ratio": pe_ratio,
        }
    except Exception:
        logger.warning("FMP profile lookup failed for %s", ticker, exc_info=True)
        return None


def get_metadata(tickers: list[str]) -> dict[str, dict]:
    """Return sector/industry/market-cap/P-E metadata for each ticker.

    Tries Financial Modeling Prep's /profile endpoint first (real sector,
    industry, market cap for both US and NSE-suffixed tickers on the free
    tier). Falls back to "Unknown"/0/None -- which only softens the
    diversification chart, it never blocks ingestion or price-based math --
    when FMP_API_KEY isn't configured or the lookup fails for a ticker.

    Structure::

        {
            "<ticker>": {
                "sector":     str,
                "industry":   str,
                "market_cap": int,
                "pe_ratio":   float | None,
                "asset_class": str,   # "ETF" | "Crypto" | "Equity"
            },
            ...
        }
    """
    metas = _parallel_map(resolve_ticker_metadata, tickers)
    fmp_profiles = _parallel_map(_fetch_fmp_profile, tickers)

    result: dict[str, dict] = {}
    for t, meta, fmp in zip(tickers, metas, fmp_profiles):
        result[t] = {
            "sector": (fmp or {}).get("sector", "Unknown"),
            "industry": (fmp or {}).get("industry", "Unknown"),
            "market_cap": (fmp or {}).get("market_cap", 0),
            "pe_ratio": (fmp or {}).get("pe_ratio"),
            "asset_class": meta.get("asset_class") or "Equity",
        }

    return result
