from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.confidence.calibration import evaluate_calibration
from app.pipeline import process_document

FIELD_PATHS = (
    "project.name",
    "project.number",
    "project.address",
    "change_order.number",
    "change_order.type",
    "financials.subtotal",
    "financials.total",
    "financials.new_contract_sum",
    "schedule.revised_completion_date",
    "approval.status",
    "approval.approved_by",
)


def _get(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _equal(expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, (int, float)):
        actual_number = _number(actual)
        return actual_number is not None and abs(float(expected) - actual_number) <= 0.01
    return str(expected).strip().lower() == str(actual).strip().lower()


def run_evaluation(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    documents_dir = data_dir / "documents"
    labels_dir = data_dir / "labels"
    documents = sorted(
        path for path in documents_dir.glob("*") if path.suffix.lower() in {".txt", ".pdf"}
    )
    if not documents:
        raise ValueError(f"Evaluation dataset is empty: no TXT/PDF files in {documents_dir}")
    missing_labels = [
        path.name for path in documents if not (labels_dir / f"{path.stem}.json").is_file()
    ]
    if missing_labels:
        raise ValueError(f"Missing ground-truth labels for: {', '.join(missing_labels)}")

    field_total = field_correct = numeric_total = numeric_correct = 0
    missing_total = missing_correct = 0
    observations: list[tuple[float, bool]] = []
    results: list[dict[str, Any]] = []
    processing_errors: list[dict[str, str]] = []
    latencies: list[float] = []
    validation_counts = {"passed": 0, "warning": 0, "failed": 0}

    for document in documents:
        label = json.loads((labels_dir / f"{document.stem}.json").read_text(encoding="utf-8"))
        start = time.perf_counter()
        try:
            result = process_document(document)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)
            predicted = result.extractions[0].model_dump(mode="json") if result.extractions else {}
            expected = label["extractions"][0]
            for path in FIELD_PATHS:
                expected_value = _get(expected, path)
                actual_value = _get(predicted, path)
                correct = _equal(expected_value, actual_value)
                field_total += 1
                field_correct += correct
                if expected_value is None:
                    missing_total += 1
                    missing_correct += actual_value is None
                if isinstance(expected_value, (int, float)):
                    numeric_total += 1
                    numeric_correct += correct
                confidence = next(
                    (
                        item["overall_score"]
                        for item in result.confidence[0]["field_scores"]
                        if item["field_path"] == path
                    ),
                    0.0,
                )
                observations.append((confidence, correct))
            for report in result.validation:
                validation_counts[report["overall_result"]] = validation_counts.get(
                    report["overall_result"], 0
                ) + 1
            results.append(
                {
                    "document": document.name,
                    "latency_ms": elapsed_ms,
                    "expected_extractions": len(label["extractions"]),
                    "actual_extractions": len(result.extractions),
                }
            )
        except Exception as exc:
            processing_errors.append({"document": document.name, "error": str(exc)})

    calibration = evaluate_calibration(
        [score for score, _ in observations],
        [label for _, label in observations],
    )
    output: dict[str, Any] = {
        "document_count": len(documents),
        "processed_count": len(results),
        "processing_error_count": len(processing_errors),
        "processing_errors": processing_errors,
        "field_level_accuracy": field_correct / field_total if field_total else 0.0,
        "numeric_accuracy": numeric_correct / numeric_total if numeric_total else 0.0,
        "missing_field_handling": missing_correct / missing_total if missing_total else None,
        "missing_field_count": missing_total,
        "validation_results": validation_counts,
        "latency_ms": {
            "mean": sum(latencies) / len(latencies) if latencies else None,
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "confidence_calibration": calibration.__dict__ if calibration else None,
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "evaluation.json").write_text(
        json.dumps(output, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run SledgeCO-AI over synthetic documents.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--output", type=Path, default=Path("eval/results"))
    args = parser.parse_args()
    print(json.dumps(run_evaluation(args.data_dir, args.output), indent=2))
