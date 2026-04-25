# F11 Spec: JSON Schema Export

## 1. Goal

Implement package-root JSON Schema export and envelope JSON validation helpers, and materialize a checked-in deterministic `Envelope` schema that the bundle writer can include in output bundles.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Replace the F10/F02 stubs for `get_envelope_schema` and `validate_envelope_json`; add a checked-in schema file for the Pydantic `Envelope`; wire `Bundles(schema=True)` / `Bundles(json_schema=True)` in `write_envelope`; add focused offline tests |
| Out of scope | Parse orchestration changes, parser/scoring changes, envelope field shape changes except schema metadata if needed, non-schema bundle behavior, Mistral OCR behavior, live Mistral calls, notebooks, CLI, install smoke testing beyond package-data assertions, `.env` reads, `PROGRESS.md` completion updates during spec creation, and commits |
| Public schema helper | `get_envelope_schema(*, use_cache: bool = True) -> dict[str, Any]` returns a JSON Schema dictionary for `gazette_mistral_pipeline.models.Envelope` |
| Cached schema behavior | With `use_cache=True`, load the checked-in package schema from `gazette_mistral_pipeline/schemas/envelope.schema.json` through `importlib.resources`; do not regenerate or write files |
| Generated schema behavior | With `use_cache=False`, generate the schema from `Envelope.model_json_schema()` and apply the same deterministic metadata normalization used for the checked-in schema; do not write files |
| Schema file path | Add `gazette_mistral_pipeline/schemas/envelope.schema.json` as package data. Update package-data configuration, currently only `py.typed`, so the schema is included after editable or wheel installs |
| Schema contents | Base the schema on Pydantic v2 APIs such as `Envelope.model_json_schema()`. Add stable top-level metadata if needed, including `$schema`, `title`, `x-library-version`, `x-schema-version`, and `x-output-format-version`; do not include timestamps, local paths, machine-specific values, or generated ordering noise |
| Deterministic serialization | The checked-in schema file must be UTF-8 JSON written with sorted keys, two-space indentation, `ensure_ascii=False`, `allow_nan=False`, and exactly one trailing newline |
| Public validation helper | `validate_envelope_json(data: Envelope | Mapping[str, Any] | str | bytes | bytearray | Path) -> Envelope` validates input against the `Envelope` Pydantic model and returns a validated `Envelope` on success |
| Validation input behavior | `Envelope` inputs return an `Envelope` without lossy reserialization; mappings use `Envelope.model_validate(...)`; JSON strings and bytes use Pydantic JSON validation; `Path` inputs read UTF-8 JSON bytes and validate them. Plain string file paths are not path inputs, to avoid ambiguity with JSON strings |
| Validation error behavior | Invalid JSON text, unsupported input types, missing files, unreadable files, or envelope shape errors fail clearly with `ValueError`, `TypeError`, `FileNotFoundError`, or Pydantic `ValidationError`; the helper must not return partially validated data |
| JSON Schema validator dependency | Do not add `jsonschema` as a runtime dependency for F11. Runtime validation is Pydantic validation against the same `Envelope` model that generates the schema. Independent JSON Schema self-validation is out of normal runtime scope unless a later approved spec adds a dependency |
| Bundle writer schema behavior | `write_envelope(env, out_dir, Bundles(schema=True))` or an equivalent dict copies the checked-in schema bytes to `<run>_schema.json` under `out_dir` and returns it under the path key `schema`; it does not generate a schema during bundle writing |
| Bundle writer existing behavior | Preserve all F10 non-schema bundle behavior, deterministic JSON bytes, same-path copy rules, missing artifact failures, and no envelope mutation |
| Runtime dependencies | No new runtime dependency is expected. Use stdlib, existing Pydantic APIs, existing package modules, and `importlib.resources` |

Suggested module layout:

```text
gazette_mistral_pipeline/
  __init__.py
  schema.py
  schemas/
    envelope.schema.json
tests/
  test_schema_export.py
```

Suggested helper shape:

```python
def get_envelope_schema(*, use_cache: bool = True) -> dict[str, Any]: ...


def validate_envelope_json(
    data: Envelope | Mapping[str, Any] | str | bytes | bytearray | Path,
) -> Envelope: ...
```

