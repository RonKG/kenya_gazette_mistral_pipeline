# Gazette Mistral Pipeline Roadmap v1

## Purpose

This roadmap turns the current notebook prototype into a lightweight, Git-installable package that processes Kenya Gazette PDFs through Mistral OCR and returns validated structured outputs.

## Architecture Choice

Use a clean Python package with one implementation per stage.

```text
PDF source
  -> Mistral OCR
  -> raw OCR JSON
  -> normalized pages
  -> joined markdown
  -> notice/table parser
  -> confidence and optional spatial hints
  -> validated envelope
  -> output bundles
```

This mirrors the Docling package's public API and build discipline, but avoids Docling dependencies and keeps runtime light.

## 1.0 Scope

Ships in 1.0:

- Git-installable Python package.
- `parse_file`, `parse_url`, `parse_source`, and `write_envelope`.
- Pydantic models for the enhanced Mistral envelope.
- Mistral OCR API pass using stdlib HTTP.
- Cached raw Mistral OCR JSON.
- Joined markdown artifact.
- Markdown parser for notices, dates, tables, and corrigenda placeholders.
- Rule-based confidence scoring.
- Optional spatial hints from Mistral response coordinates.
- JSON Schema export and validation.
- Pytest suite with mocked/replayed Mistral responses.
- Notebook examples that import the package.

Deferred until after 1.0:

- CLI.
- PyPI publishing.
- LLM repair.
- ML table/notice repair.
- Full spatial reconstruction from PDFs.
- Multi-engine package wrapper that imports both Mistral and Docling packages.

## Feature Sequence

| ID | Feature | Outcome |
|----|---------|---------|
| F01 | Project SOP scaffold | Progress file, docs, specs, agents, gates |
| F02 | Package skeleton | Installable package shell with API stubs |
| F03 | Pydantic models | Envelope, notice, table, source, confidence, bundles |
| F04 | PDF source loading | PDF URL/local path/manifest resolution and run naming |
| F05 | Mistral API pass | OCR call, raw JSON cache, replay mode |
| F06 | Normalize and stitch pages | Mistral response -> pages -> joined markdown |
| F07 | Notice and table parsing | Markdown -> notices/tables/corrigenda placeholders |
| F08 | Confidence and spatial hints | Scores plus optional coordinate summaries |
| F09 | Build validated envelope | End-of-pipeline Pydantic validation |
| F10 | Public API and bundle writer | `parse_*`, `write_envelope`, artifact bundles |
| F11 | JSON Schema export | Runtime and checked-in schema validation |
| F12 | Installable smoke test | Fresh venv install and public API checks |
| F13 | Notebook cleanup | Notebook becomes a package driver |

## Quality Gates

Gate 0: one PDF source can run through mocked/replayed Mistral and write default bundles.

Gate 1: regression checks pass on selected cached Mistral response fixtures from `prototype_outputs`.

Gate 2: deterministic IDs across repeated parses of the same cached response.

Gate 3: package imports work after install.

Gate 4: envelope validates against JSON Schema.

Gate 5: fresh virtual environment install works as a proxy for Git install.

## Comparability Rule

The Mistral and Docling packages should be comparable at the API and bundle level:

- Both return validated envelopes.
- Both write envelope/notices/tables/index/trace bundles.
- Both support schema helpers.

They do not need identical internal provenance fields.

## Runtime Dependency Rule

Keep runtime dependencies small:

- Allowed: stdlib, `pydantic`, `jsonschema`.
- Optional dev extras: `pytest`, `jupyter`, `ipykernel`.
- Excluded at runtime: `docling`, `docling-core`, `openai`, Mistral SDK packages.

Mistral API calls should use stdlib HTTP unless a later feature explicitly changes this.
