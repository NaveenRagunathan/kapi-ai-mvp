"""Portfolio ingestion business logic, kept separate from the HTTP route
handlers in main.py so it can be exercised without spinning up FastAPI."""

import logging

from fastapi import HTTPException

from app.agent import set_portfolio
from app.ingestion import ingest_portfolio

logger = logging.getLogger(__name__)


def calculate_weights(holdings_dicts: list[dict], session_id: str) -> list[dict]:
    """Normalize holding weights in place from raw_weight, falling back
    to invested-amount-derived weights, and finally to equal weighting."""
    has_raw_weights = any(h.get("raw_weight") is not None for h in holdings_dicts)
    if has_raw_weights:
        total_raw = sum(h.get("raw_weight", 0) or 0 for h in holdings_dicts)
        if total_raw == 0:
            # Log explicitly instead of silently producing fabricated equal weights
            logger.warning(
                "All raw_weights are zero for session %s — falling back to equal weights. "
                "This may indicate the LLM failed to extract weights.",
                session_id,
            )
        for h in holdings_dicts:
            h["weight"] = (
                (h.get("raw_weight") or 0) / total_raw
                if total_raw > 0
                else 1.0 / len(holdings_dicts)
            )
    else:
        invested_amounts = []
        for h in holdings_dicts:
            qty = h.get("quantity", 0) or 0
            price = h.get("avg_buy_price", 0) or 0
            invested_amounts.append(qty * price if qty else 0)
        total_invested = sum(invested_amounts)
        if total_invested == 0:
            logger.warning(
                "Total invested value is zero for session %s — falling back to equal weights.",
                session_id,
            )
        for idx, h in enumerate(holdings_dicts):
            h["weight"] = (
                invested_amounts[idx] / total_invested
                if total_invested > 0
                else 1.0 / len(holdings_dicts)
            )

    return holdings_dicts


def finalize_ingestion(session_id: str, result) -> dict:
    from app.math_engine import get_portfolio_baseline

    holdings_dicts = [h.model_dump() for h in result.holdings]
    holdings_dicts = calculate_weights(holdings_dicts, session_id)

    set_portfolio(session_id, holdings_dicts)

    baseline = get_portfolio_baseline(holdings_dicts)
    return {
        "session_id": session_id,
        "holdings": holdings_dicts,
        "count": len(holdings_dicts),
        "baseline": baseline,
    }


def ingest_text_blocking(session_id: str, text: str) -> dict:
    """Runs ingest_portfolio + finalize_ingestion off the event loop —
    both do blocking network I/O (Gemini + yfinance calls)."""
    result = ingest_portfolio(text=text)
    if not result.holdings:
        error_msg = "; ".join([e.message for e in result.errors]) or "No valid holdings found."
        raise HTTPException(status_code=400, detail=error_msg)
    return finalize_ingestion(session_id, result)


def ingest_file_blocking(session_id: str, file_bytes: bytes, file_type: str) -> dict:
    """Same as ingest_text_blocking, for the file-upload ingestion path."""
    result = ingest_portfolio(file_bytes=file_bytes, file_type=file_type)
    if not result.holdings:
        error_msg = "; ".join([e.message for e in result.errors]) or "No valid holdings found."
        raise HTTPException(status_code=400, detail=error_msg)
    return finalize_ingestion(session_id, result)
