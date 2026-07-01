"""Handles ingestion of portfolio data from uploaded files (CSV, XLSX, etc.)."""
from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Optional

import openpyxl

# ── Column-name aliases ───────────────────────────────────────────────────────

_TICKER_ALIASES = {"ticker", "symbol", "stock"}
_WEIGHT_ALIASES = {"weight", "weights", "allocation"}
_QUANTITY_ALIASES = {"quantity", "qty", "shares", "units"}
_AVG_PRICE_ALIASES = {
    "avg_buy_price", "avg price", "avg_price", "buy price", "buy_price",
    "cost price", "cost_price", "purchase price", "avg cost", "average price",
}
_INVESTED_ALIASES = {
    "invested_amount", "invested amount", "invested", "total invested", "cost value",
}


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


def _get_genai_client():
    """Build a Gemini (Vertex AI) client from GOOGLE_CREDENTIALS_JSON, or None
    if credentials aren't configured. Shared by text parsing and the CSV
    header-mapping fallback so both paths use the same LLM extraction layer."""
    try:
        import tempfile
        from google import genai

        creds_str = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
        if not creds_str:
            return None
        info = json.loads(creds_str)

        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(info, tf)
        tf.close()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tf.name

        return genai.Client(vertexai=True, project=info["project_id"], location="us-central1")
    except Exception as e:
        print(f"[ingestion] Gemini client init failed: {e}")
        return None


def _llm_map_csv_headers(headers_raw: list[str]) -> dict[str, Optional[int]]:
    """Ask Gemini to map non-standard CSV/Excel headers to canonical fields.

    Used only when direct alias matching (_find_column) can't find
    avg_buy_price/invested_amount -- the LLM here only maps COLUMN NAMES to
    field names, it never sees or invents financial values, preserving the
    golden rule that the LLM never computes/guesses money data.

    Returns a dict like {"avg_buy_price": 2, "invested_amount": None} where
    values are column indices into `headers_raw`, or None if not found.
    """
    client = _get_genai_client()
    if client is None:
        return {"avg_buy_price": None, "invested_amount": None}

    prompt = (
        "You are mapping spreadsheet column headers to canonical portfolio fields.\n"
        "Given this list of column headers (0-indexed), return ONLY a JSON object "
        "mapping each of these canonical field names to the matching header's index, "
        "or null if no header matches: \"avg_buy_price\" (average price paid per "
        "share/unit), \"invested_amount\" (total money invested in that holding).\n"
        f"Headers: {json.dumps(headers_raw)}\n"
        "Return ONLY the JSON object, e.g. {\"avg_buy_price\": 3, \"invested_amount\": null}"
    )
    try:
        result = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = result.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        mapping = json.loads(raw)
        return {
            "avg_buy_price": mapping.get("avg_buy_price"),
            "invested_amount": mapping.get("invested_amount"),
        }
    except Exception as e:
        print(f"[ingestion] Gemini header mapping failed: {e}")
        return {"avg_buy_price": None, "invested_amount": None}


# ── 1.1  File Parsers ─────────────────────────────────────────────────────────

def _resolve_money_columns(headers_lower: list[str], headers_raw: list[str]) -> tuple[Optional[int], Optional[int]]:
    """Find avg_buy_price/invested_amount columns by alias, falling back to an
    LLM-assisted header mapping when the headers don't cleanly match (e.g.
    "Buy Price" phrased unusually). The LLM only maps column NAMES here, it
    never sees or invents row values."""
    avg_price_idx = _find_column(headers_lower, _AVG_PRICE_ALIASES)
    invested_idx = _find_column(headers_lower, _INVESTED_ALIASES)

    if avg_price_idx is None and invested_idx is None:
        mapped = _llm_map_csv_headers(headers_raw)
        avg_price_idx = mapped.get("avg_buy_price")
        invested_idx = mapped.get("invested_amount")

    return avg_price_idx, invested_idx


