from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser


def normalize_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    cleaned = re.sub(r"[$,\s]", "", str(value))
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def normalize_date(value: Any) -> tuple[date | None, bool]:
    if value is None or value == "":
        return None, False
    raw = str(value).strip()
    ambiguous = bool(re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", raw))
    try:
        return parser.parse(raw, dayfirst=False).date(), ambiguous
    except (ValueError, OverflowError):
        return None, ambiguous


def normalize_days(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None
