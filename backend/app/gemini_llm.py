"""
Minimal LangChain ChatModel wrapper around google-generativeai SDK.

Uses the Gemini Developer API (generativelanguage.googleapis.com) with
Google service account OAuth credentials — no API key required.

Supports function/tool calling via Gemini's native function calling API.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterator, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_function


def _build_google_creds():
    """Build service account credentials for Gemini Developer API."""
    from google.oauth2 import service_account
    creds_str = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_str:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON not set in .env")
    info = json.loads(creds_str)
    return service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/generative-language"],
    )


def _build_genai_model(model_name: str):
    """Return a configured google.generativeai.GenerativeModel."""
    import google.generativeai as genai  # type: ignore
    genai.configure(credentials=_build_google_creds())
    return genai.GenerativeModel(model_name)


def _lc_to_gemini_contents(messages: List[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to Gemini content format."""
    contents = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            # Gemini doesn't have a system role in contents — prepend as user turn
            contents.append({"role": "user", "parts": [{"text": f"[System]: {msg.content}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        elif isinstance(msg, HumanMessage):
            contents.append({"role": "user", "parts": [{"text": msg.content}]})
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                parts = []
                for tc in msg.tool_calls:
                    parts.append({
                        "function_call": {
                            "name": tc["name"],
                            "args": tc["args"],
                        }
                    })
                if msg.content:
                    parts.append({"text": msg.content})
                contents.append({"role": "model", "parts": parts})
            else:
                contents.append({"role": "model", "parts": [{"text": msg.content or ""}]})
        elif isinstance(msg, ToolMessage):
            contents.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": msg.name or "tool",
                        "response": {"result": msg.content},
                    }
                }]
            })
    return contents


def _lc_tools_to_gemini(tools: list[BaseTool]) -> list[dict]:
    """Convert LangChain tools to Gemini function declarations."""
    declarations = []
    for t in tools:
        fn = convert_to_openai_function(t)
        # Gemini uses the same schema as OpenAI function calling
        declarations.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return [{"function_declarations": declarations}]


class GeminiChatModel(BaseChatModel):
    """LangChain ChatModel backed by google-generativeai with service account auth."""

    model_name: str = "gemini-2.0-flash"
    temperature: float = 0.1
    _bound_tools: list = []

    @property
    def _llm_type(self) -> str:
        return f"gemini-service-account/{self.model_name}"

    def bind_tools(self, tools: Sequence[Any], **kwargs) -> "GeminiChatModel":  # type: ignore
        clone = self.__class__(model_name=self.model_name, temperature=self.temperature)
        clone._bound_tools = list(tools)
        return clone

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        import google.generativeai as genai

        tools = list(self._bound_tools or [])
        model = _build_genai_model(self.model_name)

        # Separate system message from conversation
        system_instruction = None
        filtered = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_instruction = msg.content
            else:
                filtered.append(msg)

        contents = _lc_to_gemini_contents(filtered)

        gen_config = genai.types.GenerationConfig(temperature=self.temperature)
        if system_instruction:
            model = genai.GenerativeModel(
                self.model_name,
                system_instruction=system_instruction,
            )
            genai.configure(credentials=_build_google_creds())

        gemini_tools = _lc_tools_to_gemini(tools) if tools else None

        response = model.generate_content(
            contents,
            generation_config=gen_config,
            tools=gemini_tools,
        )

        candidate = response.candidates[0]
        ai_msg = self._parse_candidate(candidate)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    def _parse_candidate(self, candidate) -> AIMessage:
        """Convert Gemini candidate to LangChain AIMessage."""
        tool_calls = []
        text_parts = []

        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                fc = part.function_call
                tool_calls.append({
                    "id": f"call_{fc.name}",
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                    "type": "tool_call",
                })
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)

        return AIMessage(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
        )
