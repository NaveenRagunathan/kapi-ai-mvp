"""Handles ingestion of portfolio data from uploaded files (CSV, XLSX, etc.)."""
from __future__ import annotations

import csv
import io
import re
from typing import Optional

import openpyxl
import yfinance as yf

# ── Column-name aliases ───────────────────────────────────────────────────────

_TICKER_ALIASES = {"ticker", "symbol", "stock"}
_WEIGHT_ALIASES = {"weight", "weights", "allocation"}
_QUANTITY_ALIASES = {"quantity", "qty", "shares"}


def _find_column(headers_lower: list[str], aliases: set[str]) -> Optional[int]:
    """Return the index of the first header that matches any alias, or None."""
    for idx, h in enumerate(headers_lower):
        if h in aliases:
            return idx
    return None


def _to_float(value) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


# ── 1.1  File Parsers ─────────────────────────────────────────────────────────

def parse_csv(file_bytes: bytes) -> list[dict]:
    """Parse CSV bytes.

    Accepts case-insensitive column aliases for ticker/symbol/stock and
    weight/weights/allocation/quantity/qty/shares.

    Returns list of {"ticker": str, "raw_weight": float|None, "quantity": float|None}.
    """
    text = file_bytes.decode("utf-8-sig")  # handle BOM
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    headers_raw = rows[0]
    headers_lower = [h.strip().lower() for h in headers_raw]

    ticker_idx = _find_column(headers_lower, _TICKER_ALIASES)
    weight_idx = _find_column(headers_lower, _WEIGHT_ALIASES)
    qty_idx = _find_column(headers_lower, _QUANTITY_ALIASES)

    if ticker_idx is None:
        raise ValueError(f"No ticker column found. Headers: {headers_raw}")

    results: list[dict] = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        ticker = row[ticker_idx].strip() if ticker_idx < len(row) else ""
        if not ticker:
            continue

        raw_weight = _to_float(row[weight_idx]) if weight_idx is not None and weight_idx < len(row) else None
        quantity = _to_float(row[qty_idx]) if qty_idx is not None and qty_idx < len(row) else None

        results.append({"ticker": ticker, "raw_weight": raw_weight, "quantity": quantity})

    return results


