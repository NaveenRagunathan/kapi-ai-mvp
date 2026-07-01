"""Diversification & sector exposure (factor heuristics)."""

from app.market_data import fetch_prices, get_metadata

from ._helpers import _extract_tickers_weights


def get_diversification_and_sector_exposure(holdings: list[dict]) -> dict:
    """Compute sector breakdown and factor exposures.

    Returns
    -------
    dict with keys:
        sectors (dict sector -> float weight),
        factor_exposures (dict with Size, Value, Momentum floats in [0, 1])
    """
    tickers, weights = _extract_tickers_weights(holdings)
    metadata = get_metadata(tickers)

    # --- Sector breakdown -------------------------------------------------
    sectors: dict[str, float] = {}
    for ticker, weight in zip(tickers, weights):
        sector = metadata.get(ticker, {}).get("sector", "Unknown") or "Unknown"
        sectors[sector] = sectors.get(sector, 0.0) + float(weight)

    # --- Factor heuristics ------------------------------------------------

    # Size: fraction of portfolio in large-cap (> $10B) stocks
    size_score = 0.0
    for ticker, weight in zip(tickers, weights):
        mc = metadata.get(ticker, {}).get("market_cap", 0) or 0
        if mc > 10_000_000_000:
            size_score += float(weight)
    # Clamp to [0, 1] just in case weights don't sum to exactly 1
    size_score = float(min(max(size_score, 0.0), 1.0))

    # Value: 1 / (1 + P/E), weighted average; default 0.5 when P/E is unknown
    value_score = 0.0
    total_weight = float(weights.sum())
    for ticker, weight in zip(tickers, weights):
        pe = metadata.get(ticker, {}).get("pe_ratio", None)
        if pe is not None and pe > 0:
            v = 1.0 / (1.0 + pe)
        else:
            v = 0.5
        value_score += float(weight) * v
    if total_weight > 0:
        value_score /= total_weight
    value_score = float(min(max(value_score, 0.0), 1.0))

    # Momentum: 12-month trailing return per ticker, weighted avg, normalised [0, 1]
    prices_1y = fetch_prices(tickers, period="1y")
    ticker_returns: dict[str, float] = {}
    for ticker in tickers:
        if ticker in prices_1y.columns:
            col = prices_1y[ticker].dropna()
            if len(col) >= 2:
                ret = float(col.iloc[-1] / col.iloc[0] - 1)
            else:
                ret = 0.0
        else:
            ret = 0.0
        ticker_returns[ticker] = ret

    ret_values = list(ticker_returns.values())
    min_ret, max_ret = min(ret_values), max(ret_values)
    span = max_ret - min_ret

    momentum_score = 0.0
    for ticker, weight in zip(tickers, weights):
        raw = ticker_returns.get(ticker, 0.0)
        if span > 0:
            norm = (raw - min_ret) / span
        else:
            norm = 0.5
        momentum_score += float(weight) * norm
    if total_weight > 0:
        momentum_score /= total_weight
    momentum_score = float(min(max(momentum_score, 0.0), 1.0))

    return {
        "sectors": sectors,
        "factor_exposures": {
            "Size": size_score,
            "Value": value_score,
            "Momentum": momentum_score,
        },
    }
