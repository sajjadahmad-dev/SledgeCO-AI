from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.extraction.normalizer import normalize_amount, normalize_date, normalize_days
from app.providers.base import LLMProvider
from app.schemas.change_order import ChangeOrderExtraction
from app.schemas.enums import ApprovalStatus, ChangeOrderType
from app.schemas.fields import DateField, Evidence, ExtractedField, LineItem


def _field(value: Any, raw: Any = None) -> ExtractedField:
    return ExtractedField(
        value=value, raw_text=str(raw if raw is not None else value) if value is not None else None
    )


def build_extraction(
    data: dict[str, Any], filename: str | None = None, page_count: int | None = None
) -> ChangeOrderExtraction:
    financial_data = data.get("financials") or {}
    line_items = [
        LineItem(
            description=_field(item.get("description")),
            amount=_field(normalize_amount(item.get("amount")), item.get("amount")),
        )
        for item in financial_data.get("line_items", [])
    ]
    date_value, ambiguous = normalize_date(
        (data.get("schedule") or {}).get("revised_completion_date")
    )
    approval_date, approval_ambiguous = normalize_date((data.get("approval") or {}).get("date"))
    change_data = data.get("change_order") or {}
    approval_data = data.get("approval") or {}
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
        float(financial_data["markup_pct"])
        if financial_data.get("markup_pct") not in (None, "")
        else None,
        financial_data.get("markup_pct"),
    )
    return ChangeOrderExtraction(
        document={
            "filename": filename,
            "file_type": filename.rsplit(".", 1)[-1] if filename and "." in filename else None,
            "page_count": page_count,
        },
        project={
            key: _field((data.get("project") or {}).get(key))
            for key in ("name", "number", "address")
        },
        parties={
            party: {"name": _field((data.get("parties") or {}).get(party, {}).get("name"))}
            for party in ("owner", "contractor", "subcontractor")
        },
        change_order={
            key: _field(change_data.get(key)) for key in ("number", "title", "reason", "scope")
        }
        | {
            "type": _field(ChangeOrderType(str(change_data.get("type", "unknown")).lower())),
            "is_proposed": _field(change_data.get("is_proposed")),
        },
        financials={"line_items": line_items, **financial_fields},
        schedule={
            "days_added": _field(normalize_days((data.get("schedule") or {}).get("days_added"))),
            "revised_completion_date": DateField(
                value=date_value,
                raw_text=str((data.get("schedule") or {}).get("revised_completion_date"))
                if date_value
                else None,
                ambiguous=ambiguous,
            ),
        },
        approval={
            "status": _field(ApprovalStatus(str(approval_data.get("status", "unknown")).lower())),
            "approved_by": _field(approval_data.get("approved_by")),
            "date": DateField(
                value=approval_date,
                raw_text=str(approval_data.get("date")) if approval_date else None,
                ambiguous=approval_ambiguous,
            ),
        },
    )


def _attach_evidence(extraction: ChangeOrderExtraction, pages: list[str] | None) -> None:
    if not pages:
        return
    for field in _iter_fields(extraction):
        if not field.raw_text:
            continue
        raw_text = field.raw_text.strip()
        for page_number, page_text in enumerate(pages, start=1):
            raw_folded = raw_text.casefold()
            normalized_raw = re.sub(r"[^a-z0-9]", "", raw_folded)
            normalized_page = re.sub(r"[^a-z0-9]", "", page_text.casefold())
            if raw_folded in page_text.casefold() or (
                normalized_raw and normalized_raw in normalized_page
            ):
                quote = next(
                    (
                        line.strip()
                        for line in page_text.splitlines()
                        if raw_folded in line.casefold()
                        or (
                            normalized_raw
                            and normalized_raw in re.sub(r"[^a-z0-9]", "", line.casefold())
                        )
                    ),
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
