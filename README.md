# SledgeCO-AI

Assessment-sized change-order extraction pipeline: messy TXT/PDF inputs become
validated JSON with per-field confidence, evidence, and business validation
status. This is intentionally a focused pipeline, not a full product.

## Installation

```powershell
python -m pip install -e ".[dev,ocr]"
```

For Windows OCR, install Tesseract separately and configure its executable:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Copy `.env.example` to `.env` for persistent configuration. The default provider
is deterministic `mock`, so no API key or paid request is needed for local use.

## Features

- TXT and PDF ingestion, including mixed PDFs.
- Tesseract OCR for image-only pages with per-page OCR confidence.
- Deterministic mock extraction for reproducible development and evaluation.
- Optional Gemini provider, disabled by default.
- Pydantic-validated nested JSON.
- Per-field `value`, `raw_text`, `confidence`, `evidence`, and `validation`.
- Label-only matches and blank signature placeholders are rejected; unsupported
  values remain null with low confidence.
- Financial, date, approval, sign-convention, and PCO/CO checks.
- Explicit human-review routing; no automatic financial approval.

## Usage

```powershell
python -m app.cli extract path\to\change-order.txt
python -m app.cli extract path\to\change-order.pdf --output result.json
```

The optional API is available with `pip install -e ".[api]"` and can be served
with `uvicorn app.api:app`. The optional review app is not required for the
core pipeline.

## Streamlit review app

Install the UI and OCR dependencies from PowerShell:

```powershell
python -m pip install -e ".[streamlit,ocr]"
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
python -m streamlit run frontend\review_app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser. Upload a
PDF or TXT file in the sidebar and click **Process Document**. The app calls
the existing `app.pipeline.process_document` function, then displays the
per-field value, confidence, evidence, validation status, document validation
findings, warnings, complete JSON, and a JSON download button. It does not
duplicate OCR, extraction, normalization, validation, or routing logic, and it
never approves a change order automatically.

## Supported inputs

Plain text and PDF inputs are supported. Each PDF page is classified as
selectable text or OCR. OCR pages retain page order and mean Tesseract
confidence. Mixed PDFs are supported.

## Validation

```powershell
python -m pytest tests
```

Business rules preserve document signs, use rounding tolerances, validate
financial progressions, flag ambiguous dates, and distinguish proposed from
executed change orders.

## Architecture

`ingestion` detects files and extracts page text/OCR. `providers` supplies either
the deterministic mock extractor or the opt-in Gemini adapter. `extraction`
normalizes values and attaches evidence quotes/page numbers. `validation` runs
financial, date, approval, and PCO/CO rules. `confidence` scores every extracted
field. `routing` returns only `ready_for_review`, `needs_review`, or `blocked`.
There is no automatic financial approval state.

## Security and operations

- Document content is marked as untrusted before LLM processing.
- Missing values remain null; values are not silently invented.
- API keys are read from environment settings and are never logged.
- Input files are never modified.
- Size and extension checks run before ingestion.
- Provider, OCR, parsing, and validation failures are surfaced explicitly.
- Gemini calls occur only when `LLM_PROVIDER=gemini` is explicitly set.

## Example output

```json
{
  "source_file": "change-order.pdf",
  "routing_decision": "needs_review",
  "extractions": [
    {
      "change_order": {
        "number": {
          "value": "CO-001",
          "confidence": 0.97,
          "evidence": {"quote": "Change Order Number: CO-001", "page": 1}
        }
      }
    }
  ]
}
```

Run the included example:

```powershell
python -m app.cli extract data\examples\example_input.txt `
  --output data\examples\example_output.json
```

The generated output contains confidence and validation metadata on every
extracted field. The generated JSON is also included as a reproducible example
artifact at `data\examples\example_output.json`.

Confidence is advisory only. Even a high-confidence extraction is routed for
human review and never becomes an automatic financial approval.

## Known limitations

- The Gemini adapter currently requests JSON text over HTTP; image/Vision
  content is not yet implemented.
- OCR requires the external Tesseract executable in addition to `pytesseract`.
- Calibration results are based on the deterministic synthetic corpus and must
  be retrained/validated with representative labeled production documents.
- The mock provider is intentionally a deterministic parser for tests, not a
  replacement for LLM extraction quality.

## Synthetic dataset and evaluation

Generate the deterministic 50-document mock-provider corpus (TXT, text PDFs, scanned PDFs,
multi-page PDFs, multi-change-order documents, missing fields, deductive orders,
ambiguous dates, and noisy OCR):

```powershell
python data\synthetic\generator.py
```

Each document in `data\synthetic\documents\` has a matching ground-truth file in
`data\synthetic\labels\`. Run the labeled evaluation with:

```powershell
python -m eval.run_eval `
  --data-dir data\synthetic `
  --output eval\results
```

The evaluator fails clearly if the documents directory is empty or any document
has no matching ground truth. It reports field-level accuracy, numeric accuracy,
missing-field handling, validation outcomes, processing errors, latency, and
confidence calibration only when at least 30 field observations are available.
Metrics are written to `eval\results\evaluation.json`; no metrics are generated
from an empty or incomplete dataset.

Calibration uses a deterministic 60/20/20 train/validation/test split. The
existing heuristic is compared with logistic regression on validation Brier
score; the selected method and both ECE/Brier results are recorded. These
metrics describe this synthetic mock-provider corpus only. They are separate
from the manual Gemini checks in [docs/approach.md](docs/approach.md) and are
not a claim of production calibration.

## Assessment write-up

See [docs/approach.md](docs/approach.md) for the
concise architecture, methodology, failure modes, review strategy, and measured
evaluation results.

## OCR

Install the Python OCR adapter:

```powershell
python -m pip install -e ".[ocr]"
```

Install the Tesseract executable separately and add it to `PATH`. Text-bearing
PDF pages use selectable text; sparse/image-only pages are rendered and sent to
Tesseract. The ingestion result preserves page order, records `text` versus
`ocr` page sources, and stores the mean OCR confidence for each OCR page.
Mixed PDFs are handled page by page. If Tesseract is unavailable, the pipeline
raises an explicit runtime error rather than silently returning empty text.