def parse_csv(file_bytes: bytes) -> list[dict]:
    """Parse CSV bytes.

    Accepts case-insensitive column aliases for ticker/symbol/stock,
    weight/weights/allocation, quantity/qty/shares/units, and
    avg_buy_price/invested_amount (falling back to an LLM-assisted header
    mapping when those columns don't cleanly match a known alias).

    Returns list of {"ticker", "raw_weight", "quantity", "avg_buy_price",
    "invested_amount", "source_row"}.
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
    avg_price_idx, invested_idx = _resolve_money_columns(headers_lower, headers_raw)

    if ticker_idx is None:
        raise ValueError(f"No ticker column found. Headers: {headers_raw}")

    results: list[dict] = []
    for source_row, row in enumerate(rows[1:], start=1):
        if not any(cell.strip() for cell in row):
            continue
        ticker = row[ticker_idx].strip() if ticker_idx < len(row) else ""
        if not ticker:
            continue

        raw_weight = _to_float(row[weight_idx]) if weight_idx is not None and weight_idx < len(row) else None
        quantity = _to_float(row[qty_idx]) if qty_idx is not None and qty_idx < len(row) else None
        avg_buy_price = _to_float(row[avg_price_idx]) if avg_price_idx is not None and avg_price_idx < len(row) else None
        invested_amount = _to_float(row[invested_idx]) if invested_idx is not None and invested_idx < len(row) else None

        results.append({
            "ticker": ticker, "raw_weight": raw_weight, "quantity": quantity,
            "avg_buy_price": avg_buy_price, "invested_amount": invested_amount,
            "source_row": source_row,
        })

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
    avg_price_idx, invested_idx = _resolve_money_columns(headers_lower, headers_raw)

    if ticker_idx is None:
        raise ValueError(f"No ticker column found. Headers: {headers_raw}")

    results: list[dict] = []
    for source_row, row in enumerate(rows[1:], start=1):
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue
        ticker_val = row[ticker_idx] if ticker_idx < len(row) else None
        ticker = str(ticker_val).strip() if ticker_val is not None else ""
        if not ticker:
            continue

        raw_weight = _to_float(row[weight_idx]) if weight_idx is not None and weight_idx < len(row) else None
        quantity = _to_float(row[qty_idx]) if qty_idx is not None and qty_idx < len(row) else None
        avg_buy_price = _to_float(row[avg_price_idx]) if avg_price_idx is not None and avg_price_idx < len(row) else None
        invested_amount = _to_float(row[invested_idx]) if invested_idx is not None and invested_idx < len(row) else None

        results.append({
            "ticker": ticker, "raw_weight": raw_weight, "quantity": quantity,
            "avg_buy_price": avg_buy_price, "invested_amount": invested_amount,
            "source_row": source_row,
        })

    wb.close()
    return results


# ── 1.2  Text-to-Portfolio Regex Engine ───────────────────────────────────────

_HAIKU_PARSE_PROMPT = """You are a portfolio parser. Extract STOCK TICKER SYMBOLS and their numbers from the user's text.

Return ONLY a valid JSON array (no markdown, no explanation). Each element:
- {"ticker": "SYMBOL", "quantity": <number>}   — share count (no % sign)
- {"ticker": "SYMBOL", "raw_weight": <number>} — percentage or decimal weight (has % or is ≤ 1.0)
- {"ticker": "SYMBOL", "quantity": <number>, "avg_buy_price": <number>} — use when the
  user mentions a purchase/buy/cost price per share alongside quantity
- {"ticker": "SYMBOL", "quantity": <number>, "invested_amount": <number>} — use when the
  user mentions total money invested in that holding instead of a per-share price

CRITICAL RULES:
1. Tickers are stock symbols, ETF names, or company abbreviations — NOT common English words.
   Valid tickers: AAPL, RELIANCE, ITC, GOLDBEES, NAM-INDIA, M&M, MON100, ICICIBANK, TCS
   NOT tickers: "have", "shares", "units", "own", "bought", "of", "and", "along", "with"
2. Uppercase all tickers. Do NOT add .NS suffix.
3. If a company name is written out (e.g. "Reliance Industries"), convert to ticker "RELIANCE".
4. Numbers after a ticker (or before it) belong to that ticker.
5. Extract avg_buy_price/invested_amount ONLY when the user explicitly stated a price or
   invested amount — never estimate, guess, or compute one yourself.

Examples:
"50% AAPL, 50% MSFT" → [{"ticker":"AAPL","raw_weight":50},{"ticker":"MSFT","raw_weight":50}]
"GOLDBEES 284, ITC 100, M&M 20" → [{"ticker":"GOLDBEES","quantity":284},{"ticker":"ITC","quantity":100},{"ticker":"M&M","quantity":20}]
"Reliance: 10, TCS: 5 shares" → [{"ticker":"RELIANCE","quantity":10},{"ticker":"TCS","quantity":5}]
"I have 284 units of GOLDBEES and 100 shares of ITC" → [{"ticker":"GOLDBEES","quantity":284},{"ticker":"ITC","quantity":100}]
"bought 30 ICICIBANK and 20 M&M stocks" → [{"ticker":"ICICIBANK","quantity":30},{"ticker":"M&M","quantity":20}]
"Bought 10 RELIANCE at 2450 each" → [{"ticker":"RELIANCE","quantity":10,"avg_buy_price":2450}]
"Invested 50000 in TCS, got 20 shares" → [{"ticker":"TCS","quantity":20,"invested_amount":50000}]

