# Gazette Mistral Pipeline - Build Progress

**Project:** Kenya Gazette PDF source -> Mistral OCR -> markdown -> enhanced JSON envelope  
**Builder:** Solo, part-time  
**Target 1.0:** Git-installable lightweight package for Mistral-based gazette ETL  
**Last updated:** 2026-04-25

## How To Use This File

- Read this file at the start of every session.
- Work only on the current `⬜ Next` item unless the user explicitly overrides it.
- Every feature must have a spec in `specs/` before implementation.
- At the end of a feature, update Today, Work Items, Quality Gates, Known Debt, and Session Log.

Session-start prompt:

> Read `PROGRESS.md`. The `⬜ Next` item is what I work on. Build it.

## Today

**Current:** F18 ✅ Complete - Mistral reliability and usage  
**What:** Live Mistral upload/OCR calls now retry transient failures, raise sanitized structured errors, and record OCR usage/cost plus returned-markdown token estimates in envelope metadata.  
**Where:** `gazette_mistral_pipeline/mistral_ocr.py`, `gazette_mistral_pipeline/models/config.py`, `gazette_mistral_pipeline/models/source.py`, schema/docs/tests  
**Previous:** F17 ✅ - Add table notice provenance complete.

## Work Items

| ID | Name | Simple Explanation | Status | Commit |
|----|------|--------------------|--------|--------|
| F01 | Project SOP scaffold | Create progress, docs, specs, agents, and build gates | ✅ Complete | 954b16d |
| F02 | Package skeleton | Create git-installable Python package with public API stubs | ✅ Complete | 954b16d |
| F03 | Pydantic models | Define lightweight Mistral envelope, source, notices, tables, confidence, warnings, bundles, and spatial hints | ✅ Complete | 423f69e |
| F04 | PDF source loading | Support PDF URL, local PDF path, and manifests; derive stable run names | ✅ Complete | 164da54 |
| F05 | Mistral API pass | Send PDF source to Mistral OCR, cache raw OCR JSON, support replay mode | ✅ Complete | 8f791db |
| F06 | Normalize and stitch pages | Normalize Mistral pages and write joined markdown | ✅ Complete | 9bf8dd8 |
| F07 | Notice and table parsing | Parse joined markdown into notices, dates, tables, and corrigenda placeholders | ✅ Complete | 029c572 |
| F08 | Confidence and spatial hints | Score notices and summarize optional Mistral coordinate metadata | ✅ Complete | 3f37408 |
| F09 | Build validated envelope | Assemble and validate the enhanced Pydantic envelope | ✅ Complete | 4fe6eae |
| F10 | Public API and bundle writer | Expose parse/write functions and write output bundles | ✅ Complete | 53fcd0b |
| F11 | JSON Schema export | Generate schema helpers and checked-in envelope schema | ✅ Complete | 53fcd0b |
| F12 | Installable package smoke test | Verify install, imports, schema package data, and git-install readiness | ✅ Complete | 47083f2 |
| F13 | Notebook driver cleanup | Convert notebooks into thin examples over the package API | ✅ Complete | 69b40d2 |
| F14 | Live local PDF upload support | Upload local or network PDF paths to Mistral, OCR by `file_id`, and keep `parse_file` live-capable | ✅ Complete | 17ae63d |
| F15 | Clean page running headers | Strip repeated gazette page title/date/page-number headers from joined markdown before notice parsing | ✅ Complete | 17ae63d |
| F16 | Exclude post-notice tail | Keep ads/catalogues/subscriber notes in joined markdown but exclude them from parsed notices | ✅ Complete | a3c3317 |
| F17 | Add table notice provenance | Add notice number and parent notice context to flattened table objects so table exports remain tied to the notice they came from | ✅ Complete | 9e58929 |
| F18 | Mistral reliability and usage | Retry transient Mistral failures and record usage/cost metadata for OCR runs | ✅ Complete | ff8dc84 |

## Quality Gates

