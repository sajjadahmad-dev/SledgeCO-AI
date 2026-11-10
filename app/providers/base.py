from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    def extract(self, document_text: str, pages: list[str] | None = None) -> list[dict[str, Any]]:
        """Return one or more schema-compatible extraction dictionaries."""
