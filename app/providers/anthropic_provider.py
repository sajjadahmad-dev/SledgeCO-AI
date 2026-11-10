from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from app.extraction.prompts import EXTRACTION_SYSTEM_PROMPT
from app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for the Anthropic provider")
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
        self.model_name = model_name

    def extract(self, document_text: str, pages: list[str] | None = None) -> list[dict[str, Any]]:
        try:
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=8000,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"<untrusted_document>\n{document_text}\n</untrusted_document>",
                    }
                ],
            )
        except anthropic.AuthenticationError as exc:
            raise RuntimeError("Anthropic authentication failed; check ANTHROPIC_API_KEY.") from exc
        except anthropic.RateLimitError as exc:
            raise RuntimeError("Anthropic rate limit reached; retry later.") from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError("Could not connect to Anthropic.") from exc
        except anthropic.APIStatusError as exc:
            logger.error("Anthropic request failed with status %s.", exc.status_code)
            raise RuntimeError(f"Anthropic request failed with status {exc.status_code}.") from exc
        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", "") == "text" and hasattr(block, "text")
        )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Anthropic provider returned non-JSON extraction output") from exc
        return data if isinstance(data, list) else [data]
