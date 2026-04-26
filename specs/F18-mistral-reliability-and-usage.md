# F18 Spec: Mistral Reliability And Usage

## 1. Goal

Make live Mistral OCR runs operationally safer by retrying transient failures, surfacing sanitized structured errors, and recording OCR usage/cost metadata in the validated envelope.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Function or module | `gazette_mistral_pipeline.mistral_ocr.run_mistral_ocr`; public entries remain `parse_file`, `parse_url`, and `parse_source` |
| Input source | Existing `PdfSource` with live Mistral opt-in, or replay raw JSON through `runtime.replay_raw_json_path` |
| Output shape | Same validated `Envelope`, with additive `MistralMetadata` fields for usage, cost estimate, response bytes, and retry attempts |
| Error handling | Retry transient HTTP/network/timeout failures; fail fast for config/client/replay errors; redact API keys and authorization headers from all raised messages |
| Cost handling | Use Mistral `usage_info.pages_processed` when available and estimate OCR cost from configurable page pricing; do not present returned markdown token estimates as OCR billing data |

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `docs/library-contract-v1.md` | Defines the public pipeline, Mistral metadata, raw JSON cache, envelope shape, and additive schema-change expectations |
| `docs/library-roadmap-v1.md` | Keeps the implementation stdlib-based with no Mistral SDK or new runtime dependency |
| `docs/known-issues.md` | Requires opt-in live calls, clear unsupported response-shape failures, and no checked-in API keys |
| `specs/F05-mistral-api-pass.md` | Owns the existing OCR HTTP/cache/replay behavior that F18 hardens |
| `specs/F14-live-local-pdf-upload.md` | Owns the local PDF upload path that F18 must retry consistently with OCR calls |
| `PROGRESS.md` | Tracks F18 status and operational debt closure |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Retryable OCR HTTP error | Mock `/v1/ocr` returns 429 or 5xx before success | Retries up to configured attempts, then writes raw JSON and records attempt count |
| TC2 | Retryable upload HTTP error | Mock `/v1/files` returns transient failure before success | Upload retry succeeds, OCR uses returned `file_id`, no local path is sent as document URL |
| TC3 | Non-retryable HTTP error | Mock 400 or 401 response | Fails without retrying; exception includes status and sanitized body only |
| TC4 | Network and timeout failures | Mock `URLError` or timeout | Retries transiently and raises a typed sanitized error after final attempt |
| TC5 | Invalid or empty response payload | Mock empty, non-UTF-8, invalid JSON, or unsupported OCR shape | Fails loudly with clear payload/shape error; no raw cache is written for invalid live OCR |
| TC6 | Replay usage metadata | Cached raw JSON includes `usage_info` | Replay remains offline and metadata includes usage/cost fields derived from the cached payload |
| TC7 | Cost estimate | Raw JSON has `usage_info.pages_processed = 52` and default pricing | `estimated_ocr_cost_usd` is `0.052` |
| TC8 | Envelope/schema serialization | Build envelope from metadata with new fields | Envelope validates, schema includes new Mistral metadata fields, bundles serialize deterministically |
| TC9 | Secret redaction | API key appears in mocked error body | Raised error does not include the key or `Authorization` header text |

## 5. Integration Point

- Called by: `parse_file`, `parse_url`, and `parse_source` through `run_mistral_ocr`.
- Calls: Mistral Files API (`POST /v1/files`) for local PDFs and Mistral OCR API (`POST /v1/ocr`) for OCR.
- Side effects: live mode may perform multiple network attempts and writes one raw JSON cache only after a valid OCR response; replay mode reads exactly one raw JSON file and performs no network or API-key lookup.
- Model fields populated: existing `MistralMetadata` fields plus `usage_info`, `pages_processed`, `doc_size_bytes`, `estimated_ocr_cost_usd`, `raw_response_bytes`, `retry_attempts`, and optional returned markdown token estimates if implemented as documented estimates.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Retry defaults are configurable and validated | Unit tests for `GazetteConfig.mistral` defaults and invalid values |
| Transient failures retry on upload and OCR | `python -m pytest tests/test_mistral_ocr.py` |
| Non-retryable errors fail once and redact secrets | `python -m pytest tests/test_mistral_ocr.py` |
| Usage and cost metadata survive envelope serialization | `python -m pytest tests/test_envelope_builder.py tests/test_schema_export.py` |
| Public API remains offline-testable | `python -m pytest tests/test_public_api.py tests/test_bundle_writer.py` |
| No live Mistral calls in normal tests | `python -m pytest` passes without `MISTRAL_API_KEY` |

## 7. Definition Of Done

- [x] Implemented in `mistral_ocr.py`, `models/config.py`, and `models/source.py`.
- [x] Mocked retry/error/usage tests pass.
- [x] Envelope/schema tests pass with additive metadata fields.
- [x] README or operational docs explain retry behavior and page-based cost estimates.
- [x] `PROGRESS.md` updated with F18 completion, known debt/gotchas, and session log.
- [x] Normal tests do not make live Mistral API calls.

## 8. Open Questions And Risks

- No blocking open questions. OCR cost is estimated from page pricing and `usage_info.pages_processed`; exact invoice totals can still differ by account tier, batch mode, future pricing, or taxes.
- Returned markdown token estimates, if added, are only for downstream LLM planning and must not be described as Mistral OCR billing data.
- Retrying upload requests may create more than one uploaded file if Mistral completes the upload but the client sees a transient failure; this is acceptable for F18 and should be documented as an operational caveat.
