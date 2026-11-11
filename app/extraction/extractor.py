from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.extraction.normalizer import (
    normalize_amount,
    normalize_approval_status,
    normalize_date,
    normalize_days,
)
from app.providers.base import LLMProvider
from app.schemas.change_order import ChangeOrderExtraction
from app.schemas.enums import ChangeOrderType
from app.schemas.fields import DateField, Evidence, ExtractedField, LineItem


# ---- null-safe helpers: LLM output routinely contains null / wrong types ----------------
def _d(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _field(value: Any, raw: Any = None) -> ExtractedField:
    return ExtractedField(
        value=value, raw_text=str(raw if raw is not None else value) if value is not None else None
    )


def _pct(value: Any) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", str(value)) if value not in (None, "") else None
    return float(m.group()) if m else None


def _party_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return _text(value.get("name"))
    return _text(value)  # LLM sometimes returns a plain string


def _change_type(value: Any) -> ChangeOrderType:
    s = str(value or "").strip().lower()
    candidates = [s]
    if any(k in s for k in ("deduct", "credit", "decrease", "reduc")):
        candidates.insert(0, "deductive")
    elif any(k in s for k in ("add", "increase", "extra")):
        candidates.insert(0, "additive")
    for c in candidates:
        try:
            return ChangeOrderType(c)
        except ValueError:
            continue
    return ChangeOrderType("unknown")


def build_extraction(
    data: dict[str, Any], filename: str | None = None, page_count: int | None = None
) -> ChangeOrderExtraction:
    data = _d(data)
    financial_data = _d(data.get("financials"))
    schedule_data = _d(data.get("schedule"))
    approval_data = _d(data.get("approval"))
    change_data = _d(data.get("change_order"))
    project_data = _d(data.get("project"))
    parties_data = _d(data.get("parties"))

    line_items = [
        LineItem(
            description=_field(_text(item.get("description"))),
            amount=_field(normalize_amount(item.get("amount")), item.get("amount")),
        )
        for item in _l(financial_data.get("line_items"))
        if isinstance(item, dict)
    ]
    date_value, ambiguous = normalize_date(schedule_data.get("revised_completion_date"))
    approval_date, approval_ambiguous = normalize_date(approval_data.get("date"))
    financial_fields = {
        key: _field(normalize_amount(financial_data.get(key)), financial_data.get(key))
        for key in (
            "subtotal",
            "markup_amount",
            "total",
            "original_contract_sum",
            "net_previous_changes",
            "contract_sum_prior",
            "new_contract_sum",
        )
    }
    financial_fields["markup_pct"] = _field(
        _pct(financial_data.get("markup_pct")), financial_data.get("markup_pct")
    )
    raw_type = change_data.get("type")
    return ChangeOrderExtraction(
        document={
            "filename": filename,
            "file_type": filename.rsplit(".", 1)[-1] if filename and "." in filename else None,
            "page_count": page_count,
        },
        project={key: _field(_text(project_data.get(key))) for key in ("name", "number", "address")},
        parties={
            party: {"name": _field(_party_name(parties_data.get(party)))}
            for party in ("owner", "contractor", "subcontractor")
        },
        change_order={key: _field(_text(change_data.get(key))) for key in ("number", "title", "reason", "scope")}
        | {
            "type": _field(_change_type(raw_type), _text(raw_type)),
            "is_proposed": _field(change_data.get("is_proposed")),
        },
        financials={"line_items": line_items, **financial_fields},
        schedule={
            "days_added": _field(
                normalize_days(schedule_data.get("days_added")), schedule_data.get("days_added")
            ),
            "revised_completion_date": DateField(
                value=date_value,
                raw_text=_text(schedule_data.get("revised_completion_date")) if date_value else None,
                ambiguous=ambiguous,
            ),
        },
        approval={
            "status": _field(
                normalize_approval_status(approval_data.get("status")),
                approval_data.get("status_raw", approval_data.get("status")),
            ),
            "approved_by": _field(_text(approval_data.get("approved_by"))),
            "date": DateField(
                value=approval_date,
                raw_text=_text(approval_data.get("date")) if approval_date else None,
                ambiguous=approval_ambiguous,
            ),
        },
    )


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _found(raw: str, text: str) -> bool:
    folded = raw.casefold()
    if folded in text.casefold():
        return True
    numeric = normalize_amount(raw)
    if numeric is not None:
        numeric_text = format(numeric, "f")
        candidates = {numeric_text, f"{numeric:,.2f}"}
        return any(candidate in text for candidate in candidates)
    s = _squash(raw)
    if len(s) >= 4:  # long enough that a squashed substring match is meaningful
        return s in _squash(text)
    # very short values ("0", "5"): require a whole-token match, not a stray digit
    return bool(s) and re.search(rf"(?<![a-z0-9]){re.escape(folded.strip())}(?![a-z0-9])", text.casefold()) is not None


def _attach_evidence(extraction: ChangeOrderExtraction, pages: list[str] | None) -> None:
    if not pages:
        return
    for field in _iter_fields(extraction):
        if not field.raw_text:
            continue
        raw_text = field.raw_text.strip()
        for page_number, page_text in enumerate(pages, start=1):
            if _found(raw_text, page_text):
                quote = next(
                    (line.strip() for line in page_text.splitlines() if line.strip() and _found(raw_text, line)),
                    raw_text,
                )
                field.evidence = Evidence(quote=quote, page=page_number)
                break


def _iter_fields(value: Any):
    if isinstance(value, ExtractedField):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_fields(item)
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _iter_fields(getattr(value, name))


class Extractor:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def extract(
        self, text: str, pages: list[str] | None = None, filename: str | None = None
    ) -> list[ChangeOrderExtraction]:
        extractions = [
            build_extraction(item, filename, len(pages) if pages else None)
            for item in self.provider.extract(text, pages)
        ]
        for extraction in extractions:
            _attach_evidence(extraction, pages)
        return extractions
