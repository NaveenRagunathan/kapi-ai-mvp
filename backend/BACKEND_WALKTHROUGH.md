# Kalpi AI Backend — Full System Walkthrough

This is a script-ready, step-by-step explanation of every moving part in the backend, written for recording a video walkthrough. It covers architecture, every FastAPI endpoint, the full request lifecycle, and — in the most detail — how the "dynamic canvas" mechanism works (how the LLM's answer decides which visualization the frontend shows).

Stack: **FastAPI** (Python) + **LangChain / LangGraph** agent orchestration + **Gemini 2.5 Flash/Pro** (via Vertex AI) + **Yahoo Finance** (crumb-free chart endpoint) + **pandas/numpy** for all math.

---

## 1. The one-sentence architecture

> The LLM never computes a single number. It only *calls tools*. Every number the user sees — CAGR, Sharpe, drawdown, correlation — comes out of deterministic Python/pandas code in `math_engine/`. The LLM's only jobs are: understand the question, call the right tool, and write the English explanation.

This single design decision explains almost every file in the backend.

---

## 2. File map (what lives where)

```
backend/app/
├── main.py              FastAPI app — every HTTP route lives here
├── portfolio_service.py Business logic for ingestion (weight calc, baseline assembly)
├── ingestion.py         Parses raw input (text / CSV / Excel / screenshots) → structured holdings
├── market_data.py       Talks to Yahoo Finance — prices, ticker validation, currency/exchange
├── math_engine/         Deterministic math (package, split by concern)
│   ├── performance.py     CAGR, Sharpe, Sortino, active return
│   ├── risk.py             Max drawdown, VaR, beta, volatility
│   ├── diversification.py Sector weights, factor exposures (Size/Value/Momentum)
│   ├── whatif.py           "Sell X buy Y" trade simulation
│   ├── correlation.py     Pairwise return correlation matrix
│   ├── holdings.py         Per-holding P&L detail
│   ├── health.py            Health score + SWOT narrative generation
│   └── baseline.py          Assembles all of the above into one payload on ingestion
├── agent.py              LangChain agent: tools, system prompt, the chat() function
├── guardrails.py         Prompt-injection detection + strict JSON schema validation
├── session_store.py      In-memory session storage (holdings + chat history per user)
└── models.py              Pydantic models for holdings/validation
```

---

## 3. The two request families

Every request to this backend falls into one of two families:

1. **Ingestion** (`POST /api/portfolio/ingest*`) — "here's my portfolio, go analyze it"
2. **Chat** (`POST /api/chat`) — "answer this question about my portfolio"

Everything downstream of ingestion produces a `session_id` that chat requests reuse to look up the user's holdings.

---

## 4. Every endpoint, in detail

### `GET /health`
Trivial liveness check. Returns `{"status": "ok", "version": "0.1.0"}`. Used by Render's health check to know the container is up.

### `POST /api/portfolio/ingest` — text ingestion
**Body:** `{"text": "50% AAPL, 50% MSFT", "session_id": "optional"}`

1. Route generates a `session_id` (UUID) if the client didn't send one.
2. Runs `ingest_text_blocking(session_id, text)` in a **thread pool executor** — not directly on the event loop, because this call does real network I/O (Gemini for text parsing, Yahoo Finance for ticker validation and pricing) and would otherwise block every other concurrent request.
3. `ingest_text_blocking` → `ingestion.ingest_portfolio(text=...)` → `ingestion.parse_text_input(text)`.

### `POST /api/portfolio/ingest/file` — CSV/Excel ingestion
**Body:** multipart form, `file` + optional `session_id`.

1. MIME type is checked against an allowlist (`text/csv`, `application/vnd.ms-excel`, xlsx) **before** the body is read — rejects garbage early.
2. Size capped at 5 MB.
3. Same executor pattern as text ingestion, routes to `ingestion.parse_csv` / `parse_excel`.

### `POST /api/portfolio/ingest/images` — screenshot ingestion (the newest feature)
**Body:** multipart form, one or more `files` (max 5) + optional `session_id`.

1. Each file's MIME type is checked (`image/png`, `image/jpeg`, `image/webp`) and size-capped at 8 MB.
2. All images are read into `(bytes, mime_type)` tuples.
3. Routes to `ingestion.parse_image_input(images)`, which sends **all images in a single Gemini vision call** with a strict extraction prompt (see §6).

### `POST /api/chat` — the conversational endpoint
**Body:** `{"session_id": "...", "message": "What's my Sharpe ratio?"}`

Returns a **Server-Sent Events (SSE) stream**, not a single JSON blob. This is what makes the chat feel "live" — tokens appear incrementally instead of the UI freezing until the whole answer is ready.

Full sequence (see §7 for the deep dive):
1. `check_injection(message)` — reject prompt-injection attempts before touching the LLM.
2. If the session has no holdings yet → stream a canned "upload a portfolio first" message.
3. Otherwise → `chat_stream_generator`:
   - emit `event: status` twice (fake "thinking" indicators — UX polish, not real progress)
   - run `agent.chat(session_id, message)` in a thread executor (this is where the LangChain agent runs, calls tools, and calls Gemini)
   - stream the answer text **word by word** as `event: token`
   - emit one final `event: canvas` with the view + data the frontend should render

### `GET /api/session/{session_id}`
Returns the current holdings + chat history length for a session. Used for debugging/state inspection, not on the critical UI path.

### `DELETE /api/session/{session_id}`
Clears a session (used by "New Portfolio" in the UI).

### `GET /api/portfolio/correlation/{session_id}`
Standalone endpoint that recomputes the correlation matrix on demand. The frontend calls this directly (not through chat) when the user clicks the "Correlation" tab manually, so it doesn't need a full chat round-trip.

---

## 5. Ingestion deep dive — how raw input becomes validated holdings

This is the same funnel regardless of whether the input was text, a CSV, or a screenshot:

```
raw input (text / file bytes / images)
        │
        ▼
  parse_*() function          →  list of {ticker, raw_weight, quantity,
  (ingestion.py)                  avg_buy_price, invested_amount}
        │
        ▼
  validate_holdings()          →  for each row: resolve_ticker_metadata(ticker)
  (ingestion.py)                    - is this a real, tradeable ticker?
        │                          - what currency/exchange/asset class?
        │                          - reject the row if it doesn't resolve
        ▼
  IngestionResult(holdings=[...], errors=[...])
        │
        ▼
  portfolio_service.finalize_ingestion()
        │
        ├─ calculate_weights()      normalize weights (raw_weight, or derive
        │                           from quantity×price, or fall back to
        │                           equal-weight — logged when that fallback fires)
        │
        ├─ set_portfolio()          stash holdings on the session
        │
        └─ get_portfolio_baseline() run the FULL math suite once, up front,
                                    so the "Overview" tab has data instantly
                                    without waiting for the first chat message
```

**Why three separate parsers feed one validation gate:** the LLM (or regex fallback) that parses text, and the column-alias matching that parses CSV, are both "best effort, untrusted" — `validate_holdings()` is the single choke point that enforces "every holding has a real, tradeable ticker" regardless of how sloppy the input was. This is also where the golden rule ("LLM never computes real numbers") gets enforced structurally: the LLM only ever extracts *what the user typed*, never invents a price or a ticker that doesn't independently verify against Yahoo Finance.

### The screenshot path specifically
`ingestion.parse_image_input()` sends every screenshot to Gemini in one multimodal request with a prompt that explicitly says: *"only extract values that are actually visible... never estimate, guess, compute, or hallucinate a number."* The output is JSON-normalized through the exact same `_holdings_from_llm_json()` helper the text parser uses — so from `validate_holdings()` onward, a screenshot-derived holding and a typed holding are indistinguishable. This is deliberate: it means the entire safety net (ticker validation, currency checks, weight normalization) applies to screenshots for free.

---

## 6. Market data — the Yahoo Finance fix (important production story)

**The problem:** `yfinance`'s `.info` property and `.download()` (in recent versions) require Yahoo's cookie+crumb CSRF handshake. Yahoo aggressively rate-limits that handshake on shared cloud IPs — every ticker lookup on Render was failing with `YFRateLimitError: Too Many Requests`, even though the exact same code worked fine locally.

**The fix:** `market_data.py` no longer uses the `yfinance` package at all. It calls `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}` directly — an older, simpler Yahoo endpoint that doesn't require the crumb handshake and has proven reliable in production. This single endpoint provides:
- `meta.regularMarketPrice`, `meta.currency`, `meta.exchangeName` → ticker validation (`resolve_ticker_metadata`)
- `timestamp[]` + `indicators.quote[0].close[]` → the full daily price history (`fetch_prices`, `fetch_benchmark`)

**The tradeoff:** sector/industry data (needed for the diversification chart) isn't available on this crumb-free endpoint — the endpoint that has it (`quoteSummary`) is exactly the one that's blocked. `get_metadata()` reports `"Unknown"` for sector/industry rather than blocking anything. Everything that drives real portfolio math (prices, CAGR, Sharpe, drawdown, correlation) stays 100% live and unaffected.

**Caching:** `requests_cache` wraps all HTTP calls with a 24-hour SQLite cache, so repeated lookups of the same ticker within a day are free.

---

## 7. The chat/agent flow — deep dive

This is the part worth spending the most video time on, since it's the most "AI-native" part of the system.

### 7.1 Tool definitions
`agent.py` defines six `@tool`-decorated functions the LLM can call:

| Tool | Underlying math | Maps to canvas view |
|---|---|---|
| `get_portfolio_allocation` | just returns current holdings | `none` |
| `calculate_performance` | `math_engine.performance` | `performance` |
| `get_risk_metrics` | `math_engine.risk` | `risk` |
| `get_diversification` | `math_engine.diversification` | `diversification` |
| `simulate_trade` | `math_engine.whatif` | `whatif` |
| `get_correlation_matrix_tool` | `math_engine.correlation` | `correlation` |

Each tool is a thin wrapper: it pulls the current session's holdings from a module-level `_current_holdings` variable (set at the top of `chat()`), calls the real math function, and returns the raw dict. **The LLM never sees the math — it only sees the result.**

### 7.2 The system prompt
`SYSTEM_PROMPT` is a strict contract: *"ALWAYS call the appropriate tool... ALWAYS respond with a valid JSON object matching EXACTLY this schema."* The schema has three fields: `text` (the prose answer), `suggested_prompts` (3 follow-up questions), and `canvas_state` (`{view, data}`).

### 7.3 The agent loop
`chat(session_id, message)`:
1. Loads the last 10 turns of chat history for context.
2. Calls `executor.invoke(...)` — this is LangChain's `create_agent()` graph. Internally it may call Gemini, get back a tool-call request, execute the Python tool function, feed the result back to Gemini, and repeat until Gemini produces a final text answer (this is standard ReAct-style tool calling).
3. `parse_llm_output()` parses that final text as JSON into a `ChatResponse` pydantic model. If the LLM's JSON is malformed (happens occasionally), `make_fallback_response()` wraps the raw text in a safe default response instead of crashing.

### 7.4 The canvas reliability fix — the most important design detail
Here's the problem this session fixed twice:

**Bug 1:** the LLM would answer a question correctly in prose (e.g., "your Sharpe ratio is -0.35...") but leave `canvas_state.view` set to whatever it was on the *previous* turn — because generating that view label is a separate mental step for the LLM from generating the prose, and LLMs aren't perfectly self-consistent across fields in a single JSON blob.

**Bug 2 (subtler):** even when the LLM got the view right, it sometimes failed to faithfully **transcribe** the full tool-output dict into `canvas_state.data` — resulting in a correctly-labeled tab that rendered with blank metric cards, because `data` was `{}` or partial.

**The fix — don't trust the LLM to be internally consistent, verify against ground truth:**

```python
# Every tool stashes its real return value as a side effect
_last_tool_result: dict[str, dict] = {}

@tool
def calculate_performance(...) -> dict:
    result = calculate_performance_metrics(...)
    _last_tool_result["calculate_performance"] = result   # ← ground truth
    return result
```

After the agent finishes, `chat()` inspects the actual LangChain message history to find which tool was **really** called last (`_last_tool_called()`), looks up the map `_TOOL_TO_VIEW`, and **overwrites** both `response.canvas_state.view` and `response.canvas_state.data` with the deterministic, ground-truth values — regardless of what the LLM's JSON said:

```python
last_tool = _last_tool_called(result.get("messages", []))
expected_view = _TOOL_TO_VIEW.get(last_tool)
if expected_view:
    response.canvas_state.view = expected_view
    tool_data = _last_tool_result.get(last_tool)
    if tool_data:
        response.canvas_state.data = tool_data
```

This is the same "LLM never computes, only calls tools" philosophy extended one layer further: **the LLM also never gets to be the source of truth for which UI component renders or what data it renders with.** The backend derives both deterministically from which Python function actually executed.

### 7.5 How this reaches the frontend (the "dynamic canvas" the user sees)
1. `chat_stream_generator` (in `main.py`) streams the answer text token-by-token as SSE `event: token`.
2. After the text finishes, it sends **one** `event: canvas` with `{view, data, suggested_prompts}` — this is the corrected, ground-truth canvas state from §7.4.
3. On the frontend, `App.jsx`'s SSE handler calls `setCanvasState({view: data.view, data: data.data})` when it receives that event.
4. `VisualCanvas.jsx` renders purely off that `canvasState` prop — `activeView === 'performance'` shows the performance metrics grid + comparison chart, `activeView === 'risk'` shows drawdown + VaR, etc. There's no polling, no separate fetch — the single SSE event *is* the instruction for which component to mount.

So "the agent invokes the UI component" is literally true: the tool the agent calls determines both the answer text and, deterministically, which canvas view lights up next.

---

## 8. Guardrails

`guardrails.py` has two jobs:

1. **Input:** `check_injection(text)` — blocklist + unicode-normalization (catches zero-width character tricks, full-width homoglyphs) against known prompt-injection phrases ("ignore previous instructions", "reveal your system prompt", etc.). This runs before the message ever reaches Gemini.
2. **Output:** `parse_llm_output(raw)` — strict Pydantic schema validation (`ChatResponse`/`CanvasState`) on whatever the LLM returns, handling markdown code fences and partial JSON gracefully, falling back to a safe response if parsing truly fails.

---

## 9. Session state

`session_store.py` defines a small `SessionStore` interface with one implementation, `InMemorySessionStore` — a `TTLCache` (max 500 sessions, 1-hour inactivity eviction) holding `PortfolioSession(session_id, holdings, history)` objects. This is intentionally behind an interface so a future Redis-backed implementation (needed before horizontal scaling — in-memory state doesn't survive across multiple server processes) can be swapped in without touching `agent.py`.

---

## 10. Security posture (for completeness in the video)

- CORS locked to explicit origins (env-configurable via `ALLOWED_ORIGINS`), no wildcard methods/headers.
- Rate limiting per endpoint (`slowapi`) — tighter on the more expensive endpoints (5/min on image ingestion, which triggers a vision call; 20/min on chat).
- File/image uploads validated by MIME type and size before the body is even fully read.
- SSE token stream is stripped of control characters before reaching the browser.
- Exceptions are logged server-side with full tracebacks; the client only ever sees a generic "An error occurred" message — no stack traces leak.
- `pip-audit` runs in CI against a pinned `requirements.lock`.

---

## 11. Suggested video structure

1. **Cold open:** show the live app, paste a screenshot, watch it ingest.
2. **"Here's the promise":** LLM never computes — show `math_engine/performance.py`'s `calculate_performance_metrics()` as the actual Sharpe ratio formula, contrast with the LLM tool wrapper that just calls it.
3. **Walk the ingestion funnel** (§5) using the screenshot path as the concrete example — screen-record `parse_image_input` → `validate_holdings` → `finalize_ingestion`.
4. **Walk the chat/canvas flow** (§7) — this is the most interesting part. Show the tool table, show the system prompt, then show the `_last_tool_result` / `_TOOL_TO_VIEW` override and explain *why* it exists (the two bugs it fixes) — this is a great "here's what production AI engineering actually looks like" beat.
5. **Close on the Yahoo Finance story** (§6) — a real "it worked locally, broke in prod, here's the actual root cause and fix" narrative, which is very relatable/credible content for a technical audience.
