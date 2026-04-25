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

from gazette_mistral_pipeline import Bundles, GazetteConfig, parse_file, parse_url, write_envelope

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

The raw Mistral JSON remains the audit artifact. The joined markdown bundle is
the normalized parsing artifact and strips recognizable Kenya Gazette running
headers/footers at page boundaries before notice parsing.

Live Mistral runs are opt-in and require an explicit output directory:

```python
from pathlib import Path

from gazette_mistral_pipeline import GazetteConfig, parse_file, parse_url

live_config = GazetteConfig(
    runtime={
        "allow_live_mistral": True,
        "output_dir": Path("examples/_live_outputs/stage"),
    }
)

# Public remote PDF: sent to Mistral as document_url.
url_env = parse_url("https://example.com/source.pdf", config=live_config)

# Local or network PDF path: uploaded to Mistral Files first, then OCR'd by file_id.
file_env = parse_file(Path(r"C:\path\to\Kenya Gazette.pdf"), config=live_config)
```

## Notebook Example

Use `examples/gazette_package_driver.ipynb` as the recommended notebook driver.
It imports package-root APIs, runs a live public PDF URL smoke test when
`MISTRAL_API_KEY` is present, and includes an optional `parse_file(...)` local
PDF example. The notebook keeps generated live outputs under ignored example
output folders. Offline replay remains supported through
`runtime.replay_raw_json_path` for tests and deterministic local runs.

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