The implementation may keep thin root functions in `__init__.py` and delegate to `gazette_mistral_pipeline.schema`, or expose the helpers directly from a narrow schema module and import them at the package root.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F11 as the current `Next` item and records Gate 4 as waiting on JSON Schema export and validation |
| `docs/library-contract-v1.md` | Defines root public API exports, JSON Schema validation as part of the pipeline contract, envelope fields, and schema as an optional bundle |
| `docs/library-roadmap-v1.md` | Places F11 after public API/bundle writing and before install smoke testing, with JSON Schema export and validation required for 1.0 |
| `docs/data-quality-confidence-scoring.md` | Defines confidence, warning, and layout fields whose schema must remain visible and honest for downstream review workflows |
| `docs/known-issues.md` | Requires no secret leakage, no live tests by default, and clear validation failures for unsupported shapes |
| `specs/SOP.md` | Requires spec-first work, the standard spec sections, test matrix, pass/fail criteria, and no completion update before implementation and tests pass |
| `specs/F09-build-validated-envelope.md` | Defines the validated `Envelope` model instance that F11 serializes and validates at the schema boundary |
| `specs/F10-public-api-and-bundle-writer.md` | Leaves root schema helpers and schema bundle behavior explicitly deferred to F11 |
| `gazette_mistral_pipeline/__init__.py` | Contains the root `get_envelope_schema` and `validate_envelope_json` stubs F11 replaces |
| `gazette_mistral_pipeline/models/envelope.py` | Defines the canonical Pydantic `Envelope`, `Stats`, `DocumentConfidence`, `LayoutInfo`, and `PipelineWarning` schema source |
| `gazette_mistral_pipeline/models/notice.py` | Defines notice, table, confidence, provenance, and corrigendum shapes included in the schema |
| `gazette_mistral_pipeline/models/source.py` | Defines `PdfSource` and `MistralMetadata` shapes included in the schema |
| `gazette_mistral_pipeline/models/bundles.py` | Defines the existing `json_schema` flag and `schema` alias that F11 must wire in the bundle writer |
| `gazette_mistral_pipeline/models/config.py` | Confirms F11 does not need runtime config or secret-bearing settings |
| `gazette_mistral_pipeline/bundle_writer.py` | Contains F10 deterministic bundle writing and the F11 schema-bundle rejection path to replace |
| `pyproject.toml` | Must include the schema JSON under package data so F12 install smoke can verify schema resource availability |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Root schema helper loads checked-in schema | `get_envelope_schema()` | Returns a `dict` loaded from `gazette_mistral_pipeline/schemas/envelope.schema.json`; contains Envelope properties such as `source`, `mistral`, `stats`, `notices`, `document_confidence`, `layout_info`, `warnings`; metadata matches package constants |
| TC2 | Generated schema matches checked-in schema | `get_envelope_schema(use_cache=False)` and the checked-in schema resource | Generated schema dictionary equals the cached schema dictionary; serialized generated bytes exactly match the checked-in file bytes with sorted keys, two-space indent, UTF-8, and one trailing newline |
| TC3 | Validation happy path accepts supported shapes | A valid F10/F09 `Envelope`, its `model_dump(mode="json")` mapping, JSON string, JSON bytes, bytearray, and a `Path` to a temporary JSON file | `validate_envelope_json(...)` returns a valid `Envelope` for each supported shape; key fields such as `source.run_name`, `schema_version`, counts, notice IDs, and warning counts are preserved |
| TC4 | Validation errors fail clearly | Malformed JSON string, mapping missing required fields, mapping with forbidden extra fields on strict models, invalid confidence band, unsupported input object, and missing `Path` | Raises `ValueError`, `TypeError`, `FileNotFoundError`, or Pydantic `ValidationError` as appropriate; no partial envelope is returned |
| TC5 | Schema bundle writing copies checked-in schema | Envelope from F10 replay fixture, `write_envelope(env, out_dir, {"schema": True, "envelope": False, "joined_markdown": False, "raw_mistral_json": False, "source_metadata": False})` | Writes `<run>_schema.json`, returns `{"schema": <path>}`, and file bytes exactly equal the checked-in schema resource; no parse stages run and no other bundles are written |
| TC6 | Schema bundle composes with existing selected bundles | Same envelope with defaults plus `Bundles(schema=True)` or `Bundles(json_schema=True)` | Existing default bundles retain F10 filenames and deterministic bytes; schema path is added under key `schema`; repeated writes produce identical bytes |
| TC7 | Package-data configuration includes schema resource | Inspect `pyproject.toml` package-data entry or import the resource via `importlib.resources.files("gazette_mistral_pipeline").joinpath("schemas/envelope.schema.json")` | The schema file is present as package data alongside `py.typed`, and resource loading does not rely on current working directory paths |
| TC8 | Scope and side-effect boundary remain clean | Run focused schema/export tests with monkeypatched env/network failure guards and without opening notebooks | Tests pass offline; no `.env` read, no live Mistral call, no notebook edit/execution, no parse orchestration change, no non-schema bundle regression, and no `PROGRESS.md` completion update is required before build closure |

