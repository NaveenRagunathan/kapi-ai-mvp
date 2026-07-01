"""LangChain agent orchestration — Gemini Flash (primary) + Gemini Pro (fallback).

Auth: Google service account via GOOGLE_CREDENTIALS_JSON in .env.
Requires: Gemini API enabled at https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com
"""

import logging
import os
import json

logger = logging.getLogger(__name__)

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_vertexai import ChatVertexAI

from app.math_engine import (
    calculate_performance_metrics,
    calculate_risk_metrics,
    get_diversification_and_sector_exposure,
    run_what_if_simulation,
    get_correlation_matrix,
)
from app.guardrails import ChatResponse, parse_llm_output, make_fallback_response, _normalize_llm_raw
from app.session_store import PortfolioSession, InMemorySessionStore


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

_session_store = InMemorySessionStore(maxsize=500, ttl=3600)


def get_or_create_session(session_id: str) -> PortfolioSession:
    session = _session_store.get(session_id)
    if session is None:
        logger.info("Creating new session: %s", session_id)
        session = PortfolioSession(session_id=session_id)
        _session_store.set(session_id, session)
    return session


def set_portfolio(session_id: str, holdings: list[dict]) -> None:
    session = get_or_create_session(session_id)
    session.holdings = holdings
    logger.info("Portfolio set for session %s: %d holdings", session_id, len(holdings))


def clear_session(session_id: str) -> None:
    _session_store.delete(session_id)
    logger.info("Session cleared: %s", session_id)


# ---------------------------------------------------------------------------
# Tool context
# ---------------------------------------------------------------------------

_current_holdings: list[dict] = []

# The LLM is asked to echo each tool's raw return dict into canvas_state.data,
# but it sometimes fails to transcribe the full JSON faithfully even when it
# gets the numbers right in prose. Tools stash their real return value here
# so chat() can use the actual computed dict as canvas data instead of
# trusting the LLM's copy of it -- consistent with "the LLM never computes,
# it only calls tools" elsewhere in this codebase.
_last_tool_result: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# LangChain Tools
# ---------------------------------------------------------------------------

@tool
def get_portfolio_allocation() -> dict:
    """Return the current portfolio allocation with tickers and weights."""
    result = {"holdings": _current_holdings}
    _last_tool_result["get_portfolio_allocation"] = result
    return result


@tool
def calculate_performance(benchmark_ticker: str = "^NSEI", timeframe: str = "1y") -> dict:
    """Calculate portfolio performance metrics: CAGR, Sharpe ratio, Sortino ratio vs benchmark.
    Use benchmark_ticker='^NSEI' for Indian portfolios, '^GSPC' for US portfolios."""
    result = calculate_performance_metrics(_current_holdings, benchmark_ticker, timeframe)
    _last_tool_result["calculate_performance"] = result
    return result


@tool
def get_risk_metrics() -> dict:
    """Calculate portfolio risk metrics: Value at Risk (95% and 99%), CVaR/Expected Shortfall,
    Maximum Drawdown, Portfolio Beta, and Annualized Volatility."""
    result = calculate_risk_metrics(_current_holdings)
    _last_tool_result["get_risk_metrics"] = result
    return result


@tool
def get_diversification() -> dict:
    """Analyze portfolio sector concentration and factor exposures (Size, Value, Momentum).
    Call this for questions about sector exposure, concentration risk, or factor overlap."""
    result = get_diversification_and_sector_exposure(_current_holdings)
    _last_tool_result["get_diversification"] = result
    return result


def _resolve_ticker(ticker: str) -> str:
    """Map a bare ticker symbol to its validated version found in current holdings.
    Falls back to ticker+'.NS' if not found in holdings."""
    # Check holdings first (they are already validated with correct suffixes)
    for h in _current_holdings:
        ht = h["ticker"]
        if ht == ticker or ht.startswith(ticker + "."):
            return ht
    # Fallback: add .NS for Indian tickers without suffix
    if "." not in ticker:
        return ticker + ".NS"
    return ticker


@tool
def simulate_trade(sell_ticker: str, sell_weight: float, buy_ticker: str) -> dict:
    """Simulate the impact of swapping sell_weight of sell_ticker for buy_ticker.
    Returns comparison of original vs simulated Sharpe ratio and Max Drawdown.
    sell_weight should be between 0.0 and 1.0 (e.g. 0.2 = 20%).
    Tickers will be auto-resolved to their full suffix (e.g. GOLDBEES → GOLDBEES.NS)."""
    resolved_sell = _resolve_ticker(sell_ticker)
    resolved_buy = _resolve_ticker(buy_ticker)
    result = run_what_if_simulation(_current_holdings, resolved_sell, sell_weight, resolved_buy)
    _last_tool_result["simulate_trade"] = result
    return result


@tool
def get_correlation_matrix_tool() -> dict:
    """Compute the pairwise daily return correlation matrix for all portfolio holdings.
    Call this when the user asks about correlations, diversification quality,
    or how holdings move together."""
    result = get_correlation_matrix(_current_holdings)
    _last_tool_result["get_correlation_matrix_tool"] = result
    return result


