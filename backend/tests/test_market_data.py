"""Tests for backend/app/market_data.py — no real network calls."""

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_df(tickers, periods=10):
    """Return a small DataFrame that mimics yf.download(…)["Close"]."""
    idx = pd.date_range("2023-01-02", periods=periods, freq="B")
    data = {t: np.linspace(100, 110, periods) for t in tickers}
    return pd.DataFrame(data, index=idx)


def _make_price_series(ticker, periods=10):
    """Return a small Series that mimics single-ticker yf.download(…)["Close"]."""
    idx = pd.date_range("2023-01-02", periods=periods, freq="B")
    return pd.Series(np.linspace(100, 110, periods), index=idx, name=ticker)


# ---------------------------------------------------------------------------
# fetch_prices
# ---------------------------------------------------------------------------

class TestFetchPrices:
    """Tests for market_data.fetch_prices."""

    @patch("app.market_data.yf.download")
    def test_returns_dataframe_with_correct_columns(self, mock_download):
        """DataFrame columns must match the requested tickers."""
        tickers = ["RELIANCE.NS", "INFY.NS"]
        mock_download.return_value = {"Close": _make_price_df(tickers)}

        # Simulate the yf.download(…)["Close"] subscript that the module uses:
        # we need __getitem__ to return the DataFrame.
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: _make_price_df(tickers)
        mock_download.return_value = mock_result

        from app.market_data import fetch_prices

        df = fetch_prices(tickers, period="3y")

        mock_download.assert_called_once_with(tickers, period="3y", auto_adjust=True)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == tickers

    @patch("app.market_data.yf.download")
    def test_drops_all_nan_rows(self, mock_download):
        """Rows where every value is NaN must be removed."""
        tickers = ["TCS.NS"]
        base = _make_price_df(tickers)
        # Introduce an all-NaN row
        base.iloc[3] = np.nan

        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: base
        mock_download.return_value = mock_result

        from app.market_data import fetch_prices

        df = fetch_prices(tickers)
        assert df.isnull().all(axis=1).sum() == 0

    @patch("app.market_data.yf.download")
    def test_single_ticker_returns_dataframe(self, mock_download):
        """Even with one ticker, the return type must be DataFrame."""
        ticker = "WIPRO.NS"
        # yfinance may return a Series for a single ticker
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: _make_price_series(ticker)
        mock_download.return_value = mock_result

        from app.market_data import fetch_prices

        df = fetch_prices([ticker])
        assert isinstance(df, pd.DataFrame)
        assert ticker in df.columns

    @patch("app.market_data.yf.download")
    def test_datetimeindex(self, mock_download):
        """The returned DataFrame must have a DatetimeIndex."""
        tickers = ["HDFCBANK.NS"]
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: _make_price_df(tickers)
        mock_download.return_value = mock_result

        from app.market_data import fetch_prices

        df = fetch_prices(tickers)
        assert isinstance(df.index, pd.DatetimeIndex)


# ---------------------------------------------------------------------------
# fetch_benchmark
# ---------------------------------------------------------------------------

class TestFetchBenchmark:
    """Tests for market_data.fetch_benchmark."""

    @patch("app.market_data.yf.download")
    def test_returns_series(self, mock_download):
        """fetch_benchmark must return a pd.Series."""
        ticker = "^NSEI"
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: _make_price_series(ticker)
        mock_download.return_value = mock_result

        from app.market_data import fetch_benchmark

        s = fetch_benchmark(ticker)
        assert isinstance(s, pd.Series)

    @patch("app.market_data.yf.download")
    def test_series_name_matches_ticker(self, mock_download):
        """The Series name must match the ticker argument."""
        ticker = "^NSEI"
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: _make_price_series(ticker)
        mock_download.return_value = mock_result

        from app.market_data import fetch_benchmark

        s = fetch_benchmark(ticker)
        assert s.name == ticker

    @patch("app.market_data.yf.download")
    def test_default_ticker_is_nsei(self, mock_download):
        """Default benchmark ticker must be ^NSEI."""
        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: _make_price_series("^NSEI")
        mock_download.return_value = mock_result

        from app.market_data import fetch_benchmark

        fetch_benchmark()
        args, kwargs = mock_download.call_args
        assert args[0] == "^NSEI"

    @patch("app.market_data.yf.download")
    def test_drops_nan_values(self, mock_download):
        """NaN values in the benchmark series must be dropped."""
        ticker = "^NSEI"
        s = _make_price_series(ticker)
        s.iloc[2] = np.nan

        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: s
        mock_download.return_value = mock_result

        from app.market_data import fetch_benchmark

        result = fetch_benchmark(ticker)
        assert result.isnull().sum() == 0

    @patch("app.market_data.yf.download")
    def test_dataframe_input_normalised_to_series(self, mock_download):
        """If yfinance returns a DataFrame, fetch_benchmark converts it to Series."""
        ticker = "^NSEI"
        df = _make_price_df([ticker])

        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, key: df
        mock_download.return_value = mock_result

        from app.market_data import fetch_benchmark

        result = fetch_benchmark(ticker)
        assert isinstance(result, pd.Series)


