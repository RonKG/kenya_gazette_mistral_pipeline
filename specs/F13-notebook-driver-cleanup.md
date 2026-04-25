# F13 Spec: Notebook Driver Cleanup

## 1. Goal

Convert notebook usage into thin, offline-first examples over the package public API, with no duplicated pipeline implementation logic or checked-in secret-bearing content.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Add a thin notebook driver that imports and demonstrates the package public API; clean or replace notebook documentation so routine examples use `parse_url`, `parse_file`, `write_envelope`, `GazetteConfig`, and `Bundles`; add lightweight offline notebook hygiene checks |
| Notebook strategy | Preserve `gazette_etl_prototype.ipynb` as historical prototype context only if it is not the recommended user entry point; add a new thin example notebook, likely `examples/gazette_package_driver.ipynb`, and make README/docs point users to that driver. If the builder decides the root prototype notebook must remain the main entry point, rewrite it directly into the same thin-driver shape instead of carrying duplicated prototype code forward |
| Historical prototype handling | Do not depend on the historical prototype for tests. If retained, it should be clearly labeled historical/prototype and should have outputs cleared or tightly bounded. It must not contain hardcoded secrets or live API-key values |
| Public API used by notebook | Import from `gazette_mistral_pipeline`: `parse_url`, `parse_file`, `write_envelope`, `GazetteConfig`, `Bundles`, and optionally `get_envelope_schema` or `validate_envelope_json` for a small demonstration |
| Default execution mode | Replay/offline mode is the default. The notebook should create or reference a tiny replay fixture or documented user-provided replay JSON path, configure `GazetteConfig(runtime={"replay_raw_json_path": ..., "output_dir": ...})`, and avoid network access by default |
| Live Mistral mode | Live URL OCR may be shown only as an explicit, commented or clearly gated optional path using `runtime.allow_live_mistral=True`, an explicit `runtime.output_dir`, and API key resolution through the environment. The notebook must not read `.env`, include keys, or run live calls by default |
| Input examples | Use a PDF URL string for the primary example because URL replay is already supported. A local PDF example may be included only in replay mode and must clearly state that live local PDF upload remains unsupported until a later approved feature |
| Output examples | Demonstrate writing bundles with `write_envelope(env, out_dir, Bundles(...))` into a user-controlled output directory such as a temp/example output path. Do not write large historical outputs during normal tests |
| Notebook outputs | Checked-in notebooks must have outputs cleared or bounded to tiny demonstration output. Avoid stale absolute paths, large markdown blobs, large raw OCR JSON, full envelopes, or historical run output churn |
| Duplicated logic boundary | Notebooks must not define heavy pipeline functions already implemented in the package, including Mistral HTTP request functions, raw response normalization, markdown stitching, notice splitting, table extraction, confidence scoring, envelope assembly, schema generation, or bundle writing |
| Allowed notebook helper code | Small display helpers, path setup, environment checks, fixture path selection, and compact previews are allowed if they do not duplicate package pipeline behavior |
| Tests and validation | Add offline tests or a script that inspects notebooks structurally without executing live OCR. The validator should check imports/API usage, absence of hardcoded secrets and `.env` reads, output size limits, offline default config, and absence of duplicated heavy pipeline functions |
| README/docs update | Update `README.md` or a narrow docs page only if needed to point users from the stale prototype flow to the thin driver notebook and offline replay policy |
| Out of scope | Parser behavior changes, envelope schema changes, public API behavior changes, bundle writer behavior changes, install smoke behavior changes, live Mistral calls, runtime dependency additions, historical `prototype_outputs` regression expansion, commits, and marking `PROGRESS.md` complete during spec creation |
| Runtime dependencies | No new runtime dependency is expected. Notebook tooling such as Jupyter remains a dev/example concern only and must not be added as a runtime dependency unless this spec is revised with a clear justification |

Suggested implementation shape:

```text
examples/
  gazette_package_driver.ipynb
tests/
  test_notebook_examples.py
```

