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

        labels = {
            "Project Name",
            "Project Number",
            "Project",
            "Location",
            "Owner",
            "Contractor",
            "Subcontractor",
            "Change Order Number",
            "Title",
            "Reason",
            "Scope",
            "Type",
            "Subtotal",
            "Markup",
            "Total This Change Order",
            "Original Contract Sum",
            "Previous Change Orders Net",
            "Contract Sum Prior to This CO",
            "New Contract Sum",
            "Schedule Impact",
            "Revised Completion Date",
            "Status",
            "Approved By",
            "Approval Date",
        }

        def is_placeholder(value: str) -> bool:
            folded = re.sub(r"\s+", " ", value).strip().casefold()
            return (
                not folded
                or bool(re.fullmatch(r"[_\-\s.]+", folded))
                or bool(re.search(r"approval\s*:|signature|sign here|date\s*:", folded))
                or folded in {"name", "project name", "n/a", "na", "none", "unknown"}
            )

        def looks_like_label(line: str) -> bool:
            return any(
                re.match(rf"^\s*{re.escape(label)}\s*(?:[:：.\-]|$)", line, re.I)
                for label in sorted(labels, key=len, reverse=True)
            )

        def find(*requested_labels: str, multiline: bool = False) -> str | None:
            wanted = sorted(requested_labels, key=len, reverse=True)
            lines = document_text.splitlines()
            for index, line in enumerate(lines):
                matched_label = next(
                    (
                        label
                        for label in wanted
                        if re.match(
                            rf"^\s*{re.escape(label)}\s*(?::|：|\.|-|\s{{2,}}|$)",
                            line,
                            re.I,
                        )
                    ),
                    None,
                )
                if matched_label is None:
                    continue
                remainder = re.sub(
                    rf"^\s*{re.escape(matched_label)}\s*(?::|：|\.|-|\s{{2,}})?\s*",
                    "",
                    line,
                    flags=re.I,
                ).strip()
                values = [] if is_placeholder(remainder) else [remainder]
                consumed_next_line = False
                if not values and index + 1 < len(lines):
                    next_line = lines[index + 1].strip()
                    if next_line and not looks_like_label(next_line) and not is_placeholder(next_line):
                        values.append(next_line)
                        consumed_next_line = True
                if multiline:
                    cursor = index + 2 if consumed_next_line else index + 1
                    while cursor < len(lines):
                        continuation = lines[cursor].strip()
                        if not continuation or looks_like_label(continuation):
                            break
                        if not is_placeholder(continuation):
                            values.append(continuation)
                        cursor += 1
                if values:
                    return " ".join(values).strip()
            return None

        def money(label: str) -> str | None:
            value = find(label)
            return value.replace("$", "").replace(",", "").strip() if value else None

        def find_status() -> tuple[str | None, str | None]:
            raw_status = find("Status")
            if not raw_status:
                return None, None
            match = re.match(
                r"\s*(approved|pending|proposed|rejected|unknown)\b",
                raw_status,
                flags=re.IGNORECASE,
            )
            return (match.group(1).casefold() if match else "unknown"), raw_status

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
        status, status_raw = find_status()
        record: dict[str, Any] = {
            "project": {
                "name": find("Project Name", "Project", multiline=True),
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
                "reason": find("Reason", multiline=True),
                "scope": find("Scope", multiline=True),
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
                "status": status,
                "status_raw": status_raw,
                "approved_by": find("Approved By"),
                "date": find("Approval Date"),
            },
        }
        return [record]
