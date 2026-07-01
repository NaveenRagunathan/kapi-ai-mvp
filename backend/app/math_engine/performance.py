"""Performance metrics: CAGR, Sharpe, Sortino vs. benchmark."""

from app.market_data import fetch_prices, fetch_benchmark

from ._helpers import _extract_tickers_weights, _portfolio_daily_returns, _cagr, _sharpe, _sortino


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