The exact notebook path may differ if the builder chooses to rewrite `gazette_etl_prototype.ipynb` directly, but the final repository should have one clearly recommended thin notebook driver over the package API.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F13 as the current `Next` item and records D1/D2 notebook debt |
| `docs/library-contract-v1.md` | Defines the public parse/write/schema API that notebooks should demonstrate rather than reimplement |
| `docs/library-roadmap-v1.md` | Places notebook examples in 1.0 scope after package API, schema, and install readiness |
| `docs/known-issues.md` | Requires no API keys in notebooks, opt-in live calls, and awareness that notebook outputs can become stale |
| `specs/SOP.md` | Requires spec-first work, scoped implementation, offline tests, pass/fail criteria, and no completion update before tests pass |
| `specs/F10-public-api-and-bundle-writer.md` | Defines `parse_*`, `write_envelope`, replay behavior, live opt-in, and bundle writing that notebooks should use |
| `specs/F11-json-schema-export.md` | Defines schema helper behavior that may be demonstrated without changing schema code |
| `specs/F12-installable-package-smoke-test.md` | Confirms installed package readiness, root imports, and offline replay smoke behavior that the notebook can mirror |
| `README.md` | Contains public install and API examples that may need a narrow notebook usage update |
| `gazette_etl_prototype.ipynb` | Current historical prototype with embedded pipeline code and stale/large outputs that F13 should retire from the recommended flow |
| `gazette_mistral_pipeline/__init__.py` | Defines package-root exports the notebook should import |
| `gazette_mistral_pipeline/public_api.py` | Defines replay/live parse behavior and the supported public driver surface |
| `gazette_mistral_pipeline/bundle_writer.py` | Defines deterministic bundle writing the notebook should demonstrate |
| `tests/test_public_api.py` | Provides offline replay usage patterns and network/API-key guards suitable for notebook validation |
| `tests/test_bundle_writer.py` | Provides deterministic write examples the notebook should align with |
| `tests/test_install_smoke.py` | Provides installed-package and offline smoke expectations the notebook should not undermine |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Thin notebook imports package API | Thin driver notebook JSON inspected as text/AST-lite cell source | Notebook imports `parse_url` or `parse_file`, `write_envelope`, `GazetteConfig`, and `Bundles` from `gazette_mistral_pipeline`; it does not import package internals for pipeline stages |
| TC2 | No duplicated heavy pipeline functions | Notebook source scanned for prototype function names and logic markers such as `ocr_pdf_url`, `run_mistral_ocr`, `load_mistral_blocks`, `pages_from_blocks`, `join_pages_to_markdown`, `markdown_to_envelope`, `NOTICE_SPLIT_RE`, or direct `urllib.request.Request` OCR code | Recommended notebook contains no duplicated OCR, normalization, stitching, parsing, table extraction, confidence, envelope assembly, schema generation, or bundle writer functions |
| TC3 | No secrets, `.env`, or hardcoded API-key content | Notebook source, metadata, and outputs inspected | No API key values, bearer tokens, `.env` reads, secret-looking literals, or checked-in key placeholders beyond safe environment variable names such as `MISTRAL_API_KEY`; live mode reads keys only through environment when explicitly enabled |
| TC4 | Offline replay is default | Notebook source inspected for its default config cells | Default path uses `GazetteConfig` with `runtime.replay_raw_json_path` and does not set `allow_live_mistral=True` unless in a commented or opt-in live cell; default run does not require `MISTRAL_API_KEY` |
| TC5 | Notebook outputs are cleared or bounded | Notebook JSON inspected for output counts and serialized output size | Cells have no outputs or only tiny demonstration outputs under a documented byte/line threshold; no full raw OCR JSON, full joined markdown, full envelope, huge tables, or stale absolute-path output is checked in |
| TC6 | Bundle writing demonstration stays package-level | Thin notebook source inspected | Example calls `write_envelope(...)` with `Bundles` or a bundle dict and writes to a controlled example/temp output path; it does not manually serialize envelope, joined markdown, raw OCR JSON, schema, notices, tables, index, or trace bundles |
| TC7 | README/docs point to the thin driver if needed | `README.md` or a narrow docs update reviewed | Public docs no longer direct users to the historical embedded-logic prototype as the main path; they describe replay/offline default behavior and explicit live mode boundaries without secrets |
| TC8 | Historical prototype is safe if retained | `gazette_etl_prototype.ipynb` inspected when retained | It is labeled historical or not referenced as the current example, contains no secrets, and either has outputs cleared/bounded or is replaced by the thin driver content |
| TC9 | Normal tests remain offline and lightweight | `python -m pytest tests/test_notebook_examples.py` and `python -m pytest` | Tests pass without API keys, network access, live Mistral calls, notebook execution, `.env`, or historical `prototype_outputs`; they use only stdlib JSON inspection and existing package/dev tooling |
| TC10 | Existing package behavior is unchanged | Existing F10-F12 tests run | `tests/test_public_api.py`, `tests/test_bundle_writer.py`, `tests/test_install_smoke.py`, and the full offline suite continue passing, with no parser, schema, writer, smoke, or runtime dependency changes |

