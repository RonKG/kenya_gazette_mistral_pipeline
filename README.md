# Gazette Mistral Pipeline

Lightweight Mistral OCR ETL for Kenya Gazette PDFs.

Target pipeline:

```text
PDF source -> Mistral OCR API -> raw OCR JSON -> joined markdown -> enhanced JSON envelope
```

## Status

This repository is an early lightweight package. It exposes replay-capable
public parse functions, deterministic bundle writing, and JSON Schema helpers;
remaining work is tracked in `PROGRESS.md`.

## Installation

Local editable development:

```shell
pip install -e ".[dev]"
```

Future Git install:

```shell
pip install "git+https://github.com/<owner>/gazette-mistral-pipeline.git"
```

Install smoke from a local checkout:

```shell
python scripts/install_smoke.py --repo-path . --mode local-path
```

The smoke runs from a temporary working directory outside the repository and
uses replay fixtures, so it does not require `MISTRAL_API_KEY` or live Mistral
network calls.

## Public API

```python
from gazette_mistral_pipeline import parse_file, parse_url, write_envelope

env = parse_url("https://example.com/source.pdf")
written = write_envelope(env, "prototype_outputs/example")
```

## Runtime Dependencies

Runtime dependencies are intentionally small:

```text
pydantic>=2.0
```

## License

Apache-2.0. See `LICENSE`.