Now parse this input and return ONLY the JSON array:"""


def _extract_json_array(raw: str) -> list:
    """Strip markdown code fences (if present) and parse a JSON array."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    return json.loads(raw)


def _holdings_from_llm_json(parsed: list) -> list[dict]:
    """Normalize a parsed LLM JSON array (from either the text or image
    extraction prompts) into the shared raw-holding dict shape."""
    results = []
    for item in parsed:
        ticker = str(item.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        raw_weight = item.get("raw_weight")
        quantity = item.get("quantity")
        avg_buy_price = item.get("avg_buy_price")
        invested_amount = item.get("invested_amount")
        results.append({
            "ticker": ticker,
            "raw_weight": float(raw_weight) if raw_weight is not None else None,
            "quantity": float(quantity) if quantity is not None else None,
            "avg_buy_price": float(avg_buy_price) if avg_buy_price is not None else None,
            "invested_amount": float(invested_amount) if invested_amount is not None else None,
        })
    return results


def _parse_text_with_gemini(text: str) -> list[dict]:
    """Call Gemini Flash (Vertex AI) to parse free-form portfolio text into structured holdings."""
    client = _get_genai_client()
    if client is None:
        return []
    try:
        result = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{_HAIKU_PARSE_PROMPT}\n{text}",
        )
        parsed = _extract_json_array(result.text)
        return _holdings_from_llm_json(parsed)
    except Exception as e:
        print(f"[ingestion] Gemini parse failed: {e}")
        return []


