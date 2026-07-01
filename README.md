# Kalpi AI Portfolio Analyzer

An institutional-grade AI portfolio analyzer that turns raw investment data into personalized, interactive financial insights through a Chat + Canvas interface.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│   IngestionForm │ ChatPanel │ VisualCanvas │ Charts      │
└────────────┬───────────────────────┬────────────────────┘
             │ REST (JSON/multipart)  │
┌────────────▼───────────────────────▼────────────────────┐
│                  FastAPI Backend                         │
│  /api/portfolio/ingest  /api/chat  /api/session/:id     │
└────────────┬───────────────────────┬────────────────────┘
             │                       │
┌────────────▼───────────┐  ┌────────▼──────────────────┐
│  Guardrails Engine     │  │  LangChain Orchestrator    │
│  · Injection detection │  │  · Claude Sonnet 4.6       │
│  · Output validation   │  │    (+ Gemini 2.0 fallback) │
│  · ChatResponse schema │  │  · 5 deterministic tools   │
└────────────────────────┘  └────────┬──────────────────┘
                                     │
┌────────────────────────────────────▼──────────────────────┐
│                Financial Math Engine                       │
│  get_portfolio_allocation  │  calculate_performance_metrics│
│  calculate_risk_metrics    │  get_diversification          │
│  run_what_if_simulation    │  get_correlation_matrix       │
└────────────────────────────┬──────────────────────────────┘
                             │
┌────────────────────────────▼──────────────────────────────┐
│              Market Data Service                           │
│  yfinance + requests-cache (24hr SQLite)                   │
│  fetch_prices · fetch_benchmark · get_metadata             │
└────────────────────────────────────────────────────────────┘
```


---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Recharts, vanilla CSS |
| Backend | FastAPI, uvicorn |
| AI Orchestration | LangChain (Claude Sonnet 4.6 primary, Gemini 2.0 Flash fallback) |
| Market Data | yfinance, requests-cache (SQLite, 24hr TTL) |
| Math | pandas, numpy (all deterministic — LLM never computes) |
| Validation | Pydantic v2 |

---

## Feature Implementation

### 1. Zero-Friction Portfolio Ingestion
Three input modes handled by `backend/app/ingestion.py`:
- **File upload** — CSV or Excel (.xlsx/.xls) via `POST /api/portfolio/ingest/file`
- **Text paste** — Free-text like `"50% AAPL, 50% MSFT"` or `"Reliance: 10 shares"` via `POST /api/portfolio/ingest`
- **Auto-normalization** — weights are normalized to sum=1.0; quantities are converted to value-weights via live prices
- **Ticker validation** — auto-appends `.NS` suffix for Indian stocks that fail bare-ticker lookup

### 2. Chat + Canvas Interface
- **Chat panel** — conversational interface with message history, typing indicator, suggested prompt chips, and prompt-injection warning banners
- **Canvas panel** — five tabs (Performance, Risk, Diversification, Correlation, What-If) that auto-switch based on `canvas_state.view` returned by the AI
- **Real-time sync** — every AI response includes a `canvas_state` field that drives which charts appear

### 3. Deep-Dive Financial Analysis
All metrics are computed by deterministic Python functions — the LLM is strictly an orchestrator.

| Tool | Metrics |
|---|---|
| `calculate_performance_metrics` | CAGR, Sharpe, Sortino, active return vs benchmark |
| `calculate_risk_metrics` | Max Drawdown, VaR (95%), Beta, annualized volatility |
| `get_diversification_and_sector_exposure` | Sector weights, Size/Value/Momentum factor scores |
| `get_correlation_matrix` | Pairwise return correlations (1Y daily), rendered as heatmap |
| `run_what_if_simulation` | Side-by-side Sharpe + MDD comparison for a proposed trade |

### 4. Proactive & Context-Aware Interactions
- **Suggested prompts** — every AI response includes 2–3 `suggested_prompts` that logically follow from the current analysis
- **What-if simulation** — mid-conversation trade swaps recompute all metrics instantly
- **Prompt injection protection** — `guardrails.py` blocks messages containing override phrases before they reach the LLM; the frontend shows a dismissible warning banner

---

## How the Agent Manages Portfolio State

```
Session lifecycle
─────────────────
1. User ingests portfolio  →  POST /api/portfolio/ingest
                               ingest_portfolio() normalizes holdings
                               set_portfolio(session_id, holdings) stores in RAM

2. User sends chat message  →  POST /api/chat
                                check_injection() — blocks if unsafe
                                session = get_or_create_session(session_id)
                                _current_holdings = session.holdings  ← injected as context
                                agent_executor.invoke(input, chat_history[-10:])
                                  ↓ LLM decides which tool to call
                                  ↓ Tool reads _current_holdings (module-level state)
                                  ↓ Returns deterministic result
                                parse_llm_output() validates ChatResponse schema
                                session.history.append(...)  ← persisted across turns

3. Delete session  →  DELETE /api/session/:id
                       clear_session() removes from RAM
```

Sessions are stored in an in-memory Python dict (`_sessions: dict[str, PortfolioSession]`). The last 10 messages are injected as `chat_history` on each turn so the LLM retains conversational context without an external database.

---

## Setup & Run

### Prerequisites
- Python 3.11+
- Node.js 20+
- `ANTHROPIC_API_KEY` (required for primary LLM)
- `GOOGLE_APPLICATION_CREDENTIALS` (optional, for Gemini fallback)

### Backend

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for tests

cp ../.env.example .env
# Edit .env — set ANTHROPIC_API_KEY

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # starts on http://localhost:5173
```


---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API key (primary LLM) |
| `GOOGLE_APPLICATION_CREDENTIALS` | No | Path to GCP service account JSON (Gemini fallback) |
| `SESSION_SECRET` | No | Secret for future session signing |

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

103 tests across 5 modules (ingestion, market data, math engine, guardrails, agent, API).

---

## Project Structure

```
kalpi_ai/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + endpoints
│   │   ├── ingestion.py     # CSV/Excel/text portfolio parsing
│   │   ├── market_data.py   # yfinance data fetcher + cache
│   │   ├── math_engine.py   # All financial calculations
│   │   ├── guardrails.py    # Injection detection + output validation
│   │   ├── agent.py         # LangChain orchestrator + session state
│   ├── tests/               # 103 unit + integration tests
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api/service.js
│       └── components/
│           ├── IngestionForm.jsx
│           ├── ChatPanel.jsx
│           ├── VisualCanvas.jsx
│           └── Charts.jsx
├── .env.example
└── README.md
```
