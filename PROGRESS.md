# Gazette Mistral Pipeline - Build Progress

**Project:** Kenya Gazette PDF source -> Mistral OCR -> markdown -> enhanced JSON envelope  
**Builder:** Solo, part-time  
**Target 1.0:** Git-installable lightweight package for Mistral-based gazette ETL  
**Last updated:** 2026-04-25

## How To Use This File

- Read this file at the start of every session.
- Work only on the current `Next` item unless the user explicitly overrides it.
- Every feature must have a spec in `specs/` before implementation.
- At the end of a feature, update Today, Work Items, Quality Gates, Known Debt, and Session Log.

Session-start prompt:

> Read `PROGRESS.md`. The `Next` item is what I work on. Build it.

## Today

**Current:** F03 - Pydantic models  
**What:** Define the lightweight Mistral envelope, source metadata, notices, tables, confidence, warnings, bundles, and optional spatial hints.  
**Where:** `gazette_mistral_pipeline/models/`, future `schema` integration  
**Previous:** F02 Complete - Package skeleton created, tests passed, editable install succeeded.

## Work Items

| ID | Name | Simple Explanation | Status | Commit |
|----|------|--------------------|--------|--------|
| F01 | Project SOP scaffold | Create progress, docs, specs, agents, and build gates | Complete | - |
| F02 | Package skeleton | Create git-installable Python package with public API stubs | Complete | - |
| F03 | Pydantic models | Define lightweight Mistral envelope, source, notices, tables, confidence, warnings, bundles, and spatial hints | Next | - |
| F04 | PDF source loading | Support PDF URL, local PDF path, and manifests; derive stable run names | Not started | - |
| F05 | Mistral API pass | Send PDF source to Mistral OCR, cache raw OCR JSON, support replay mode | Not started | - |
| F06 | Normalize and stitch pages | Normalize Mistral pages and write joined markdown | Not started | - |
| F07 | Notice and table parsing | Parse joined markdown into notices, dates, tables, and corrigenda placeholders | Not started | - |
| F08 | Confidence and spatial hints | Score notices and summarize optional Mistral coordinate metadata | Not started | - |
| F09 | Build validated envelope | Assemble and validate the enhanced Pydantic envelope | Not started | - |
| F10 | Public API and bundle writer | Expose parse/write functions and write output bundles | Not started | - |
| F11 | JSON Schema export | Generate schema helpers and checked-in envelope schema | Not started | - |
| F12 | Installable package smoke test | Verify install, imports, schema package data, and git-install readiness | Not started | - |
| F13 | Notebook driver cleanup | Convert notebooks into thin examples over the package API | Not started | - |

## Quality Gates

| Gate | Condition | Status |
|------|-----------|--------|
| Gate 0 | Package processes one PDF source through mocked or replayed Mistral and writes default bundles | Not reached |
| Gate 1 | Regression checks pass on selected cached Mistral OCR JSON fixtures from `prototype_outputs` | Not reached |
| Gate 2 | Re-running the same cached response produces deterministic source IDs, run IDs, and notice IDs | Not reached |
| Gate 3 | `from gazette_mistral_pipeline import parse_file, write_envelope` works after install | Partial - F02 import smoke passed; callable implementation waits for F10 |
| Gate 4 | Envelope validates against its JSON Schema | Not reached |
| Gate 5 | Fresh virtual environment install works as proxy for `pip install git+...` | Not reached |

## Known Debt And Gotchas

| ID | Item | Type | Target | Consequence if forgotten |
|----|------|------|--------|--------------------------|
| D1 | Current parsing logic is duplicated across notebooks | Active debt | F07/F13 | Parser behavior will drift between prototype and package |
| D2 | Existing notebooks may contain stale execution output and paths | Enduring gotcha | - | Visual notebook output may not reflect current code until cells are rerun |
| D3 | Mistral API calls must be opt-in in tests | Enduring gotcha | - | Normal test runs could become slow, flaky, or billable |
| D4 | Mistral response JSON may not contain word-level coordinates | Enduring gotcha | - | Spatial hints can improve provenance but cannot promise full reading-order reconstruction |
| D5 | API keys must come from environment/config, not checked-in notebooks or fixtures | Enduring gotcha | - | Secret leakage risk |

## Reference Docs

- `docs/library-contract-v1.md` - public API, envelope contract, output bundles
- `docs/library-roadmap-v1.md` - architecture and feature sequence
- `docs/data-quality-confidence-scoring.md` - confidence and spatial hint rules
- `docs/known-issues.md` - parser limitations and operational caveats
- `specs/SOP.md` - feature build workflow
- `specs/F01-project-sop-scaffold.md` - completed scaffold spec
- `specs/F02-package-skeleton.md` - completed package skeleton spec

## Session Log

| Date | Task | Summary |
|------|------|---------|
| 2026-04-25 | F01 Project SOP scaffold | Created Docling-style project documents, feature list, gates, and agent workflow for the Mistral package. |
| 2026-04-25 | F02 Package skeleton | Created installable package shell, public API stubs, `pyproject.toml`, README, Apache-2.0 license, and skeleton tests. `python -m pytest tests/test_package_skeleton.py` passed; `python -m pip install -e .` passed. |

Add a row here at the end of every session.
