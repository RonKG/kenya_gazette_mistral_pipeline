# F05 Spec: Mistral API Pass

## 1. Goal

Send a resolved PDF source through Mistral OCR using stdlib HTTP, cache the raw OCR JSON, and support deterministic replay from cached raw JSON without implementing the public parse pipeline.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Mistral OCR request execution, raw JSON cache writing, raw JSON replay loading, and `MistralMetadata` population only |
| Primary module | `gazette_mistral_pipeline/mistral_ocr.py` |
| Model inputs | `gazette_mistral_pipeline.models.PdfSource` from F04 and optional `gazette_mistral_pipeline.models.GazetteConfig` |
| Runtime config | `GazetteConfig.mistral.model`, `GazetteConfig.mistral.api_key_env`, `GazetteConfig.mistral.timeout_seconds`, and `GazetteConfig.runtime.replay_raw_json_path` |
| Output shape | A lightweight stdlib dataclass such as `MistralOcrResult(raw_json: Any, metadata: MistralMetadata)`; raw JSON is left in Mistral's native shape for F06 normalization |
| Cache path | Live OCR writes canonical JSON to `<cache_dir>/<source.run_name>.raw.json`; replay reads `GazetteConfig.runtime.replay_raw_json_path` and does not call Mistral |
| Raw JSON hash | `raw_json_sha256` is the SHA-256 of the exact UTF-8 bytes written or read for replay |
| API key handling | At call time, read `os.environ[config.mistral.api_key_env]`; never store API keys in Pydantic models, cache files, fixtures, logs, errors, docs, or `request_options` |
| HTTP implementation | Use stdlib only, expected to be `urllib.request`, `urllib.error`, `json`, `os`, `hashlib`, `pathlib`, and local helpers; no Mistral SDK, OpenAI SDK, `requests`, Docling, or docling-core runtime dependency |
| PDF URL behavior | For `PdfSource.source_type == "pdf_url"`, call Mistral OCR with `document.type = "document_url"` and `document.document_url = source.source_value` |
| Local PDF behavior | For `PdfSource.source_type == "local_pdf"`, do not pass the local filesystem path as `document_url`; implement an explicit Mistral upload/file-reference helper if live local OCR is supported in F05, and mock that helper in tests |
| Replay behavior | Replay mode accepts cached raw JSON for either PDF URL or local PDF sources, validates that the file is non-empty JSON, computes metadata, and performs no env var lookup, upload, or OCR HTTP request |
| Error handling | Missing API key, missing replay file, empty/invalid raw JSON, unsupported source type, HTTP errors, and local upload failures raise clear exceptions without leaking authorization headers or key values |

F05 must keep `parse_file`, `parse_url`, and `parse_source` as package-root stubs. Wiring source loading, OCR, normalization, parsing, envelope assembly, and bundle writing into the public API lands in F10 unless a later approved spec changes that sequence.

### Proposed Module Layout

```text
gazette_mistral_pipeline/
  mistral_ocr.py
tests/
  fixtures/
    mistral_ocr_minimal.raw.json
  test_mistral_ocr.py
```

Suggested public package-internal helpers:

```python
MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"


@dataclass(frozen=True)
class MistralOcrResult:
    raw_json: Any
    metadata: MistralMetadata


def run_mistral_ocr(
    source: PdfSource,
    *,
    config: GazetteConfig | None = None,
    cache_dir: str | Path,
) -> MistralOcrResult:
    """Call live Mistral OCR or replay cached raw JSON for one resolved source."""


def load_raw_mistral_json(path: str | Path) -> Any:
    """Load cached Mistral raw JSON for replay without normalizing pages."""


def write_raw_mistral_json(payload: Any, path: str | Path) -> str:
    """Write canonical raw JSON and return the written bytes' SHA-256."""


def build_document_url_ocr_body(source: PdfSource, *, model: str) -> dict[str, Any]:
    """Build the Mistral OCR body for a PDF URL source."""
```

Suggested internal helpers:

