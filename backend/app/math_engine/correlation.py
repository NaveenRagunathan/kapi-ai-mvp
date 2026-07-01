"""Correlation matrix, with TTL caching."""

import copy
import time

from app.market_data import fetch_prices

# Correlation matrices are expensive (a yfinance price fetch per
# ticker) and identical for a given holding set within a short window, so
# cache the result keyed by the sorted ticker set.
_CORRELATION_CACHE: dict = {}
_CORRELATION_CACHE_TTL = 300  # 5 minutes


def get_correlation_matrix(holdings: list[dict]) -> dict:
    """Compute pairwise correlation matrix of daily returns for all holdings.

    Returns:
        {
            "tickers": ["AAPL", "MSFT", ...],
            "matrix": [[1.0, 0.7, ...], [0.7, 1.0, ...], ...],  # NxN correlation values
            "labels": ["AAPL", "MSFT", ...]  # same as tickers, for chart labeling
        }
    """
    tickers = [h["ticker"] for h in holdings]

    # Cache keyed by the sorted ticker set — same holdings within
    # the TTL window skip the yfinance round trip entirely.
    cache_key = tuple(sorted(tickers))
    cached = _CORRELATION_CACHE.get(cache_key)
    if cached and time.time() - cached["ts"] < _CORRELATION_CACHE_TTL:
        return copy.deepcopy(cached["data"])

    result = _compute_correlation_matrix(tickers)
    _CORRELATION_CACHE[cache_key] = {"data": result, "ts": time.time()}
    return copy.deepcopy(result)


def _compute_correlation_matrix(tickers: list[str]) -> dict:
    if len(tickers) < 2:
        return {"tickers": tickers, "matrix": [[1.0]], "labels": tickers}

    prices = fetch_prices(tickers, period="1y")
    returns = prices.pct_change().dropna()

    # Compute correlation matrix
    corr_matrix = returns.corr()

    # Reorder to match holdings order
    available = [t for t in tickers if t in corr_matrix.columns]
    corr_matrix = corr_matrix.loc[available, available]

    return {
        "tickers": available,
        "matrix": corr_matrix.values.tolist(),
        "labels": available,
    }
