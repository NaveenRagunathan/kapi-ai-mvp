"""Portfolio health score, grade, and SWOT insight generation."""


def get_portfolio_health_and_swot(holdings: list[dict], perf: dict, risk: dict, div: dict) -> dict:
    """Generate dynamic health score, grade, and SWOT insights from mathematical results."""
    sharpe = float(perf.get("portfolio_sharpe", 0.5))
    mdd = abs(float(risk.get("max_drawdown", -0.15)))

    sectors = div.get("sectors", {})
    hhi = sum(w**2 for w in sectors.values())

    score = 60.0 + (sharpe * 15.0) - (mdd * 40.0) - (hhi * 20.0)
    score = min(max(score, 30.0), 99.0)

    if score >= 90:
        grade = "A+"
    elif score >= 80:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 60:
        grade = "C+"
    elif score >= 50:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    strengths = []
    weaknesses = []
    opportunities = []
    threats = []

    max_sector = max(sectors.items(), key=lambda x: x[1]) if sectors else ("None", 0.0)
    if max_sector[1] > 0.40:
        weaknesses.append(f"High concentration in {max_sector[0]} sector ({max_sector[1]*100:.1f}%) increases sector correction vulnerability.")
        opportunities.append(f"Consider diversifying 10-15% of your {max_sector[0]} holdings into defensive sectors like Gold or Technology.")
    else:
        strengths.append(f"Well diversified across {len(sectors)} sectors (max sector exposure: {max_sector[1]*100:.1f}%).")

    if sharpe > 1.0:
        strengths.append(f"Outstanding risk-adjusted performance (Sharpe Ratio: {sharpe:.2f}) outperforming the broader benchmark.")
    elif sharpe > 0.0:
        strengths.append(f"Positive Sharpe Ratio of {sharpe:.2f} indicates positive risk-adjusted excess returns.")
    else:
        weaknesses.append(f"Negative risk-adjusted return (Sharpe Ratio: {sharpe:.2f}) indicates poor compensation for downside volatility.")

    if mdd > 0.25:
        threats.append(f"High historical maximum drawdown of {mdd*100:.1f}% indicates severe downside risk during market pullbacks.")
    else:
        strengths.append(f"Moderate historical maximum drawdown of {mdd*100:.1f}%, reflecting disciplined downside protection.")

    beta = float(risk.get("portfolio_beta", 1.0))
    if beta > 1.2:
        threats.append(f"High market sensitivity (Beta: {beta:.2f}) exposes the portfolio to exaggerated losses during market sell-offs.")
        opportunities.append("Add low-beta or inverse-correlated assets (like Gold ETF) to dampen market shocks.")
    elif beta < 0.8:
        strengths.append(f"Defensive profile (Beta: {beta:.2f}) provides a buffer against systemic market declines.")
    else:
        strengths.append(f"Market-matching beta profile ({beta:.2f}) allows participating fully in equity market rallies.")

    if not weaknesses:
        weaknesses.append("No critical capital efficiency weaknesses identified.")
    if not opportunities:
        opportunities.append("Explore factor-tilted ETFs (e.g. Value or Quality) to capture historical premiums.")
    if not threats:
        threats.append("Rising inflation or sudden interest rate hikes could compress short-term equity valuations.")

    return {
        "score": round(score, 1),
        "grade": grade,
        "swot": {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "opportunities": opportunities,
            "threats": threats
        }
    }
