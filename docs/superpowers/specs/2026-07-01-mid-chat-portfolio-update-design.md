# Mid-Chat Portfolio Update — Design

## Problem

Once a portfolio is ingested, there is no way to change it without clicking
"New Portfolio," which wipes the session's chat history and canvas state
entirely. If a user pastes a new/updated portfolio (text, CSV/Excel, or a
screenshot) into the chat mid-conversation, the agent has no tool to act on
it — it can only apologize and suggest the user start over (confirmed via a
live screenshot of the current behavior).

## Goals

- Support replacing the active portfolio mid-chat via three channels: pasted
  chat text, file attach (CSV/Excel), and image attach (screenshots).
- Keep the existing chat thread and canvas state intact — no reset of
  `messages` or navigation away from the chat view. Old messages remain
  visible; the agent is instructed to treat them as stale once a new
  portfolio is loaded.
- Reuse the existing ingestion pipeline (`ingest_portfolio` +
  `finalize_ingestion` semantics) rather than building a second parser.

## Non-goals

- Incremental edits (e.g. "remove TCS", "bump HDFC to 15%") without a full
  re-paste/re-upload — out of scope for this iteration.
- Raising the 1000-char chat input cap in `guardrails.check_injection` —
  explicitly deferred; if long pastes get rejected, that's handled
  separately.
- Archiving/snapshotting the pre-update session server-side — the old
  portfolio's data is simply overwritten in place, matching how "New
  Portfolio" already behaves today.

## Architecture

Two independent paths converge on the same effect (overwrite
`session.holdings`, recompute baseline, refresh the frontend's holdings
panel) without touching `messages` or resetting the view:

1. **Pasted chat text** → a new LangChain tool `update_portfolio(raw_text)`
   is added to the agent's toolset. The system prompt instructs the agent:
   if the user's message looks like portfolio holdings data (tickers,
   quantities, weights, a holdings table) rather than a question, call this
   tool instead of answering normally.
2. **File/image attach in chat** → a new attach affordance in `ChatPanel`
   calls the *existing* `/api/portfolio/ingest/file` and
   `/api/portfolio/ingest/images` endpoints directly, passing the current
   `session_id`. These endpoints already overwrite holdings for a given
   `session_id` (see `finalize_ingestion` → `set_portfolio`), so no backend
   change is needed for this path — only frontend wiring.

## Backend changes

### `agent.py`

- Add a module-level `_current_session_id: str | None = None`, set at the
  top of `chat()` alongside the existing `_current_holdings = session.holdings`
  assignment. This mirrors the existing (already session-unsafe-under-
  concurrency) global-state pattern used for `_current_holdings` — not fixing
  that concurrency debt here, just following the existing convention.
- New tool:
  ```python
  @tool
  def update_portfolio(raw_text: str) -> dict:
      """Replace the current portfolio with new holdings described in raw_text.
      Call this when the user pastes new portfolio data (tickers, quantities,
      weights, or a holdings table) instead of asking a question."""
  ```
  Implementation: calls `ingest_portfolio(text=raw_text)`. On success (holdings
  found), calls `calculate_weights`, `set_portfolio(_current_session_id, holdings)`,
  `get_portfolio_baseline(holdings)`, updates `_current_holdings` in place, and
  returns `{"success": True, "holdings": [...], "baseline": {...}, "count": n}`.
  On failure (no holdings parsed), returns
  `{"success": False, "error": "<message from ingestion errors>"}` so the agent
  can explain the problem instead of silently failing.
- System prompt addition: instruct the agent to call `update_portfolio` when
  the message contains new portfolio data, and to disregard metrics discussed
  earlier in the conversation for the previous portfolio once an update
  succeeds.
- `_TOOL_TO_VIEW` and the canvas-override logic: `update_portfolio` maps to
  `canvas_state.view = "none"` (consistent with `get_portfolio_allocation`).
- In `chat()`, after the existing canvas-override block, add: if the last
  tool called was `update_portfolio` and its result had `success: True`, set
  `response.portfolio_update = {"holdings": ..., "baseline": ..., "count": ...}`
  on the `ChatResponse`.

### `guardrails.py`

