from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.pipeline import process_document

app = FastAPI(title="SledgeCO-AI", version="0.1.0")


@app.post("/extract")
async def extract_document(file: UploadFile = File(...)) -> dict:  # noqa: B008
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".text", ".pdf"}:
        raise HTTPException(status_code=415, detail="Only TXT and PDF files are supported")
    contents = await file.read()
    with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
        temporary.write(contents)
        temporary_path = Path(temporary.name)
    try:
        return process_document(temporary_path).model_dump(mode="json")
    finally:
        temporary_path.unlink(missing_ok=True)
