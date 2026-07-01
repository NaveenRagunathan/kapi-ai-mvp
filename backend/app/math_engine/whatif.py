"""What-if trade simulation."""

import copy

from .performance import calculate_performance_metrics
from .risk import calculate_risk_metrics


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
    # Normalize tickers and resolve matching tickers in holdings/suffixes
    sell_ticker = sell_ticker.upper().strip()
    buy_ticker = buy_ticker.upper().strip()

    def find_matching_ticker(name: str) -> str:
        for h in holdings:
            if h["ticker"].upper() == name:
                return h["ticker"]
        name_base = name.split(".")[0]
        for h in holdings:
            h_base = h["ticker"].split(".")[0].upper()
            if h_base == name_base:
                return h["ticker"]
        try:
            from app.market_data import resolve_ticker_metadata
            meta = resolve_ticker_metadata(name)
            if meta.get("valid"):
                return meta["ticker"]
        except Exception:
            pass
        return name

    sell_resolved = find_matching_ticker(sell_ticker)
    buy_resolved = find_matching_ticker(buy_ticker)

    # --- Build modified holdings ------------------------------------------
    modified = copy.deepcopy(holdings)

    # Reduce sell_ticker allocation
    for h in modified:
        if h["ticker"] == sell_resolved:
            h["weight"] = max(0.0, h["weight"] - sell_weight)
            break

    # Increase buy_ticker allocation (add entry if not present)
    buy_found = False
    for h in modified:
        if h["ticker"] == buy_resolved:
            h["weight"] += sell_weight
            buy_found = True
            break
    if not buy_found:
        modified.append({"ticker": buy_resolved, "weight": sell_weight})

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
        f"Selling {sell_weight * 100:.1f}% of {sell_resolved} and buying {buy_resolved} "
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
