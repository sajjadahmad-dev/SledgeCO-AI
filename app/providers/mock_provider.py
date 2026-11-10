from __future__ import annotations

import re
from typing import Any

from app.providers.base import LLMProvider


class MockProvider(LLMProvider):
    """Deterministic key/value extractor used without network access."""

    def extract(self, document_text: str, pages: list[str] | None = None) -> list[dict[str, Any]]:
        if document_text.startswith("MULTI CHANGE ORDER"):
            sections = re.split(r"(?m)(?=^CHANGE ORDER\s*$)", document_text)
            return [
                extracted
                for section in sections
                if section.strip().startswith("CHANGE ORDER")
                for extracted in self.extract(section, pages)
            ]

        def find(label: str) -> str | None:
            match = re.search(
                rf"(?im)^[ \t]*{re.escape(label)}[ \t]*:[ \t]*(.+?)[ \t]*$",
                document_text,
            )
            if not match:
                label_folded = label.casefold()
                for line in document_text.splitlines():
                    candidate = line.strip()
                    if not candidate.casefold().startswith(label_folded):
                        continue
                    remainder = candidate[len(label) :].strip()
                    if label_folded == "project" and remainder.casefold().startswith("number"):
                        continue
                    value = remainder.lstrip(":. ").strip()
                    if value:
                        return value
                return None
            value = match.group(1).strip()
            return value or None

        def money(label: str) -> str | None:
            value = find(label)
            return re.sub(r"[$,]", "", value) if value else None

        items: list[dict[str, Any]] = []
        for match in re.finditer(
            r"(?im)^\s*\d+\.\s*(.+?)\s+-\s+\$?([\d,]+(?:\.\d{1,2})?)\s*$", document_text
        ):
            items.append(
                {"description": match.group(1).strip(), "amount": match.group(2).replace(",", "")}
            )
        markup_match = re.search(
            r"(?im)^\s*Markup\s*\(([\d.]+)%\)\s*:\s*\$?([\d,]+(?:\.\d{1,2})?)\s*$",
            document_text,
        )
        record: dict[str, Any] = {
            "project": {
                "name": find("Project"),
                "number": find("Project Number"),
                "address": find("Location"),
            },
            "parties": {
                "owner": {"name": find("Owner")},
                "contractor": {"name": find("Contractor")},
                "subcontractor": {"name": find("Subcontractor")},
            },
            "change_order": {
                "number": find("Change Order Number"),
                "title": find("Title"),
                "reason": find("Reason"),
                "scope": find("Scope"),
                "type": (find("Type") or "unknown").lower(),
                "is_proposed": (
                    True
                    if re.search(r"\b(?:PCO|proposed)\b", document_text, re.I)
                    else None
                ),
            },
            "financials": {
                "line_items": items,
                "subtotal": money("Subtotal"),
                "markup_pct": markup_match.group(1) if markup_match else None,
                "markup_amount": markup_match.group(2).replace(",", "") if markup_match else None,
                "total": money("Total This Change Order"),
                "original_contract_sum": money("Original Contract Sum"),
                "net_previous_changes": money("Previous Change Orders Net"),
                "contract_sum_prior": money("Contract Sum Prior to This CO"),
                "new_contract_sum": money("New Contract Sum"),
            },
            "schedule": {
                "days_added": find("Schedule Impact"),
                "revised_completion_date": find("Revised Completion Date"),
            },
            "approval": {
                "status": (find("Status") or "unknown").lower(),
                "approved_by": find("Approved By"),
                "date": find("Approval Date"),
            },
        }
        return [record]
