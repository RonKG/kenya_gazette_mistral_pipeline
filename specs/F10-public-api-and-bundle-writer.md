# F10 Spec: Public API and Bundle Writer

## 1. Goal

Expose the package-root parse/write functions over the completed F04-F09 stages and write deterministic output bundles from a validated `Envelope` plus available stage artifacts.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Public package-root wiring for `parse_file`, `parse_url`, `parse_source`, and `write_envelope`; a narrow bundle writer module; and any minimal `RuntimeOptions` fields needed to make parse/output behavior explicit |
| Out of scope | JSON Schema export or validation, `get_envelope_schema`, `validate_envelope_json`, notebook edits, CLI behavior, package install smoke tests, live local PDF upload/file-reference support, parser/scoring changes, envelope shape changes beyond paths needed for existing models, heavy dependencies, `PROGRESS.md` completion updates during spec creation, and commits |
| Public parse functions | Replace the F02 stubs for `parse_file(path, *, config=None)`, `parse_url(url, *, config=None)`, and `parse_source(source, *, config=None)` with real callables returning a validated `Envelope` |
| Public writer function | Replace the F02 `write_envelope(env, out_dir, bundles=None)` stub with a real callable returning `dict[str, Path]` keyed by written artifact names |
| Schema functions | `get_envelope_schema` and `validate_envelope_json` must remain F11 stubs in F10 |
| Parse source inputs | `parse_file` accepts a local PDF path and delegates to `parse_source`; `parse_url` accepts a PDF URL string and delegates to `parse_source`; `parse_source` accepts `PdfSource`, PDF URL string, local PDF `str`/`Path`, or a source value supported by F04 `resolve_pdf_source` |
| Replay/raw JSON input | `GazetteConfig.runtime.replay_raw_json_path` is the normal offline path for F10 tests and local PDF parsing; when set, `parse_*` must read that raw JSON through F05 replay behavior and must not read an API key, call Mistral, upload files, or perform network I/O |
| Live URL OCR input | Live URL OCR is opt-in. F10 should add or use an explicit lightweight runtime switch such as `RuntimeOptions.allow_live_mistral: bool = False`; if no replay path is configured and the switch is false, `parse_url`/`parse_source` must raise a clear error before reading API keys or calling Mistral |
| Live URL OCR output directory | If live URL OCR is explicitly enabled, `config.runtime.output_dir` or an equivalent explicit stage artifact directory must be provided so F05 has a deterministic cache directory for `<run>.raw.json`; missing output directory in live mode is an error |
| Local PDF live behavior | Preserve the F05 limitation: `parse_file` and `parse_source` for `local_pdf` work in replay mode only. Without `runtime.replay_raw_json_path`, local PDF parse must fail clearly and must not pass the local filesystem path as `document_url` |
| Output directory behavior during parse | `parse_*` must not write final bundles automatically. If an explicit runtime output/stage directory is provided, it may write stage artifacts needed by the pipeline, especially `<run>_joined.md`, and should pass that joined markdown path into F07 provenance. In replay mode without an output/stage directory, parse should build the envelope in memory and avoid implicit writes outside the replay file read |
| Stage orchestration | One source is processed as F04 source resolution, F05 Mistral OCR or replay, F06 page normalization and markdown stitching, F07 notice/table/corrigenda parsing, F08 confidence/layout scoring, and F09 validated envelope building |
| Parse output | A validated `gazette_mistral_pipeline.models.Envelope` whose source, Mistral metadata, stats, notices, tables, corrigenda, confidence, layout, and warnings come from F04-F09 outputs |
| Writer input | `write_envelope` accepts an `Envelope` instance or envelope-compatible mapping if implementation chooses to validate mappings with `Envelope.model_validate(...)`; `out_dir` is created as needed; `bundles` accepts `Bundles`, `dict`, or `None` and defaults to `Bundles()` |
| Writer output | A deterministic `dict[str, Path]` containing only selected and successfully written artifacts. Keys should match bundle names such as `envelope`, `joined_markdown`, `raw_mistral_json`, `source_metadata`, `notices`, `tables`, `document_index`, and `debug_trace` |
| Writer filenames | Use `env.source.run_name` as the stem: `<run>_envelope.json`, `<run>_joined.md`, `<run>.raw.json`, `<run>_source.json`, `<run>_notices.json`, `<run>_tables.json`, `<run>_index.json`, and `<run>_trace.json` |
| Writer serialization | JSON artifacts use UTF-8, deterministic formatting with sorted keys, indentation, one trailing newline, `Envelope.model_dump(mode="json")` or equivalent Pydantic JSON-safe dumps, and no non-stdlib JSON dependency |
| Source metadata bundle | `source_metadata=True` writes a JSON serialization of `env.source` to `<run>_source.json`; it must not read secrets or mutate the envelope to backfill `source_metadata_path` |
| Raw Mistral JSON bundle | `raw_mistral_json=True` copies bytes from `env.mistral.raw_json_path` to `<run>.raw.json` when the path is present and readable. If source and destination are the same resolved path, do not duplicate or rewrite it; return the existing path. If requested but unavailable, fail clearly |
| Joined markdown bundle | `joined_markdown=True` copies bytes/text from a joined markdown path recorded in notice/corrigendum provenance, normally `provenance.source_markdown_path`, when present and readable. If source and destination are the same resolved path, do not duplicate or rewrite it. If requested but unavailable, fail clearly |
| Envelope-derived optional bundles | `notices=True` writes `env.notices`; `tables=True` writes `env.tables`; `document_index=True` writes a compact artifact manifest/index derived from the envelope and the paths written in this call; `debug_trace=True` writes a deterministic debug summary from existing envelope metadata, confidence, layout, warnings, and notice IDs without re-running parser stages |
| Bundle manifest behavior | Do not add a new `Bundles` flag for a separate manifest in F10. The returned path dictionary is the in-memory manifest. If `document_index=True`, `<run>_index.json` should include the same artifact keys/relative filenames plus source/stats/version summary |
| Schema bundle behavior | `Bundles.json_schema` / alias `schema=True` remains F11 scope. If requested in F10, raise `NotImplementedError` or `ValueError` naming F11; do not generate schema files |
| Error handling | Invalid source inputs, unsupported live mode, missing replay files, unsupported raw JSON shapes, missing stage artifact files for selected bundles, schema bundle requests, invalid bundle dicts, and invalid envelope mappings fail clearly without partial success being hidden |
| Side effects | `parse_*` may read local PDFs for source hashing, read replay JSON, perform explicitly enabled live URL OCR, and write stage artifacts only to explicit output/cache directories. `write_envelope` writes only selected bundle files under `out_dir` or returns existing same-path artifacts; it does not call Mistral, read `.env`, execute notebooks, update `PROGRESS.md`, commit, or export schemas |
| Runtime dependencies | No new runtime dependency is expected. Use stdlib, existing Pydantic models, and existing package modules only unless implementation discovers a compelling reason and the spec is revised first |