```python
def _resolve_api_key(config: GazetteConfig) -> str: ...
def _post_json(url: str, body: dict[str, Any], *, api_key: str, timeout_seconds: float) -> Any: ...
def _upload_local_pdf(source: PdfSource, *, config: GazetteConfig, api_key: str) -> str: ...
def _build_uploaded_document_ocr_body(upload_reference: str, *, model: str) -> dict[str, Any]: ...
def _metadata_from_raw_json(raw_json: Any, *, source: PdfSource, raw_json_path: Path, raw_json_sha256: str, config: GazetteConfig, document_url: str | None, replay: bool) -> MistralMetadata: ...
def _extract_mistral_doc_ids(raw_json: Any) -> list[str]: ...
def _count_pages(raw_json: Any) -> int | None: ...
```

The local upload helper may be skipped only if F05 explicitly chooses not to support live local OCR yet; in that case, local sources must still work in replay mode and live local calls must fail with a clear message. Under no condition should implementation treat a local path string as a remote `document_url`.

### Mistral OCR Request Shape

The PDF URL request should match the prototype's n8n-compatible shape:

```json
{
  "model": "mistral-ocr-latest",
  "document": {
    "type": "document_url",
    "document_url": "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/eng@2026-04-17/source.pdf"
  }
}
```

