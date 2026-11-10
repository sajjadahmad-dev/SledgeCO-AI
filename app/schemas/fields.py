from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Evidence(BaseModel):
    quote: str = ""
    page: int | None = Field(default=None, ge=1)


class ExtractedField[T](BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    value: T | None = None
    raw_text: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: Evidence | None = None
    validation: str = "not_checked"


class LineItem(BaseModel):
    description: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    amount: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])


class DateField(ExtractedField[date]):
    ambiguous: bool = False