Suggested module layout:

```text
gazette_mistral_pipeline/
  __init__.py
  public_api.py          # optional, if keeping __init__.py thin
  bundle_writer.py      # optional narrow writer module
tests/
  test_public_api.py
  test_bundle_writer.py
```

Suggested internal parse helper shape:

```python
def parse_source(source: PdfSource | str | Path, *, config: GazetteConfig | None = None) -> Envelope:
    """Resolve one source, run F04-F09, and return a validated envelope."""
```

The implementation may keep this helper directly in `__init__.py` or delegate from `__init__.py` to a package-internal module. Root imports must keep the public API names from `docs/library-contract-v1.md`.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F10 as the current `Next` item and records Gate 0/Gate 3 expectations for parse/write behavior |
| `docs/library-contract-v1.md` | Defines root public API signatures, pipeline order, envelope fields, and default/optional bundle names |
| `docs/library-roadmap-v1.md` | Places F10 after validated envelope assembly and before JSON Schema export, install smoke testing, and notebook cleanup |
| `docs/data-quality-confidence-scoring.md` | Defines confidence and spatial outputs that F10 must carry through from F08 without changing scoring behavior |
| `docs/known-issues.md` | Requires no secret leakage, opt-in live calls, support for replay/offline testing, parser-limit visibility, and explicit local PDF upload limitations |
| `specs/SOP.md` | Requires spec-first work, scoped implementation, offline/mocked tests, pass/fail criteria, and no completion update before tests pass |
| `specs/F04-pdf-source-loading.md` | Provides source resolution, source hashes, run names, and source metadata boundaries used by public parse functions and bundle filenames |
| `specs/F05-mistral-api-pass.md` | Provides OCR/replay behavior, raw JSON cache metadata, safe API key handling, and the explicit live local PDF limitation F10 must preserve |
| `specs/F06-normalize-and-stitch-pages.md` | Provides page normalization, joined markdown rendering, stage artifact writing, and stats used by parse orchestration and bundle writing |
| `specs/F07-notice-and-table-parsing.md` | Provides joined-markdown parsing, provenance, notice/table/corrigenda outputs, and source markdown path handling |
| `specs/F08-confidence-and-spatial-hints.md` | Provides scored notices, document confidence, layout info, and warnings that F10 must pass unchanged into F09 |
| `specs/F09-build-validated-envelope.md` | Provides `EnvelopeBuildInputs` and `build_envelope(...)`, the final assembly step F10 calls before returning public parse results |
| `gazette_mistral_pipeline/__init__.py` | Contains the F02 root stubs F10 replaces while leaving F11 schema stubs intact |
| `gazette_mistral_pipeline/models/bundles.py` | Defines the existing `Bundles` flags, defaults, and `schema` alias that F10 writer must honor or reject as F11 scope |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Replay happy path through public `parse_url` | PDF URL, `GazetteConfig(runtime.replay_raw_json_path=<small raw JSON fixture>, runtime.output_dir=<tmp stage dir>)` | Returns validated `Envelope`; source run name comes from F04; F05 replay metadata points to fixture; F06-F09 outputs are populated; joined markdown stage artifact is written under the explicit stage dir; no API key lookup, network call, final bundle write, schema export, notebook access, or `.env` read occurs |
| TC2 | Local PDF replay path | Temporary `.pdf` file plus replay raw JSON fixture and explicit stage dir | `parse_file` returns an envelope with `source_type=="local_pdf"` and local file SHA-256; replay bypasses upload and network; joined markdown provenance points to the stage artifact; live local OCR is not attempted |
| TC3 | Live URL OCR requires explicit opt-in | PDF URL with no replay path and default config | Raises a clear error naming the live Mistral opt-in requirement before reading `MISTRAL_API_KEY` or calling `urllib.request.urlopen`; no files are written |
| TC4 | Live URL OCR with mocked HTTP | PDF URL, config with explicit live opt-in and explicit output/stage dir, monkeypatched env var and `urlopen` | Calls F05 URL OCR once with mocked HTTP, writes `<run>.raw.json` to the explicit stage/cache dir, completes F06-F09, returns an `Envelope`, and performs no real network call |
| TC5 | Live local PDF remains unsupported | Temporary local `.pdf`, no replay path, even if live opt-in is true | Raises the F05/F10 clear unsupported-local-live error; does not upload, does not call Mistral, and does not pass the local path as `document_url` |
| TC6 | Public stubs become real callables | Import `parse_file`, `parse_url`, `parse_source`, and `write_envelope` from package root | These F10 functions no longer raise the F02 `NotImplementedError` on valid offline inputs; `get_envelope_schema` and `validate_envelope_json` still raise F11 stub errors |
| TC7 | Default bundle writer from replay parse | Envelope returned by TC1 or TC2, `write_envelope(env, out_dir)` with default `Bundles()` | Writes deterministic default artifacts that are available: envelope JSON, source metadata JSON, raw Mistral JSON copy, and joined markdown copy; returned paths use contract filenames; content is deterministic across repeated writes |
| TC8 | Optional bundle writer outputs | Same envelope, `Bundles(notices=True, tables=True, document_index=True, debug_trace=True, joined_markdown=False, raw_mistral_json=False)` or equivalent dict | Writes only selected envelope-derived JSON artifacts plus defaults still true unless explicitly disabled; notice/table counts match envelope stats; index includes artifact manifest keys and relative filenames; no raw/joined files are written when disabled |
| TC9 | No duplication and same-path boundaries | `out_dir` is the same directory that already contains `<run>.raw.json` or `<run>_joined.md` from parse stage | Writer returns existing same-path raw/joined paths without copying a file over itself or changing bytes; repeated writes produce identical JSON bytes for envelope-derived files |
| TC10 | Missing selected stage artifact fails clearly | Envelope has `mistral.raw_json_path=None`, missing file path, or no provenance `source_markdown_path`, while the corresponding bundle flag is true | `write_envelope` raises `ValueError` or `FileNotFoundError` naming the unavailable selected bundle; already-written behavior is either avoided by preflight checks or documented and tested |
| TC11 | Schema bundle stays out of scope | `write_envelope(env, out_dir, {"schema": True})` or `Bundles(schema=True)` | Raises a clear F11-scope error; no schema file is written and schema helper stubs remain unchanged |
| TC12 | Invalid inputs and bundle dicts | Invalid source value, invalid envelope mapping, malformed bundle dict with unknown fields, unsupported raw JSON replay shape | Raises clear validation or value errors from the owning stage/model; no live calls, no `.env` reads, and no misleading partial envelope is returned |

