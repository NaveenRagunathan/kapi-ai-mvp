"""Portfolio math: returns, volatility, Sharpe, drawdown, correlation, VaR.

The LLM NEVER computes numbers — it only calls these functions.
All numeric computation is deterministic and happens here.
"""

import math
import copy

import numpy as np
import pandas as pd

from app.market_data import fetch_prices, fetch_benchmark, get_metadata


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RF_DAILY = 0.06 / 252  # daily risk-free rate (6 % annualised)


def _extract_tickers_weights(holdings: list[dict]) -> tuple[list[str], np.ndarray]:
    """Return (tickers, weights_array) from a holdings list."""
    tickers = [h["ticker"] for h in holdings]
    weights = np.array([h["weight"] for h in holdings], dtype=float)
    return tickers, weights


def _portfolio_daily_returns(
    prices: pd.DataFrame, tickers: list[str], weights: np.ndarray
) -> pd.Series:
    """Compute weighted daily returns of the portfolio."""
    # Only keep columns present in the price DataFrame (order matters)
    valid = [(t, w) for t, w in zip(tickers, weights) if t in prices.columns]
    if not valid:
        raise ValueError("None of the requested tickers appear in the price data.")
    valid_tickers, valid_weights = zip(*valid)
    valid_weights = np.array(valid_weights, dtype=float)
    # Re-normalise so weights still sum to 1 after any missing-ticker drop
    valid_weights /= valid_weights.sum()

    daily_returns = prices[list(valid_tickers)].pct_change().dropna()
    port_returns = (daily_returns * valid_weights).sum(axis=1)
    return port_returns


def _cagr(daily_returns: pd.Series) -> float:
    """Compound Annual Growth Rate from a daily returns series."""
    n = len(daily_returns)
    if n == 0:
        return 0.0
    cumulative = (1 + daily_returns).prod() - 1
    return float((1 + cumulative) ** (252 / n) - 1)


def _sharpe(daily_returns: pd.Series) -> float:
    """Annualised Sharpe ratio (risk-free = 6 % p.a.)."""
    excess = daily_returns - _RF_DAILY
    std = daily_returns.std()
    if std == 0:
        return 0.0
    return float(excess.mean() / std * math.sqrt(252))


def _sortino(daily_returns: pd.Series) -> float:
    """Annualised Sortino ratio using only negative-return days for downside std."""
    excess = daily_returns - _RF_DAILY
    downside = daily_returns[daily_returns < 0]
    downside_std = downside.std()
    if downside_std == 0 or np.isnan(downside_std):
        return 0.0
    return float(excess.mean() / downside_std * math.sqrt(252))


# ---------------------------------------------------------------------------
# 3.1  Performance metrics
# ---------------------------------------------------------------------------


def calculate_performance_metrics(
    holdings: list[dict],
    benchmark_ticker: str = "^NSEI",
    timeframe: str = "1y",
) -> dict:
    """Compute portfolio and benchmark performance metrics.

    Returns
    -------
    dict with keys:
        portfolio_cagr, benchmark_cagr, portfolio_sharpe,
        benchmark_sharpe, active_return, sortino
    """
    tickers, weights = _extract_tickers_weights(holdings)

    prices = fetch_prices(tickers, period=timeframe)
    port_returns = _portfolio_daily_returns(prices, tickers, weights)

    bench_series = fetch_benchmark(benchmark_ticker, period=timeframe)
    bench_returns = bench_series.pct_change().dropna()

    portfolio_cagr = _cagr(port_returns)
    benchmark_cagr = _cagr(bench_returns)

    portfolio_sharpe = _sharpe(port_returns)
    benchmark_sharpe = _sharpe(bench_returns)

    active_return = portfolio_cagr - benchmark_cagr
    sortino = _sortino(port_returns)

    return {
        "portfolio_cagr": float(portfolio_cagr),
        "benchmark_cagr": float(benchmark_cagr),
        "portfolio_sharpe": float(portfolio_sharpe),
        "benchmark_sharpe": float(benchmark_sharpe),
        "active_return": float(active_return),
        "sortino": float(sortino),
    }


# ---------------------------------------------------------------------------
# 3.2  Risk metrics
# ---------------------------------------------------------------------------