_TOOLS = [
    get_portfolio_allocation,
    calculate_performance,
    get_risk_metrics,
    get_diversification,
    simulate_trade,
    get_correlation_matrix_tool,
]

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an institutional-grade portfolio analyst for Kalpi Capital.

ABSOLUTE RULES — never break these:
1. ALWAYS call the appropriate tool to get any financial number. Never invent or estimate metrics.
2. ALWAYS respond with a valid JSON object matching EXACTLY this schema — nothing else:
   {
     "text": "<rich plain-English analysis with key numbers from tools>",
     "suggested_prompts": ["<follow-up question 1>", "<follow-up question 2>", "<follow-up question 3>"],
     "canvas_state": {
       "view": "<one of: performance | risk | diversification | whatif | correlation | none>",
       "data": { <the raw dict returned by the tool you called> }
     }
   }
3. canvas_state.view must match the analysis:
   - performance / returns / CAGR / Sharpe query → "performance"
   - risk / drawdown / VaR / beta / CVaR query → "risk"
   - sector / factor / diversification / concentration query → "diversification"
   - what-if / swap / simulate / replace query → "whatif"
   - correlation / how holdings move / matrix query → "correlation"
   - allocation / holdings / weights query → "none"
4. canvas_state.data must be the FULL dict returned by the tool.
5. suggested_prompts must be 3 specific, actionable follow-up questions.
6. In text: cite key numbers, compare to benchmarks, give actionable insights. Be specific.
7. For Indian portfolios, default benchmark is ^NSEI (Nifty 50).
8. Use a professional, clean, conversational, and interactive tone. Avoid AI-sloppy phrasing, robotic patterns, or overly dense tables/text blocks.
9. Keep markdown formatting extremely clean. Use bulleted lists properly (e.g. `* Item text` or `* **Item Name**: description`). Never mix bold markers and lists in a confusing way (e.g., avoid `* **Item**:` on a line by itself).

You only discuss portfolio analysis. Respond only in the JSON schema above."""


# ---------------------------------------------------------------------------
# LLM Builder — Gemini 2.5 Flash (primary) + Gemini 2.5 Pro (fallback) via Vertex AI
# ---------------------------------------------------------------------------

def _setup_vertex_credentials():
    """Write service account JSON to a temp file and set GOOGLE_APPLICATION_CREDENTIALS."""
    import tempfile
    creds_str = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_str:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON not set in .env")
    info = json.loads(creds_str)
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(info, tf)
    tf.close()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tf.name
    return info.get("project_id", "")


def _build_agent():
    project_id = _setup_vertex_credentials()
    location = "us-central1"

    flash = ChatVertexAI(
        model_name="gemini-2.5-flash",
        project=project_id,
        location=location,
        temperature=0.1,
    )
    pro = ChatVertexAI(
        model_name="gemini-2.5-pro",
        project=project_id,
        location=location,
        temperature=0.1,
    )
    llm = flash.with_fallbacks([pro])
    print(f"[agent] Gemini 2.5 Flash (primary) + Pro (fallback) on Vertex AI {location}")
    return create_agent(llm, tools=_TOOLS, system_prompt=SYSTEM_PROMPT)


_agent_executor = None


def _get_agent():
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = _build_agent()
    return _agent_executor


# ---------------------------------------------------------------------------
# Canvas view resolution
# ---------------------------------------------------------------------------

# Maps each math tool to the canvas view that displays its output. The LLM
# also picks canvas_state.view itself, but it occasionally mislabels it
# (e.g. leaves it on a previous turn's view) even when it called the right
# tool and answered correctly in text. Since we know exactly which tool ran,
# we can deterministically override a mismatched view instead of trusting
# the LLM's JSON field to be internally consistent with its own tool calls.
_TOOL_TO_VIEW = {
    "calculate_performance": "performance",
    "get_risk_metrics": "risk",
    "get_diversification": "diversification",
    "simulate_trade": "whatif",
    "get_correlation_matrix_tool": "correlation",
    "get_portfolio_allocation": "none",
}


def _last_tool_called(messages: list) -> str | None:
    """Return the name of the last math tool invoked in this turn, if any."""
    last_tool = None
    for m in messages:
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            last_tool = tool_calls[-1].get("name")
    return last_tool


# ---------------------------------------------------------------------------
# Main Chat Function
# ---------------------------------------------------------------------------

def chat(session_id: str, user_message: str) -> ChatResponse:
    global _current_holdings
    session = get_or_create_session(session_id)
    _current_holdings = session.holdings
    _last_tool_result.clear()

    executor = _get_agent()

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

    # The LLM sometimes mislabels canvas_state.view (e.g. leaves it on the
    # previous turn's view), or fails to faithfully transcribe the tool's
    # full return dict into canvas_state.data even when it gets the numbers
    # right in prose. Override both from what we know actually ran.
    last_tool = _last_tool_called(result.get("messages", [])) if isinstance(result, dict) else None
    expected_view = _TOOL_TO_VIEW.get(last_tool)
    if expected_view:
        response.canvas_state.view = expected_view
        tool_data = _last_tool_result.get(last_tool)
        if tool_data:
            response.canvas_state.data = tool_data

    session.history.append({"role": "user", "content": user_message})
    session.history.append({"role": "assistant", "content": _normalize_llm_raw(raw_output)})

    return response
