from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser

from app.schemas.enums import ApprovalStatus

_NULLISH = {"n/a", "na", "none", "null", "-", "--", "unknown"}


def normalize_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip()
    if s.casefold() in _NULLISH:
        return None
    # credits: ($1,200.00)  -$1,200.00  1,200.00-  (whole string wrapped in parentheses)
    negative = bool(
        re.fullmatch(r"\s*\(\s*[^\d()]*[\d.,]+\s*[^\d()]*\)\s*", s)
        or re.match(r"\s*[-\u2212\u2013]", s)
        or re.search(r"\d\s*-\s*$", s)
    )
    m = re.search(r"\d[\d,]*\.?\d*|\.\d+", s)
    if not m:
        return None
    try:
        amount = Decimal(m.group().replace(",", ""))
    except InvalidOperation:
        return None
    return -amount if negative else amount


def normalize_date(value: Any) -> tuple[date | None, bool]:
    if value is None or value == "":
        return None, False
    raw = str(value).strip()
    ambiguous = False
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", raw)
    if m:  # 03/04/2026 is ambiguous; 03/15/2026 is not
        a, b = int(m.group(1)), int(m.group(2))
        ambiguous = a <= 12 and b <= 12 and a != b
    try:
        # Parse twice with different defaults: if results differ, the text lacked a
        # year/month/day and dateutil would have silently filled it from "today".
        d1 = parser.parse(raw, dayfirst=False, default=datetime(1900, 1, 1))
        d2 = parser.parse(raw, dayfirst=False, default=datetime(1901, 2, 2))
    except (ValueError, OverflowError, TypeError):
        return None, ambiguous
    if d1 != d2:
        return None, ambiguous
    return d1.date(), ambiguous


def normalize_days(value: Any) -> int | None:
    if value is None:
        return None
    s = str(value).casefold()
    if re.search(r"\b(none|no change|no impact|zero)\b", s):
        return 0
    match = re.search(r"[-\u2212]?\d+", s)
    if not match:
        return None
    n = int(match.group().replace("\u2212", "-"))
    return -n if re.search(r"\b(reduc|decrease|less)", s) and n > 0 else n


def normalize_approval_status(value: Any) -> ApprovalStatus:
    """Normalize a status label without allowing explanatory text into the enum."""
    if value is None:
        return ApprovalStatus.UNKNOWN
    match = re.match(
        r"\s*(approved|pending|proposed|rejected|unknown)\b",
        str(value),
        flags=re.IGNORECASE,
    )
    if not match:
        return ApprovalStatus.UNKNOWN
    status = match.group(1).casefold()
    if status == "proposed":
        return ApprovalStatus.PENDING
    return ApprovalStatus(status)