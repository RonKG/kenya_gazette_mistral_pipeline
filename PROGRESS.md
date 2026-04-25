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

**Current:** F13 ✅ - Notebook driver cleanup complete  
**What:** Recommended notebook driver now uses the package API in offline replay mode.  
**Where:** `examples/gazette_package_driver.ipynb`, `README.md`, notebook hygiene tests  
**Previous:** F12 ✅ - Installable package smoke test implemented and tested.

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

## Quality Gates

| Gate | Condition | Status |
|------|-----------|--------|
| Gate 0 | Package processes one PDF source through mocked or replayed Mistral and writes default bundles | ✅ Reached - F10 replay public parse and default bundle writer tests pass offline |
| Gate 1 | Regression checks pass on selected cached Mistral OCR JSON fixtures from `prototype_outputs` | 🟨 Partial - F06 representative block-list raw JSON fixture passes; F07 representative inline notice/table/corrigenda snippets pass; F08 inline confidence/layout scoring snippets pass; broader cached-response regression waits for envelope stages |
| Gate 2 | Re-running the same cached response produces deterministic source IDs, run IDs, and notice IDs | 🟨 Partial - F07 deterministic notice IDs and content hashes pass on inline joined-markdown fixtures; F08 deterministic confidence scores pass on inline fixtures; cached-response rerun waits for later envelope stages |
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
| D6 | Live local PDF OCR upload/file-reference support is not implemented yet | Active debt | Later approved upload spec | Local PDF sources work in replay mode, but live local OCR fails until an explicit upload flow is added |

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

Add a row here at the end of every session.
