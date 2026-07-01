"""Portfolio math: returns, volatility, Sharpe, drawdown, correlation, VaR.

The LLM NEVER computes numbers — it only calls these functions.
All numeric computation is deterministic and happens here.

Split into submodules by concern (performance, risk, diversification,
whatif, correlation, holdings, health, baseline). This __init__ re-exports
the public API so callers can keep doing `from app.math_engine import X`.
"""

from app.market_data import fetch_prices, fetch_benchmark, get_metadata

from .performance import calculate_performance_metrics
from .risk import calculate_risk_metrics
from .diversification import get_diversification_and_sector_exposure
from .whatif import run_what_if_simulation
from .correlation import get_correlation_matrix
from .holdings import get_holdings_detail
from .health import get_portfolio_health_and_swot
from .baseline import get_portfolio_baseline

__all__ = [
    "calculate_performance_metrics",
    "calculate_risk_metrics",
    "get_diversification_and_sector_exposure",
    "run_what_if_simulation",
    "get_correlation_matrix",
    "get_holdings_detail",
    "get_portfolio_health_and_swot",
    "get_portfolio_baseline",
]
