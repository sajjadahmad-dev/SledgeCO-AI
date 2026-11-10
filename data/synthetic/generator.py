"""Generate a deterministic synthetic change-order corpus."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
DOCUMENTS = ROOT / "documents"
LABELS = ROOT / "labels"
RANDOM_SEED = 20261111


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _record(index: int, category: str) -> dict[str, Any]:
    line_items = [
        {"description": "Mobilization and field coordination", "amount": 1200.0 + index * 10},
        {"description": "Materials and installation", "amount": 2300.0 + index * 15},
    ]
    subtotal = sum(item["amount"] for item in line_items)
    markup = round(subtotal * 0.1, 2)
    total = round(subtotal + markup, 2)
    original = 1_000_000.0 + index * 1000
    previous = index * 250.0
    prior = original + previous
    new_sum = prior + total
    return {
        "category": category,
        "project": {
            "name": f"Riverside Medical Pavilion {index:02d}",
            "number": f"RMP-2026-{index:03d}",
            "address": f"{100 + index} Harbor Avenue, Columbus, OH 43215",
        },
        "parties": {
            "owner": {"name": "Northstar Development Group"},
            "contractor": {"name": "Keystone Builders LLC"},
            "subcontractor": {"name": "Atlas Electrical Services"},
        },
        "change_order": {
            "number": f"CO-{index:03d}",
            "title": f"Level {index % 6 + 1} coordination revision",
            "reason": "Issued for coordination and field conditions",
            "scope": "Revise installation, furnish materials, and coordinate affected trades",
            "type": "deductive" if category == "deductive" else "additive",
            "is_proposed": category == "proposed",
        },
        "financials": {
            "line_items": line_items,
            "subtotal": subtotal,
            "markup_pct": 10.0,
            "markup_amount": markup,
            "total": -total if category == "deductive" else total,
            "original_contract_sum": original,
            "net_previous_changes": previous,
            "contract_sum_prior": prior,
            "new_contract_sum": prior - total if category == "deductive" else new_sum,
        },
        "schedule": {
            "days_added": 4 + index % 8,
            "revised_completion_date": f"2026-{(index % 9) + 1:02d}-{(index % 20) + 1:02d}",
        },
        "approval": {
            "status": "pending" if category in {"missing_approval", "proposed"} else "approved",
            "approved_by": None if category == "missing_approval" else "Morgan Lee, Project Manager",
            "date": None if category == "missing_approval" else "2026-03-15",
        },
    }


def _text(record: dict[str, Any], *, noisy: bool = False, ambiguous: bool = False) -> str:
    project = record["project"]
    parties = record["parties"]
    change = record["change_order"]
    financials = record["financials"]
    lines = financials["line_items"]
    completion = record["schedule"]["revised_completion_date"]
    approval = record["approval"]
    date_text = "03/04/26" if ambiguous else completion
    address = project["address"] or ""
    subcontractor = parties["subcontractor"]["name"] or ""
    approved_by = approval["approved_by"] or ""
    approval_date = approval["date"] or ""
    output = f"""CHANGE ORDER
Project: {project['name']}
Project Number: {project['number']}
Location: {address}
Owner: {parties['owner']['name']}
Contractor: {parties['contractor']['name']}
Subcontractor: {subcontractor}
Change Order Number: {change['number']}
Title: {change['title']}
Reason: {change['reason']}
Scope: {change['scope']}
Type: {change['type'].title()}

Line Items:
1. {lines[0]['description']} - {_money(lines[0]['amount'])}
2. {lines[1]['description']} - {_money(lines[1]['amount'])}
Subtotal: {_money(financials['subtotal'])}
Markup ({financials['markup_pct']:.0f}%): {_money(financials['markup_amount'])}
Total This Change Order: {_money(financials['total'])}
Original Contract Sum: {_money(financials['original_contract_sum'])}
Previous Change Orders Net: {_money(financials['net_previous_changes'])}
Contract Sum Prior to This CO: {_money(financials['contract_sum_prior'])}
New Contract Sum: {_money(financials['new_contract_sum'])}
Schedule Impact: {record['schedule']['days_added']} calendar days added
Revised Completion Date: {date_text}
Status: {approval['status'].title()}
Approved By: {approved_by}
Approval Date: {approval_date}
"""
    if noisy:
        output = output.replace("Contractor", "Contrator").replace("Subtotal", "SubtotaI")
    return output


def _write_pdf(path: Path, text: str, *, scanned: bool = False, pages: int = 1) -> None:
    if scanned:
        image = Image.new("RGB", (1700, 2200), "white")
        draw = ImageDraw.Draw(image)
        draw.multiline_text((80, 80), text, fill="black", spacing=12)
        image.save(path, "PDF", resolution=150.0)
        return
    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    chunks = text.splitlines()
    per_page = max(1, (len(chunks) + pages - 1) // pages)
    for page in range(pages):
        y = height - 50
        for line in chunks[page * per_page : (page + 1) * per_page]:
            pdf.drawString(40, y, line[:120])
            y -= 14
        pdf.showPage()
    pdf.save()


def generate_dataset(count: int = 50, seed: int = RANDOM_SEED) -> dict[str, int]:
    random.seed(seed)
    DOCUMENTS.mkdir(parents=True, exist_ok=True)
    LABELS.mkdir(parents=True, exist_ok=True)
    for old in DOCUMENTS.glob("*"):
        if old.is_file():
            old.unlink()
    for old in LABELS.glob("*.json"):
        old.unlink()
    categories = (
        ["clean_txt"] * 10
        + ["clean_pdf"] * 10
        + ["table_pdf"] * 4
        + ["conflicting_amounts"] * 2
        + ["multi_change_order"] * 2
        + ["multi_page"] * 5
        + ["scanned_pdf"] * 5
        + ["missing_fields"] * 4
        + ["deductive"] * 3
        + ["ambiguous_date"] * 2
        + ["noisy_ocr"] * 2
        + ["proposed"] * 1
    )[:count]
    for index, category in enumerate(categories, start=1):
        record = _record(index, category)
        if category == "missing_fields":
            record["project"]["address"] = None
            record["parties"]["subcontractor"]["name"] = None
        elif category == "conflicting_amounts":
            record["financials"]["subtotal"] += 125.0
        text = _text(record, noisy=category == "noisy_ocr", ambiguous=category == "ambiguous_date")
        label_records = [record]
        if category == "multi_page":
            text = text + "\nCONTINUATION\n" + text.split("CHANGE ORDER", 1)[1]
        elif category == "multi_change_order":
            second = _record(index + 50, "clean_txt")
            text = "MULTI CHANGE ORDER\n" + text + "\n" + _text(second)
            label_records.append(second)
        stem = f"co_{index:03d}_{category}"
        if category == "clean_txt" or category in {"missing_fields", "deductive", "ambiguous_date", "noisy_ocr", "proposed"}:
            path = DOCUMENTS / f"{stem}.txt"
            path.write_text(text, encoding="utf-8")
        else:
            path = DOCUMENTS / f"{stem}.pdf"
            _write_pdf(path, text, scanned=category == "scanned_pdf", pages=2 if category == "multi_page" else 1)
        (LABELS / f"{stem}.json").write_text(
            json.dumps({"document": path.name, "extractions": label_records}, indent=2) + "\n",
            encoding="utf-8",
        )
    return {"documents": len(list(DOCUMENTS.glob("*"))), "labels": len(list(LABELS.glob("*.json")))}


if __name__ == "__main__":
    print(json.dumps(generate_dataset(), indent=2))