- Add `portfolio_update: dict | None = None` to `ChatResponse`.

### `main.py`

- In `chat_stream_generator`, after the existing `canvas` SSE event, emit a
  `portfolio_update` event with the same payload whenever
  `response.portfolio_update` is not `None`:
  ```
  event: portfolio_update
  data: {"holdings": [...], "baseline": {...}, "count": n}
  ```

## Frontend changes

### `ChatPanel.jsx`

- Add an attach button (paperclip icon) next to the message input. Clicking
  opens a native file picker accepting `.csv,.xlsx,.xls,image/png,image/jpeg,image/webp`.
- On file selection, call a new `onAttach(file)` prop (wired to a new handler
  in `App.jsx`) rather than making API calls directly from `ChatPanel`, to
  keep API orchestration centralized in `App.jsx` as it already is for
  `handleSend`/`handleIngestStart`.

### `App.jsx`

- Extract the welcome-message-building logic currently inline in
  `handleIngestStart` (lines ~50-100: CAGR/Sharpe/MDD/grade/sector summary →
  `welcomeText` + `smartPrompts`) into a shared helper function
  `buildPortfolioSummaryMessage(baseline, holdingsCount)` so both the initial
  ingest flow and the new mid-chat update flow produce consistent messaging
  without duplicating the string-building logic.
- New handler `handlePortfolioAttach(file)`:
  1. Determine file type (image MIME → `ingestPortfolioImages`, else →
     `ingestPortfolioFile`), passing the existing `sessionId`.
  2. On success: update `holdings` and `baseline` state, append an assistant
     message to `messages` using `buildPortfolioSummaryMessage`, and reset
     `canvasState` to `{ view: 'none', data: {} }` (consistent with what a
     fresh ingest does) — but without touching prior `messages` entries.
  3. On failure: append an assistant-style error message to `messages`
     inline (no navigation, no clearing of state) so the user can retry.
- In `handleSend`'s SSE event switch (inside `sendChatMessageStream`'s
  callback), add a case for `portfolio_update`: update `holdings` and
  `baseline` state the same way item 2 above does, so a chat-text-detected
  update refreshes the "N holdings" badge and Overview tab live, without
  requiring a page action.
- No path in this feature clears `messages` or navigates away from
  `view === 'analysis'`.

## Data flow summary

```
User pastes portfolio text in chat
  → POST /api/chat
    → agent detects holdings-like text → calls update_portfolio tool
      → ingest_portfolio + set_portfolio (session.holdings overwritten)
      → returns success + new baseline
    → chat() sets response.portfolio_update
  → SSE: token events (agent's narration) + portfolio_update event
  → App.jsx updates holdings/baseline state live; messages thread untouched

User attaches CSV/screenshot in chat
  → POST /api/portfolio/ingest/file|images (existing endpoint, session_id passed)
    → set_portfolio (session.holdings overwritten)
  → App.jsx appends summary message, updates holdings/baseline state
```

## Testing

- `test_agent.py`: unit tests for `update_portfolio` tool — successful parse
  overwrites `_current_holdings` and returns the expected dict shape; failed
  parse (garbage text) returns `success: False` with an error message; the
  tool correctly calls `set_portfolio` for the active session.
- `test_api.py`: SSE stream includes a `portfolio_update` event when the
  agent's last tool call was `update_portfolio` with `success: True`, and
  omits it otherwise (e.g. a normal risk-metrics question).
- Manual/E2E: paste a new portfolio mid-chat and confirm the Overview tab,
  health grade, and holdings badge update without the chat thread or canvas
  resetting; repeat for file attach and image attach.

## Open risks

- `_current_holdings`/`_current_session_id` globals are not concurrency-safe
  across simultaneous requests from different sessions — this is pre-existing
  debt in `agent.py`, not introduced or fixed by this change.
- LLM tool-selection reliability: the agent might occasionally fail to call
  `update_portfolio` when it should (e.g. ambiguous phrasing mixing a
  question with pasted data). No heuristic fallback is included per the
  chosen design (LLM tool-call detection only) — if this proves unreliable
  in practice, a heuristic pre-check can be added later.