def parse_excel(file_bytes: bytes) -> list[dict]:
    """Parse .xlsx bytes using openpyxl. Same output as parse_csv."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers_raw = [str(h) if h is not None else "" for h in rows[0]]
    headers_lower = [h.strip().lower() for h in headers_raw]

    ticker_idx = _find_column(headers_lower, _TICKER_ALIASES)
    weight_idx = _find_column(headers_lower, _WEIGHT_ALIASES)
    qty_idx = _find_column(headers_lower, _QUANTITY_ALIASES)

    if ticker_idx is None:
        raise ValueError(f"No ticker column found. Headers: {headers_raw}")

    results: list[dict] = []
    for row in rows[1:]:
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue
        ticker_val = row[ticker_idx] if ticker_idx < len(row) else None
        ticker = str(ticker_val).strip() if ticker_val is not None else ""
        if not ticker:
            continue

        raw_weight = _to_float(row[weight_idx]) if weight_idx is not None and weight_idx < len(row) else None
        quantity = _to_float(row[qty_idx]) if qty_idx is not None and qty_idx < len(row) else None

        results.append({"ticker": ticker, "raw_weight": raw_weight, "quantity": quantity})

    wb.close()
    return results


# ── 1.2  Text-to-Portfolio Regex Engine ───────────────────────────────────────

# Pattern variants (tried in order):
#   1. "<number>% <TICKER>"  — percentage before ticker
#   2. "<TICKER> <number>%"  — percentage after ticker
#   3. "<TICKER> <decimal>"  — decimal weight (0 < x <= 1)
#   4. "<TICKER>: <number>"  — colon quantity mode

_RE_PCT_BEFORE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*([A-Za-z][A-Za-z0-9.&_-]{0,19})")
_RE_PCT_AFTER = re.compile(r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s+(\d+(?:\.\d+)?)\s*%")
_RE_DECIMAL = re.compile(r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s+(\d*\.\d+)")
_RE_COLON_QTY = re.compile(r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s*:\s*(\d+(?:\.\d+)?)")


def parse_text_input(text: str) -> list[dict]:
    """Parse free text portfolio descriptions.

    Supported formats:
    - "50% AAPL, 50% MSFT"         → weight mode (percentage before ticker)
    - "AAPL 60%, MSFT 40%"         → weight mode (percentage after ticker)
    - "AAPL 0.5, MSFT 0.5"         → decimal weight mode
    - "Reliance: 10, TCS: 5"       → quantity mode

    Returns list of {"ticker": str, "raw_weight": float|None, "quantity": float|None}.
    """
    if not text or not text.strip():
        return []

    # Try percentage-before-ticker first
    matches_pct_before = _RE_PCT_BEFORE.findall(text)
    if matches_pct_before:
        return [
            {"ticker": t.upper(), "raw_weight": float(w), "quantity": None}
            for w, t in matches_pct_before
        ]

    # Try percentage-after-ticker
    matches_pct_after = _RE_PCT_AFTER.findall(text)
    if matches_pct_after:
        return [
            {"ticker": t.upper(), "raw_weight": float(w), "quantity": None}
            for t, w in matches_pct_after
        ]

    # Try colon-quantity mode (must come before decimal to avoid mis-classifying)
    matches_colon = _RE_COLON_QTY.findall(text)
    if matches_colon:
        return [
            {"ticker": t.upper(), "raw_weight": None, "quantity": float(q)}
            for t, q in matches_colon
        ]

    # Try decimal weight mode
    matches_decimal = _RE_DECIMAL.findall(text)
    if matches_decimal:
        return [
            {"ticker": t.upper(), "raw_weight": float(w), "quantity": None}
            for t, w in matches_decimal
        ]

    return []


# ── 1.3  Ticker Validator ─────────────────────────────────────────────────────

def _ticker_info_valid(info: dict) -> bool:
    """Return True when the yfinance info dict indicates a real instrument."""
    # yfinance returns an empty dict or minimal dict for invalid tickers
    return bool(info) and (
        "regularMarketPrice" in info
        or "currentPrice" in info
        or "previousClose" in info
        or "shortName" in info
        or "longName" in info
    )


def validate_tickers(holdings: list[dict]) -> list[dict]:
    """Validate each ticker via yfinance.

    Auto-appends .NS for Indian stocks when the plain ticker fails.
    Adds "valid": bool and "name": str to each holding.
    """
    results = []
    for holding in holdings:
        h = dict(holding)
        ticker = h["ticker"]

        # --- attempt 1: ticker as-is ---
        try:
            info = yf.Ticker(ticker).info
        except Exception:
            info = {}

        if _ticker_info_valid(info):
            h["valid"] = True
            h["name"] = info.get("shortName") or info.get("longName") or ticker
            results.append(h)
            continue

        # --- attempt 2: try ticker + ".NS" (Indian NSE) ---
        if not ticker.endswith(".NS"):
            ns_ticker = ticker + ".NS"
            try:
                ns_info = yf.Ticker(ns_ticker).info
            except Exception:
                ns_info = {}

            if _ticker_info_valid(ns_info):
                h["ticker"] = ns_ticker
                h["valid"] = True
                h["name"] = ns_info.get("shortName") or ns_info.get("longName") or ns_ticker
                results.append(h)
                continue

        # --- both attempts failed ---
        h["valid"] = False
        h["name"] = ""
        results.append(h)

    return results


# ── 1.4  Normalizer ───────────────────────────────────────────────────────────

def normalize_weights(holdings: list[dict]) -> list[dict]:
    """Compute final portfolio weights.

    - Filters out invalid holdings.
    - If raw_weight provided: normalise so sum == 1.0.
    - If quantity provided: fetch current price via yfinance, compute value weights.

    Returns list of {"ticker": str, "weight": float, "name": str}.
    """
    valid_holdings = [h for h in holdings if h.get("valid", True)]

    if not valid_holdings:
        return []

    # Determine mode from first holding that has a value
    use_quantity = all(h.get("raw_weight") is None for h in valid_holdings)

    if use_quantity:
        # Fetch current prices and compute market-value weights
        values = []
        for h in valid_holdings:
            qty = h.get("quantity") or 0.0
            try:
                info = yf.Ticker(h["ticker"]).info
                price = (
                    info.get("regularMarketPrice")
                    or info.get("currentPrice")
                    or info.get("previousClose")
                    or 0.0
                )
            except Exception:
                price = 0.0
            values.append(float(price) * float(qty))

        total = sum(values)
        if total == 0:
            raise ValueError("Unable to compute value weights: all prices/quantities are zero.")

        return [
            {"ticker": h["ticker"], "weight": v / total, "name": h.get("name", "")}
            for h, v in zip(valid_holdings, values)
        ]

    else:
        # Raw weight mode
        weights = [float(h.get("raw_weight") or 0.0) for h in valid_holdings]
        total = sum(weights)
        if total == 0:
            raise ValueError("Sum of weights is zero; cannot normalize.")

        return [
            {"ticker": h["ticker"], "weight": w / total, "name": h.get("name", "")}
            for h, w in zip(valid_holdings, weights)
        ]


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_portfolio(
    file_bytes: bytes = None,
    file_type: str = None,
    text: str = None,
) -> list[dict]:
    """Main entry point for portfolio ingestion.

    Args:
        file_bytes: Raw file content (CSV or XLSX).
        file_type:  "csv" or "xlsx" (case-insensitive).
        text:       Free-text portfolio description.

    Returns:
        Normalized, validated list of {"ticker": str, "weight": float, "name": str}.
    """
    if file_bytes is not None and file_type:
        ft = file_type.lower().lstrip(".")
        if ft == "csv":
            holdings = parse_csv(file_bytes)
        elif ft in ("xlsx", "xls"):
            holdings = parse_excel(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {file_type!r}")
    elif text is not None:
        holdings = parse_text_input(text)
    else:
        raise ValueError("Provide either (file_bytes + file_type) or text.")

    holdings = validate_tickers(holdings)
    return normalize_weights(holdings)
