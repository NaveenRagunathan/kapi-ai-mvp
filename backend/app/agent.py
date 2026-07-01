"""LangChain agent orchestration for portfolio analysis queries."""

import os
from dataclasses import dataclass, field

from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.math_engine import (
    calculate_performance_metrics,
    calculate_risk_metrics,
    get_diversification_and_sector_exposure,
    run_what_if_simulation,
)
from app.guardrails import ChatResponse, parse_llm_output, make_fallback_response


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

@dataclass
class PortfolioSession:
    session_id: str
    holdings: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)  # {"role": "user"|"assistant", "content": str}


# In-memory store
_sessions: dict[str, PortfolioSession] = {}


def get_or_create_session(session_id: str) -> PortfolioSession:
    if session_id not in _sessions:
        _sessions[session_id] = PortfolioSession(session_id=session_id)
    return _sessions[session_id]


def set_portfolio(session_id: str, holdings: list[dict]) -> None:
    session = get_or_create_session(session_id)
    session.holdings = holdings


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Tool context (set before each chat() call)
# ---------------------------------------------------------------------------

_current_holdings: list[dict] = []


# ---------------------------------------------------------------------------
# LangChain Tools
# ---------------------------------------------------------------------------

@tool
def get_portfolio_allocation() -> dict:
    """Return the current portfolio allocation with tickers and weights."""
    return {"holdings": _current_holdings}


@tool
def calculate_performance(benchmark_ticker: str = "^NSEI", timeframe: str = "1y") -> dict:
    """Calculate portfolio performance metrics: CAGR, Sharpe ratio, Sortino ratio vs benchmark."""
    return calculate_performance_metrics(_current_holdings, benchmark_ticker, timeframe)


@tool
def get_risk_metrics() -> dict:
    """Calculate portfolio risk: Value at Risk, Maximum Drawdown, Beta, Volatility."""
    return calculate_risk_metrics(_current_holdings)


@tool
def get_diversification() -> dict:
    """Analyze portfolio sector concentration and factor exposures (Size, Value, Momentum)."""
    return get_diversification_and_sector_exposure(_current_holdings)


@tool
def simulate_trade(sell_ticker: str, sell_weight: float, buy_ticker: str) -> dict:
    """Simulate swapping a portion of one holding for another and compare Sharpe/drawdown."""
    return run_what_if_simulation(_current_holdings, sell_ticker, sell_weight, buy_ticker)


_TOOLS = [
    get_portfolio_allocation,
    calculate_performance,
    get_risk_metrics,
    get_diversification,
    simulate_trade,
]

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an institutional-grade portfolio analyst for Kalpi Capital.

RULES (never break these):
1. You MUST call tools to get all financial metrics. Never invent numbers or do math yourself.
2. Always respond with valid JSON matching this exact schema:
   {"text": "...", "suggested_prompts": ["...", "..."], "canvas_state": {"view": "performance"|"risk"|"diversification"|"whatif"|"none", "data": {...}}}
3. Set canvas_state.view to the most relevant analysis type based on what was discussed.
4. Include 2-3 suggested_prompts that logically follow from the current analysis.
5. canvas_state.data should contain the raw tool result for the frontend to visualize.

You are analyzing a portfolio. The user may ask about returns, risk, diversification, or what-if scenarios."""


# ---------------------------------------------------------------------------
# Agent Builder
# ---------------------------------------------------------------------------

def _build_agent():
    primary = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    fallback = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
    llm = primary.with_fallbacks([fallback])

    return create_agent(
        llm,
        tools=_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


_agent_executor = None


def _get_agent():
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = _build_agent()
    return _agent_executor


# ---------------------------------------------------------------------------
# Main Chat Function
# ---------------------------------------------------------------------------

def chat(session_id: str, user_message: str) -> ChatResponse:
    global _current_holdings
    session = get_or_create_session(session_id)
    _current_holdings = session.holdings

    executor = _get_agent()

    # Build the message list: history (last 10) + current user message
    messages: list = []
    for m in session.history[-10:]:
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        else:
            messages.append(AIMessage(content=m["content"]))
    messages.append(HumanMessage(content=user_message))

    result = executor.invoke({
        "input": user_message,
        "chat_history": [
            ("human" if m["role"] == "user" else "ai", m["content"])
            for m in session.history[-10:]
        ],
        "messages": messages,
    })

    # The new create_agent returns AgentState with a messages list;
    # fall back to an "output" key for compatibility with mocked AgentExecutor.
    if isinstance(result, dict) and "output" in result:
        raw_output = result["output"]
    elif isinstance(result, dict) and "messages" in result:
        last = result["messages"][-1]
        raw_output = last.content if hasattr(last, "content") else str(last)
    else:
        raw_output = str(result)

    try:
        response = parse_llm_output(raw_output)
    except ValueError:
        response = make_fallback_response(raw_output)

    # Update history
    session.history.append({"role": "user", "content": user_message})
    session.history.append({"role": "assistant", "content": raw_output})

    return response
