# Gazette Mistral Pipeline Contract v1

## Purpose

This document defines the target public contract for the lightweight Mistral-only gazette ETL package.

The package processes:

```text
PDF source -> Mistral OCR API -> raw OCR JSON -> joined markdown -> enhanced JSON envelope
```

It is designed to be swappable with the Docling-based package in an external ETL process, while keeping source-specific fields honest.

## Scope

In scope for version 1.0:

- Accept a PDF URL or local PDF file.
- Call the Mistral OCR API.
- Cache the raw Mistral OCR JSON response.
- Stitch page markdown into a joined markdown artifact.
- Parse joined markdown into notices, tables, dates, warnings, confidence scores, and optional spatial hints.
- Return a validated Pydantic envelope.
- Write output bundles.
- Export and validate JSON Schema.
- Install directly from Git.

Out of scope for version 1.0:

- Docling PDF processing.
- Mistral SDK dependency.
- PyPI publishing.
- CLI.
- Guaranteed word-level spatial reconstruction.
- LLM repair or semantic validation.

## Public API

The package root should expose:

```python
from gazette_mistral_pipeline import (
    parse_file,
    parse_url,
    parse_source,
    write_envelope,
    get_envelope_schema,
    validate_envelope_json,
    Envelope,
    Bundles,
)
```

Target signatures:

```python
def parse_file(path: str | Path, *, config: GazetteConfig | None = None) -> Envelope:
    """Send a local PDF file through Mistral and return a validated envelope."""

def parse_url(url: str, *, config: GazetteConfig | None = None) -> Envelope:
    """Send a PDF URL through Mistral and return a validated envelope."""

def parse_source(source: PdfSource | str | Path, *, config: GazetteConfig | None = None) -> Envelope:
    """Resolve a PDF source, call Mistral, and return a validated envelope."""

def write_envelope(env: Envelope, out_dir: str | Path, bundles: Bundles | dict | None = None) -> dict[str, Path]:
    """Write selected output artifacts and return their paths."""
```

## Input Contract

The canonical input is one PDF source:

- PDF URL, usually a Kenyalaw `source.pdf` URL.
- Local PDF path.
- Manifest/config JSON listing one or more PDF sources for batch use.

The API key must come from environment or runtime config. It must not be embedded in checked-in notebooks, fixtures, or source metadata.

## Pipeline Contract

Each source is processed as:

1. Resolve PDF source and derive `run_name`.
2. Build a Mistral OCR request.
3. Call Mistral OCR.
4. Cache the raw response as `<run>.raw.json`.
5. Normalize response pages.
6. Stitch page markdown as `<run>_joined.md`, removing recognizable page running headers/footers at page boundaries.
7. Parse markdown into notices and tables.
8. Add confidence scores, warnings, and optional spatial hints.
9. Validate a Pydantic `Envelope`.
10. Optionally validate the serialized envelope against JSON Schema.
11. Write selected bundles.

## Envelope Shape

The v1 envelope should include:

- `library_version`
- `schema_version`
- `output_format_version`
- `generated_at_utc`
- `source`
- `mistral`
- `stats`
- `notices`
- `tables`
- `document_confidence`
- `layout_info`
- `warnings`

The envelope is Mistral-specific. It should not pretend to contain Docling fields such as Docling document dictionaries or Docling layout provenance.

## Source Metadata

`source` should include:

- `source_type`: `pdf_url` or `local_pdf`
- `source_value`: URL or path string
- `run_name`
- `source_sha256`: local file hash when available, otherwise stable hash of source string
- `source_metadata_path`: optional output path for `<run>_source.json`

## Mistral Metadata

`mistral` should include:

- `model`
- `document_url` when applicable
- `raw_json_path`
- `raw_json_sha256`
- `mistral_doc_ids`
- `page_count`
- `request_options`

## Notice Contract

Each notice should include:

- `notice_id`
- `notice_no`
- `dates_found`
- `raw_markdown`
- `text`
- `tables`
- `table_count`
- `confidence_scores`
- `confidence_reasons`
- `provenance`

`notice_id` must be deterministic for the same source and same Mistral response.

## Bundle Contract

Default bundles should be fast and useful:

- `envelope`: `<run>_envelope.json`
- `joined_markdown`: `<run>_joined.md` after page normalization and boundary running-header cleanup
- `raw_mistral_json`: `<run>.raw.json`
- `source_metadata`: `<run>_source.json`

Optional bundles:

- `notices`: `<run>_notices.json`
- `tables`: `<run>_tables.json`
- `document_index`: `<run>_index.json`
- `debug_trace`: `<run>_trace.json`
- `schema`: `<run>_schema.json` or package schema file

## Interchangeability With Docling Package

An external ETL runner should be able to choose an engine with minimal branching:

```python
if engine == "mistral":
    from gazette_mistral_pipeline import parse_file, write_envelope
else:
    from kenya_gazette_parser import parse_file, write_envelope
```

The envelopes should be close, but not identical. Source-specific metadata belongs under source/provenance objects.

## Versioning

- `library_version` tracks package code.
- `schema_version` tracks envelope shape.
- `output_format_version` is an integer for downstream compatibility checks.

Breaking envelope changes require a major schema version bump. Additive optional fields can use a minor schema version bump.
