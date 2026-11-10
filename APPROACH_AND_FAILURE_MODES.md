# SledgeCO-AI: Approach and Failure Modes

## Problem and solution

SledgeCO-AI turns messy construction change-order TXT and PDF documents into
validated, reviewable JSON. It extracts project, party, change-order, financial,
schedule, and approval data; preserves nulls for missing information; attaches
source evidence and confidence to each field; and routes every result to human
review.

The system never auto-approves a financial change.

## Architecture

1. **Ingestion** detects TXT/PDF inputs, enforces size/type limits, extracts
   selectable PDF text, and uses Tesseract for sparse/image-only PDF pages.
2. **Providers** expose a deterministic mock provider for tests and an opt-in
   Anthropic adapter for production experiments.
3. **Extraction** normalizes amounts, dates, enums, and schedule values, then
   attaches evidence quotes and page numbers.
4. **Validation** checks arithmetic relationships, dates, approvals, sign
   conventions, and proposed-versus-executed orders.
5. **Confidence** combines evidence matching, format validity, validation,
   scan quality, and ambiguity signals.
6. **Routing** returns `ready_for_review`, `needs_review`, or `blocked`.

## Technologies

Python 3.12, Pydantic v2, PyMuPDF, Pillow, Tesseract/pytesseract, dateutil,
RapidFuzz, Click, pytest, scikit-learn, and optional Anthropic/FastAPI support.

## Extraction and normalization

The mock provider parses deterministic labeled documents for reproducible
evaluation. Amounts are converted to `Decimal`, dates to ISO dates, schedule
durations to integers, and enums to constrained values. Missing or unreadable
values remain `null`; the pipeline does not infer replacements.

Each extracted field contains:

```json
{
  "value": "CO-001",
  "raw_text": "CO-001",
  "confidence": 0.97,
  "evidence": {"quote": "Change Order Number: CO-001", "page": 1},
  "validation": "not_checked"
}
```

`confidence` is extraction confidence. `validation` is a separate business-rule
status (`passed`, `warning`, `failed`, or `not_checked`).

## Confidence methodology

The heuristic scorer weights fuzzy evidence match (30%), format validity (15%),
related arithmetic validation (25%), scan quality (10%), and ambiguity penalty
(20%). Scores are clamped to `[0, 1]`. Evaluation additionally compares the
heuristic with logistic regression using a deterministic 60/20/20 split.

## Validation rules

- Line items approximately equal subtotal.
- Markup percentage/amount and total relationships are checked.
- Contract sum progression is checked.
- Deductive labels are not forced to negative; sign conventions are reported.
- Dates are checked for plausibility and ambiguity.
- Approval completeness is checked.
- PCO/proposed versus executed CO indicators are flagged.

## Failure modes and limitations

- Poor OCR can produce missing or incorrect fields; OCR confidence is retained
  and the result is routed for review.
- Tesseract is an external dependency and failures are explicit.
- Ambiguous dates remain flagged rather than silently disambiguated.
- Conflicting arithmetic routes to review or blocked status.
- The mock provider is intentionally narrow and is not a production LLM.
- The Anthropic adapter is opt-in and currently requests JSON text; strict
  tool-use schema enforcement is not part of this assessment implementation.
- Calibration results are based on synthetic mock-provider data and are not
  production calibration evidence.

## Human review strategy

`ready_for_review` means the extraction and checks are internally consistent,
not that the change is approved. Warnings, ambiguity, low confidence, missing
approval, or OCR uncertainty route to `needs_review`. Critical validation
failures or very low confidence route to `blocked`. Human reviewers remain
responsible for financial approval.

## Evaluation

The repository includes 50 generated TXT/PDF documents and 50 matching ground
truth JSON files. The latest mock-provider evaluation with real Tesseract OCR
processed all 50 documents with zero processing errors:

- Field-level accuracy: 98.36%
- Numeric accuracy: 98.67%
- Missing-field handling: 100%
- Mean latency: 395.59 ms (maximum: 4,989.27 ms)
- Heuristic ECE/Brier: 0.0919 / 0.0375
- Logistic calibration ECE/Brier: 0.00038 / 0.0179

These are synthetic-corpus measurements, not claims about production data.
Full raw results are in `eval/results/evaluation.json`.
