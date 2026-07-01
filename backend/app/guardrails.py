"""Input/output guardrails and validation for AI-generated responses."""

import json
import re
from typing import Literal, List

from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# 4.2 Pydantic models
# ---------------------------------------------------------------------------

class CanvasState(BaseModel):
    view: Literal["performance", "risk", "diversification", "whatif", "none"]
    data: dict


class ChatResponse(BaseModel):
    text: str
    suggested_prompts: List[str]
    canvas_state: CanvasState


# ---------------------------------------------------------------------------
# 4.1 Injection detector
# ---------------------------------------------------------------------------

_BLOCKED_PHRASES = [
    "ignore previous instructions",
    "system prompt",
    "you are now a",
    "forget your instructions",
    "disregard",
    "act as",
    "jailbreak",
    "dan",
]

_MAX_INPUT_LENGTH = 1000


def check_injection(text: str) -> tuple[bool, str]:
    """Returns (is_safe, reason).

    is_safe=True means the text is clean and safe to pass to the LLM.

    Block conditions (return (False, reason)):
    - len(text) > 1000 chars
    - Contains any of (case-insensitive):
      "ignore previous instructions", "system prompt", "you are now a",
      "forget your instructions", "disregard", "act as", "jailbreak", "DAN"

    Return (True, "ok") if clean.
    """
    if len(text) > _MAX_INPUT_LENGTH:
        return (False, f"Input exceeds maximum length of {_MAX_INPUT_LENGTH} characters")

    lower = text.lower()
    for phrase in _BLOCKED_PHRASES:
        if phrase in lower:
            return (False, f"Blocked phrase detected: '{phrase}'")

    return (True, "ok")


# ---------------------------------------------------------------------------
# 4.2 Output parser / validator
# ---------------------------------------------------------------------------

def parse_llm_output(raw: str) -> ChatResponse:
    """Parse JSON from LLM response string.

    Steps:
    1. Try json.loads(raw) directly
    2. If raw contains markdown code block ```json...```, extract content and retry
    3. Validate against ChatResponse Pydantic model
    4. On validation failure: raise ValueError with descriptive message

    Note: The OutputFixingParser retry (re-calling LLM) is handled in agent.py,
    not here. This function just parses and validates.
    """
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

    if parsed is None:
        raise ValueError(f"Could not parse JSON from LLM output: {raw!r}")

    # Step 3 & 4: validate against ChatResponse model
    try:
        return ChatResponse.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(f"LLM output failed schema validation: {exc}") from exc


def make_fallback_response(text: str) -> ChatResponse:
    """Create a safe ChatResponse when parsing fails completely."""
    return ChatResponse(
        text=text,
        suggested_prompts=[],
        canvas_state=CanvasState(view="none", data={}),
    )