Normal F11 tests must be offline. Use inline fixtures, F09/F10 helper fixtures, temporary files, and monkeypatched network/env guards. Do not read `.env`, require `MISTRAL_API_KEY`, call live Mistral, execute or edit notebooks, depend on historical `prototype_outputs`, or add a runtime JSON Schema validator dependency.

## 5. Integration Point

- Called by:
  - External users importing `get_envelope_schema` and `validate_envelope_json` from `gazette_mistral_pipeline`.
  - `write_envelope(...)` when `Bundles(schema=True)` or `Bundles(json_schema=True)` is selected.
  - F12 install smoke tests verifying package data and root imports after installation.

- Calls:
  - `Envelope.model_json_schema()` for generated schema output.
  - `Envelope.model_validate(...)` and Pydantic JSON validation APIs for envelope validation.
  - `importlib.resources.files(...)` to load the checked-in package schema resource.
  - Existing `Bundles`, `Envelope`, and deterministic JSON helpers or equivalent stdlib serialization.

- Side effects:
  - `get_envelope_schema(use_cache=True)` reads the package schema resource only.
  - `get_envelope_schema(use_cache=False)` generates an in-memory schema only.
  - `validate_envelope_json(...)` may read only the explicit `Path` argument when one is supplied.
  - `write_envelope(...)` writes the selected schema bundle under `out_dir` when requested.
  - F11 does not call Mistral, read `.env`, execute notebooks, alter parse orchestration, mutate envelopes, update `PROGRESS.md` during spec creation, or commit.

- Model fields covered:
  - The schema must cover all current `Envelope` fields: `library_version`, `schema_version`, `output_format_version`, `generated_at_utc`, `source`, `mistral`, `stats`, `notices`, `tables`, `corrigenda`, `document_confidence`, `layout_info`, and `warnings`.
  - Nested schema definitions must cover source metadata, Mistral metadata, notice provenance, confidence scores, extracted tables, corrigenda, document confidence, layout info, and pipeline warnings.

- Quality gate contribution:
  - F11 completes Gate 4 for the package by exporting the envelope JSON Schema, checking in a deterministic schema resource, validating envelope JSON through the canonical Pydantic `Envelope` model, and wiring schema bundle output.
  - Independent validation through an external `jsonschema` runtime library is explicitly out of F11 scope because that dependency is not currently present.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Root schema helpers are real | Public API tests or `tests/test_schema_export.py` import `get_envelope_schema` and `validate_envelope_json` from package root and call them without F11 stub errors |
