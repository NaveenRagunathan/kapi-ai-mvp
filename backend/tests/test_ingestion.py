"""Tests for Module 1: Portfolio Ingestion Service."""
import io
import csv
import unittest
from unittest.mock import patch, MagicMock

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_csv(rows: list[dict], fieldnames: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


def _make_xlsx(rows: list[dict], headers: list[str]) -> bytes:
    """Build a minimal xlsx file in memory using openpyxl."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── parse_csv ─────────────────────────────────────────────────────────────────

class TestParseCsv:
    def test_ticker_and_weight_columns(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "AAPL", "Weight": "0.5"}, {"Ticker": "MSFT", "Weight": "0.5"}],
            ["Ticker", "Weight"],
        )
        result = parse_csv(data)
        assert len(result) == 2
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["raw_weight"] == pytest.approx(0.5)
        assert result[0]["quantity"] is None

    def test_symbol_and_allocation_columns(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"symbol": "RELIANCE", "allocation": "40"}, {"symbol": "TCS", "allocation": "60"}],
            ["symbol", "allocation"],
        )
        result = parse_csv(data)
        assert result[0]["ticker"] == "RELIANCE"
        assert result[0]["raw_weight"] == pytest.approx(40.0)

    def test_stock_and_quantity_columns(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"stock": "INFY", "qty": "10"}, {"stock": "WIPRO", "qty": "20"}],
            ["stock", "qty"],
        )
        result = parse_csv(data)
        assert result[0]["ticker"] == "INFY"
        assert result[0]["quantity"] == pytest.approx(10.0)
        assert result[0]["raw_weight"] is None

    def test_shares_column(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "TSLA", "Shares": "5"}],
            ["Ticker", "Shares"],
        )
        result = parse_csv(data)
        assert result[0]["quantity"] == pytest.approx(5.0)

    def test_case_insensitive_headers(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"TICKER": "NVDA", "WEIGHTS": "1.0"}],
            ["TICKER", "WEIGHTS"],
        )
        result = parse_csv(data)
        assert result[0]["ticker"] == "NVDA"
        assert result[0]["raw_weight"] == pytest.approx(1.0)

    def test_empty_rows_skipped(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "AAPL", "Weight": "0.5"}, {"Ticker": "", "Weight": ""}],
            ["Ticker", "Weight"],
        )
        result = parse_csv(data)
        assert len(result) == 1

    def test_missing_value_column_returns_none(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "AAPL"}],
            ["Ticker"],
        )
        result = parse_csv(data)
        assert result[0]["raw_weight"] is None
        assert result[0]["quantity"] is None


# ── parse_excel ───────────────────────────────────────────────────────────────

class TestParseExcel:
    def test_basic_xlsx(self):
        from app.ingestion import parse_excel
        data = _make_xlsx(
            [{"Ticker": "AAPL", "Weight": 0.6}, {"Ticker": "MSFT", "Weight": 0.4}],
            ["Ticker", "Weight"],
        )
        result = parse_excel(data)
        assert len(result) == 2
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["raw_weight"] == pytest.approx(0.6)

    def test_quantity_column_xlsx(self):
        from app.ingestion import parse_excel
        data = _make_xlsx(
            [{"Symbol": "TCS", "Quantity": 100}],
            ["Symbol", "Quantity"],
        )
        result = parse_excel(data)
        assert result[0]["ticker"] == "TCS"
        assert result[0]["quantity"] == pytest.approx(100.0)


# ── parse_text_input ──────────────────────────────────────────────────────────

class TestParseTextInput:
    def test_percentage_weight_mode(self):
        from app.ingestion import parse_text_input
        result = parse_text_input("50% AAPL, 50% MSFT")
        tickers = {r["ticker"] for r in result}
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        for r in result:
            assert r["raw_weight"] == pytest.approx(50.0)
        assert all(r["quantity"] is None for r in result)

    def test_decimal_weight_mode(self):
        from app.ingestion import parse_text_input
        result = parse_text_input("AAPL 0.5, MSFT 0.5")
        tickers = {r["ticker"] for r in result}
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        for r in result:
            assert r["raw_weight"] == pytest.approx(0.5)

    def test_colon_quantity_mode(self):
        from app.ingestion import parse_text_input
        result = parse_text_input("Reliance: 10, TCS: 5")
        by_ticker = {r["ticker"]: r for r in result}
        assert "RELIANCE" in by_ticker
        assert "TCS" in by_ticker
        assert by_ticker["RELIANCE"]["quantity"] == pytest.approx(10.0)
        assert by_ticker["TCS"]["quantity"] == pytest.approx(5.0)
        assert by_ticker["RELIANCE"]["raw_weight"] is None

    def test_newline_separated(self):
        from app.ingestion import parse_text_input
        result = parse_text_input("30% AAPL\n40% MSFT\n30% GOOG")
        assert len(result) == 3

    def test_mixed_case_tickers_uppercased(self):
        from app.ingestion import parse_text_input
        result = parse_text_input("aapl 0.6, msft 0.4")
        tickers = {r["ticker"] for r in result}
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_empty_string_returns_empty(self):
        from app.ingestion import parse_text_input
        assert parse_text_input("") == []

    def test_percentage_with_ticker_after(self):
        from app.ingestion import parse_text_input
        result = parse_text_input("AAPL 60%, MSFT 40%")
        by_ticker = {r["ticker"]: r for r in result}
        assert by_ticker["AAPL"]["raw_weight"] == pytest.approx(60.0)
        assert by_ticker["MSFT"]["raw_weight"] == pytest.approx(40.0)


# ── validate_tickers ──────────────────────────────────────────────────────────

def _mock_ticker(info: dict):
    """Return a mock yfinance.Ticker whose .info returns the given dict."""
    m = MagicMock()
    m.info = info
    return m


class TestValidateTickers:
    def test_valid_us_ticker(self):
        from app.ingestion import validate_tickers
        holdings = [{"ticker": "AAPL", "raw_weight": 1.0, "quantity": None}]

        with patch("app.ingestion.yf.Ticker") as mock_yf:
            mock_yf.return_value = _mock_ticker({"shortName": "Apple Inc.", "regularMarketPrice": 150})
            result = validate_tickers(holdings)

        assert result[0]["valid"] is True
        assert result[0]["name"] == "Apple Inc."

    def test_invalid_ticker_marked_false(self):
        from app.ingestion import validate_tickers
        holdings = [{"ticker": "ZZZINVALID", "raw_weight": 1.0, "quantity": None}]

        with patch("app.ingestion.yf.Ticker") as mock_yf:
            # Both plain and .NS attempts return empty info
            mock_yf.return_value = _mock_ticker({})
            result = validate_tickers(holdings)

        assert result[0]["valid"] is False

    def test_indian_stock_auto_appends_ns(self):
        from app.ingestion import validate_tickers
        holdings = [{"ticker": "RELIANCE", "raw_weight": 1.0, "quantity": None}]

        def side_effect(sym):
            if sym == "RELIANCE":
                return _mock_ticker({})  # fails without .NS
            if sym == "RELIANCE.NS":
                return _mock_ticker({"shortName": "Reliance Industries", "regularMarketPrice": 2800})
            return _mock_ticker({})

        with patch("app.ingestion.yf.Ticker", side_effect=side_effect):
            result = validate_tickers(holdings)

        assert result[0]["valid"] is True
        assert result[0]["ticker"] == "RELIANCE.NS"
        assert result[0]["name"] == "Reliance Industries"

    def test_name_fallback_when_no_shortname(self):
        from app.ingestion import validate_tickers
        holdings = [{"ticker": "MSFT", "raw_weight": 1.0, "quantity": None}]

        with patch("app.ingestion.yf.Ticker") as mock_yf:
            mock_yf.return_value = _mock_ticker({"longName": "Microsoft Corporation", "regularMarketPrice": 300})
            result = validate_tickers(holdings)

        assert result[0]["valid"] is True
        assert "Microsoft" in result[0]["name"]


# ── normalize_weights ─────────────────────────────────────────────────────────

class TestNormalizeWeights:
    def test_raw_weights_sum_to_one(self):
        from app.ingestion import normalize_weights
        holdings = [
            {"ticker": "AAPL", "raw_weight": 60.0, "quantity": None, "valid": True, "name": "Apple"},
            {"ticker": "MSFT", "raw_weight": 40.0, "quantity": None, "valid": True, "name": "Microsoft"},
        ]
        result = normalize_weights(holdings)
        total = sum(r["weight"] for r in result)
        assert total == pytest.approx(1.0)
        assert result[0]["weight"] == pytest.approx(0.6)
        assert result[1]["weight"] == pytest.approx(0.4)

    def test_already_decimal_weights_normalized(self):
        from app.ingestion import normalize_weights
        holdings = [
            {"ticker": "AAPL", "raw_weight": 0.5, "quantity": None, "valid": True, "name": "Apple"},
            {"ticker": "MSFT", "raw_weight": 0.5, "quantity": None, "valid": True, "name": "Microsoft"},
        ]
        result = normalize_weights(holdings)
        assert sum(r["weight"] for r in result) == pytest.approx(1.0)

    def test_quantity_mode_uses_price(self):
        from app.ingestion import normalize_weights
        holdings = [
            {"ticker": "AAPL", "raw_weight": None, "quantity": 10.0, "valid": True, "name": "Apple"},
            {"ticker": "MSFT", "raw_weight": None, "quantity": 10.0, "valid": True, "name": "Microsoft"},
        ]

        def side_effect(sym):
            prices = {"AAPL": 150.0, "MSFT": 300.0}
            m = MagicMock()
            m.info = {"regularMarketPrice": prices.get(sym, 100.0)}
            return m

        with patch("app.ingestion.yf.Ticker", side_effect=side_effect):
            result = normalize_weights(holdings)

        total = sum(r["weight"] for r in result)
        assert total == pytest.approx(1.0)
        by_ticker = {r["ticker"]: r for r in result}
        # AAPL: 10*150=1500, MSFT: 10*300=3000, total=4500
        assert by_ticker["AAPL"]["weight"] == pytest.approx(1500 / 4500)
        assert by_ticker["MSFT"]["weight"] == pytest.approx(3000 / 4500)

    def test_output_keys_present(self):
        from app.ingestion import normalize_weights
        holdings = [
            {"ticker": "AAPL", "raw_weight": 1.0, "quantity": None, "valid": True, "name": "Apple"},
        ]
        result = normalize_weights(holdings)
        assert set(result[0].keys()) >= {"ticker", "weight", "name"}

    def test_invalid_holdings_excluded(self):
        from app.ingestion import normalize_weights
        holdings = [
            {"ticker": "AAPL", "raw_weight": 0.7, "quantity": None, "valid": True, "name": "Apple"},
            {"ticker": "ZZZINVALID", "raw_weight": 0.3, "quantity": None, "valid": False, "name": ""},
        ]
        result = normalize_weights(holdings)
        tickers = [r["ticker"] for r in result]
        assert "ZZZINVALID" not in tickers
        assert sum(r["weight"] for r in result) == pytest.approx(1.0)


# ── ingest_portfolio (integration, mocked) ────────────────────────────────────

class TestIngestPortfolio:
    def test_csv_end_to_end(self):
        from app.ingestion import ingest_portfolio
        data = _make_csv(
            [{"Ticker": "AAPL", "Weight": "0.6"}, {"Ticker": "MSFT", "Weight": "0.4"}],
            ["Ticker", "Weight"],
        )

        with patch("app.ingestion.yf.Ticker") as mock_yf:
            mock_yf.side_effect = lambda sym: _mock_ticker(
                {"shortName": sym + " Inc.", "regularMarketPrice": 100}
            )
            result = ingest_portfolio(file_bytes=data, file_type="csv")

        assert len(result) == 2
        assert sum(r["weight"] for r in result) == pytest.approx(1.0)

    def test_text_end_to_end(self):
        from app.ingestion import ingest_portfolio

        with patch("app.ingestion.yf.Ticker") as mock_yf:
            mock_yf.side_effect = lambda sym: _mock_ticker(
                {"shortName": sym + " Corp", "regularMarketPrice": 100}
            )
            result = ingest_portfolio(text="50% AAPL, 50% MSFT")

        assert len(result) == 2
        assert sum(r["weight"] for r in result) == pytest.approx(1.0)

    def test_xlsx_end_to_end(self):
        from app.ingestion import ingest_portfolio
        data = _make_xlsx(
            [{"Ticker": "AAPL", "Weight": 0.5}, {"Ticker": "GOOG", "Weight": 0.5}],
            ["Ticker", "Weight"],
        )

        with patch("app.ingestion.yf.Ticker") as mock_yf:
            mock_yf.side_effect = lambda sym: _mock_ticker(
                {"shortName": sym + " Inc.", "regularMarketPrice": 100}
            )
            result = ingest_portfolio(file_bytes=data, file_type="xlsx")

        assert len(result) == 2
        assert sum(r["weight"] for r in result) == pytest.approx(1.0)

    def test_raises_on_no_input(self):
        from app.ingestion import ingest_portfolio
        with pytest.raises(ValueError):
            ingest_portfolio()