# ---------------------------------------------------------------------------
# get_metadata
# ---------------------------------------------------------------------------

def _make_mock_ticker(info: dict):
    """Create a mock yf.Ticker instance with the given .info dict."""
    mock_ticker = MagicMock()
    mock_ticker.info = info
    return mock_ticker


class TestGetMetadata:
    """Tests for market_data.get_metadata."""

    @patch("app.market_data.yf.Ticker")
    def test_equity_structure(self, mock_ticker_cls):
        """Equity ticker: asset_class == 'Equity', all keys present."""
        mock_ticker_cls.return_value = _make_mock_ticker({
            "quoteType": "EQUITY",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 5_000_000_000,
        })

        from app.market_data import get_metadata

        result = get_metadata(["INFY.NS"])
        assert "INFY.NS" in result
        entry = result["INFY.NS"]
        assert entry["sector"] == "Technology"
        assert entry["industry"] == "Software"
        assert entry["market_cap"] == 5_000_000_000
        assert entry["asset_class"] == "Equity"

    @patch("app.market_data.yf.Ticker")
    def test_etf_asset_class(self, mock_ticker_cls):
        """ETF quoteType maps to asset_class == 'ETF'."""
        mock_ticker_cls.return_value = _make_mock_ticker({
            "quoteType": "ETF",
            "sector": "Unknown",
            "industry": "Unknown",
            "marketCap": 1_000_000,
        })

        from app.market_data import get_metadata

        result = get_metadata(["NIFTYBEES.NS"])
        assert result["NIFTYBEES.NS"]["asset_class"] == "ETF"

    @patch("app.market_data.yf.Ticker")
    def test_crypto_asset_class(self, mock_ticker_cls):
        """CRYPTOCURRENCY quoteType maps to asset_class == 'Crypto'."""
        mock_ticker_cls.return_value = _make_mock_ticker({
            "quoteType": "CRYPTOCURRENCY",
            "sector": "Unknown",
            "industry": "Unknown",
            "marketCap": 800_000_000_000,
        })

        from app.market_data import get_metadata

        result = get_metadata(["BTC-USD"])
        assert result["BTC-USD"]["asset_class"] == "Crypto"

    @patch("app.market_data.yf.Ticker")
    def test_missing_keys_default_to_unknown(self, mock_ticker_cls):
        """Missing info keys must fall back to 'Unknown' (sector/industry)."""
        mock_ticker_cls.return_value = _make_mock_ticker({})

        from app.market_data import get_metadata

        result = get_metadata(["XYZ.NS"])
        entry = result["XYZ.NS"]
        assert entry["sector"] == "Unknown"
        assert entry["industry"] == "Unknown"
        assert entry["asset_class"] == "Equity"  # default when quoteType missing
        assert entry["market_cap"] == 0

    @patch("app.market_data.yf.Ticker")
    def test_multiple_tickers(self, mock_ticker_cls):
        """Multiple tickers each get their own metadata dict."""
        tickers = ["A.NS", "B.NS", "C.NS"]

        def side_effect(t):
            return _make_mock_ticker({
                "quoteType": "EQUITY",
                "sector": f"Sector_{t}",
                "industry": f"Industry_{t}",
                "marketCap": 1_000,
            })

        mock_ticker_cls.side_effect = side_effect

        from app.market_data import get_metadata

        result = get_metadata(tickers)
        assert set(result.keys()) == set(tickers)
        for t in tickers:
            assert result[t]["sector"] == f"Sector_{t}"
