from __future__ import annotations

import faulthandler
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import BaseModel

from app.config import get_settings
from app.pipeline import process_document
from app.schemas.fields import ExtractedField


def _iter_fields(value: Any, path: str = ""):
    if isinstance(value, ExtractedField):
        yield {
            "field": path,
            "value": _display_value(value.value),
            "confidence": value.confidence,
            "evidence": _display_evidence(value.evidence),
            "validation": value.validation,
        }
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_fields(item, f"{path}[{index}]")
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            child_path = f"{path}.{name}" if path else name
            yield from _iter_fields(getattr(value, name), child_path)


def _display_value(value: Any) -> Any:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _display_evidence(evidence: Any) -> str:
    if evidence is None:
        return ""
    page = f" (page {evidence.page})" if evidence.page is not None else ""
    return f"{evidence.quote}{page}"


def _validation_counts(validation: dict[str, Any]) -> dict[str, int]:
    return {
        "passed": validation.get("passed_count", 0),
        "warnings": validation.get("warning_count", 0),
        "failed": validation.get("failed_count", 0),
    }


def _render_validation(result: Any) -> None:
    st.subheader("Document validation")
    for index, validation in enumerate(result.validation, start=1):
        counts = _validation_counts(validation)
        title = f"Change order {index}: {validation.get('overall_result', 'not_checked')}"
        with st.expander(title, expanded=counts["failed"] > 0):
            st.write(
                f"Passed: {counts['passed']} | "
                f"Warnings: {counts['warnings']} | Failed: {counts['failed']}"
            )
            rules = validation.get("rules", [])
            if rules:
                st.dataframe(
                    rules,
                    column_config={
                        "passed": st.column_config.CheckboxColumn("Passed"),
                        "message": st.column_config.TextColumn("Message", width="large"),
                    },
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info("No non-trivial validation findings.")


def _render_warnings(result: Any) -> None:
    warnings = [
        warning.model_dump()
        for extraction in result.extractions
        for warning in extraction.warnings
    ]
    if warnings:
        st.subheader("Extraction warnings")
        st.warning("Review the warnings before acting on this document.")
        st.dataframe(warnings, hide_index=True, width="stretch")


def _process_upload(uploaded_file: Any) -> Any:
    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(prefix="sledgeco_", suffix=suffix, delete=False) as handle:
        temporary_path = Path(handle.name)
        handle.write(uploaded_file.getvalue())
    try:
        return process_document(temporary_path, get_settings())
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    st.set_page_config(
        page_title="SledgeCO-AI Document Review",
        page_icon="📄",
        layout="wide",
    )
    st.title("SledgeCO-AI")
    st.caption("Change-order extraction and validation review")
    st.info(
        "Provider is set by LLM_PROVIDER in .env (mock = offline regex, "
        "gemini = free Gemini API). This app never auto-approves a change order."
    )

    with st.sidebar:
        st.header("Process a document")
        uploaded_file = st.file_uploader(
            "Upload a change-order document",
            type=["pdf", "txt"],
            help="PDF files may contain selectable text, scanned pages, or both.",
        )
        process_clicked = st.button(
            "Process Document",
            type="primary",
            disabled=uploaded_file is None,
            width="stretch",
        )
        st.caption("Supported: PDF and TXT. OCR requires Tesseract on Windows.")
        st.caption(f"Provider in use: {get_settings().llm_provider}")

    if not uploaded_file:
        st.markdown(
            "Upload a PDF or TXT change order from the sidebar, then select "
            "**Process Document** to begin."
        )
        return

    upload_key = (uploaded_file.name, uploaded_file.size)
    if st.session_state.get("upload_key") != upload_key:
        st.session_state["upload_key"] = upload_key
        st.session_state.pop("result", None)
        st.session_state.pop("processed_name", None)

    if process_clicked:
        faulthandler.dump_traceback_later(20, exit=False, file=sys.stderr)
        try:
            with st.spinner("Extracting, validating, and scoring fields..."):
                print("START processing", uploaded_file.name, flush=True)
                st.session_state["result"] = _process_upload(uploaded_file)
                st.session_state["processed_name"] = uploaded_file.name
                print("DONE processing", flush=True)
        except Exception as exc:
            print(f"FAILED: {type(exc).__name__} {exc}", flush=True)
            st.error(f"{type(exc).__name__}: {exc}")
            st.session_state.pop("result", None)
        finally:
            faulthandler.cancel_dump_traceback_later()

    result = st.session_state.get("result")
    if result is None:
        return

    st.success(f"Processed: {st.session_state.get('processed_name', uploaded_file.name)}")
    summary_col, decision_col, download_col = st.columns([2, 2, 1])
    summary_col.metric("Change orders found", len(result.extractions))
    decision_col.metric("Routing decision", result.routing_decision.value)
    json_text = json.dumps(result.model_dump(mode="json"), indent=2)
    download_col.download_button(
        "Download JSON",
        data=json_text,
        file_name=f"{Path(result.source_file).stem}_extraction.json",
        mime="application/json",
        width="stretch",
    )

    if result.routing_decision.value == "blocked":
        st.error("This document is blocked by validation or confidence findings.")
    elif result.routing_decision.value == "needs_review":
        st.warning("Human review is required. Confidence does not approve a change order.")
    else:
        st.info("Ready for human review. This application never auto-approves changes.")

    for index, extraction in enumerate(result.extractions, start=1):
        st.header(f"Extracted fields — change order {index}")
        rows = list(_iter_fields(extraction))
        st.dataframe(
            rows,
            column_config={
                "field": st.column_config.TextColumn("Field", width="medium"),
                "value": st.column_config.TextColumn("Value", width="medium"),
                "confidence": st.column_config.ProgressColumn(
                    "Confidence", min_value=0.0, max_value=1.0, format="%.2f"
                ),
                "evidence": st.column_config.TextColumn("Evidence", width="large"),
                "validation": st.column_config.TextColumn("Validation"),
            },
            hide_index=True,
            width="stretch",
        )

    _render_validation(result)
    _render_warnings(result)

    with st.expander("Complete validated JSON", expanded=False):
        st.json(result.model_dump(mode="json"))


if __name__ == "__main__":
    main()
