"""Google Gemini via the Google AI Studio free tier.  Get a key: https://aistudio.google.com/apikey
.env:  GEMINI_API_KEY=...   GEMINI_MODEL=gemini-flash-latest   (copy a current free model name from AI Studio)

NOTE: free-tier prompts may be used by Google to improve its products -> use SYNTHETIC documents only.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from app.providers.base import LLMProvider
from app.providers.llm_common import (
    SYSTEM_PROMPT,
    ProviderError,
    parse_records,
    post_json,
    user_message,
)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 client: httpx.Client | None = None) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is empty (add it to .env)")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        self.client = client

    def extract(self, document_text: str, pages: list[str] | None = None) -> list[dict[str, Any]]:
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_message(document_text)}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        data = post_json(f"{BASE}/{self.model}:generateContent",
                         {"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                         body, client=self.client)
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            reason = (data.get("candidates") or [{}])[0].get("finishReason") if isinstance(data, dict) else None
            raise ProviderError(f"Gemini returned no content (finishReason={reason})") from None
        return parse_records(text)
