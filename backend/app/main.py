import asyncio
import json
import logging
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Resolve .env relative to this file so it works in any deployment
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from app.agent import chat, get_or_create_session, clear_session
from app.guardrails import check_injection
from app.math_engine import get_correlation_matrix
from app.portfolio_service import ingest_text_blocking, ingest_file_blocking

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Kalpi AI Portfolio Analyzer", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security response headers
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"  # disabled in favour of CSP
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Restrict CORS — explicit methods and headers only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Accept"],
    allow_credentials=False,
)

# ---------------------------------------------------------------------------
# Upload constants
# ---------------------------------------------------------------------------

_ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# SSE token sanitizer
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

def _sanitize_token(text: str) -> str:
    """Strip dangerous control characters from an LLM output token before streaming."""
    return _CONTROL_CHAR_RE.sub("", text)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


class TextPortfolioRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


@app.post("/api/portfolio/ingest")
@limiter.limit("10/minute")
async def ingest_from_text(request: Request, body: TextPortfolioRequest):
    session_id = body.session_id or str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, ingest_text_blocking, session_id, body.text)


@app.post("/api/portfolio/ingest/file")
@limiter.limit("10/minute")
async def ingest_from_file(request: Request, file: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    # Validate MIME type before reading body
    if file.content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload a CSV or Excel file.")

    contents = await file.read()

    # Enforce file size cap
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB).")

    file_type = "excel" if file.filename.endswith((".xlsx", ".xls")) else "csv"
    session_id = session_id or str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, ingest_file_blocking, session_id, contents, file_type)


class ChatRequest(BaseModel):
    session_id: str
    message: str


async def chat_stream_generator(session_id: str, message: str):
    yield f"event: status\ndata: {json.dumps({'message': 'Analyzing query and resolving intent...'})}\n\n"
    await asyncio.sleep(0.4)
    yield f"event: status\ndata: {json.dumps({'message': 'Executing quantitative math tools...'})}\n\n"

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, chat, session_id, message)

        text = response.text
        words = text.split(" ")
        for word in words:
            # Strip control characters before streaming LLM output
            safe_word = _sanitize_token(word)
            yield f"event: token\ndata: {json.dumps({'text': safe_word + ' '})}\n\n"
            await asyncio.sleep(0.02)

        canvas_payload = {
            "view": response.canvas_state.view,
            "data": response.canvas_state.data,
            "suggested_prompts": response.suggested_prompts,
        }
        yield f"event: canvas\ndata: {json.dumps(canvas_payload)}\n\n"
    except asyncio.CancelledError:
        # Always re-raise CancelledError so the event loop can clean up
        raise
    except Exception:
        # Log the full exception server-side; never send internals to the client
        logger.exception("Chat stream error for session %s", session_id)
        yield f"event: error\ndata: {json.dumps({'detail': 'An error occurred. Please try again.'})}\n\n"


@app.post("/api/chat")
@limiter.limit("20/minute")
async def chat_endpoint(request: Request, body: ChatRequest):
    is_safe, reason = check_injection(body.message)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Message blocked: {reason}")

    session = get_or_create_session(body.session_id)
    if not session.holdings:
        async def fallback_generator():
            fallback_text = (
                "Please upload a portfolio first before asking questions. "
                "You can paste text like '50% AAPL, 50% MSFT' or upload a CSV file."
            )
            yield f"event: status\ndata: {json.dumps({'message': 'Resolving portfolio context...'})}\n\n"
            await asyncio.sleep(0.3)
            for word in fallback_text.split(" "):
                yield f"event: token\ndata: {json.dumps({'text': word + ' '})}\n\n"
                await asyncio.sleep(0.02)
            yield f"event: canvas\ndata: {json.dumps({'view': 'none', 'data': {}, 'suggested_prompts': []})}\n\n"
        return StreamingResponse(fallback_generator(), media_type="text/event-stream")

    return StreamingResponse(chat_stream_generator(body.session_id, body.message), media_type="text/event-stream")


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


@app.get("/api/portfolio/correlation/{session_id}")
def get_correlation(session_id: str):
    session = get_or_create_session(session_id)
    if not session.holdings:
        raise HTTPException(status_code=404, detail="No portfolio loaded for this session")
    return get_correlation_matrix(session.holdings)