Normal F13 tests must be offline. They should inspect notebook files as JSON and source text rather than executing live OCR. Do not require `MISTRAL_API_KEY`, do not read `.env`, do not call Mistral, and do not depend on historical `prototype_outputs`.

## 5. Integration Point

- Called by:
  - Developers and users who want a notebook-first example for the package.
  - README/docs examples that point to the recommended notebook driver.
  - Offline test suite notebook hygiene checks.

- Calls:
  - Package-root `parse_url`, `parse_file`, `write_envelope`, `GazetteConfig`, and `Bundles`.
  - Optional package-root `validate_envelope_json` or `get_envelope_schema` only for a small demonstration.
  - Stdlib-only notebook validation code in tests, such as `json` and `pathlib`.

- Side effects:
  - The notebook may write replay stage artifacts and bundles only under explicit example output directories when a user runs it.
  - Normal tests only read notebook JSON and source text.
  - F13 does not call Mistral, read `.env`, require `MISTRAL_API_KEY`, change parser behavior, change schema behavior, change install smoke behavior, add runtime dependencies, commit, or mark `PROGRESS.md` complete during spec creation.

- Model fields populated:
  - F13 defines no new model fields.
  - Any envelope shown by the notebook comes from existing public parse functions and remains governed by F09-F11 behavior.

- Quality gate contribution:
  - F13 should close D1 by removing duplicated active parser/pipeline logic from the recommended notebook path.
  - F13 should close or narrow D2 by clearing/bounding stale notebook outputs and documenting replay/offline defaults.
  - Gate 1 and Gate 2 may remain partial unless implementation deliberately adds broader cached-response regression fixtures, which is not required for notebook cleanup.
  - Gate 3, Gate 4, and Gate 5 should remain reached and must not regress.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Recommended notebook is thin | Review and tests confirm it imports package-root API names and contains no heavy duplicated OCR/parser/writer implementation |
| Notebook default is offline | Notebook config defaults to replay mode and does not require an API key, network, or live Mistral call |
| Live mode is explicit only | Any live OCR example is commented or gated with `allow_live_mistral=True`, explicit output dir, and environment-only API key access |
| Secrets boundary holds | Notebook source, metadata, and outputs contain no hardcoded API keys, bearer tokens, `.env` reads, or secret-bearing fixture data |
| Output churn is controlled | Checked-in notebook outputs are cleared or bounded and contain no huge/stale raw OCR, joined markdown, or envelope dumps |
| Historical prototype is not the main driver | If `gazette_etl_prototype.ipynb` is retained, docs label it historical or stop pointing to it as the primary example; otherwise it is rewritten into the thin-driver shape |
| Docs remain accurate | README or narrow docs update points users to replay/offline notebook usage and explicit live mode policy if notebook guidance changes |
| Runtime dependencies stay lightweight | Review confirms no runtime dependencies are added; any notebook tooling remains dev/example-only and existing |
| Existing package contracts remain unchanged | F10-F12 public API, bundle writer, schema export, and install smoke tests continue to pass |
| Offline test suite passes | `python -m pytest tests/test_notebook_examples.py`, `python -m pytest tests/test_public_api.py tests/test_bundle_writer.py tests/test_install_smoke.py`, and `python -m pytest` pass without API keys or network |