def calculate_risk_metrics(holdings: list[dict]) -> dict:
    """Compute portfolio risk metrics using 3-year daily data.

    Returns
    -------
    dict with keys:
        max_drawdown, value_at_risk_95, portfolio_beta, volatility_annualized
    """
    tickers, weights = _extract_tickers_weights(holdings)

    prices = fetch_prices(tickers, period="3y")
    port_returns = _portfolio_daily_returns(prices, tickers, weights)

    # Max drawdown
    cum_returns = (1 + port_returns).cumprod()
    drawdown = cum_returns / cum_returns.cummax() - 1
    max_drawdown = float(drawdown.min())

    # VaR (95 %)
    var_95 = float(-np.percentile(port_returns.dropna(), 5))

    # Beta vs. benchmark
    bench_series = fetch_benchmark("^NSEI", period="3y")
    bench_returns = bench_series.pct_change().dropna()

    # Align on common dates
    combined = pd.concat([port_returns, bench_returns], axis=1).dropna()
    combined.columns = ["port", "bench"]

    bench_var = combined["bench"].var()
    if bench_var == 0:
        beta = 1.0
    else:
        beta = float(combined["port"].cov(combined["bench"]) / bench_var)

    # Annualised volatility
    volatility_annualized = float(port_returns.std() * math.sqrt(252))

    return {
        "max_drawdown": max_drawdown,
        "value_at_risk_95": var_95,
        "portfolio_beta": beta,
        "volatility_annualized": volatility_annualized,
    }


# ---------------------------------------------------------------------------
# 3.3  Diversification & sector exposure
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 3.4  What-if simulation
# ---------------------------------------------------------------------------


def run_what_if_simulation(
    holdings: list[dict],
    sell_ticker: str,
    sell_weight: float,
    buy_ticker: str,
) -> dict:
    """Simulate the effect of replacing ``sell_weight`` of ``sell_ticker``
    with ``buy_ticker``.

    Returns
    -------
    dict with keys:
        original_sharpe, simulated_sharpe,
        original_max_drawdown, simulated_max_drawdown,
        message
    """
    # --- Build modified holdings ------------------------------------------
    modified = copy.deepcopy(holdings)

    # Reduce sell_ticker allocation
    for h in modified:
        if h["ticker"] == sell_ticker:
            h["weight"] = max(0.0, h["weight"] - sell_weight)
            break

    # Increase buy_ticker allocation (add entry if not present)
    buy_found = False
    for h in modified:
        if h["ticker"] == buy_ticker:
            h["weight"] += sell_weight
            buy_found = True
            break
    if not buy_found:
        modified.append({"ticker": buy_ticker, "weight": sell_weight})

    # Remove zero-weight entries
    modified = [h for h in modified if h["weight"] > 0]

    # Re-normalise weights to sum = 1.0
    total = sum(h["weight"] for h in modified)
    if total > 0:
        for h in modified:
            h["weight"] /= total

    # --- Compute metrics for original and simulated portfolios ------------
    original_perf = calculate_performance_metrics(holdings)
    original_risk = calculate_risk_metrics(holdings)

    simulated_perf = calculate_performance_metrics(modified)
    simulated_risk = calculate_risk_metrics(modified)

    original_sharpe = float(original_perf["portfolio_sharpe"])
    simulated_sharpe = float(simulated_perf["portfolio_sharpe"])
    original_max_drawdown = float(original_risk["max_drawdown"])
    simulated_max_drawdown = float(simulated_risk["max_drawdown"])

    sharpe_delta = simulated_sharpe - original_sharpe
    drawdown_delta = simulated_max_drawdown - original_max_drawdown

    direction = "improves" if sharpe_delta >= 0 else "reduces"
    drawdown_dir = "improves" if drawdown_delta >= 0 else "worsens"

    message = (
        f"Selling {sell_weight * 100:.1f}% of {sell_ticker} and buying {buy_ticker} "
        f"{direction} the Sharpe ratio by {sharpe_delta:+.3f} "
        f"(from {original_sharpe:.3f} to {simulated_sharpe:.3f}) and "
        f"{drawdown_dir} max drawdown by {drawdown_delta:+.3f} "
        f"(from {original_max_drawdown:.3f} to {simulated_max_drawdown:.3f})."
    )

    return {
        "original_sharpe": original_sharpe,
        "simulated_sharpe": simulated_sharpe,
        "original_max_drawdown": original_max_drawdown,
        "simulated_max_drawdown": simulated_max_drawdown,
        "message": message,
    }
