# F09 Spec: Build Validated Envelope

## 1. Goal

Assemble already-produced F04-F08 stage outputs into a deterministic, validated `Envelope` Pydantic model without wiring the public parse API or writing bundles.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Package-internal envelope assembly only: combine resolved source metadata, Mistral metadata, F06 document/page/markdown counts, F07 parsed notices/tables/corrigenda, and F08 scored notices/document confidence/layout info/warnings into one validated `Envelope` |
| Out of scope | Public `parse_file`, `parse_url`, or `parse_source` wiring; `write_envelope`; bundle writing; JSON Schema export or validation; live Mistral calls; notebook edits; `.env` reads; `PROGRESS.md` completion updates; commits |
| Primary module | Add `gazette_mistral_pipeline/envelope_builder.py` |
| Input source | `PdfSource` from F04, `MistralMetadata` from F05, F06 stats from `compute_stats(...)` or `StitchedMarkdownResult`, `ParsedMarkdownResult` from F07, and `ScoredParsingResult` from F08 |
| Output shape | A validated `gazette_mistral_pipeline.models.envelope.Envelope` instance |
| Version fields | Populate `library_version` from `gazette_mistral_pipeline.__version__.LIBRARY_VERSION`, `schema_version` from `gazette_mistral_pipeline.__version__.SCHEMA_VERSION`, and `output_format_version` from a local builder constant such as `OUTPUT_FORMAT_VERSION = 1` |
| Generated timestamp | Populate `generated_at_utc` with current UTC by default. Tests must be deterministic by passing an injectable `now` parameter as either a timezone-aware `datetime` or a zero-argument clock callable returning one. Caller-supplied datetimes must be timezone-aware and normalized to UTC; naive datetimes should fail clearly |
| Stats assembly | Build `Stats` from F06 `document_count`, `page_count`, `char_count_markdown`, actual scored notice count, actual flattened table count, and `len(warnings)` |
| Count consistency | `Stats.notice_count`, `Stats.table_count`, and `Stats.warnings_count` must equal the actual envelope list lengths. If F07 `notice_count` or `table_count` disagrees with the actual parsed/scored lists, raise `ValueError` with the mismatched count name. If `MistralMetadata.page_count` differs from F06 normalized `page_count`, keep F06 as the envelope stat and either preserve an existing warning or add a bounded F09 warning only if implementation can do so without hiding the mismatch |
| Notices | Use F08 `scored_notices` as the authoritative envelope `notices` because they contain final confidence scores and reasons. Preserve notice order exactly |
| Tables | Flatten tables from the authoritative scored notices in notice order and table order. Do not concatenate `ParsedMarkdownResult.tables` with notice-attached tables, because that duplicates tables. Use `ParsedMarkdownResult.tables` only for consistency checks |
| Corrigenda | Use F07 `ParsedMarkdownResult.corrigenda` unchanged and preserve order |
| Confidence and layout | Use F08 `document_confidence` and `layout_info` unchanged except for normal Pydantic validation during final envelope construction |
| Warnings | Use F08 warnings as the base warning list and preserve order. If F09 adds any assembly warning, append it after F08 warnings and compute `warnings_count` after the final list is known |
| Validation | Validate the final shape by constructing or `model_validate`-ing `Envelope`. Bad Pydantic field shapes, invalid version fields, invalid generated time, or unsupported input types must fail clearly rather than returning a partial envelope |
| Runtime dependencies | No new runtime dependencies. Use stdlib, existing Pydantic models, and existing package modules only |

Suggested package-internal input shape and helper:

```python
@dataclass(frozen=True)
class EnvelopeBuildInputs:
    source: PdfSource | Mapping[str, Any]
    mistral: MistralMetadata | Mapping[str, Any]
    f06_stats: Mapping[str, int] | StitchedMarkdownResult
    parsed: ParsedMarkdownResult
    scored: ScoredParsingResult


def build_envelope(
    inputs: EnvelopeBuildInputs,
    *,
    now: datetime | Callable[[], datetime] | None = None,
) -> Envelope: ...
```

