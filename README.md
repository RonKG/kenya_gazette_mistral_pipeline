# Gazette Mistral Pipeline

Lightweight Mistral OCR ETL for Kenya Gazette PDFs.

Target pipeline:

```text
PDF source -> Mistral OCR API -> raw OCR JSON -> joined markdown -> enhanced JSON envelope
```

## Status

This repository is in early package scaffolding. F02 provides an installable
package shell and public API stubs. The real Mistral API pass, parsing, models,
schema validation, and bundle writing land in later features tracked in
`PROGRESS.md`.

## Installation

Local editable development:

```shell
pip install -e ".[dev]"
```

Future Git install:

```shell
pip install "git+https://github.com/<owner>/gazette-mistral-pipeline.git"
```

## Planned API

```python
from gazette_mistral_pipeline import parse_file, parse_url, write_envelope

env = parse_url("https://example.com/source.pdf")
written = write_envelope(env, "prototype_outputs/example")
```

In F02 these functions intentionally raise `NotImplementedError`.

## Runtime Dependencies

F02 has no runtime dependencies. Later features will add only the small
dependencies needed for validated envelopes and schema checks.

## License

Apache-2.0. See `LICENSE`.
