"""Tests for backend/app/math_engine.py — all external I/O is mocked."""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Synthetic data fixtures
# ---------------------------------------------------------------------------

dates = pd.date_range("2022-01-01", periods=756, freq="B")
np.random.seed(42)
prices = pd.DataFrame(
    {
        "AAPL": 150 * np.cumprod(1 + np.random.normal(0.0005, 0.015, 756)),
        "MSFT": 300 * np.cumprod(1 + np.random.normal(0.0006, 0.012, 756)),
    },
    index=dates,
)
benchmark = pd.Series(
    100 * np.cumprod(1 + np.random.normal(0.0004, 0.010, 756)),
    index=dates,
    name="^NSEI",
)

holdings = [{"ticker": "AAPL", "weight": 0.6}, {"ticker": "MSFT", "weight": 0.4}]

FAKE_METADATA = {
    "AAPL": {
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3_000_000_000_000,
        "pe_ratio": 28.5,
    },
    "MSFT": {
        "sector": "Technology",
        "industry": "Software",
        "market_cap": 2_800_000_000_000,
        "pe_ratio": 32.0,
    },
}


def _mock_fetch_prices(tickers, period="3y"):
    """Return synthetic prices filtered to requested tickers."""
    cols = [t for t in tickers if t in prices.columns]
    if not cols:
        # Unknown ticker (e.g. buy_ticker in what-if): return a synthetic series
        return pd.DataFrame(
            {
                tickers[0]: 100
                * np.cumprod(1 + np.random.normal(0.0003, 0.012, 756))
            },
            index=dates,
        )
    return prices[cols].copy()


def _mock_fetch_benchmark(ticker="^NSEI", period="3y"):
    return benchmark.copy()


def _mock_get_metadata(tickers):
    return {
        t: FAKE_METADATA.get(
            t,
            {
                "sector": "Unknown",
                "industry": "Unknown",
                "market_cap": 5_000_000_000,
                "pe_ratio": None,
            },
        )
        for t in tickers
    }


# ---------------------------------------------------------------------------
# 3.1  calculate_performance_metrics
# ---------------------------------------------------------------------------


@patch("app.math_engine.get_metadata")
@patch("app.math_engine.fetch_benchmark", side_effect=_mock_fetch_benchmark)
@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
def test_performance_metrics_returns_expected_keys(mock_fp, mock_fb, mock_gm):
    from app.math_engine import calculate_performance_metrics

    result = calculate_performance_metrics(holdings)

    expected_keys = {
        "portfolio_cagr",
        "benchmark_cagr",
        "portfolio_sharpe",
        "benchmark_sharpe",
        "active_return",
        "sortino",
    }
    assert set(result.keys()) == expected_keys, f"Keys mismatch: {set(result.keys())}"
    for k, v in result.items():
        assert isinstance(v, float), f"Expected float for {k}, got {type(v)}"


@patch("app.math_engine.get_metadata")
@patch("app.math_engine.fetch_benchmark", side_effect=_mock_fetch_benchmark)
@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
def test_performance_metrics_sharpe_is_reasonable(mock_fp, mock_fb, mock_gm):
    from app.math_engine import calculate_performance_metrics

    result = calculate_performance_metrics(holdings)

    assert -5 <= result["portfolio_sharpe"] <= 10, (
        f"portfolio_sharpe out of range: {result['portfolio_sharpe']}"
    )
    assert -5 <= result["benchmark_sharpe"] <= 10, (
        f"benchmark_sharpe out of range: {result['benchmark_sharpe']}"
    )


# ---------------------------------------------------------------------------
# 3.2  calculate_risk_metrics
# ---------------------------------------------------------------------------


@patch("app.math_engine.fetch_benchmark", side_effect=_mock_fetch_benchmark)
@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
def test_risk_metrics_returns_expected_keys(mock_fp, mock_fb):
    from app.math_engine import calculate_risk_metrics

    result = calculate_risk_metrics(holdings)

    expected_keys = {
        "max_drawdown",
        "value_at_risk_95",
        "portfolio_beta",
        "volatility_annualized",
    }
    assert set(result.keys()) == expected_keys, f"Keys mismatch: {set(result.keys())}"
    for k, v in result.items():
        assert isinstance(v, float), f"Expected float for {k}, got {type(v)}"


