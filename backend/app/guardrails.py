"""Input/output guardrails and validation for AI-generated responses."""

import json
import re
import unicodedata
from typing import Literal, List

from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# 4.2 Pydantic models
# ---------------------------------------------------------------------------

class CanvasState(BaseModel):
    view: Literal["performance", "risk", "diversification", "whatif", "correlation", "none"]
    data: dict


class ChatResponse(BaseModel):
    text: str
    suggested_prompts: List[str]
    canvas_state: CanvasState
    portfolio_update: dict | None = None


# ---------------------------------------------------------------------------
# 4.1 Injection detector
# ---------------------------------------------------------------------------

_BLOCKED_PHRASES = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the above",
    "disregard previous instructions",
    "disregard all previous instructions",
    "system prompt",
    "you are now a",
    "you are no longer",
    "forget your instructions",
    "forget everything above",
    "new instructions",
    "override your instructions",
    "reveal your instructions",
    "reveal your system prompt",
    "print your instructions",
    "repeat your instructions",
    "disregard",
    "act as",
    "jailbreak",
    "dan",
]

# Zero-width / invisible characters are sometimes used to split up
# blocked phrases (e.g. "ignore​previous​instructions").
_ZERO_WIDTH_RE = re.compile(r"[​-‏‪-‮﻿]")

_MAX_INPUT_LENGTH = 1000


def _normalize_for_matching(text: str) -> str:
    """Normalize text so obfuscated phrase variants still match the blocklist.

    - Unicode NFKC normalization collapses full-width/homoglyph characters
      (e.g. fullwidth "ｉｇｎｏｒｅ") down to their ASCII equivalents.
    - Zero-width characters are stripped since they're sometimes inserted
      mid-word to dodge substring matching.
    - Runs of whitespace are collapsed to a single space so phrases split
      across newlines/tabs/extra spaces still match.
    """
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def check_injection(text: str) -> tuple[bool, str]:
    """Returns (is_safe, reason).

    is_safe=True means the text is clean and safe to pass to the LLM.

    Block conditions (return (False, reason)):
    - len(text) > 1000 chars
    - Contains any blocked phrase (case-insensitive) after normalizing
      unicode homoglyphs, zero-width characters, and whitespace runs.

    Return (True, "ok") if clean.

    Note: this is a defense-in-depth layer, not a complete defense against
    prompt injection. The primary defenses are the sandboxed system prompt
    in agent.py and strict output schema validation in parse_llm_output().
    """
    if len(text) > _MAX_INPUT_LENGTH:
        return (False, f"Input exceeds maximum length of {_MAX_INPUT_LENGTH} characters")

    normalized = _normalize_for_matching(text)
    for phrase in _BLOCKED_PHRASES:
        if phrase in normalized:
            return (False, f"Blocked phrase detected: '{phrase}'")

    return (True, "ok")


# ---------------------------------------------------------------------------
# 4.2 Output parser / validator
# ---------------------------------------------------------------------------

def _normalize_llm_raw(raw) -> str:
    """Normalize LLM output to a plain string.

    Handles:
    - Plain str
    - Vertex AI multi-modal content blocks: [{'type': 'text', 'text': '...'}]
    - Single dict with 'text' key
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, dict):
                parts.append(item.get("text", "") or item.get("content", ""))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if isinstance(raw, dict):
        return raw.get("text", "") or raw.get("content", "") or str(raw)
    return str(raw)


def parse_llm_output(raw) -> ChatResponse:
    """Parse JSON from LLM response.

    Handles content blocks, markdown formatting, and partial text wrapping.
    """
    # Step 0: Extract text from content blocks list if necessary
    if isinstance(raw, list):
        txt_parts = []
        for part in raw:
            if isinstance(part, dict) and "text" in part:
                txt_parts.append(part["text"])
            elif isinstance(part, str):
                txt_parts.append(part)
        raw = "".join(txt_parts)
    elif not isinstance(raw, str):
        raw = str(raw)

    parsed = None

    # Step 1: try direct parse
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    # Step 2: try extracting from markdown code block
    if parsed is None:
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                pass

    # Step 3: try finding the first '{' and last '}' and parsing that substring
    if parsed is None:
        start_idx = raw.find("{")
        end_idx = raw.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            try:
                parsed = json.loads(raw[start_idx:end_idx+1])
            except (json.JSONDecodeError, ValueError):
                pass

    if parsed is None:
        raise ValueError(f"Could not parse JSON from LLM output: {raw!r}")

    # Normalize parsed['text'] if it's a list/dict of content blocks
    if isinstance(parsed, dict) and "text" in parsed:
        parsed["text"] = _normalize_llm_raw(parsed["text"])

    # Validate against ChatResponse model
    try:
        return ChatResponse.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(f"LLM output failed schema validation: {exc}") from exc


def make_fallback_response(text) -> ChatResponse:
    """Create a safe ChatResponse when parsing fails completely."""
    return ChatResponse(
        text=_normalize_llm_raw(text),
        suggested_prompts=[],
        canvas_state=CanvasState(view="none", data={}),
    )