## 7. Definition Of Done

- [x] `specs/F13-notebook-driver-cleanup.md` is approved before implementation starts.
- [x] One clearly recommended thin notebook driver exists and demonstrates package-root parsing and bundle writing through `parse_url` or `parse_file`, `write_envelope`, `GazetteConfig`, and `Bundles`.
- [x] `gazette_etl_prototype.ipynb` is either rewritten into that thin-driver shape or preserved only as labeled historical prototype context outside the recommended user path.
- [x] Notebook default configuration is replay/offline and does not require `MISTRAL_API_KEY`, network access, `.env`, live Mistral calls, or historical `prototype_outputs`.
- [x] Any live OCR path is explicit, opt-in, environment-only for API keys, and not executed by normal tests.
- [x] Checked-in notebook outputs are cleared or bounded to tiny demonstration output with no huge/stale artifacts.
- [x] Notebook source contains no duplicated heavy pipeline functions for OCR, normalization, stitching, notice/table parsing, confidence scoring, envelope assembly, schema export, or bundle writing.
- [x] README or narrow docs are updated if needed to point users to the thin notebook and replay/offline policy.
- [x] Offline notebook validation tests or scripts cover imports/API usage, no duplicated heavy functions, no secrets, output bounds, offline defaults, and docs expectations.
- [x] Existing public API, bundle writer, schema export, install smoke, and full offline tests pass.
- [x] No runtime dependency is added unless this spec is revised with a clear justification.
- [x] F13 does not change parser behavior, schema behavior, smoke test behavior, live Mistral behavior, historical regression fixture scope, Git history, or `PROGRESS.md` completion status during spec creation.

## 8. Open Questions And Risks

Q1. Should F13 edit `gazette_etl_prototype.ipynb` directly, add a new examples notebook, or both?

Recommended answer: add a new thin driver notebook under `examples/` and preserve the existing root prototype only as historical context if it remains useful. This avoids rewriting a large exploratory artifact while giving users a clean current entry point. If having two notebooks is confusing, replace the root prototype with the thin driver and move any historical explanation into markdown prose.

Q2. Should the notebook execute a live Mistral call as part of the example?

Recommended answer: no by default. Keep replay/offline as the executable path. Include live URL OCR only as an explicit opt-in cell or commented snippet using `allow_live_mistral=True`, `runtime.output_dir`, and `MISTRAL_API_KEY` from the environment.

Q3. Should F13 add real regression coverage over historical `prototype_outputs`?

Recommended answer: no. Notebook cleanup can mention that Gate 1 and Gate 2 remain partial, but broader cached-response regression fixtures should be a separate approved feature because it changes test scope and maintenance cost.

Q4. Should notebook tests execute the notebook?

Recommended answer: no for F13 normal tests. Static JSON/source inspection is enough to enforce thin-driver, secret, output, and offline-default rules without requiring Jupyter execution, kernels, network, or API keys. Executed notebook smoke can be a later optional dev check if needed.

Q5. Should F13 add notebook dependencies?

Recommended answer: no runtime dependency. If `jupyter` or `ipykernel` is already present as a dev extra, the notebook can rely on that for humans. The automated checks should use stdlib JSON inspection so the package runtime dependency policy stays lightweight.

Q6. How small should checked-in notebook output be?

Recommended answer: prefer clearing all outputs. If a tiny demonstration output is kept, cap it with a test threshold and avoid absolute machine paths, full envelopes, full markdown, full raw OCR JSON, or historical run data.

Q7. What is the main implementation risk?

Recommended answer: retaining enough prototype code that the notebook keeps drifting from the package parser. The builder should make the recommended notebook call only package-root APIs and add tests that fail when heavy duplicate function names or direct OCR HTTP code reappear.

Q8. Are there unresolved questions that should block implementation?

Recommended answer: no. The recommended answers above are sufficient for implementation if approved.
