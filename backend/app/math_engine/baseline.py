"""Assembles the full baseline package returned on portfolio ingestion."""

import pandas as pd

from app.market_data import fetch_prices, fetch_benchmark

from ._helpers import _extract_tickers_weights, _portfolio_daily_returns
from .performance import calculate_performance_metrics
from .risk import calculate_risk_metrics
from .diversification import get_diversification_and_sector_exposure
from .correlation import get_correlation_matrix
from .holdings import get_holdings_detail
from .health import get_portfolio_health_and_swot


def get_portfolio_baseline(holdings: list[dict]) -> dict:
    """Generate the complete baseline package for the portfolio on ingestion."""
    perf = calculate_performance_metrics(holdings)
    risk = calculate_risk_metrics(holdings)
    div = get_diversification_and_sector_exposure(holdings)
    corr = get_correlation_matrix(holdings)

    # Calculate 1Y Comparison Chart data for UI visualization
    comparison_list = []
    try:
        tickers, weights = _extract_tickers_weights(holdings)
        prices_1y = fetch_prices(tickers, period="1y")
        port_returns_1y = _portfolio_daily_returns(prices_1y, tickers, weights)
        bench_series_1y = fetch_benchmark("^NSEI", period="1y")
        bench_returns_1y = bench_series_1y.pct_change().dropna()

        combined_1y = pd.concat([port_returns_1y, bench_returns_1y], axis=1).dropna()
        combined_1y.columns = ["port", "bench"]
        if not combined_1y.empty:
            cum_port = (1 + combined_1y["port"]).cumprod()
            cum_bench = (1 + combined_1y["bench"]).cumprod()

            # Start comparison base at 100.0
            start_date = combined_1y.index[0] - pd.Timedelta(days=1)
            comparison_list.append({
                "date": start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date),
                "portfolio": 100.0,
                "benchmark": 100.0
            })
            for date, row in combined_1y.iterrows():
                comparison_list.append({
                    "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
                    "portfolio": float(cum_port.loc[date] * 100),
                    "benchmark": float(cum_bench.loc[date] * 100)
                })
    except Exception:
        pass
    perf["comparison"] = comparison_list

    # Calculate 3Y Drawdown Chart data for UI visualization
    drawdown_list = []
    try:
        tickers, weights = _extract_tickers_weights(holdings)
        prices_3y = fetch_prices(tickers, period="3y")
        port_returns_3y = _portfolio_daily_returns(prices_3y, tickers, weights)
        cum_returns_3y = (1 + port_returns_3y).cumprod()
        drawdown_series = cum_returns_3y / cum_returns_3y.cummax() - 1
        for date, val in drawdown_series.items():
            drawdown_list.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
                "drawdown": float(val)
            })
    except Exception:
        pass
    risk["drawdown"] = drawdown_list

    holdings_detail = get_holdings_detail(holdings)
    health = get_portfolio_health_and_swot(holdings, perf, risk, div)

    total_investment = sum(h["invested_value"] for h in holdings_detail)
    portfolio_worth = sum(h["current_value"] for h in holdings_detail)
    total_returns = portfolio_worth - total_investment
    total_returns_pct = (total_returns / total_investment) if total_investment > 0 else 0.0

    today_gain = sum(h["today_pl"] for h in holdings_detail)
    today_pct = (today_gain / portfolio_worth) if portfolio_worth > 0 else 0.0

    return {
        "summary": {
            "total_investment": total_investment,
            "portfolio_worth": portfolio_worth,
            "total_returns": total_returns,
            "total_returns_pct": total_returns_pct,
            "today_gain": today_gain,
            "today_pct": today_pct,
            "health_score": health["score"],
            "health_grade": health["grade"]
        },
        "health": health,
        "holdings": holdings_detail,
        "performance": perf,
        "risk": risk,
        "diversification": div,
        "correlation": corr
    }
