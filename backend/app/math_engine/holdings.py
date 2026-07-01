"""Per-holding detail (invested value, live price, trend signal)."""

import math

from app.market_data import fetch_prices, get_metadata


def get_holdings_detail(holdings: list[dict]) -> list[dict]:
    """Compute detailed holdings with actual invested values, historical returns, and trend signals."""
    tickers = [h["ticker"] for h in holdings]
    metadata = get_metadata(tickers)

    # Fetch 1y price data to compute 1y return and last day return
    prices_1y = fetch_prices(tickers, period="1y")

    details = []
    for h in holdings:
        ticker = h["ticker"]
        weight = h.get("weight")
        if weight is None or (isinstance(weight, float) and math.isnan(weight)):
            invested_amounts = []
            for other_h in holdings:
                o_qty = other_h.get("quantity", 0) or 0
                o_price = other_h.get("avg_buy_price") or other_h.get("invested_amount") or 0
                invested_amounts.append(float(o_qty) * float(o_price) if o_qty else float(o_price))
            total_invested = sum(invested_amounts)

            qty = h.get("quantity", 0) or 0
            price = h.get("avg_buy_price") or h.get("invested_amount") or 0
            this_invested = float(qty) * float(price) if qty else float(price)
            weight = this_invested / total_invested if total_invested > 0 else 1.0 / len(holdings)

        name = h.get("name") or metadata.get(ticker, {}).get("name") or ticker

        live_price = 100.0
        overall_return = 0.0
        today_return = 0.0

        col = []
        if ticker in prices_1y.columns:
            col = prices_1y[ticker].dropna()
            if len(col) >= 2:
                live_price = float(col.iloc[-1])
                today_return = float(col.iloc[-1] / col.iloc[-2] - 1.0)
                overall_return = float(col.iloc[-1] / col.iloc[0] - 1.0)
            elif len(col) == 1:
                live_price = float(col.iloc[0])

        qty = h.get("quantity")
        user_invested = h.get("invested_amount")

        if qty is not None and qty > 0:
            current_value = float(qty * live_price)
            if user_invested is not None and user_invested > 0:
                invested_value = float(user_invested)
            else:
                invested_value = current_value / (1.0 + overall_return) if overall_return > -0.9 else current_value
        else:
            current_value = weight * 100000.0
            invested_value = current_value / (1.0 + overall_return) if overall_return > -0.9 else current_value

        pl_value = current_value - invested_value
        if invested_value > 0:
            overall_return = pl_value / invested_value

        today_pl = current_value * today_return

        if len(col) >= 50:
            sma_50 = float(col.iloc[-50:].mean())
            signal = "Trending Up" if live_price > sma_50 else "Downtrend"
        else:
            signal = "Trending Up" if overall_return > 0.05 else "Downtrend" if overall_return < -0.05 else "Neutral"

        details.append({
            "ticker": ticker,
            "name": name,
            "weight": weight,
            "live_price": live_price,
            "invested_value": invested_value,
            "current_value": current_value,
            "pl_percent": overall_return,
            "pl_value": pl_value,
            "today_percent": today_return,
            "today_pl": today_pl,
            "signal": signal
        })
    return details
