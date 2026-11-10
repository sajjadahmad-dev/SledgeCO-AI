# Failure modes

- Unsupported extensions and files over the configured size are rejected.
- Missing values remain `null`; the extractor does not invent values.
- Arithmetic mismatches become validation failures and route to `blocked`.
- Ambiguous dates and sign-convention differences become warnings and route to
  `needs_review`.
- Provider output that is not valid JSON raises an explicit extraction error.
- Scanned PDFs are marked in ingestion and receive a confidence quality penalty.
