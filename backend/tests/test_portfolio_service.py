"""Tests for calculate_weights in app/portfolio_service.py."""

import pytest

from app.portfolio_service import calculate_weights


class TestCalculateWeightsFromRawWeight:
    def test_normalizes_raw_weights_to_sum_one(self):
        holdings = [
            {"ticker": "AAPL", "raw_weight": 60},
            {"ticker": "MSFT", "raw_weight": 40},
        ]
        result = calculate_weights(holdings, "sess1")
        assert result[0]["weight"] == pytest.approx(0.6)
        assert result[1]["weight"] == pytest.approx(0.4)

    def test_zero_raw_weights_fall_back_to_equal_weight(self):
        holdings = [
            {"ticker": "AAPL", "raw_weight": 0},
            {"ticker": "MSFT", "raw_weight": 0},
            {"ticker": "GOOG", "raw_weight": 0},
        ]
        result = calculate_weights(holdings, "sess2")
        for h in result:
            assert h["weight"] == pytest.approx(1.0 / 3)

    def test_mixed_none_and_raw_weight_treated_as_zero(self):
        holdings = [
            {"ticker": "AAPL", "raw_weight": 100},
            {"ticker": "MSFT", "raw_weight": None},
        ]
        result = calculate_weights(holdings, "sess3")
        assert result[0]["weight"] == pytest.approx(1.0)
        assert result[1]["weight"] == pytest.approx(0.0)


class TestCalculateWeightsFromInvestedAmount:
    def test_derives_weights_from_quantity_times_price(self):
        holdings = [
            {"ticker": "AAPL", "quantity": 10, "avg_buy_price": 100},
            {"ticker": "MSFT", "quantity": 5, "avg_buy_price": 200},
        ]
        result = calculate_weights(holdings, "sess4")
        # invested: AAPL=1000, MSFT=1000 -> 50/50
        assert result[0]["weight"] == pytest.approx(0.5)
        assert result[1]["weight"] == pytest.approx(0.5)

    def test_zero_invested_amount_falls_back_to_equal_weight(self):
        holdings = [
            {"ticker": "AAPL", "quantity": 0, "avg_buy_price": 0},
            {"ticker": "MSFT", "quantity": 0, "avg_buy_price": 0},
        ]
        result = calculate_weights(holdings, "sess5")
        for h in result:
            assert h["weight"] == pytest.approx(0.5)

    def test_no_raw_weight_key_uses_invested_amount_path(self):
        holdings = [{"ticker": "AAPL", "quantity": 2, "avg_buy_price": 50}]
        result = calculate_weights(holdings, "sess6")
        assert result[0]["weight"] == pytest.approx(1.0)
