"""Tests for backend/app/market_data.py — no real network calls.

market_data.py talks to Yahoo's crumb-free `v8/finance/chart` endpoint via
app.market_data._fetch_chart(), so all tests here mock that single seam
rather than any HTTP library directly.
"""

from unittest.mock import patch

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chart(ticker, periods=10, currency="INR", name="Test Corp",
                 exchange="NSI", instrument_type="EQUITY", price=100.0):
    """Build a fake Yahoo chart-endpoint result (what _fetch_chart returns)."""
    dates = pd.bdate_range("2023-01-02", periods=periods)
    timestamps = [int(d.timestamp()) for d in dates]
    closes = list(np.linspace(100, 110, periods))
    return {
        "meta": {
            "currency": currency,
            "symbol": ticker,
            "exchangeName": exchange,
            "instrumentType": instrument_type,
            "regularMarketPrice": price,
            "shortName": name,
            "longName": name,
        },
        "timestamp": timestamps,
        "indicators": {"quote": [{"close": closes}]},
    }


# ---------------------------------------------------------------------------
# fetch_prices
# ---------------------------------------------------------------------------

class TestFetchPrices:
    """Tests for market_data.fetch_prices."""

    @patch("app.market_data._fetch_chart")
    def test_returns_dataframe_with_correct_columns(self, mock_chart):
        tickers = ["RELIANCE.NS", "INFY.NS"]
        mock_chart.side_effect = lambda t, **kw: _make_chart(t)

        from app.market_data import fetch_prices

        df = fetch_prices(tickers, period="3y")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == tickers

    @patch("app.market_data._fetch_chart")
    def test_drops_all_nan_rows(self, mock_chart):
        """Rows where every value is NaN must be removed."""
        ticker = "TCS.NS"
        chart = _make_chart(ticker)
        chart["indicators"]["quote"][0]["close"][3] = None
        mock_chart.return_value = chart

        from app.market_data import fetch_prices

        df = fetch_prices([ticker])
        assert df.isnull().all(axis=1).sum() == 0

    @patch("app.market_data._fetch_chart")
    def test_single_ticker_returns_dataframe(self, mock_chart):
        ticker = "WIPRO.NS"
        mock_chart.return_value = _make_chart(ticker)

        from app.market_data import fetch_prices

        df = fetch_prices([ticker])
        assert isinstance(df, pd.DataFrame)
        assert ticker in df.columns

    @patch("app.market_data._fetch_chart")
    def test_datetimeindex(self, mock_chart):
        tickers = ["HDFCBANK.NS"]
        mock_chart.side_effect = lambda t, **kw: _make_chart(t)

        from app.market_data import fetch_prices

        df = fetch_prices(tickers)
        assert isinstance(df.index, pd.DatetimeIndex)

    @patch("app.market_data._fetch_chart")
    def test_unresolvable_ticker_omitted(self, mock_chart):
        """A ticker that fails to resolve is simply dropped, not an error."""
        def side_effect(t, **kw):
            return None if t == "BOGUS" else _make_chart(t)
        mock_chart.side_effect = side_effect

        from app.market_data import fetch_prices

        df = fetch_prices(["RELIANCE.NS", "BOGUS"])
        assert "BOGUS" not in df.columns
        assert "RELIANCE.NS" in df.columns


# ---------------------------------------------------------------------------
# fetch_benchmark
# ---------------------------------------------------------------------------

class TestFetchBenchmark:
    """Tests for market_data.fetch_benchmark."""

    @patch("app.market_data._fetch_chart")
    def test_returns_series(self, mock_chart):
        ticker = "^NSEI"
        mock_chart.return_value = _make_chart(ticker)

        from app.market_data import fetch_benchmark

        s = fetch_benchmark(ticker)
        assert isinstance(s, pd.Series)

    @patch("app.market_data._fetch_chart")
    def test_series_name_matches_ticker(self, mock_chart):
        ticker = "^NSEI"
        mock_chart.return_value = _make_chart(ticker)

        from app.market_data import fetch_benchmark

        s = fetch_benchmark(ticker)
        assert s.name == ticker

    @patch("app.market_data._fetch_chart")
    def test_default_ticker_is_nsei(self, mock_chart):
        mock_chart.return_value = _make_chart("^NSEI")

        from app.market_data import fetch_benchmark

        fetch_benchmark()
        args, kwargs = mock_chart.call_args
        assert args[0] == "^NSEI"

    @patch("app.market_data._fetch_chart")
    def test_drops_nan_values(self, mock_chart):
        ticker = "^NSEI"
        chart = _make_chart(ticker)
        chart["indicators"]["quote"][0]["close"][2] = None
        mock_chart.return_value = chart

        from app.market_data import fetch_benchmark

        result = fetch_benchmark(ticker)
        assert result.isnull().sum() == 0

    @patch("app.market_data._fetch_chart")
    def test_unresolvable_ticker_returns_empty_series(self, mock_chart):
        mock_chart.return_value = None

        from app.market_data import fetch_benchmark

        result = fetch_benchmark("BOGUS")
        assert isinstance(result, pd.Series)
        assert result.empty