@patch("app.math_engine.fetch_benchmark", side_effect=_mock_fetch_benchmark)
@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
def test_risk_metrics_max_drawdown_is_negative(mock_fp, mock_fb):
    from app.math_engine import calculate_risk_metrics

    result = calculate_risk_metrics(holdings)

    assert result["max_drawdown"] < 0, (
        f"max_drawdown should be negative, got {result['max_drawdown']}"
    )


@patch("app.math_engine.fetch_benchmark", side_effect=_mock_fetch_benchmark)
@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
def test_risk_metrics_var_is_positive(mock_fp, mock_fb):
    from app.math_engine import calculate_risk_metrics

    result = calculate_risk_metrics(holdings)

    assert result["value_at_risk_95"] > 0, (
        f"value_at_risk_95 should be positive, got {result['value_at_risk_95']}"
    )


# ---------------------------------------------------------------------------
# 3.3  get_diversification_and_sector_exposure
# ---------------------------------------------------------------------------


@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
@patch("app.math_engine.get_metadata", side_effect=_mock_get_metadata)
def test_diversification_returns_sectors_and_factors(mock_gm, mock_fp):
    from app.math_engine import get_diversification_and_sector_exposure

    result = get_diversification_and_sector_exposure(holdings)

    assert "sectors" in result, "Missing 'sectors' key"
    assert "factor_exposures" in result, "Missing 'factor_exposures' key"

    sectors = result["sectors"]
    assert isinstance(sectors, dict), "sectors must be a dict"
    assert len(sectors) > 0, "sectors must not be empty"

    factor_exposures = result["factor_exposures"]
    assert isinstance(factor_exposures, dict), "factor_exposures must be a dict"
    for factor in ("Size", "Value", "Momentum"):
        assert factor in factor_exposures, f"Missing factor: {factor}"
        val = factor_exposures[factor]
        assert isinstance(val, float), f"Expected float for factor {factor}, got {type(val)}"
        assert 0.0 <= val <= 1.0, f"Factor {factor} out of [0,1] range: {val}"


# ---------------------------------------------------------------------------
# 3.4  run_what_if_simulation
# ---------------------------------------------------------------------------


@patch("app.math_engine.get_metadata")
@patch("app.math_engine.fetch_benchmark", side_effect=_mock_fetch_benchmark)
@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
def test_what_if_returns_expected_keys(mock_fp, mock_fb, mock_gm):
    from app.math_engine import run_what_if_simulation

    result = run_what_if_simulation(
        holdings,
        sell_ticker="AAPL",
        sell_weight=0.1,
        buy_ticker="MSFT",
    )

    expected_keys = {
        "original_sharpe",
        "simulated_sharpe",
        "original_max_drawdown",
        "simulated_max_drawdown",
        "message",
    }
    assert set(result.keys()) == expected_keys, f"Keys mismatch: {set(result.keys())}"
    for k in (
        "original_sharpe",
        "simulated_sharpe",
        "original_max_drawdown",
        "simulated_max_drawdown",
    ):
        assert isinstance(result[k], float), f"Expected float for {k}, got {type(result[k])}"
    assert isinstance(result["message"], str)


@patch("app.math_engine.get_metadata")
@patch("app.math_engine.fetch_benchmark", side_effect=_mock_fetch_benchmark)
@patch("app.math_engine.fetch_prices", side_effect=_mock_fetch_prices)
def test_what_if_message_mentions_tickers(mock_fp, mock_fb, mock_gm):
    from app.math_engine import run_what_if_simulation

    sell_t = "AAPL"
    buy_t = "MSFT"
    result = run_what_if_simulation(
        holdings,
        sell_ticker=sell_t,
        sell_weight=0.1,
        buy_ticker=buy_t,
    )

    msg = result["message"]
    assert sell_t in msg, f"sell_ticker '{sell_t}' not found in message: {msg!r}"
    assert buy_t in msg, f"buy_ticker '{buy_t}' not found in message: {msg!r}"