Helper names may change if tests document the package-internal contract, but F10 should be able to call one clear `build_envelope(...)` helper.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F09 as the current `Next` item and defines the work as assembling parsed notices, confidence scores, layout hints, warnings, and counts into the validated envelope |
| `docs/library-contract-v1.md` | Defines the pipeline contract, target envelope fields, source metadata, Mistral metadata, notice contract, and bundle boundary |
| `docs/library-roadmap-v1.md` | Places F09 after confidence/spatial hints and before public API/bundle writing and JSON Schema validation |
| `docs/data-quality-confidence-scoring.md` | Defines document confidence, warning counts, layout hint expectations, and regression signals that F09 must carry through unchanged |
| `docs/known-issues.md` | Requires no API key leakage, no live tests, honest optional spatial metadata, and clear failures for unsupported shapes |
| `specs/SOP.md` | Requires spec-first implementation, test matrix, integration point, pass/fail criteria, and no completion update before implementation and tests pass |
| `specs/F04-pdf-source-loading.md` | Defines the `PdfSource` model that F09 stores under `Envelope.source` |
| `specs/F05-mistral-api-pass.md` | Defines the `MistralMetadata` model that F09 stores under `Envelope.mistral` |
| `specs/F06-normalize-and-stitch-pages.md` | Defines F06 stats feeding `Stats.document_count`, `Stats.page_count`, and `Stats.char_count_markdown` |
| `specs/F07-notice-and-table-parsing.md` | Defines `ParsedMarkdownResult`, parsed notices, flattened parser tables, corrigenda, and parser counts that F09 checks |
| `specs/F08-confidence-and-spatial-hints.md` | Defines `ScoredParsingResult`, authoritative scored notices, document confidence, layout info, and warnings consumed by F09 |
| `gazette_mistral_pipeline/models/envelope.py` | Defines `Envelope`, `Stats`, `DocumentConfidence`, `LayoutInfo`, and `PipelineWarning` |
| `gazette_mistral_pipeline/models/notice.py` | Defines `Notice`, `ExtractedTable`, `Corrigendum`, and confidence/provenance fields included in the envelope |
| `gazette_mistral_pipeline/models/source.py` | Defines `PdfSource` and `MistralMetadata` fields included in the envelope |
| `gazette_mistral_pipeline/__version__.py` | Provides canonical `LIBRARY_VERSION` and `SCHEMA_VERSION` constants |
| `gazette_etl_prototype.ipynb` | Shows the prototype `markdown_to_envelope(...)` behavior, especially the transition from joined markdown to envelope stats, but F09 must replace it with validated package models |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Valid envelope happy path | Inline `PdfSource`, `MistralMetadata`, F06 stats for one document/page, F07 parsed result with one notice/table/corrigendum, F08 scored result, and fixed UTC `now` | Returns `Envelope`; version fields match constants; source/mistral are populated; stats counts match actual lists; notice/table/corrigendum order is preserved; `Envelope.model_dump(mode="json")` succeeds |
| TC2 | Degraded parse carries warnings and low confidence | F08 scored result with low document confidence, low-scored notices, unavailable layout info, and one or more `PipelineWarning` objects | Envelope remains valid; warnings are preserved in order; `stats.warnings_count == len(envelope.warnings)`; document confidence reasons are unchanged |
| TC3 | Missing optional metadata remains valid | `PdfSource.source_sha256=None`, `PdfSource.source_metadata_path=None`, `MistralMetadata.raw_json_path=None`, `raw_json_sha256=None`, `document_url=None`, empty doc ids, and unavailable layout info | Envelope validates because optional fields remain optional; required version, source type/value/run name, model, stats, notices, confidence, layout, and warnings are still populated |
| TC4 | Deterministic generated time and ordering | Same inputs and same fixed timezone-aware UTC datetime passed twice | Two envelopes have identical `model_dump(mode="json")`; notice order, flattened table order, corrigenda order, warning order, and generated timestamp are stable |
| TC5 | Default generated time is current UTC | Build without passing a timestamp, with test bounds captured immediately before and after calling `build_envelope(...)` | `generated_at_utc` is timezone-aware UTC and falls within the captured bounds; no other input-dependent ordering changes |
| TC6 | Naive generated time fails clearly | Valid inputs plus `now=datetime(2026, 4, 25, 12, 0, 0)` without timezone | Raises `ValueError` or a narrow custom validation error naming `generated_at_utc` or `now` and timezone/UTC |
| TC7 | Notice count mismatch fails | `ParsedMarkdownResult.notice_count` or equivalent test double count differs from `len(parsed.notices)` or `len(scored.scored_notices)` | Raises `ValueError` naming `notice_count`; no partial `Envelope` is returned |
| TC8 | Table count mismatch fails | Parser flattened table count differs from the tables attached to scored notices, or a notice `table_count` differs from `len(notice.tables)` | Raises `ValueError` naming `table_count` or the offending notice id; no duplicated table list is produced |
| TC9 | Tables are flattened once | Parsed result exposes `parsed.tables` and scored notices also contain the same table objects | Envelope `tables` contains the notice-attached tables exactly once in notice/table order; it does not concatenate both sources |
| TC10 | Warning count is always actual list length | F08 result contains two warnings and F09 appends no additional warnings, or appends one bounded assembly warning if implementing page-count mismatch warning | `stats.warnings_count` equals the final `len(envelope.warnings)` in both cases |
| TC11 | Pydantic validation catches bad input shape | Pass a source or mistral mapping missing required fields, a notice mapping with an invalid confidence band through a focused validation helper, or deliberately construct invalid envelope payload in the builder path | Test asserts a clear `ValidationError` or builder `ValueError`; strict extra fields remain rejected by the relevant Pydantic models |
| TC12 | Public API and side-effect boundary remain unchanged | Import package root and call `parse_file`, `parse_url`, and `parse_source`; inspect temporary output directory after F09 tests | Public parse functions still raise the existing F10 stub errors; no raw JSON, joined markdown, envelope JSON, bundles, schemas, notebooks, `.env`, network calls, or `PROGRESS.md` updates are produced |

