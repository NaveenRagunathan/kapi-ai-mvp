"""MCP Server for Kalpi Portfolio Analyzer — exposes math engine tools via FastMCP."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Kalpi Portfolio Analyzer")


@mcp.tool()
def calculate_risk_metrics(holdings: list) -> dict:
    """Calculate portfolio risk metrics: Value at Risk (95%), Maximum Drawdown, Beta, and annualized volatility.

    Args:
        holdings: List of dicts with 'ticker' (str) and 'weight' (float) keys.
                  Example: [{"ticker": "RELIANCE.NS", "weight": 0.6}, {"ticker": "TCS.NS", "weight": 0.4}]

    Returns:
        Dict with keys: max_drawdown, value_at_risk_95, portfolio_beta, volatility_annualized
    """
    from app.math_engine import calculate_risk_metrics as _calc
    return _calc(holdings)


@mcp.tool()
def calculate_performance_metrics(holdings: list, benchmark_ticker: str = "^NSEI", timeframe: str = "1y") -> dict:
    """Calculate portfolio performance vs benchmark: CAGR, Sharpe ratio, Sortino ratio, and active return.

    Args:
        holdings: List of dicts with 'ticker' and 'weight' keys.
        benchmark_ticker: Benchmark ticker symbol (default: ^NSEI for Nifty 50, use ^GSPC for S&P 500)
        timeframe: Lookback period: "1y", "3y", or "5y"

    Returns:
        Dict with keys: portfolio_cagr, benchmark_cagr, portfolio_sharpe, benchmark_sharpe, active_return, sortino
    """
    from app.math_engine import calculate_performance_metrics as _calc
    return _calc(holdings, benchmark_ticker, timeframe)


@mcp.tool()
def get_diversification_and_sector_exposure(holdings: list) -> dict:
    """Analyze portfolio sector concentration and factor exposures (Size, Value, Momentum).

    Args:
        holdings: List of dicts with 'ticker' and 'weight' keys.

    Returns:
        Dict with 'sectors' (weighted breakdown) and 'factor_exposures' (Size, Value, Momentum scores 0-1)
    """
    from app.math_engine import get_diversification_and_sector_exposure as _calc
    return _calc(holdings)


@mcp.tool()
def run_what_if_simulation(holdings: list, sell_ticker: str, sell_weight: float, buy_ticker: str) -> dict:
    """Simulate swapping a portion of one asset for another and compare before/after metrics.

    Args:
        holdings: Current portfolio as list of dicts with 'ticker' and 'weight'.
        sell_ticker: Ticker symbol to reduce.
        sell_weight: Fraction of portfolio to move (e.g., 0.1 = 10%).
        buy_ticker: Ticker symbol to buy with the freed allocation.

    Returns:
        Dict with original_sharpe, simulated_sharpe, original_max_drawdown, simulated_max_drawdown, message
    """
    from app.math_engine import run_what_if_simulation as _calc
    return _calc(holdings, sell_ticker, sell_weight, buy_ticker)