Normal F10 tests must be offline by default. Use replay JSON fixtures, temporary local PDFs, and monkeypatched HTTP/env only for mocked live URL behavior. Do not run live Mistral calls in normal tests.

## 5. Integration Point

- Called by:
  - External users importing `parse_file`, `parse_url`, `parse_source`, and `write_envelope` from `gazette_mistral_pipeline`.
  - Later F12 install smoke tests verifying root imports and callable public behavior.
  - Later F13 notebook cleanup, which should become a thin example over these public functions.

- Calls:
  - F04 `resolve_pdf_source` / `resolve_pdf_sources` behavior for source classification and deterministic run names.
  - F05 `run_mistral_ocr(...)` for replay or explicitly enabled live URL OCR.
  - F06 `normalize_mistral_pages(...)`, `stitch_markdown_pages(...)`, `write_joined_markdown(...)`, and `compute_stats(...)`.
  - F07 `parse_joined_markdown(...)`.
  - F08 `score_parsed_notices(...)`.
  - F09 `EnvelopeBuildInputs` and `build_envelope(...)`.
  - Existing `Bundles`, `GazetteConfig`, `RuntimeOptions`, and Pydantic models.

- Side effects:
  - `parse_*` reads local PDFs for F04 hashing, reads replay raw JSON when configured, reads the configured API key only for explicitly enabled live URL OCR, and writes raw/joined stage artifacts only under explicit output/cache directories.
  - `write_envelope` creates `out_dir` and writes selected bundle artifacts there, or returns an existing same-path raw/joined artifact without rewriting it.
  - F10 does not export JSON Schema, validate against JSON Schema, edit notebooks, read `.env`, update `PROGRESS.md`, commit, or add dependencies.