| Checked-in schema exists | `gazette_mistral_pipeline/schemas/envelope.schema.json` exists and is readable through `importlib.resources` |
| Schema generation is deterministic | Test compares generated schema bytes with the checked-in resource bytes using sorted keys, two-space indent, UTF-8, and one trailing newline |
| Schema metadata is stable | Test asserts schema metadata matches `LIBRARY_VERSION`, `SCHEMA_VERSION`, and F09 `OUTPUT_FORMAT_VERSION`, with no timestamp or local path metadata |
| Validation accepts supported shapes | Tests validate `Envelope`, mapping, JSON string, JSON bytes, bytearray, and `Path` inputs and assert a returned `Envelope` |
| Validation rejects bad shapes | Tests cover malformed JSON, missing required fields, forbidden extras on strict models, invalid nested values, unsupported input type, and missing file path |
| Schema bundle is wired | Bundle writer tests assert `schema=True` writes `<run>_schema.json`, returns key `schema`, and file bytes equal the checked-in schema resource |
| Existing F10 writer behavior remains intact | Existing `tests/test_bundle_writer.py` expectations for default and optional non-schema bundles still pass |
| Runtime dependencies stay lightweight | Review confirms no runtime dependency is added for schema generation or validation unless this spec is revised with justification |
| Scope is respected | Review confirms no parser changes, parse orchestration changes, live Mistral calls, `.env` reads, notebook edits, CLI work, install-smoke feature work, commits, or premature `PROGRESS.md` completion update |
| Offline tests pass | `python -m pytest tests/test_schema_export.py tests/test_public_api.py tests/test_bundle_writer.py` and `python -m pytest` pass without API keys, network access, live Mistral calls, notebook execution, or historical output folders |

## 7. Definition Of Done

- [x] `specs/F11-json-schema-export.md` is approved before implementation starts.
- [x] Root `get_envelope_schema` and `validate_envelope_json` no longer raise F11 stub errors.
- [x] `get_envelope_schema()` loads the checked-in package schema resource by default.
- [x] `get_envelope_schema(use_cache=False)` generates the same schema in memory from the `Envelope` Pydantic model.
- [x] `gazette_mistral_pipeline/schemas/envelope.schema.json` is checked in with deterministic sorted JSON bytes and one trailing newline.
- [x] Package-data configuration includes `schemas/*.json` so the schema resource is available after install.
- [x] `validate_envelope_json(...)` accepts the supported input shapes and returns a validated `Envelope`.
- [x] Invalid JSON, invalid envelope shape, unsupported input type, and missing path cases fail clearly.
- [x] `write_envelope(..., Bundles(schema=True))` writes/copies the checked-in schema to `<run>_schema.json` and returns it under key `schema`.
- [x] Existing non-schema bundle writer behavior remains unchanged.
- [x] No new runtime dependency is added unless this spec is revised with justification.
- [x] Unit tests cover at least the matrix above using offline fixtures and temporary files only.
- [x] Existing F09/F10 tests still pass.
- [x] F11 does not edit notebooks, read/use `.env`, run live Mistral calls, implement parser/parse orchestration changes, implement F12 install smoke work beyond package-data inclusion, commit changes, or mark `PROGRESS.md` complete before builder/tester closure.

## 8. Open Questions And Risks

Q1. Should `validate_envelope_json(...)` return `bool` because the F10 stub annotation returned `bool`, or return the validated `Envelope`?

Recommended answer: return the validated `Envelope`. The stub was explicitly deferred and not a shipped contract, and returning the model gives callers both validation and typed data. Failures should raise clear exceptions rather than returning `False`, which can hide why validation failed.

Q2. Should F11 add `jsonschema` as a runtime dependency to validate strictly against the exported JSON Schema?

Recommended answer: no. The current runtime dependency list contains only Pydantic, and the schema is generated from the same `Envelope` model. Use Pydantic validation at runtime and keep independent JSON Schema validator checks out of scope unless a later approved spec adds `jsonschema` with a clear reason.

Q3. Should schema bundle writing generate the schema on each call or copy the checked-in resource?

Recommended answer: copy the checked-in resource. Bundle writing should be deterministic, fast, and independent of Pydantic schema generation details at runtime. Freshness is enforced by tests comparing generated bytes to the checked-in schema.

Q4. Should plain `str` inputs to `validate_envelope_json(...)` be treated as JSON text or filesystem paths?

Recommended answer: treat plain strings only as JSON text. Accept `Path` for file inputs. This avoids ambiguous behavior when a JSON document string happens to resemble a path or a missing path could be misreported as malformed JSON.

Q5. What is the main implementation risk?

Recommended answer: schema drift. If the Pydantic `Envelope` shape changes but the checked-in schema is not regenerated, downstream bundle users get stale validation metadata. F11 should prevent that with an exact generated-bytes freshness test and deterministic serialization.

Q6. Are there any unresolved questions that should block implementation?

Recommended answer: no. The recommended answers above are sufficient for implementation if approved.
