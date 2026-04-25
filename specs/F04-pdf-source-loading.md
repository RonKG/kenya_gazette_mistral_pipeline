# F04 Spec: PDF Source Loading

## 1. Goal

Resolve PDF URLs, local PDF paths, and JSON manifests into deterministic `PdfSource` models with stable run names and source hashes, without calling Mistral.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Source resolution only; no Mistral API calls, OCR JSON parsing, markdown stitching, bundle writing, or envelope assembly |
| Primary module | `gazette_mistral_pipeline/source_loading.py` |
| Model populated | `gazette_mistral_pipeline.models.PdfSource` |
| Inputs | PDF URL string, local PDF `str`/`Path`, existing `PdfSource`, or JSON manifest path |
| Manifest format | JSON object with a `sources` list; each item has `source_type` or `type` plus `source_value` or `value` |
| Public helpers | `derive_run_name`, `source_sha256`, `resolve_pdf_source`, `resolve_pdf_sources`, `load_source_manifest` |
| Runtime dependencies | None beyond stdlib and existing Pydantic dependency |
| Error handling | Invalid source types, missing local files, non-PDF paths/URLs, malformed manifests, and duplicate run names fail with clear `ValueError` or `FileNotFoundError` |
| Network behavior | No network requests; URL sources are validated syntactically only |
| Secret handling | No API keys, headers, signed URL contents, or environment values are read or written |

F04 must keep `parse_file`, `parse_url`, and `parse_source` as stubs. Wiring public API stubs into the full pipeline lands in F10.

### JSON Manifest Shape

Preferred manifest:

```json
{
  "sources": [
    {
      "source_type": "pdf_url",
      "source_value": "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/eng@2026-04-17/source.pdf"
    },
    {
      "source_type": "local_pdf",
      "source_value": "fixtures/sample.pdf",
      "run_name": "sample"
    }
  ]
}
```

Accepted aliases:

- `type` for `source_type`
- `value` for `source_value`
- top-level list of source items, for lightweight manifests

Text manifests from the notebook prototype are not part of the public F04 contract. They can be added later if real usage requires them.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | F04 is the current `⬜ Next` feature |
| `docs/library-contract-v1.md` | Defines accepted PDF URL/local inputs, source metadata fields, stable `run_name`, and `source_sha256` expectations |
| `docs/library-roadmap-v1.md` | Places source loading before Mistral API, page normalization, parsing, and envelope assembly |
| `docs/known-issues.md` | Requires stable output names, no API keys in source metadata, and no assumptions about local PDF upload behavior |
| `specs/SOP.md` | Requires spec-first implementation, small feature scope, and tests before progress updates |
| `examples/historical/gazette_etl_prototype.ipynb` | Contains the existing URL validation, manifest reading, and Kenyalaw AKN run-name extraction behavior to preserve |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Kenyalaw URL run name | `https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/eng@2026-04-17/source.pdf` | `PdfSource(source_type="pdf_url", run_name="gazette_2026-04-17_68")`; `source_sha256` is stable hash of normalized URL |
| TC2 | Generic PDF URL run name | `https://example.com/files/My Gazette 01.pdf?download=1` | URL validates; run name derives from path stem as sanitized `My_Gazette_01`; query string does not affect run name but remains in `source_value` |
| TC3 | Local PDF path | Temporary `.pdf` file | `source_type="local_pdf"`; `source_value` is a stable string path; `run_name` derives from file stem; `source_sha256` hashes file bytes |
| TC4 | JSON manifest resolution | Manifest with URL and local file entries | `resolve_pdf_sources` returns two `PdfSource` models in manifest order |
| TC5 | Existing `PdfSource` input | Prebuilt `PdfSource` with all required fields | Returned unchanged or equivalently validated; no file/network side effect |
| TC6 | Duplicate run names | Two sources resolving to same `run_name` without override | Raises `ValueError` naming the duplicate run name |
| TC7 | Invalid URL | `ftp://example.com/file.pdf` or URL path not ending in `.pdf` | Raises `ValueError` with source value included |
| TC8 | Missing local PDF | Nonexistent `.pdf` path | Raises `FileNotFoundError` |
| TC9 | Malformed manifest | Missing `sources`, missing source value, unknown source type, or invalid JSON | Raises clear `ValueError` |
| TC10 | No live I/O | URL inputs and manifests containing URLs | Tests do not perform HTTP requests and do not require `MISTRAL_API_KEY` |

## 5. Integration Point

Called by later features:

- F05 uses resolved `PdfSource` objects to decide whether to send a `document_url` request or a local upload/request flow.
- F09 stores the resolved source under `Envelope.source`.
- F10 public `parse_file`, `parse_url`, and `parse_source` call these helpers before invoking the rest of the pipeline.
- F10 bundle writing uses `run_name` to build output paths such as `<run>.raw.json`, `<run>_joined.md`, and `<run>_source.json`.

Calls:

- `PdfSource.model_validate(...)` from F03.
- `hashlib.sha256` for URL string hashes and local file byte hashes.
- `json.loads` / `json.load` for manifests.
- `pathlib.Path` and `urllib.parse` for source classification.

Side effects:

- Reads local PDF bytes only when resolving local PDFs.
- Reads JSON manifest files.
- Does not create output directories, write metadata, call Mistral, or download URLs.

Model fields populated:

- `PdfSource.source_type`
- `PdfSource.source_value`
- `PdfSource.run_name`
- `PdfSource.source_sha256`
- `PdfSource.source_metadata_path` remains `None` in F04 unless an explicit metadata filename helper is added; actual writing lands in F10.

Target module layout:

```text
gazette_mistral_pipeline/
  source_loading.py
tests/
  test_source_loading.py
```

Suggested implementation outline:

```python
def derive_run_name(source_value: str | Path, *, source_type: str | None = None) -> str:
    """Return stable sanitized run name for a PDF URL or local PDF path."""


def source_sha256(source_value: str | Path, *, source_type: str) -> str:
    """Hash local PDF bytes, or hash the normalized URL/source string."""


def resolve_pdf_source(source: str | Path | PdfSource, *, run_name: str | None = None) -> PdfSource:
    """Resolve one PDF source into a validated PdfSource."""


def resolve_pdf_sources(sources: Iterable[str | Path | PdfSource] | str | Path) -> list[PdfSource]:
    """Resolve multiple sources or one manifest path into unique PdfSource objects."""


def load_source_manifest(path: str | Path) -> list[dict[str, str]]:
    """Load and normalize a JSON manifest without resolving source side effects."""
```

Run-name rules:

1. Kenyalaw AKN URLs matching `/officialGazette/YYYY-MM-DD/NUMBER/` become `gazette_YYYY-MM-DD_NUMBER`.
2. Other PDF URLs use the URL path stem, not query or fragment.
3. Local PDF paths use the local file stem.
4. User-provided `run_name` values are sanitized but otherwise respected.
5. Empty or fully stripped names fail with `ValueError`.
6. Sanitization replaces non-alphanumeric, underscore, dot, or hyphen characters with `_`, collapses repeated underscores, and trims leading/trailing underscores.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Source loader module exists | `gazette_mistral_pipeline/source_loading.py` imports cleanly |
| PDF URL resolution works | Unit tests validate Kenyalaw and generic PDF URLs |
| Local PDF resolution works | Unit tests create a temporary PDF file and verify file-byte SHA-256 |
| Manifest loading works | Unit tests validate preferred and alias JSON manifest shapes |
| Invalid inputs fail clearly | Unit tests cover invalid URL schemes, non-PDF paths, missing files, malformed manifests, and duplicate run names |
| No network or Mistral dependency | Tests pass without `MISTRAL_API_KEY` and without HTTP calls |
| F03 models still work | `python -m pytest tests/test_models.py` passes |
| F02 stubs still work | `python -m pytest tests/test_package_skeleton.py` passes |

## 7. Definition Of Done

- [x] `gazette_mistral_pipeline/source_loading.py` implemented.
- [x] `derive_run_name`, `source_sha256`, `resolve_pdf_source`, `resolve_pdf_sources`, and `load_source_manifest` implemented.
- [x] Kenyalaw AKN run-name extraction matches the prototype behavior.
- [x] Local PDF SHA-256 uses file bytes.
- [x] URL SHA-256 uses a deterministic normalized source string without network access.
- [x] JSON manifests support preferred and alias shapes.
- [x] Duplicate resolved run names fail unless the user supplied distinct `run_name` values.
- [x] Tests added in `tests/test_source_loading.py`.
- [x] Existing `tests/test_package_skeleton.py` and `tests/test_models.py` still pass.
- [x] `python -m pytest` passes.
- [x] `PROGRESS.md` updated only after tests pass: F04 complete, F05 next, session log row added.

## 8. Open Questions And Risks

Q1. Should F04 expose source-loading helpers from the package root?

Recommended answer: no for now. Keep root API stable around the planned public `parse_*` and model exports. F10 can decide which lower-level helpers, if any, should become root exports.

Q2. Should F04 support text manifests from the notebook prototype?

Recommended answer: no. Use JSON manifests for the package contract because they can represent both URL and local PDF sources cleanly. Add text support later only if needed.

Q3. Should F04 download URL PDFs to compute the real file SHA-256?

Recommended answer: no. F04 must not perform network I/O. For URLs, `source_sha256` should be a deterministic hash of the normalized source string; F05 or later can record response hashes for downloaded/uploaded artifacts if needed.

Q4. Should `resolve_pdf_sources` automatically rename duplicate run names?

Recommended answer: no. Fail loudly so output folders and bundle names remain predictable. Users can supply explicit distinct `run_name` values in the manifest.

Q5. Should local file paths be resolved to absolute paths in `source_value`?

Recommended answer: yes. Store a stable resolved path string for local files after confirming the file exists. This makes source metadata unambiguous for later Mistral upload handling.