# Regex fallback patterns (used only when Gemini is unavailable)
_RE_AT_PRICE = re.compile(
    r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s+(\d+(?:\.\d+)?)\s*(?:shares?|units?)?\s*(?:@|at)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_RE_PCT_BEFORE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*([A-Za-z][A-Za-z0-9.&_-]{0,19})")
_RE_PCT_AFTER = re.compile(r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s+(\d+(?:\.\d+)?)\s*%")
_RE_DECIMAL = re.compile(r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s+(\d*\.\d+)")
_RE_COLON_QTY = re.compile(r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s*:\s*(\d+(?:\.\d+)?)")
_RE_SPACE_QTY = re.compile(r"([A-Za-z][A-Za-z0-9.&_-]{0,19})\s+(\d+)")


def _parse_text_regex(text: str) -> list[dict]:
    """Regex-based fallback parser for common portfolio text formats.

    Best-effort only -- this path is used exclusively when Gemini/credentials
    are unavailable. Anything it can't extract (e.g. avg_buy_price) simply
    surfaces as a normal validation error downstream, same as an incomplete
    CSV row.
    """
    matches = _RE_AT_PRICE.findall(text)
    if matches:
        return [
            {"ticker": t.upper(), "raw_weight": None, "quantity": float(q), "avg_buy_price": float(p)}
            for t, q, p in matches
        ]
    matches = _RE_PCT_BEFORE.findall(text)
    if matches:
        return [{"ticker": t.upper(), "raw_weight": float(w), "quantity": None} for w, t in matches]
    matches = _RE_PCT_AFTER.findall(text)
    if matches:
        return [{"ticker": t.upper(), "raw_weight": float(w), "quantity": None} for t, w in matches]
    matches = _RE_COLON_QTY.findall(text)
    if matches:
        return [{"ticker": t.upper(), "raw_weight": None, "quantity": float(q)} for t, q in matches]
    matches = _RE_DECIMAL.findall(text)
    if matches:
        return [{"ticker": t.upper(), "raw_weight": float(w), "quantity": None} for t, w in matches]
    matches = _RE_SPACE_QTY.findall(text)
    if matches:
        return [{"ticker": t.upper(), "raw_weight": None, "quantity": float(q)} for t, q in matches]
    return []


def parse_text_input(text: str) -> list[dict]:
    """Parse free text portfolio descriptions using Claude Haiku with regex fallback.

    Accepts any natural language format:
    - "50% AAPL, 50% MSFT"
    - "GOLDBEES 284, ITC 100, M&M 20"
    - "Reliance: 10, TCS: 5 shares"
    - "I have 100 shares of ITC and 30 of ICICI Bank"

    Returns list of {"ticker": str, "raw_weight": float|None, "quantity": float|None}.
    """
    if not text or not text.strip():
        return []
    result = _parse_text_with_gemini(text)
    if result:
        return result
    return _parse_text_regex(text)


# ── 1.2b  Screenshot-to-Portfolio (Gemini Vision) ─────────────────────────────

_IMAGE_PARSE_PROMPT = """You are a portfolio parser. These images are screenshots of a stock
broker/investing app showing a user's holdings (e.g. a portfolio/holdings tab, a positions
list, or an account summary). Extract every distinct holding visible across ALL images and
return ONLY a valid JSON array (no markdown, no explanation). Each element:
- {"ticker": "SYMBOL", "quantity": <number>}   — share/unit count
- {"ticker": "SYMBOL", "raw_weight": <number>} — percentage or decimal weight, only if quantity
  isn't shown but an allocation % is
- {"ticker": "SYMBOL", "quantity": <number>, "avg_buy_price": <number>} — use when a per-share
  average/buy price is visible alongside quantity
- {"ticker": "SYMBOL", "quantity": <number>, "invested_amount": <number>} — use when a total
  invested value is visible instead of a per-share price

CRITICAL RULES:
1. Only extract values that are actually visible in the image. NEVER estimate, guess, compute,
   or hallucinate a number that isn't legible in the screenshot.
2. Tickers are stock/ETF symbols or company names shown in the holdings list — ignore UI chrome
   (tab labels, "Total", "P&L", buttons, navigation text).
3. Uppercase all tickers. Convert a written-out company name to its ticker if obvious
   (e.g. "Reliance Industries" -> "RELIANCE"). Do NOT add a .NS suffix.
4. If the same ticker appears in more than one image (e.g. duplicate screenshot), include it only once.
5. If a number is cut off, blurry, or ambiguous, omit that field for that holding rather than guessing.
6. If no holdings are legible in the images at all, return an empty JSON array: []

Return ONLY the JSON array."""


def _parse_images_with_gemini(images: list[tuple[bytes, str]]) -> list[dict]:
    """Call Gemini (Vertex AI) vision to extract holdings from one or more
    portfolio screenshots in a single multimodal request.

    images: list of (raw_bytes, mime_type) tuples, e.g. (b"...", "image/png").
    """
    client = _get_genai_client()
    if client is None:
        return []
    try:
        from google.genai import types

        parts = [
            types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
            for img_bytes, mime_type in images
        ]
        contents = parts + [_IMAGE_PARSE_PROMPT]
        result = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
        )
        parsed = _extract_json_array(result.text)
        return _holdings_from_llm_json(parsed)
    except Exception as e:
        print(f"[ingestion] Gemini image parse failed: {e}")
        return []


def parse_image_input(images: list[tuple[bytes, str]]) -> list[dict]:
    """Parse one or more portfolio screenshots into structured holdings.

    images: list of (raw_bytes, mime_type) tuples.

    Unlike text/CSV parsing there is no regex fallback -- if Gemini is
    unavailable or extracts nothing, this returns an empty list and the
    caller surfaces a normal "no valid holdings found" error.

    Returns list of {"ticker": str, "raw_weight": float|None, "quantity": float|None,
    "avg_buy_price": float|None, "invested_amount": float|None}.
    """
    if not images:
        return []
    return _parse_images_with_gemini(images)


# ── 1.3  Shared validation gate ───────────────────────────────────────────────
#
# Both ingestion paths (CSV/Excel and free-text/LLM) funnel their raw dicts
# through validate_holdings(). This is the ONLY place that enforces mandatory
# fields, resolves ticker existence + currency/exchange (via
# market_data.resolve_ticker_metadata), and rejects mixed-currency portfolios.
# Nothing downstream of this function ever sees an unvalidated holding.

from pydantic import ValidationError as _PydanticValidationError

from app.market_data import resolve_ticker_metadata
from app.models import Holding, HoldingInput, HoldingValidationError, IngestionResult


def validate_holdings(raw: list[dict]) -> IngestionResult:
    """Validate raw ingestion dicts (from either CSV/Excel or text/LLM parsing)
    into an IngestionResult.

    Two modes:
    1. Full holding: needs quantity + avg_buy_price (or invested_amount).
    2. Weight-only: needs raw_weight (e.g. "50% AAPL, 50% MSFT") → quantity & price are None.

    Rejects (with a per-row HoldingValidationError, holding excluded):
      - malformed rows (bad types, empty ticker)
      - rows with neither raw_weight nor (quantity + price)
      - tickers that don't resolve via yfinance

    Rejects the ENTIRE batch (holdings=[]) if the resolved holdings span more
    than one currency -- mixed-currency portfolios aren't supported yet.
    """
    errors: list[HoldingValidationError] = []
    inputs: list[HoldingInput] = []

    for item in raw:
        try:
            inputs.append(HoldingInput(**item))
        except _PydanticValidationError as exc:
            errors.append(HoldingValidationError(
                row=item.get("source_row"), ticker=item.get("ticker"),
                message=f"row {item.get('source_row', '?')}: invalid holding data - {exc}",
            ))

    candidates: list[HoldingInput] = []
    for hi in inputs:
        has_weight = hi.raw_weight is not None
        has_quantity = hi.quantity is not None
        has_price = hi.avg_buy_price is not None or hi.invested_amount is not None

        if not has_weight and not has_quantity:
            errors.append(HoldingValidationError(
                row=hi.source_row, ticker=hi.ticker, field="quantity",
                message=f"row {hi.source_row or '?'}: provide either a weight (e.g. 50%) or quantity for {hi.ticker}.",
            ))
            continue
        if has_quantity and not has_price:
            errors.append(HoldingValidationError(
                row=hi.source_row, ticker=hi.ticker, field="avg_buy_price",
                message=f"row {hi.source_row or '?'}: missing avg_buy_price (or invested_amount) for {hi.ticker}.",
            ))
            continue
        candidates.append(hi)

    if not candidates:
        return IngestionResult(holdings=[], errors=errors)

    resolved: list[tuple[HoldingInput, dict]] = []
    for hi in candidates:
        meta = resolve_ticker_metadata(hi.ticker)
        if not meta["valid"]:
            errors.append(HoldingValidationError(
                row=hi.source_row, ticker=hi.ticker, field="ticker",
                message=f"row {hi.source_row or '?'}: ticker '{hi.ticker}' not found.",
            ))
            continue
        resolved.append((hi, meta))

    if not resolved:
        return IngestionResult(holdings=[], errors=errors)

    currencies = {meta["currency"] for _, meta in resolved}
    if len(currencies) > 1:
        errors.append(HoldingValidationError(
            message=(
                "Mixed-currency portfolios aren't supported yet — please keep all "
                f"holdings in one currency (found: {', '.join(sorted(currencies))})."
            ),
        ))
        return IngestionResult(holdings=[], errors=errors)

    holdings: list[Holding] = []
    for hi, meta in resolved:
        is_weight_only = hi.raw_weight is not None and hi.quantity is None
        if is_weight_only:
            try:
                holdings.append(Holding(
                    ticker=meta["ticker"],
                    name=meta["name"] or hi.ticker,
                    quantity=None,
                    avg_buy_price=None,
                    raw_weight=hi.raw_weight,
                    currency=meta["currency"],
                    exchange=meta["exchange"],
                    asset_class=meta["asset_class"],
                ))
            except _PydanticValidationError as exc:
                errors.append(HoldingValidationError(
                    row=hi.source_row, ticker=hi.ticker,
                    message=f"row {hi.source_row or '?'}: {hi.ticker} - {exc}",
                ))
            continue
        avg_buy_price = hi.avg_buy_price
        if avg_buy_price is None and hi.quantity:
            avg_buy_price = hi.invested_amount / hi.quantity
        try:
            holdings.append(Holding(
                ticker=meta["ticker"],
                name=meta["name"] or hi.ticker,
                quantity=hi.quantity,
                avg_buy_price=avg_buy_price,
                invested_amount=hi.invested_amount or 0.0,
                currency=meta["currency"],
                exchange=meta["exchange"],
                asset_class=meta["asset_class"],
            ))
        except _PydanticValidationError as exc:
            errors.append(HoldingValidationError(
                row=hi.source_row, ticker=hi.ticker,
                message=f"row {hi.source_row or '?'}: {hi.ticker} - {exc}",
            ))

    return IngestionResult(holdings=holdings, errors=errors)


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_portfolio(
    file_bytes: bytes = None,
    file_type: str = None,
    text: str = None,
    images: list[tuple[bytes, str]] = None,
) -> IngestionResult:
    """Main entry point for portfolio ingestion.

    Args:
        file_bytes: Raw file content (CSV or XLSX).
        file_type:  "csv" or "xlsx" (case-insensitive).
        text:       Free-text portfolio description.
        images:     List of (raw_bytes, mime_type) portfolio screenshots.

    Returns:
        IngestionResult(holdings=[Holding, ...], errors=[HoldingValidationError, ...]).
    """
    if file_bytes is not None and file_type:
        ft = file_type.lower().lstrip(".")
        if ft == "csv":
            raw = parse_csv(file_bytes)
        elif ft in ("xlsx", "xls"):
            raw = parse_excel(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {file_type!r}")
    elif images:
        raw = parse_image_input(images)
    elif text is not None:
        raw = parse_text_input(text)
    else:
        raise ValueError("Provide either (file_bytes + file_type), images, or text.")

    return validate_holdings(raw)