| Gate | Condition | Status |
|------|-----------|--------|
| Gate 0 | Package processes one PDF source through mocked or replayed Mistral and writes default bundles | ✅ Reached - F10 replay public parse and default bundle writer tests pass offline; F18 mocked live OCR/upload retry and usage metadata tests also pass offline |
| Gate 1 | Regression checks pass on selected cached Mistral OCR JSON fixtures from `prototype_outputs` | ✅ Reached - `tests/test_cached_mistral_regression.py` runs the full replay pipeline on two committed real-gazette fixtures (2026-04-17 vol 68, 2009-12-11 vol 103), asserts pinned page count, notice/table count ranges, pinned SHA256 hashes, F17 table notice provenance, and verifies F15 running-header cleanup plus F16 post-notice tail exclusion on the 2009 fixture; 6 Gate 1/F15/F16/F17 tests pass offline |
| Gate 2 | Re-running the same cached response produces deterministic source IDs, run IDs, and notice IDs | ✅ Reached - `tests/test_cached_mistral_regression.py` runs each fixture twice and asserts run names, SHA256s, page/notice/table counts, all notice IDs in order, all notice content hashes, and Mistral metadata are byte-identical across runs; 2 Gate 2 parametrized tests pass offline |
| Gate 3 | `from gazette_mistral_pipeline import parse_file, write_envelope` works after install | ✅ Reached - F12 local fresh-venv install smoke verifies root parse/write/schema imports after install |
| Gate 4 | Envelope validates against its JSON Schema | ✅ Reached - F11 exports deterministic envelope JSON Schema, validates JSON inputs through the canonical `Envelope`, and writes schema bundles offline |
| Gate 5 | Fresh virtual environment install works as proxy for `pip install git+...` | ✅ Reached - F12 standalone local-path install smoke passes offline and optional Git URL smoke is explicit only |

## Known Debt And Gotchas

| ID | Item | Type | Target | Consequence if forgotten |
|----|------|------|--------|--------------------------|
| D1 | Recommended notebook path uses package APIs instead of prototype parser logic | Closed in F13 | - | Historical prototype code is retained only as labeled context, not as the supported package example |
| D2 | Existing notebook output staleness is narrowed to historical prototype context | Enduring gotcha | - | The recommended driver has cleared outputs; the historical prototype may still show stale bounded output until rerun |
| D3 | Mistral API calls must be opt-in in tests | Enduring gotcha | - | Normal test runs could become slow, flaky, or billable |
| D4 | Mistral response JSON may not contain word-level coordinates | Enduring gotcha | - | Spatial hints can improve provenance but cannot promise full reading-order reconstruction |
| D5 | API keys must come from environment/config, not checked-in notebooks or fixtures | Enduring gotcha | - | Secret leakage risk |
| D6 | Live local PDF OCR upload/file-reference support | Closed in F14 | - | Local and network PDF paths now upload to Mistral Files with `purpose="ocr"` and OCR by returned `file_id` |
| D7 | Repeated PDF running headers pollute notice text | Closed in F15 | - | Joined markdown now strips recognizable standalone page title/date/page-number lines at page boundaries before notice parsing |
| D8 | Post-notice ads and subscriber pages can pollute final notice | Closed in F16 | - | Final parsed notices now stop before detected catalogue, subscriber, and advertisement tail material while joined markdown keeps the full source text |
| D9 | Local PDF upload retries can duplicate uploaded files after ambiguous transient failures | Enduring gotcha | - | If Mistral receives an upload but the client times out before the response, retrying may create another uploaded file; F18 does not add uploaded-file cleanup controls |

## Reference Docs