- Model fields populated:
  - `Envelope` fields are populated by F09 from F04-F08 outputs.
  - `PdfSource.source_metadata_path` may remain whatever source loading/envelope construction supplied; writer must not mutate it as a side effect.
  - `MistralMetadata.raw_json_path` and `raw_json_sha256` come from F05 live cache or replay input.
  - Notice/corrigendum provenance should carry `source_markdown_path` when parse had an explicit stage output directory and F06 wrote joined markdown.

- Quality gate contribution:
  - F10 should satisfy Gate 0 for one mocked or replayed source writing default bundles.
  - F10 should satisfy the callable part of Gate 3 for root `parse_file` and `write_envelope`; full install smoke remains F12.
  - F10 must not claim Gate 4 because JSON Schema export/validation remains F11.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Root parse functions are real | Public API tests import `parse_file`, `parse_url`, and `parse_source` and run them successfully with replay/offline fixtures |
| Root writer is real | Bundle writer tests call `write_envelope(...)` and receive a deterministic `dict[str, Path]` for selected artifacts |
| F04-F09 orchestration is complete | Tests assert source, Mistral metadata, stats, notices, tables, confidence, layout, warnings, and envelope validation all come from the existing stage helpers |
| Replay mode is offline | Tests monkeypatch env/network to fail and prove replay parses without API key lookup or HTTP calls |
| Live URL OCR is opt-in | Tests assert default no-replay URL parsing fails before env/network access, and a mocked opt-in live URL parse succeeds with no real network |
| Live local PDF remains deferred | Tests assert local PDFs without replay fail clearly and never use a local path as a remote document URL |
| Output dirs are explicit | Tests assert parse-time stage artifacts are written only when an explicit output/stage directory is configured, and final bundles are written only by `write_envelope` under `out_dir` |
| Default bundles match contract where artifacts exist | Tests verify envelope, joined markdown, raw Mistral JSON, and source metadata filenames/content for an envelope with available stage artifact paths |
| Optional bundles are deterministic | Tests verify notices, tables, document index, and debug trace JSON content/order across repeated writes |
| Missing selected artifacts fail clearly | Tests cover requested raw/joined bundles when paths are absent or unreadable |
| Schema remains F11 | Tests verify schema bundle requests and root schema helper calls still raise F11-scope errors |
| Side-effect boundary is respected | Review and tests confirm no notebook edits, `.env` reads, schema files, dependency additions, `PROGRESS.md` completion update, commits, or live Mistral calls in normal tests |
| Offline test suite passes | `python -m pytest tests/test_public_api.py tests/test_bundle_writer.py` and `python -m pytest` pass without API keys or network access |

