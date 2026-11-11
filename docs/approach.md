# SledgeCO-AI: Approach and Failure Modes

SledgeCO-AI turns messy change-order PDFs or text into validated JSON with a
confidence score on every extracted field. It never approves a change order:
it prepares a reviewable record and indicates how much human review is needed.

## Pipeline

```text
PDF / TXT -> ingest -> Gemini extraction -> normalization -> validation
          -> confidence -> routing -> Streamlit review UI + JSON
```

1. **Ingestion.** Reads text page by page, preserves page order, and detects
   sparse or image-only PDF pages. OCR requires the external Tesseract
   executable.
2. **Extraction.** The provider interface keeps the model swappable. Real runs
   use the opt-in Gemini HTTP adapter (`GEMINI_MODEL`, default
   `gemini-flash-latest`); the deterministic `MockProvider` runs offline for
   tests. The prompt treats document content as untrusted data, requests
   `null` for absent fields, and preserves printed values.
3. **Normalization.** Amounts, including credits such as `($1,200.00)`, become
   signed decimals. Dates retain an ambiguity flag, `None` schedule values
   become zero, and status/type values are normalized to enums. Printed text is
   stored beside the normalized value.
4. **Evidence.** Extracted fields carry a source quote and page number when
   evidence is found.
5. **Validation.** Rules independently check line-item and markup arithmetic,
   contract-sum progression, dates, approval completeness, sign conventions,
   and proposed-versus-executed orders. The model cannot approve its own
   numbers.
6. **Confidence.** Each field uses a weighted blend of evidence match, format
   validity, related validation, scan quality, and ambiguity. Field scores roll
   up to a document score. Missing fields are not scored as extracted values.
7. **Routing.** Failed error rules or very low confidence produce `blocked`.
   Failed warning rules, ambiguity, or low confidence produce `needs_review`.
   A clean, sufficiently evidenced extraction produces `ready_for_review`.
   `ready_for_review` still requires human review; no route means automatic
   financial approval.
8. **Review UI.** Streamlit shows values, confidence, evidence, validation
   status, findings, and downloadable JSON.

## What was tested

The following are manual checks on synthetic documents only. They are not a
statistical evaluation and no accuracy percentage is claimed.

| Document | What it tests | Verified result |
|---|---|---|
| `mock_format_1.pdf` | Clean labelled form | Validation passed; `warning_count=0`, `failed_count=0`, routing `ready_for_review` |
| `01_clean_approved.pdf` | Standard layout and approval | CO number and total extracted; approval status detected |
| `03_deductive_credit.pdf` | Parenthesized credit amounts | Total `-7,410.67`, subtotal `-6,616.67`, markup `-794.00`, type `deductive`; sums tie out |
| `04_arithmetic_error.pdf` | Intentionally wrong printed total | Independent validation fails; document is blocked |
| `05_ambiguous_date.pdf` | Date/layout case | Gemini extraction completed; routing `ready_for_review`; this fixture contains `03/02/2026`, which is not ambiguous |
| `06_prompt_injection.pdf` | Instructions embedded in document text | Extracted total `7,199.47`, not `$0`; routing `ready_for_review` |
| `07_missing_fields.pdf` | Absent fields | Missing values remain null and are not counted as extracted low-confidence fields |
| `08_multipage.pdf` | Totals on page 2 | Multi-page extraction path is covered by the fixture set |
| `09_scanned_image_only.pdf` | No usable text layer | Explicit failure: `Tesseract executable was not found` when Tesseract is unavailable |

## Failure modes

- **Confidence can saturate.** Correctly evidenced fields often score `1.00`.
  Scores drop for failed checks, missing evidence, ambiguity, or scans. A
  correctly quoted but semantically wrong value can still score high. These are
  uncalibrated heuristics.
- **One model call per document.** There is no self-consistency check, so a
  confidently wrong extraction is not caught by disagreement between runs.
- **Scanned or handwritten pages.** Image-only pages require Tesseract or a
  vision-capable model. Without Tesseract, the pipeline raises an explicit
  error rather than returning empty output.
- **Prompt injection.** The prompt treats document text as untrusted and
  arithmetic is independently checked. This is a defense, not a guarantee;
  non-arithmetic fields still require human review.
- **Validation scope.** Names, addresses, and many dates are not independently
  verified beyond evidence and format checks.
- **Date ambiguity.** Ambiguous numeric dates are interpreted using the
  configured convention and flagged for review; other locales are not fully
  resolved.
- **Credit signs.** Parentheses and minus signs are normalized reliably. A
  credit written only in words still depends on model extraction and change
  type.
- **Free-tier constraints.** Rate limits and latency can affect Gemini calls.
  Only synthetic documents should be sent through a free-tier setup; real
  customer documents require an appropriate paid or zero-retention setup.
- **Multiple change orders.** The schema supports a list, but this path has
  limited manual coverage.

## Next steps

1. Build a labelled evaluation set and report per-field accuracy and wrongly
   passed documents.
2. Calibrate confidence using reviewer corrections.
3. Add OCR or a vision model for scanned pages.
4. Add self-consistency runs for fields that move money.
5. Map extracted items to customer cost codes and jobs.
