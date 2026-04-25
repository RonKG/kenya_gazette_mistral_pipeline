# Known Issues

## API Keys

Mistral API keys must not be stored in notebooks, docs, fixtures, or committed source files.

Use environment variables or runtime config.

## Live API Tests

Live Mistral API tests are opt-in only. Normal test runs must use mocked HTTP or cached Mistral response fixtures.

Reason:

- Live API calls are slower.
- They may incur cost.
- They may fail due to network, rate limits, or service changes.

## Mistral Response Shape

The package targets Mistral OCR response JSON. It should support common shapes seen in existing fixtures:

- A single object containing `pages`.
- A list of OCR blocks, each containing `pages`.
- Legacy page-list shapes used by earlier notebook exports.

Unsupported shapes should fail loudly with clear error messages.

## Spatial Metadata

Mistral JSON may include page dimensions and coordinates for images or tables. It may not include word-level coordinates.

The package should treat spatial data as optional hints, not as a required reading-order engine.

## Notebook Output Staleness

Notebook execution outputs can show old paths, old run names, or old stats until cells are rerun.

The package source and test results are the source of truth once package work begins.

## Existing Output Folders

`prototype_outputs` contains historical runs from different naming schemes:

- `gazette_YYYY-MM-DD_N`
- `ke-government-gazette-dated-...`
- `source`

Future package outputs should use a stable run name derived from the PDF source or manifest metadata.

## Markdown Parser Limits

The parser is markdown and regex based. It can miss or merge notices when OCR output is badly ordered or when notice headers are corrupted.

Confidence scores and trace bundles should make these cases visible.

## Local PDF Upload Path

For local PDFs, Mistral OCR may require an upload or file-reference step before OCR. This must be implemented explicitly in the Mistral API feature and covered by replay tests.

The package should not assume local PDFs can be passed exactly like document URLs unless the API supports that request shape.