- `docs/library-contract-v1.md` - public API, envelope contract, output bundles
- `docs/library-roadmap-v1.md` - architecture and feature sequence
- `docs/data-quality-confidence-scoring.md` - confidence and spatial hint rules
- `docs/known-issues.md` - parser limitations and operational caveats
- `specs/SOP.md` - feature build workflow
- `specs/F01-project-sop-scaffold.md` - completed scaffold spec
- `specs/F02-package-skeleton.md` - completed package skeleton spec
- `specs/F03-pydantic-models.md` - completed Pydantic model spec
- `specs/F04-pdf-source-loading.md` - completed PDF source loading spec
- `specs/F05-mistral-api-pass.md` - completed Mistral API pass spec
- `specs/F06-normalize-and-stitch-pages.md` - completed page normalization and stitching spec
- `specs/F07-notice-and-table-parsing.md` - completed notice and table parsing spec
- `specs/F08-confidence-and-spatial-hints.md` - completed confidence and spatial hints spec
- `specs/F09-build-validated-envelope.md` - completed validated envelope builder spec
- `specs/F10-public-api-and-bundle-writer.md` - completed public API and bundle writer spec
- `specs/F11-json-schema-export.md` - completed JSON Schema export spec
- `specs/F12-installable-package-smoke-test.md` - completed installable package smoke test spec
- `specs/F13-notebook-driver-cleanup.md` - completed notebook driver cleanup spec
- `specs/F14-live-local-pdf-upload.md` - completed live local PDF upload spec
- `specs/F15-clean-page-running-headers.md` - completed page running header cleanup spec
- `specs/F16-exclude-post-notice-tail.md` - completed final notice tail exclusion spec
- `specs/F17-add-table-notice-provenance.md` - completed table notice provenance spec
- `specs/F18-mistral-reliability-and-usage.md` - planned Mistral retry, error, and usage metadata feature

## Session Log

| Date | Task | Summary |
|------|------|---------|
| 2026-04-25 | F01 Project SOP scaffold | Created Docling-style project documents, feature list, gates, and agent workflow for the Mistral package. |
| 2026-04-25 | F02 Package skeleton | Created installable package shell, public API stubs, `pyproject.toml`, README, Apache-2.0 license, and skeleton tests. `python -m pytest tests/test_package_skeleton.py` passed; `python -m pip install -e .` passed. |
| 2026-04-25 | F03 Pydantic models | Added strict Pydantic model layer, model root exports, config and bundle defaults, optional spatial hints, and model tests. `python -m pytest tests/test_package_skeleton.py tests/test_models.py` passed. |
| 2026-04-25 | F04 PDF source loading | Added source-loading helpers for PDF URLs, local PDFs, JSON manifests, stable run names, source SHA-256 hashes, and invalid-input checks. `python -m pytest` passed. |
| 2026-04-25 | F05 Mistral API pass | Added stdlib Mistral OCR URL requests, deterministic raw JSON cache/replay helpers, safe `MistralMetadata` population, explicit live-local unsupported behavior, and mocked/replay tests. `python -m pytest` passed. |
| 2026-04-25 | F06 Normalize and stitch pages | Added page normalization dataclasses/helpers, deterministic sorting, joined markdown rendering/writing, representative raw JSON fixture, and F06 stats. `python -m pytest tests/test_page_normalization.py` and `python -m pytest` passed. |
| 2026-04-25 | F07 Notice and table parsing | Added pure joined-markdown notice parsing, table extraction, corrigenda placeholders, deterministic hashes/IDs, provenance, and neutral F08 confidence placeholders. `python -m pytest tests/test_notice_parsing.py` and `python -m pytest` passed. |
| 2026-04-25 | F08 Confidence and spatial hints | Added deterministic notice confidence scoring, document confidence aggregation, layout hint summaries, and bounded pipeline warnings. `python -m pytest tests/test_confidence_scoring.py` and `python -m pytest` passed. |
| 2026-04-25 | F09 Build validated envelope | Added pure envelope assembly from F04-F08 outputs, canonical versions/timestamps, count drift checks, single-pass table flattening, Pydantic validation, and F09 tests. `python -m pytest tests/test_envelope_builder.py` and `python -m pytest` passed. |
| 2026-04-25 | F10 Public API and bundle writer | Wired package-root parse functions through F04-F09, added explicit replay/live/output runtime controls, implemented deterministic bundle writing, kept schema helpers as F11 stubs, and added F10 public API/bundle writer tests. `python -m pytest tests/test_public_api.py tests/test_bundle_writer.py` and `python -m pytest` passed. |
| 2026-04-25 | F11 JSON Schema export | Added package-root schema export and validation helpers, checked-in deterministic envelope schema package data, schema bundle writing, and F11 tests. `python -m pytest tests/test_schema_export.py tests/test_public_api.py tests/test_bundle_writer.py` and `python -m pytest` passed. |
| 2026-04-25 | F12 Installable package smoke test | Added a standalone fresh-venv local install smoke with wheel content inspection, installed-package import/resource/metadata checks, optional explicit Git URL mode, and offline replay parse/write/schema validation. `python -m pytest tests/test_install_smoke.py`, `python scripts/install_smoke.py --repo-path . --mode local-path`, and `python -m pytest` passed. |
| 2026-04-25 | F13 Notebook driver cleanup | Added the thin offline replay notebook driver, tiny replay fixture, README guidance, historical prototype labeling/default-offline guard, and static notebook hygiene tests. `python -m pytest tests/test_notebook_examples.py`, `python -m pytest tests/test_public_api.py tests/test_bundle_writer.py tests/test_install_smoke.py`, and `python -m pytest` passed. |

