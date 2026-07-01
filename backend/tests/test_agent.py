"""Tests for the agentic orchestrator (app/agent.py).

All tests mock the LLM — no real API calls are made.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import app.agent as agent_module
from app.agent import (
    PortfolioSession,
    chat,
    clear_session,
    get_or_create_session,
    set_portfolio,
)
from app.guardrails import ChatResponse, CanvasState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_chat_response_json() -> str:
    return json.dumps({
        "text": "Your portfolio has a Sharpe ratio of 1.2.",
        "suggested_prompts": ["What is my VaR?", "Show sector breakdown"],
        "canvas_state": {
            "view": "performance",
            "data": {"cagr": 0.15, "sharpe": 1.2},
        },
    })


def _make_mock_executor(output: str) -> MagicMock:
    mock_exec = MagicMock()
    mock_exec.invoke.return_value = {"output": output}
    return mock_exec


# ---------------------------------------------------------------------------
# Session management tests
# ---------------------------------------------------------------------------

class TestGetOrCreateSession:
    def setup_method(self):
        # Clear internal state before each test
        agent_module._session_store._cache.clear()

    def test_creates_new_session(self):
        session = get_or_create_session("abc")
        assert isinstance(session, PortfolioSession)
        assert session.session_id == "abc"
        assert session.holdings == []
        assert session.history == []

    def test_returns_same_session_on_second_call(self):
        session1 = get_or_create_session("abc")
        session2 = get_or_create_session("abc")
        assert session1 is session2

    def test_different_ids_create_different_sessions(self):
        s1 = get_or_create_session("s1")
        s2 = get_or_create_session("s2")
        assert s1 is not s2
        assert s1.session_id == "s1"
        assert s2.session_id == "s2"


class TestSetPortfolio:
    def setup_method(self):
        agent_module._session_store._cache.clear()

    def test_stores_holdings_in_session(self):
        holdings = [{"ticker": "RELIANCE.NS", "weight": 0.6}, {"ticker": "TCS.NS", "weight": 0.4}]
        set_portfolio("sess1", holdings)
        session = get_or_create_session("sess1")
        assert session.holdings == holdings

    def test_creates_session_if_not_exists(self):
        assert "new_sess" not in agent_module._session_store._cache
        set_portfolio("new_sess", [{"ticker": "INFY.NS", "weight": 1.0}])
        assert "new_sess" in agent_module._session_store._cache

    def test_overwrites_existing_holdings(self):
        set_portfolio("sess2", [{"ticker": "RELIANCE.NS", "weight": 1.0}])
        set_portfolio("sess2", [{"ticker": "TCS.NS", "weight": 1.0}])
        session = get_or_create_session("sess2")
        assert session.holdings == [{"ticker": "TCS.NS", "weight": 1.0}]


class TestClearSession:
    def setup_method(self):
        agent_module._session_store._cache.clear()

    def test_removes_session(self):
        get_or_create_session("to_clear")
        assert "to_clear" in agent_module._session_store._cache
        clear_session("to_clear")
        assert "to_clear" not in agent_module._session_store._cache

    def test_no_error_on_missing_session(self):
        # Should not raise
        clear_session("nonexistent")


# ---------------------------------------------------------------------------
# Chat function tests
# ---------------------------------------------------------------------------

class TestChatUpdatesHistory:
    def setup_method(self):
        agent_module._session_store._cache.clear()

    def test_history_updated_after_chat(self):
        session_id = "hist_test"
        mock_executor = _make_mock_executor(_valid_chat_response_json())

        with patch("app.agent._get_agent", return_value=mock_executor):
            response = chat(session_id, "How is my portfolio performing?")

        session = get_or_create_session(session_id)
        assert len(session.history) == 2
        assert session.history[0] == {"role": "user", "content": "How is my portfolio performing?"}
        assert session.history[1]["role"] == "assistant"
        assert session.history[1]["content"] == _valid_chat_response_json()

    def test_history_accumulates_across_calls(self):
        session_id = "multi_turn"
        mock_executor = _make_mock_executor(_valid_chat_response_json())

        with patch("app.agent._get_agent", return_value=mock_executor):
            chat(session_id, "First question")
            chat(session_id, "Second question")

        session = get_or_create_session(session_id)
        assert len(session.history) == 4  # 2 messages per turn

    def test_returns_valid_chat_response(self):
        session_id = "resp_test"
        mock_executor = _make_mock_executor(_valid_chat_response_json())

        with patch("app.agent._get_agent", return_value=mock_executor):
            response = chat(session_id, "Tell me about my risk")

        assert isinstance(response, ChatResponse)
        assert response.text == "Your portfolio has a Sharpe ratio of 1.2."
        assert response.canvas_state.view == "performance"
        assert len(response.suggested_prompts) == 2

    def test_executor_invoked_with_user_message(self):
        session_id = "invoke_test"
        mock_executor = _make_mock_executor(_valid_chat_response_json())

        with patch("app.agent._get_agent", return_value=mock_executor):
            chat(session_id, "Analyze diversification")

        mock_executor.invoke.assert_called_once()
        call_kwargs = mock_executor.invoke.call_args[0][0]
        assert call_kwargs["input"] == "Analyze diversification"

    def test_chat_history_passed_as_last_10_messages(self):
        session_id = "history_limit"
        mock_executor = _make_mock_executor(_valid_chat_response_json())

        # Pre-populate 12 messages (6 turns)
        session = get_or_create_session(session_id)
        for i in range(12):
            role = "user" if i % 2 == 0 else "assistant"
            session.history.append({"role": role, "content": f"msg {i}"})

        with patch("app.agent._get_agent", return_value=mock_executor):
            chat(session_id, "New question")

        call_kwargs = mock_executor.invoke.call_args[0][0]
        # Only last 10 messages passed as chat_history
        assert len(call_kwargs["chat_history"]) == 10


class TestChatFallbackOnInvalidJson:
    def setup_method(self):
        agent_module._session_store._cache.clear()

    def test_fallback_on_invalid_json(self):
        session_id = "fallback_test"
        invalid_output = "Sorry, I cannot help with that right now."
        mock_executor = _make_mock_executor(invalid_output)

        with patch("app.agent._get_agent", return_value=mock_executor):
            response = chat(session_id, "What is my Sharpe?")

        assert isinstance(response, ChatResponse)
        assert response.text == invalid_output
        assert response.suggested_prompts == []
        assert response.canvas_state.view == "none"
        assert response.canvas_state.data == {}

    def test_fallback_on_partial_json(self):
        session_id = "partial_json"
        partial = '{"text": "incomplete'
        mock_executor = _make_mock_executor(partial)

        with patch("app.agent._get_agent", return_value=mock_executor):
            response = chat(session_id, "Risk?")

        assert isinstance(response, ChatResponse)
        assert response.canvas_state.view == "none"

    def test_fallback_on_wrong_schema(self):
        session_id = "wrong_schema"
        wrong = json.dumps({"message": "hello", "extra": "field"})
        mock_executor = _make_mock_executor(wrong)

        with patch("app.agent._get_agent", return_value=mock_executor):
            response = chat(session_id, "Something")

        assert isinstance(response, ChatResponse)
        assert response.canvas_state.view == "none"

    def test_history_still_updated_on_fallback(self):
        session_id = "fallback_history"
        mock_executor = _make_mock_executor("not json at all")

        with patch("app.agent._get_agent", return_value=mock_executor):
            chat(session_id, "Question?")

        session = get_or_create_session(session_id)
        assert len(session.history) == 2
        assert session.history[0]["role"] == "user"
        assert session.history[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Holdings context tests
# ---------------------------------------------------------------------------

class TestCurrentHoldingsContext:
    def setup_method(self):
        agent_module._session_store._cache.clear()

    def test_holdings_set_as_current_before_invoke(self):
        session_id = "holdings_ctx"
        holdings = [{"ticker": "HDFC.NS", "weight": 1.0}]
        set_portfolio(session_id, holdings)

        captured = {}
        mock_executor = MagicMock()

        def capture_invoke(args):
            captured["holdings"] = agent_module._current_holdings
            return {"output": _valid_chat_response_json()}

        mock_executor.invoke.side_effect = capture_invoke

        with patch("app.agent._get_agent", return_value=mock_executor):
            chat(session_id, "Analyze me")

        assert captured["holdings"] == holdings