Normal F09 tests must be offline. Use inline fixtures, existing F04-F08 helper outputs, and small Pydantic model fixtures. Do not read `.env`, require `MISTRAL_API_KEY`, call live Mistral, execute or edit notebooks, depend on full historical `prototype_outputs`, write final bundles, export JSON Schema, update `PROGRESS.md`, or commit.

## 5. Integration Point

Called by later features:

- F10 public `parse_file`, `parse_url`, and `parse_source` will call `build_envelope(...)` after F04 source resolution, F05 OCR/replay metadata, F06 normalization/stitching, F07 parsing, and F08 scoring/layout summarization.
- F10 `write_envelope(...)` will serialize the validated `Envelope` returned by F09 and write selected bundles.
- F11 will export and validate JSON Schema for the F09-assembled envelope shape.

Calls:

- `PdfSource.model_validate(...)` and `MistralMetadata.model_validate(...)` when mappings are accepted as convenience inputs.
- `Stats`, `Envelope`, and other existing Pydantic models from `gazette_mistral_pipeline.models`.
- `ParsedMarkdownResult` from `gazette_mistral_pipeline.notice_parsing`.
- `ScoredParsingResult` from `gazette_mistral_pipeline.confidence_scoring`.
- `StitchedMarkdownResult` or F06 stats mapping from `gazette_mistral_pipeline.page_normalization`.
- `datetime.now(timezone.utc)` only when no deterministic timestamp is supplied.

Side effects:

- `build_envelope(...)` is pure except for reading the current UTC clock when no timestamp is supplied.
- F09 does not read files, write files, read environment variables, call Mistral, access the network, execute notebooks, edit notebooks, export schemas, update `PROGRESS.md`, or commit.

Model fields populated:

- `Envelope.library_version`
- `Envelope.schema_version`
- `Envelope.output_format_version`
- `Envelope.generated_at_utc`
- `Envelope.source`
- `Envelope.mistral`
- `Envelope.stats`
- `Envelope.notices`
- `Envelope.tables`
- `Envelope.corrigenda`
- `Envelope.document_confidence`
- `Envelope.layout_info`
- `Envelope.warnings`

Quality gate contribution:

- F09 should move the project toward Gate 4 by validating the assembled object as a Pydantic `Envelope`.
- Gate 4 is not fully reached in F09 because JSON Schema export and JSON Schema validation are explicitly F11 scope.
- After F09 implementation, `PROGRESS.md` may record Gate 4 as partial only if tests prove Pydantic envelope validation passes; it must not be marked fully reached until F11.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Builder module imports cleanly | `python -m pytest tests/test_envelope_builder.py` imports `gazette_mistral_pipeline.envelope_builder` without importing notebooks |
| Envelope validates | Tests assert `build_envelope(...)` returns an `Envelope` and `model_dump(mode="json")` succeeds for happy-path, degraded, and missing-optional-metadata fixtures |
| Version fields are canonical | Tests assert `library_version == LIBRARY_VERSION`, `schema_version == SCHEMA_VERSION`, and `output_format_version == 1` |
| Timestamp is deterministic-testable | Tests pass a fixed timezone-aware UTC datetime and compare repeated `model_dump(mode="json")` output |
| Default timestamp is UTC | Unit test verifies default `generated_at_utc` is timezone-aware UTC and falls between captured UTC bounds |
| Counts are trustworthy | Unit tests assert `Stats` counts match actual envelope list lengths and count mismatches raise clear errors |
| Tables are not duplicated | Unit test verifies envelope tables are flattened from scored notices once and preserve order |
| Warnings are consistent | Unit tests assert warning order is preserved and `stats.warnings_count == len(envelope.warnings)` |
| Validation catches bad shapes | Unit tests cover invalid source/mistral mappings, invalid generated time, invalid counts, or deliberately invalid envelope payloads |
| Scope is respected | Review confirms no public `parse_*` wiring, bundle writing, JSON Schema export/validation, live Mistral calls, `.env` reads, notebook edits, `PROGRESS.md` completion update, dependency changes, or commits |
| Offline tests pass | `python -m pytest tests/test_envelope_builder.py` and `python -m pytest` pass without API keys, network access, live Mistral calls, notebook execution, or historical output folders |

## 7. Definition Of Done

- [x] `gazette_mistral_pipeline/envelope_builder.py` exists with a narrow package-internal `build_envelope(...)` helper and any necessary frozen dataclass/input shape.
- [x] `build_envelope(...)` assembles a validated `Envelope` from F04-F08 outputs and returns the Pydantic model instance.
- [x] `library_version`, `schema_version`, `output_format_version`, and deterministic-testable `generated_at_utc` are populated correctly.
- [x] `Stats` combines F06 document/page/markdown counts with actual notice/table/warning counts and fails clearly on inconsistent parser/scorer counts.
- [x] Notices use F08 scored notices as authoritative, preserving order and final confidence details.
- [x] Tables are flattened exactly once from scored notices, preserving order and avoiding duplicate concatenation with `ParsedMarkdownResult.tables`.
- [x] Corrigenda, document confidence, layout info, and warnings are carried through from F07/F08 and validate in the final envelope.
- [x] Unit tests cover at least the matrix above using offline inline fixtures and existing helper outputs.
- [x] Existing F04-F08 tests still pass.
- [x] F09 does not implement public `parse_*` wiring, `write_envelope`, output bundle writing, JSON Schema export/validation, live Mistral calls, notebook edits, dependency changes, or commits. `PROGRESS.md` was updated only after tests passed.

## 8. Open Questions And Risks

Q1. Should mismatched parser/scorer counts become warnings or hard failures?

Recommended answer: hard failures for internal count mismatches. F09 is assembling typed package stage outputs; mismatched notice/table counts indicate programmer error or contract drift and should not produce a misleading validated envelope.

Q2. Should envelope tables come from `ParsedMarkdownResult.tables` or from scored notices?

Recommended answer: flatten from F08 scored notices. They are the authoritative final notices after scoring. Use `ParsedMarkdownResult.tables` only as a consistency check so F09 does not duplicate tables by merging both sources.

Q3. How should `generated_at_utc` handle naive datetimes?

Recommended answer: reject naive datetimes with a clear error and normalize timezone-aware inputs to UTC. This keeps serialized envelopes deterministic and avoids hidden local-time assumptions in tests and downstream loaders.

Q4. Should F09 add warnings for `MistralMetadata.page_count` differing from F06 normalized `page_count`?

Recommended answer: only if the implementation can keep it bounded and explicit. F06 `page_count` should remain the envelope stat because it counts normalized non-empty markdown pages. Raw Mistral page count can differ when blank pages are skipped, so a warning is useful but should not block valid envelopes unless required fields are missing.

Q5. Does F09 complete Quality Gate 4?

Recommended answer: no. F09 provides Pydantic `Envelope` validation and should count as partial progress toward Gate 4. Full Gate 4 requires JSON Schema export and JSON Schema validation in F11.

Q6. Should F09 expose `build_envelope(...)` from the package root?

Recommended answer: no. Keep it package-internal for F09. F10 can decide public root exports when it wires `parse_file`, `parse_url`, `parse_source`, and `write_envelope`.

Q7. What is the main implementation risk?

Recommended answer: silently reconciling inconsistent stage outputs. The builder should preserve order, compute actual counts from final lists, and raise clear errors when F06-F08 result contracts disagree rather than hiding drift inside a valid-looking envelope.
