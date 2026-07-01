"""Shared validation contract for portfolio holdings.

Both ingestion paths (CSV/Excel column parsing and free-text/LLM parsing) must
produce holdings that pass through this contract before they reach
math_engine.py. The LLM only ever extracts/normalizes fields it saw in the
user's input here -- it never computes or guesses a financial value; that
stays 100% deterministic (yfinance lookups + arithmetic) in
market_data.py/ingestion.py/math_engine.py.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator


class HoldingInput(BaseModel):
    """Raw, pre-validation holding as extracted from CSV/Excel or LLM/regex
    text parsing. Money fields are optional here -- validate_holdings() in
    ingestion.py is what promotes this into a fully validated Holding."""

    ticker: str
    quantity: Optional[float] = None
    avg_buy_price: Optional[float] = None
    invested_amount: Optional[float] = None
    raw_weight: Optional[float] = None
    source_row: Optional[int] = None

    @field_validator("ticker")
    @classmethod
    def _upper_strip(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not v:
            raise ValueError("ticker must not be empty")
        return v


class Holding(BaseModel):
    """Validated holding with optional money fields.

    Two modes:
    - Full holding: quantity + avg_buy_price present → invested_amount computed.
    - Weight-only: raw_weight present, quantity/avg_buy_price None → analysis
      uses weights + live prices only (no absolute P&L).
    """

    ticker: str
    name: str
    quantity: Optional[float] = None
    avg_buy_price: Optional[float] = None
    invested_amount: float = 0.0
    raw_weight: Optional[float] = None
    currency: Literal["INR", "USD", "OTHER"]
    exchange: Optional[str] = None
    asset_class: Optional[str] = None
    weight: Optional[float] = None

    @field_validator("quantity")
    @classmethod
    def _qty_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("quantity must be > 0")
        return v

    @field_validator("avg_buy_price")
    @classmethod
    def _price_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("avg_buy_price must be > 0")
        return v

    @model_validator(mode="after")
    def _derive_invested_amount(self) -> "Holding":
        if not self.invested_amount and self.quantity is not None and self.avg_buy_price is not None:
            self.invested_amount = self.quantity * self.avg_buy_price
        return self


class HoldingValidationError(BaseModel):
    """One per-row/per-item ingestion error, surfaced to the frontend so it
    can render messages like 'row 3: missing avg_buy_price'."""

    row: Optional[int] = None
    ticker: Optional[str] = None
    field: Optional[str] = None
    message: str


class IngestionResult(BaseModel):
    """Outcome of validate_holdings(): the valid holdings plus a list of
    per-row errors, so the caller can decide whether to proceed, block, or
    show a partial-success banner."""

    holdings: list[Holding]
    errors: list[HoldingValidationError]

    @property
    def accepted_count(self) -> int:
        return len(self.holdings)

    @property
    def rejected_count(self) -> int:
        return len(self.errors)