## 7. Definition Of Done

- [x] `specs/F10-public-api-and-bundle-writer.md` is approved before implementation starts.
- [x] Package-root `parse_file`, `parse_url`, `parse_source`, and `write_envelope` are real callables with the public signatures from `docs/library-contract-v1.md`.
- [x] Root `get_envelope_schema` and `validate_envelope_json` remain F11 stubs.
- [x] Public parse functions orchestrate F04-F09 in order and return a validated `Envelope`.
- [x] Replay/raw JSON input behavior is explicit, offline, and covered for URL and local PDF sources.
- [x] Live URL OCR is gated by an explicit opt-in and uses mocked HTTP in normal tests only.
- [x] Live local PDF upload/file-reference OCR remains explicitly unsupported unless a later approved spec adds upload support.
- [x] Output/stage directory behavior is deterministic and avoids implicit writes outside configured directories.
- [x] Bundle writer materializes selected artifacts with deterministic filenames and JSON formatting.
- [x] Bundle writer copies available raw JSON and joined markdown artifacts without duplicating same-path files and fails clearly when selected artifacts are unavailable.
- [x] Schema bundle requests are rejected or deferred clearly to F11.
- [x] No runtime dependencies are added unless this spec is revised with a clear justification.
- [x] Unit tests cover at least the matrix above using offline replay fixtures and mocked HTTP only.
- [x] Existing F04-F09 tests still pass.
- [x] F10 does not edit notebooks, export schemas, implement F11/F13 work, read/use `.env`, run live Mistral calls in normal tests, commit changes, or mark `PROGRESS.md` complete before builder/tester closure.

## 8. Open Questions And Risks

Q1. Should F10 add explicit runtime fields for live opt-in and output/stage directory?

Recommended answer: yes. Add the smallest possible fields, such as `RuntimeOptions.allow_live_mistral: bool = False` and `RuntimeOptions.output_dir: Path | None = None`, because the existing parse signatures only accept `config` and F05 live OCR needs a deterministic cache directory. This keeps live calls opt-in and avoids hidden writes.

Q2. Should `parse_*` write final bundles automatically when `runtime.output_dir` is set?

Recommended answer: no. Keep parsing and final bundle writing separate. `parse_*` may write stage artifacts needed to build the envelope, while `write_envelope` is the only public function that writes final selected bundles.

Q3. How should `write_envelope` find joined markdown when it only receives an `Envelope`?

Recommended answer: use existing provenance paths, primarily `Notice.provenance.source_markdown_path` and corrigendum provenance if needed. If the selected joined markdown bundle is requested and no readable joined markdown path is available, fail clearly rather than reconstructing markdown from notices or silently omitting the file.

Q4. Should `write_envelope` write a separate manifest file by default?

Recommended answer: no. The existing `Bundles` model does not include a manifest flag. Return the path dictionary as the in-memory manifest, and include artifact manifest data in `<run>_index.json` only when `document_index=True`.

Q5. Should F10 implement live local PDF upload support?

Recommended answer: no. Preserve the F05 limitation for F10. Local PDFs should parse through replay mode now; live local upload/file-reference support needs its own explicit spec and mocked tests once the Mistral upload flow is confirmed.

Q6. Should bundle writing mutate the envelope to update path fields?

Recommended answer: no. Treat `Envelope` as an already-built validated record. `write_envelope` should serialize or copy artifacts and return paths, not mutate `env.source.source_metadata_path`, `env.mistral.raw_json_path`, provenance paths, counts, or timestamps.

Q7. What is the main implementation risk?

Recommended answer: hidden side effects and partial bundle writes. The builder should preflight selected artifact availability where practical, keep parse-time stage writes separate from final bundles, and test repeated writes for deterministic bytes and no self-copy duplication.
