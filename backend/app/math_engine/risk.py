"""Risk metrics: max drawdown, VaR, beta, volatility."""

import math

import numpy as np
import pandas as pd

from app.market_data import fetch_prices, fetch_benchmark

from ._helpers import _extract_tickers_weights, _portfolio_daily_returns


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
