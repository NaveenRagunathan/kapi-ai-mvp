import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from app.ingestion import ingest_portfolio
from app.agent import chat, set_portfolio, get_or_create_session, clear_session
from app.guardrails import check_injection

app = FastAPI(title="Kalpi AI Portfolio Analyzer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


class TextPortfolioRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


@app.post("/api/portfolio/ingest")
async def ingest_from_text(body: TextPortfolioRequest):
    session_id = body.session_id or str(uuid.uuid4())
    holdings = ingest_portfolio(text=body.text)
    set_portfolio(session_id, holdings)
    return {"session_id": session_id, "holdings": holdings, "count": len(holdings)}


@app.post("/api/portfolio/ingest/file")
async def ingest_from_file(file: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    contents = await file.read()
    file_type = "excel" if file.filename.endswith((".xlsx", ".xls")) else "csv"
    session_id = session_id or str(uuid.uuid4())
    holdings = ingest_portfolio(file_bytes=contents, file_type=file_type)
    set_portfolio(session_id, holdings)
    return {"session_id": session_id, "holdings": holdings, "count": len(holdings)}


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")
def chat_endpoint(body: ChatRequest):
    is_safe, reason = check_injection(body.message)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Message blocked: {reason}")

    session = get_or_create_session(body.session_id)
    if not session.holdings:
        from app.guardrails import make_fallback_response
        return make_fallback_response(
            "Please upload a portfolio first before asking questions. "
            "You can paste text like '50% AAPL, 50% MSFT' or upload a CSV file."
        )

    response = chat(body.session_id, body.message)
    return response


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    session = get_or_create_session(session_id)
    return {
        "session_id": session_id,
        "holdings": session.holdings,
        "history_length": len(session.history),
    }


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    clear_session(session_id)
    return {"message": "Session cleared"}