HTTP headers:

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer <runtime env key>` |
| `Content-Type` | `application/json` |

The implementation may add Mistral OCR options only when they are stored as non-secret request options and covered by tests. F05 should not add image extraction, page normalization, markdown stitching, or parser behavior.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F05 as the current `Next` feature and records API key/live-call gotchas |
| `docs/library-contract-v1.md` | Defines the package pipeline, raw Mistral JSON cache, Mistral metadata fields, and no-SDK scope |
| `docs/library-roadmap-v1.md` | Places stdlib Mistral OCR before F06 page normalization and keeps SDK dependencies out of runtime |
| `docs/known-issues.md` | Requires env/config API keys, opt-in live calls, explicit local upload handling, and support for known raw JSON shapes |
| `specs/SOP.md` | Requires spec-first implementation, lightweight dependencies, mocked/replayed Mistral tests, and pass/fail criteria |
| `specs/F04-pdf-source-loading.md` | Provides resolved `PdfSource` objects, stable run names, and local path/URL classification for F05 |
| `examples/historical/gazette_etl_prototype.ipynb` | Provides the current OCR request body, stdlib HTTP approach, raw JSON cache file naming, and replay/raw JSON behavior |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | PDF URL live OCR with mocked HTTP | `PdfSource(source_type="pdf_url", source_value=<Kenyalaw PDF URL>, run_name="gazette_2026-04-17_68")`, env var set, mocked `urllib.request.urlopen` response with `{"id": "doc_1", "model": "mistral-ocr-latest", "pages": [{"index": 0, "markdown": "text"}]}` | Sends one POST to `/v1/ocr` with `document.type = "document_url"`; writes `<tmp>/gazette_2026-04-17_68.raw.json`; returns raw JSON and `MistralMetadata(model="mistral-ocr-latest", document_url=<URL>, mistral_doc_ids=["doc_1"], page_count=1, raw_json_path=<path>, raw_json_sha256=<hash>)` |
| TC2 | Replay mode bypasses network and API key | `GazetteConfig(runtime.replay_raw_json_path=<fixture>)` with no Mistral env var set | Reads fixture, computes `raw_json_sha256`, populates metadata with `request_options["replay"] == True`, and does not call `urlopen`, upload helpers, or env key validation |
| TC3 | Missing API key for live OCR | PDF URL source, no replay path, `config.mistral.api_key_env = "MISTRAL_API_KEY_TEST"`, env var absent or blank | Raises a clear environment/config error naming the env var but not including any key value; no cache file is written |
| TC4 | HTTP error is sanitized | PDF URL source, env var set, mocked `urllib.error.HTTPError` with response body | Raises a clear Mistral OCR error with status code and sanitized body; authorization header and API key are not present in the message |
| TC5 | Raw JSON cache is deterministic | Same mocked OCR payload and same source run twice in deterministic mode | Cache file bytes and `raw_json_sha256` are stable across runs; JSON is UTF-8 with sorted or otherwise canonical formatting chosen by implementation |
| TC6 | Local PDF does not use `document_url` path | `PdfSource(source_type="local_pdf", source_value=<local path>, run_name="sample")` with mocked upload/file-reference helper | OCR request uses the upload/file-reference output, not the local path string as `document.document_url`; metadata does not store secrets and does not mislabel the local path as a remote URL |
| TC7 | Local PDF replay works without upload | Local PDF source plus `runtime.replay_raw_json_path=<fixture>` | Reads replay JSON and populates metadata without checking for API key, uploading the file, or requiring network access |
| TC8 | Invalid replay JSON fails loudly | Replay path points to missing, empty, or invalid JSON file | Raises `FileNotFoundError` or `ValueError` with the path and failure reason; no network request is attempted |
| TC9 | Known raw JSON shapes produce metadata counts | Fixture is a single object with `pages`, a list of block objects with `pages`, or a legacy page list with `markdown` entries | `page_count` and `mistral_doc_ids` are best-effort populated without normalizing/stitching pages; unsupported shapes fail loudly with `ValueError` |
| TC10 | Public API stubs remain stubs | Import `parse_file`, `parse_url`, and `parse_source` after adding F05 | Each still raises the existing `NotImplementedError` pointing to F10; F05 tests call `mistral_ocr.run_mistral_ocr` directly |

Normal test runs must not make live Mistral API calls. Any optional live smoke test must be separately marked, skipped by default, require an explicit environment opt-in such as `GAZETTE_RUN_LIVE_MISTRAL=1`, require a runtime API key, and must not be part of the F05 pass criteria.

## 5. Integration Point

Called by later features:

- F06 consumes `MistralOcrResult.raw_json` or `load_raw_mistral_json(...)` output to normalize pages and stitch markdown.
- F09 places `MistralOcrResult.metadata` under `Envelope.mistral`.
- F10 public `parse_file`, `parse_url`, and `parse_source` resolve sources with F04 helpers, call F05 OCR/replay, and pass raw JSON into F06-F09.
- F10 bundle writing can reuse the F05 raw JSON cache path as the default `raw_mistral_json` bundle.

Calls:

- `PdfSource` and `GazetteConfig` / `MistralOptions` / `RuntimeOptions` from F03.
- `MistralMetadata.model_validate(...)` or direct model construction from F03.
- `os.environ` only for the env var named by `GazetteConfig.mistral.api_key_env`.
- `urllib.request.Request` and `urllib.request.urlopen` for stdlib HTTP.
- `json.dumps` / `json.loads`, `hashlib.sha256`, and `pathlib.Path` for cache and replay behavior.

Side effects:

- Live mode reads the Mistral API key from the process environment at runtime.
- Live mode sends HTTPS requests to Mistral OCR and, for live local PDF support, to the required upload/file-reference endpoint.
- Live mode writes one raw JSON cache file under the caller-provided `cache_dir`.
- Replay mode reads one raw JSON file and performs no network or env-var secret lookup.
- F05 does not write joined markdown, envelope JSON, source metadata, notice/table bundles, schemas, or `PROGRESS.md`.

Model fields populated:

- `MistralMetadata.model`: `config.mistral.model` or model value in raw JSON when safely available, with config as the fallback.
- `MistralMetadata.raw_json_path`: string path to the cached or replayed raw JSON file.
- `MistralMetadata.raw_json_sha256`: SHA-256 of raw JSON bytes read or written.
- `MistralMetadata.document_url`: source URL for PDF URL requests; local upload reference only if it is truly a remote document URL/reference accepted by Mistral; never a local filesystem path.
- `MistralMetadata.mistral_doc_ids`: best-effort list from top-level raw JSON IDs and block IDs.
- `MistralMetadata.page_count`: best-effort count across supported raw JSON shapes.
- `MistralMetadata.request_options`: non-secret options such as `source_type`, `document_type`, `timeout_seconds`, `replay`, and any OCR request flags; never include API keys or Authorization headers.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Mistral OCR module exists | `gazette_mistral_pipeline/mistral_ocr.py` imports cleanly |
| PDF URL request body matches prototype | Unit test inspects mocked `urllib.request.Request` body and headers |
| Raw JSON cache writes deterministic bytes | Unit test verifies cache file path, contents, and SHA-256 |
| Replay mode avoids live behavior | Unit test verifies replay works without API key and without any mocked network call being invoked |
| API key stays runtime-only | Unit tests verify missing-key error names only the env var and metadata/request options contain no secret values |
| Local PDF path is not sent as `document_url` | Unit test covers local source with mocked upload/file-reference flow or clear unsupported-live-local error, plus replay success |
| Mistral metadata fields are populated | Unit tests cover `model`, `raw_json_path`, `raw_json_sha256`, `document_url`, `mistral_doc_ids`, `page_count`, and safe `request_options` |
| HTTP failures are clear and sanitized | Unit test mocks `HTTPError` and asserts no Authorization header or API key appears in exception text |
| Public parse stubs remain unchanged | Existing package skeleton tests and new F05 test assert `parse_*` still raise `NotImplementedError` until F10 |
| Normal tests make no live calls | `python -m pytest` passes with no `MISTRAL_API_KEY` and no network access |

## 7. Definition Of Done

- [x] `specs/F05-mistral-api-pass.md` approved before implementation starts.
- [x] `gazette_mistral_pipeline/mistral_ocr.py` implemented with stdlib HTTP/cache/replay helpers only.
- [x] No runtime dependency added for Mistral SDK, OpenAI SDK, `requests`, Docling, or docling-core.
- [x] `run_mistral_ocr(...)`, raw JSON load/write helpers, metadata helper, and HTTP helpers are covered by unit tests.
- [x] Replay mode reads cached raw JSON and bypasses API key lookup and network calls.
- [x] Live URL mode builds the Mistral `document_url` OCR request shape from the prototype.
- [x] Local PDF behavior is explicit: supported through mocked upload/file-reference helpers or clearly rejected for live OCR while replay remains supported.
- [x] `MistralMetadata` is populated with raw JSON path/hash, model, document URL/reference where applicable, doc IDs, page count, and non-secret request options.
- [x] `parse_file`, `parse_url`, and `parse_source` remain stubs until F10.
- [x] Tests are added in `tests/test_mistral_ocr.py` with no normal live Mistral API calls.
- [x] Existing `tests/test_package_skeleton.py`, `tests/test_models.py`, and `tests/test_source_loading.py` still pass.
- [x] `python -m pytest` passes without `MISTRAL_API_KEY`.
- [x] `PROGRESS.md` is updated only by the builder after implementation and tests pass, not during spec creation.

## 8. Open Questions And Risks

Q1. Should F05 fully support live OCR for local PDFs?

Recommended answer: yes if the current Mistral API upload/file-reference shape can be verified during implementation using stdlib HTTP. If not, keep local live OCR explicitly unsupported in F05 with a clear error, while preserving local replay support. Do not pass a local path as `document_url`.

Q2. Should F05 expose `run_mistral_ocr` from the package root?

Recommended answer: no. Keep it as a package-internal helper imported from `gazette_mistral_pipeline.mistral_ocr`. The root public API should remain the planned `parse_*` and bundle/schema functions until F10.

Q3. Should F05 validate every possible Mistral raw JSON response shape?

Recommended answer: no. F05 should require valid JSON, support the known raw shapes listed in `docs/known-issues.md`, and fail loudly on unsupported shapes. Deep page normalization and markdown stitching belong to F06.

Q4. Should replay mode require the replay JSON to match the current `PdfSource`?

Recommended answer: no for F05. Replay should be a deterministic raw JSON input path. Later envelope validation can compare source metadata and warnings if needed.

Q5. Should F05 store the request body in `MistralMetadata.request_options`?

Recommended answer: store only non-secret summaries such as source type, document type, timeout, replay flag, and model/options. Do not store Authorization headers, API keys, signed URLs with sensitive query strings, or local filesystem paths beyond what already belongs in `PdfSource.source_value`.
