from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from app.pipeline import process_document

st.set_page_config(page_title="SledgeCO-AI Review", layout="wide")
st.title("SledgeCO-AI Change Order Review")
uploaded = st.file_uploader("Upload a TXT or PDF change order", type=["txt", "pdf"])
if uploaded:
    suffix = Path(uploaded.name).suffix
    temporary_path = Path("review_upload" + suffix)
    temporary_path.write_bytes(uploaded.getvalue())
    try:
        result = process_document(temporary_path)
        st.metric("Routing decision", result.routing_decision.value)
        st.json(json.loads(result.model_dump_json()))
    finally:
        temporary_path.unlink(missing_ok=True)
