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

    def test_avg_buy_price_column(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "AAPL", "Quantity": "10", "avg_buy_price": "180.5"}],
            ["Ticker", "Quantity", "avg_buy_price"],
        )
        result = parse_csv(data)
        assert result[0]["avg_buy_price"] == pytest.approx(180.5)
        assert result[0]["invested_amount"] is None

    def test_buy_price_alias_column(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "TCS", "Qty": "5", "Buy Price": "3800"}],
            ["Ticker", "Qty", "Buy Price"],
        )
        result = parse_csv(data)
        assert result[0]["avg_buy_price"] == pytest.approx(3800.0)

    def test_invested_amount_column(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "TCS", "Qty": "20", "invested amount": "50000"}],
            ["Ticker", "Qty", "invested amount"],
        )
        result = parse_csv(data)
        assert result[0]["invested_amount"] == pytest.approx(50000.0)
        assert result[0]["avg_buy_price"] is None

    def test_source_row_is_one_indexed(self):
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "AAPL", "Qty": "1"}, {"Ticker": "MSFT", "Qty": "2"}],
            ["Ticker", "Qty"],
        )
        result = parse_csv(data)
        assert result[0]["source_row"] == 1
        assert result[1]["source_row"] == 2

    @patch("app.ingestion._llm_map_csv_headers")
    def test_unmatched_headers_fall_back_to_llm_mapping(self, mock_llm_map):
        """When avg_buy_price/invested_amount don't match any alias, the LLM
        header-mapping fallback should be consulted."""
        from app.ingestion import parse_csv
        mock_llm_map.return_value = {"avg_buy_price": 2, "invested_amount": None}
        data = _make_csv(
            [{"Ticker": "AAPL", "Qty": "10", "Weird Cost Col": "180"}],
            ["Ticker", "Qty", "Weird Cost Col"],
        )
        result = parse_csv(data)
        mock_llm_map.assert_called_once()
        assert result[0]["avg_buy_price"] == pytest.approx(180.0)

    @patch("app.ingestion._llm_map_csv_headers")
    def test_standard_headers_skip_llm_mapping(self, mock_llm_map):
        """When aliases already match, the LLM fallback must not be called."""
        from app.ingestion import parse_csv
        data = _make_csv(
            [{"Ticker": "AAPL", "Qty": "10", "avg_buy_price": "180"}],
            ["Ticker", "Qty", "avg_buy_price"],
        )
        parse_csv(data)
        mock_llm_map.assert_not_called()


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

    def test_at_price_regex_fallback(self):
        """'TICKER qty at price' should extract avg_buy_price via the regex
        fallback (no Gemini credentials configured in the test environment)."""
        from app.ingestion import _parse_text_regex
        result = _parse_text_regex("RELIANCE 10 at 2450")
        assert len(result) == 1
        assert result[0]["ticker"] == "RELIANCE"
        assert result[0]["quantity"] == pytest.approx(10.0)
        assert result[0]["avg_buy_price"] == pytest.approx(2450.0)

    def test_at_symbol_price_regex_fallback(self):
        from app.ingestion import _parse_text_regex
        result = _parse_text_regex("TCS 5 shares @ 3800")
        assert result[0]["ticker"] == "TCS"
        assert result[0]["quantity"] == pytest.approx(5.0)
        assert result[0]["avg_buy_price"] == pytest.approx(3800.0)

    @patch("app.ingestion._get_genai_client")
    def test_gemini_extracts_avg_buy_price(self, mock_get_client):
        from app.ingestion import _parse_text_with_gemini
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.text = '[{"ticker":"RELIANCE","quantity":10,"avg_buy_price":2450}]'
        mock_client.models.generate_content.return_value = mock_result
        mock_get_client.return_value = mock_client

        result = _parse_text_with_gemini("Bought 10 RELIANCE at 2450 each")
        assert result[0]["ticker"] == "RELIANCE"
        assert result[0]["quantity"] == pytest.approx(10.0)
        assert result[0]["avg_buy_price"] == pytest.approx(2450.0)

    @patch("app.ingestion._get_genai_client")
    def test_gemini_extracts_invested_amount(self, mock_get_client):
        from app.ingestion import _parse_text_with_gemini
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.text = '[{"ticker":"TCS","quantity":20,"invested_amount":50000}]'
        mock_client.models.generate_content.return_value = mock_result
        mock_get_client.return_value = mock_client

        result = _parse_text_with_gemini("Invested 50000 in TCS, got 20 shares")
        assert result[0]["invested_amount"] == pytest.approx(50000.0)


# ── validate_tickers ──────────────────────────────────────────────────────────

def _mock_ticker(info: dict):
    """Return a mock yfinance.Ticker whose .info returns the given dict."""
    m = MagicMock()
    m.info = info
    return m


def _mock_chart(*, currency="USD", name="Test Corp", exchange="NMS", instrument_type="EQUITY"):
    """Build a fake Yahoo chart-endpoint result matching what
    app.market_data._fetch_chart returns, for mocking ticker resolution."""
    return {
        "meta": {
            "currency": currency,
            "shortName": name,
            "exchangeName": exchange,
            "instrumentType": instrument_type,
            "regularMarketPrice": 100,
        },
        "timestamp": [],
        "indicators": {"quote": [{"close": []}]},
    }


@pytest.mark.skip(reason="deprecated")
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

@pytest.mark.skip(reason="deprecated")
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
            [{"Ticker": "AAPL", "Quantity": "10", "Avg Price": "150.0"}, {"Ticker": "MSFT", "Quantity": "5", "Avg Price": "300.0"}],
            ["Ticker", "Quantity", "Avg Price"],
        )

        with patch("app.market_data._fetch_chart") as mock_chart:
            mock_chart.side_effect = lambda sym, **kw: _mock_chart(name=sym + " Inc.")
            result = ingest_portfolio(file_bytes=data, file_type="csv")

        assert len(result.holdings) == 2

    def test_text_end_to_end(self):
        from app.ingestion import ingest_portfolio

        with patch("app.market_data._fetch_chart") as mock_chart:
            mock_chart.side_effect = lambda sym, **kw: _mock_chart(name=sym + " Corp")
            result = ingest_portfolio(text="AAPL: 10 qty @ 150.00\nMSFT: 5 qty @ 300.00")

        assert len(result.holdings) == 2

    def test_xlsx_end_to_end(self):
        from app.ingestion import ingest_portfolio
        data = _make_xlsx(
            [{"Ticker": "AAPL", "Quantity": 10, "Avg Price": 150.0}, {"Ticker": "GOOG", "Quantity": 20, "Avg Price": 100.0}],
            ["Ticker", "Quantity", "Avg Price"],
        )

        with patch("app.market_data._fetch_chart") as mock_chart:
            mock_chart.side_effect = lambda sym, **kw: _mock_chart(name=sym + " Inc.")
            result = ingest_portfolio(file_bytes=data, file_type="xlsx")

        assert len(result.holdings) == 2

    def test_raises_on_no_input(self):
        from app.ingestion import ingest_portfolio
        with pytest.raises(ValueError):
            ingest_portfolio()
