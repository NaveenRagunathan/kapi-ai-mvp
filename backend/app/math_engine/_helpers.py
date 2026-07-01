"""Shared internal helpers used across the math_engine submodules."""

import math

import numpy as np
import pandas as pd

_RF_DAILY = 0.06 / 252  # daily risk-free rate (6 % annualised)


def _extract_tickers_weights(holdings: list[dict]) -> tuple[list[str], np.ndarray]:
    """Return (tickers, weights_array) from a holdings list."""
    tickers = [h["ticker"] for h in holdings]

    # Dynamically compute weights if they are missing, None, or NaN
    has_weights = all(h.get("weight") is not None and not (isinstance(h.get("weight"), float) and math.isnan(h.get("weight"))) for h in holdings)
    if not has_weights:
        invested_amounts = []
        for h in holdings:
            qty = h.get("quantity", 0) or 0
            price = h.get("avg_buy_price") or h.get("invested_amount") or 0
            if qty and price:
                invested_amounts.append(float(qty) * float(price))
            elif price:
                invested_amounts.append(float(price))
            else:
                invested_amounts.append(0.0)
        total_invested = sum(invested_amounts)
        if total_invested > 0:
            weights = np.array([amt / total_invested for amt in invested_amounts], dtype=float)
        else:
            weights = np.array([1.0 / len(holdings)] * len(holdings), dtype=float)
    else:
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
