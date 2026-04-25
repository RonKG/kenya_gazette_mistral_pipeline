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
from pathlib import Path

from gazette_mistral_pipeline import Bundles, GazetteConfig, parse_url, write_envelope

config = GazetteConfig(
    runtime={
        "replay_raw_json_path": Path("examples/tiny_replay.raw.json"),
        "output_dir": Path("examples/_example_outputs/stage"),
    }
)

env = parse_url("https://example.com/source.pdf", config=config)
written = write_envelope(
    env,
    "examples/_example_outputs/bundles",
    Bundles(notices=True, tables=True, document_index=True),
)
```

## Notebook Example

Use `examples/gazette_package_driver.ipynb` as the recommended notebook driver.
It imports package-root APIs and defaults to offline replay with the tiny
`examples/tiny_replay.raw.json` fixture, so it does not require `MISTRAL_API_KEY`,
network access, `.env`, live Mistral calls, or historical `prototype_outputs`.

Historical notebooks `examples/historical/gazette_etl_prototype.ipynb` and
`examples/historical/gazette_iteration_pipeline.ipynb` are prototype context only
and are not the current user entry point.

## Runtime Dependencies

Runtime dependencies are intentionally small:

```text
pydantic>=2.0
```

## License

Apache-2.0. See `LICENSE`.
