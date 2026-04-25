# F14 Spec: Live Local PDF Upload

## 1. Goal

Allow `parse_file(path)` to run live Mistral OCR on a local or network-accessible PDF path by uploading the file to Mistral first, then processing the returned file reference through the existing pipeline.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Function or module | `gazette_mistral_pipeline.mistral_ocr.run_mistral_ocr`; public entry remains `parse_file(path, config=...)` |
| Input source | Existing `PdfSource` with `source_type="local_pdf"` and `runtime.allow_live_mistral=True` |
| Output shape | Same validated `Envelope` returned by URL and replay paths |
| Error handling | Missing local file and non-PDF paths still fail during source loading; missing API key fails before upload; upload/OCR HTTP errors redact secrets |
| Network behavior | Normal tests use mocked HTTP only; live calls remain opt-in through `runtime.allow_live_mistral=True` and require `runtime.output_dir` |

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `docs/library-contract-v1.md` | Declares local PDF file support as part of the public API target |
| `docs/library-roadmap-v1.md` | Requires stdlib HTTP and no Mistral SDK runtime dependency |
| `docs/known-issues.md` | Calls out local PDF upload as the missing explicit implementation |
| `PROGRESS.md` | Tracks F14 and closes D6 when implemented |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Local live PDF happy path | `parse_file(local.pdf)` with live opt-in and mocked upload/OCR responses | Upload endpoint receives PDF bytes, OCR endpoint receives returned `file_id`, raw JSON cache and joined markdown are written |
| TC2 | Replay remains offline | `parse_file(local.pdf)` with `replay_raw_json_path` | No upload or OCR network calls |
| TC3 | Live mode still gated | `parse_file(local.pdf)` without `allow_live_mistral` | Existing live-mode guard raises before network |
| TC4 | API errors are clear | Mock upload/OCR HTTP error | RuntimeError includes status/body and redacts API key |
| TC5 | Metadata is honest | Local live PDF envelope | `source.source_type="local_pdf"`, `mistral.document_url is None`, request options include `document_type="file_id"` and uploaded file metadata |

## 5. Integration Point

- Called by: `parse_file` -> `parse_source` -> `run_mistral_ocr`.
- Calls: Mistral Files API (`POST /v1/files`) and OCR API (`POST /v1/ocr`).
- Side effects: uploads the local PDF to Mistral, writes `<run>.raw.json` into `runtime.output_dir`, writes joined markdown in the existing public API flow.
- Model fields populated: `MistralMetadata.raw_json_path`, `raw_json_sha256`, `mistral_doc_ids`, `page_count`, and `request_options` with upload/OCR metadata.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Local live parse works without real network in tests | `python -m pytest tests/test_public_api.py` |
| No new runtime dependencies | Review `pyproject.toml` unchanged |
| Replay path remains offline | Existing and new replay tests pass |
| Full test suite remains green | `python -m pytest` |

## 7. Definition Of Done

- [x] Implemented in `mistral_ocr.py`.
- [x] Mocked upload + OCR tests pass.
- [x] Public docs/notebook messaging updated.
- [x] `PROGRESS.md` updated.
- [x] Normal tests do not make live API calls.

## 8. Open Questions And Risks

- Mistral's public docs describe uploaded OCR support through a `file_id`; tests will mock this shape. A manual live notebook run should be used to confirm the exact upload contract with a real key.
- Uploaded files may persist in the Mistral workspace depending on account defaults. F14 will not auto-delete uploaded files unless a later feature adds cleanup controls.