# ---------------------------------------------------------------------------
# get_metadata
# ---------------------------------------------------------------------------

class TestGetMetadata:
    """Tests for market_data.get_metadata — sector/industry are always
    "Unknown" since that data isn't available crumb-free; asset_class comes
    from resolve_ticker_metadata."""

    @patch("app.market_data.resolve_ticker_metadata")
    def test_reports_unknown_sector_and_industry(self, mock_resolve):
        mock_resolve.return_value = {"asset_class": "Equity", "valid": True}

        from app.market_data import get_metadata
        result = get_metadata(["INFY.NS"])

        entry = result["INFY.NS"]
        assert entry["sector"] == "Unknown"
        assert entry["industry"] == "Unknown"
        assert entry["market_cap"] == 0
        assert entry["asset_class"] == "Equity"

    @patch("app.market_data.resolve_ticker_metadata")
    def test_asset_class_reflects_resolved_ticker(self, mock_resolve):
        mock_resolve.return_value = {"asset_class": "ETF", "valid": True}

        from app.market_data import get_metadata
        result = get_metadata(["NIFTYBEES.NS"])

        assert result["NIFTYBEES.NS"]["asset_class"] == "ETF"

    @patch("app.market_data.resolve_ticker_metadata")
    def test_multiple_tickers_each_get_own_entry(self, mock_resolve):
        mock_resolve.side_effect = lambda t: {"asset_class": "Equity", "valid": True}

        from app.market_data import get_metadata
        result = get_metadata(["A.NS", "B.NS"])

        assert set(result.keys()) == {"A.NS", "B.NS"}


# ---------------------------------------------------------------------------
# resolve_ticker_metadata
# ---------------------------------------------------------------------------

class TestResolveTickerMetadata:
    """Tests for market_data.resolve_ticker_metadata — real India/US differentiation."""

    @patch("app.market_data._fetch_chart")
    def test_us_ticker_currency_and_exchange(self, mock_chart):
        mock_chart.return_value = _make_chart(
            "AAPL", currency="USD", name="Apple Inc", exchange="NMS",
        )

        from app.market_data import resolve_ticker_metadata

        result = resolve_ticker_metadata("AAPL")
        assert result["valid"] is True
        assert result["ticker"] == "AAPL"
        assert result["currency"] == "USD"
        assert result["exchange"] == "NMS"
        assert result["asset_class"] == "Equity"

    @patch("app.market_data._fetch_chart")
    def test_indian_ticker_currency_and_exchange(self, mock_chart):
        mock_chart.return_value = _make_chart(
            "RELIANCE.NS", currency="INR", name="Reliance Industries", exchange="NSI",
        )

        from app.market_data import resolve_ticker_metadata

        result = resolve_ticker_metadata("RELIANCE.NS")
        assert result["currency"] == "INR"
        assert result["exchange"] == "NSI"

    @patch("app.market_data._fetch_chart")
    def test_bare_indian_ticker_ns_fallback_reads_real_currency(self, mock_chart):
        """Bare 'RELIANCE' should retry with .NS, then read currency from that
        result rather than assuming INR from the suffix."""
        def side_effect(t, **kw):
            if t == "RELIANCE":
                return None
            if t == "RELIANCE.NS":
                return _make_chart("RELIANCE.NS", currency="INR", name="Reliance Industries", exchange="NSI")
            return None

        mock_chart.side_effect = side_effect

        from app.market_data import resolve_ticker_metadata

        result = resolve_ticker_metadata("RELIANCE")
        assert result["valid"] is True
        assert result["ticker"] == "RELIANCE.NS"
        assert result["currency"] == "INR"

    @patch("app.market_data._fetch_chart")
    def test_invalid_ticker(self, mock_chart):
        mock_chart.return_value = None

        from app.market_data import resolve_ticker_metadata

        result = resolve_ticker_metadata("BOGUSXYZ")
        assert result["valid"] is False
        assert result["currency"] == "OTHER"

    @patch("app.market_data._fetch_chart")
    def test_unmapped_currency_falls_back_to_other(self, mock_chart):
        mock_chart.return_value = _make_chart(
            "MC.PA", currency="EUR", name="Some EU Co", exchange="PAR",
        )

        from app.market_data import resolve_ticker_metadata

        result = resolve_ticker_metadata("MC.PA")
        assert result["valid"] is True
        assert result["currency"] == "OTHER"

    @patch("app.market_data._fetch_chart")
    def test_etf_instrument_type_maps_to_etf(self, mock_chart):
        mock_chart.return_value = _make_chart(
            "NIFTYBEES.NS", currency="INR", name="Nifty BeES", exchange="NSI",
            instrument_type="ETF",
        )

        from app.market_data import resolve_ticker_metadata

        result = resolve_ticker_metadata("NIFTYBEES.NS")
        assert result["asset_class"] == "ETF"