| 2026-04-25 | Gates 1 and 2 regression and determinism tests | Copied two real-gazette cached Mistral OCR JSON fixtures (2026-04-17 vol 68, 2009-12-11 vol 103) to `tests/fixtures/`, wrote `tests/test_cached_mistral_regression.py` with 4 parametrized tests covering Gate 1 (full replay + pinned SHA256/stats checks) and Gate 2 (double-run ID/hash/count determinism). All 4 tests pass offline. PROGRESS.md gates updated to ✅. |
| 2026-04-25 | F14 Live local PDF upload support | Added stdlib Mistral Files upload for `parse_file(path)`, OCR-by-`file_id`, honest local PDF metadata, mocked public API/unit tests, README/notebook guidance, and closed D6. `python -m pytest tests/test_mistral_ocr.py tests/test_public_api.py`, `python -m pytest tests/test_notebook_examples.py`, and `python -m pytest` passed. |
| 2026-04-25 | F15 Clean page running headers spec | Documented the next feature to remove repeated gazette page title/date/page-number header fragments from stitched markdown before notice parsing, based on screenshots and the 2009 cached OCR fixture. Implementation intentionally not started yet. |
| 2026-04-25 | F16 Exclude post-notice tail spec | Documented a planned parser cleanup that keeps post-notice ads/catalogues/subscriber notes in joined markdown but excludes them from parsed `Notice` objects, with conservative final-notice boundary rules and cached 2009 regression coverage. |
| 2026-04-25 | F15 Clean page running headers | Added conservative page-boundary running header/footer cleanup during markdown stitching while preserving raw OCR pages, covered observed header permutations and 2009 cached replay regression, updated docs, and closed D7. `python -m pytest tests/test_page_normalization.py tests/test_cached_mistral_regression.py` and `python -m pytest` passed. |
| 2026-04-25 | F16 Exclude post-notice tail | Added conservative final-notice tail detection in notice parsing, kept joined markdown intact, excluded catalogue/subscriber/ad-charge tail material from parsed notices, updated parser marker/docs, and closed D8. `python -m pytest tests/test_notice_parsing.py tests/test_cached_mistral_regression.py` and `python -m pytest` passed. |
| 2026-04-25 | F17 Add table notice provenance | Added parent notice context fields to extracted tables, stamped them during notice parsing, preserved/backfilled them during envelope flattening, updated docs/schema, and verified flat table bundles keep `notice_no`/`notice_id` links. `python -m pytest tests/test_notice_parsing.py tests/test_envelope_builder.py tests/test_bundle_writer.py tests/test_schema_export.py tests/test_cached_mistral_regression.py` and `python -m pytest` passed. |
| 2026-04-25 | F18 Mistral reliability and usage | Added configurable retry/backoff for Mistral upload/OCR calls, sanitized structured request and payload errors, `usage_info`/page cost metadata, raw response byte and retry counts, returned-markdown token estimates, schema/docs updates, and mocked retry/error/usage tests. `python -m pytest tests/test_mistral_ocr.py tests/test_public_api.py tests/test_envelope_builder.py tests/test_schema_export.py tests/test_bundle_writer.py`, `python -m pytest tests/test_notebook_examples.py`, and `python -m pytest` passed. |

Add a row here at the end of every session.
