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

BASE = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY is empty (add it to .env)")
        self.model = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.client = client

    def extract(self, document_text: str, pages: list[str] | None = None) -> list[dict[str, Any]]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message(document_text)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        data = post_json(
            BASE,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            body,
            client=self.client,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Groq returned no content") from exc
        return parse_records(text)
