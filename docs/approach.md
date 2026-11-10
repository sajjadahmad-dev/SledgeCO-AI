# Approach

The pipeline separates ingestion, provider calls, normalization, schema validation,
business-rule validation, confidence scoring, and routing. The default mock
provider is deterministic for local development and tests. The Anthropic adapter
is opt-in through `.env`; document content is explicitly marked as untrusted.

Routing never approves a financial change automatically. Results are returned for
review even when all extraction and arithmetic checks pass.
