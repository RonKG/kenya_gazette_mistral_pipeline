# F17 Spec: Add Table Notice Provenance

## 1. Goal

Add parent-notice provenance to every extracted table so both nested notice tables and flattened table bundles remain tied to the gazette notice they came from, with `notice_no` as the most important downstream link.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Function or module | Primary: `gazette_mistral_pipeline.notice_parsing`; secondary validation/preservation point: `gazette_mistral_pipeline.envelope_builder`; serialization surface: `gazette_mistral_pipeline.bundle_writer` |
| Input source | F06 joined markdown parsed by `parse_joined_markdown(...)`, then F08 scored notices consumed by `build_envelope(...)` |
| Existing model allowance | `ExtractedTable` in `gazette_mistral_pipeline/models/notice.py` already allows extra fields and currently defines `headers`, `rows`, `records`, `raw_table_markdown`, `source`, and `column_count` |
| Required table context for parsed notices | Every table attached to a parsed `Notice` must include additive fields `notice_no` and `notice_id` copied from its parent notice. For the current parser, `notice_no` is a non-empty string from the matched gazette notice header. If a future parser emits a notice without a notice number, keep `notice_id` required and include `notice_no=None` rather than omitting the key |
| Secondary notice context | Include additive fields derived from parent notice provenance: `notice_page_span`, `notice_pages`, and `notice_stitched_from`. These are secondary context only; they must not become the primary table identity |
| Run context | Include `source_run_name` when available from `run_name` or `source_id` at parse time, or from `Envelope.source.run_name` during envelope build if missing. This field is optional and additive |
| Output shape | `ParsedMarkdownResult.tables`, each `Notice.tables`, `Envelope.tables`, and `<run>_tables.json` contain the same table data plus the parent-notice context fields |
| Preferred stamping route | Stamp tables in `parse_joined_markdown(...)` after computing `content_sha256`, `provenance`, and `notice_id`, but before constructing the final `Notice`. This ensures nested `notice.tables` and parser-level `ParsedMarkdownResult.tables` are enriched from the same table objects |
| Envelope builder route | Preserve enriched table fields when flattening F08 scored notices. Add a narrow defensive enrichment/check in `_flatten_scored_notice_tables(...)` only to backfill missing parent context from the notice if legacy parser output reaches the builder |
| Bundle writer behavior | No special writer logic beyond existing `table.model_dump(mode="json")`; once `Envelope.tables` has context, `<run>_tables.json` inherits it |
| Error handling | Preserve current parser behavior: non-string markdown raises `TypeError`, blank markdown returns an empty `ParsedMarkdownResult`, and count mismatches still fail in `build_envelope(...)` |
| Out of scope | Table-granular page localization, table identity redesign, OCR spatial joins, live Mistral calls, new runtime dependencies, notebook execution, and non-table provenance refactors |
| Runtime dependencies | No new runtime dependencies; use stdlib, existing Pydantic models, and existing package modules only |

Recommended additive table fields:

| Field | Type | Meaning |
|-------|------|---------|
| `notice_no` | `str | None` | Gazette notice number from the parent `Notice`; the primary downstream link for tables |
| `notice_id` | `str` | Deterministic parent notice id |
| `notice_page_span` | `tuple[int, int] | None` serialized as JSON array/null | Parent notice `provenance.page_span`; only set when deterministic |
| `notice_pages` | `list[int]` | Page indexes parsed from parent `provenance.stitched_from` entries like `page:12` |
| `notice_stitched_from` | `list[str]` | Parent notice `provenance.stitched_from` copied verbatim |
| `source_run_name` | `str | None` | Source/run name when available |

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F17 as the current `Next` item and states the problem: flattened table exports lose notice-level context |
| `docs/library-contract-v1.md` | Defines the notice contract, envelope shape, optional table bundle, source run metadata, and additive versioning expectations |
| `docs/library-roadmap-v1.md` | Keeps F17 within the lightweight package architecture and runtime dependency rule |
| `docs/data-quality-confidence-scoring.md` | States that tables should remain attached to the notice that contains them and that page/spatial hints are diagnostic |
| `docs/known-issues.md` | Reminds implementers that spatial metadata is optional and live Mistral tests must stay opt-in |
| `specs/SOP.md` | Requires spec-first implementation, canonical links, test matrix, integration point, pass/fail criteria, definition of done, and open risks |
| `specs/F07-notice-and-table-parsing.md` | Defines the parser stage that attaches markdown tables to notices |
| `specs/F09-build-validated-envelope.md` | Defines the envelope builder behavior that flattens notice-attached tables exactly once |
| `specs/F10-public-api-and-bundle-writer.md` | Defines bundle writing and the optional `<run>_tables.json` output |
| `specs/F11-json-schema-export.md` | Covers schema export; F17 changes the serialized envelope/table shape and should update schema expectations if needed |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Parser stamps one notice table | Joined markdown with one `GAZETTE NOTICE NO. 3000` and one markdown table | `result.notices[0].tables[0]` and `result.tables[0]` include `notice_no="3000"`, the parent `notice_id`, `notice_pages`, `notice_page_span`, `notice_stitched_from`, and `source_run_name` when `run_name` is supplied |
| TC2 | Multiple notices preserve correct parent context | Joined markdown with two notices, each with a table | Tables retain the correct parent `notice_no`/`notice_id` in notice order and table order; no table is attributed to the adjacent notice |
| TC3 | Multi-page notice uses page span as secondary context | Notice body crosses an F06 page boundary and contains a table | Table includes parent `notice_no` and `notice_id`; `notice_pages`/`notice_stitched_from` reflect all parent pages; no single page is used as the table identity |
| TC4 | Envelope flattening preserves provenance | Parsed/scored result with enriched notice tables passed to `build_envelope(...)` | `Envelope.tables` contains the enriched table objects once, preserving context fields and order from scored notices |
| TC5 | Tables bundle contains parent context | Replay or inline parsed envelope written with `Bundles(tables=True)` | `<run>_tables.json` entries include `notice_no` and `notice_id`; writer does not need custom table logic |
| TC6 | Blank markdown remains empty | `parse_joined_markdown("")` | Returns zero notices and zero tables without provenance-field errors |
| TC7 | Table extraction helper remains reusable | Direct `extract_markdown_tables(...)` call outside a notice | Extracted tables remain valid without parent context because they are not yet attached to a parsed notice |
| TC8 | Schema/validation accepts additive table fields | Envelope containing enriched tables is serialized and validated through existing schema/Pydantic helpers after schema update if required | Extra table fields survive `model_dump(mode="json")`; no strict-model failures occur |
| TC9 | Cached regression stays offline | Existing cached raw JSON fixture with table-bearing notices | Replay pipeline produces table bundle entries with notice context without live Mistral calls or API keys |

Normal F17 tests must be offline. Use inline joined-markdown fixtures, existing parser/envelope fixtures, temporary bundle directories, and cached raw JSON replay where useful. Do not require `MISTRAL_API_KEY`, call live Mistral, read `.env`, execute notebooks, or add runtime dependencies.

## 5. Integration Point

- Called by:
  - `parse_joined_markdown(...)` while constructing each `Notice`.
  - `score_parsed_notices(...)`, which deep-copies notices and should preserve `ExtractedTable` extra fields.
  - `build_envelope(...)`, which flattens tables from authoritative scored notices.
  - `write_envelope(...)`, which serializes `Envelope.tables` to `<run>_tables.json` when selected.

- Calls:
  - Existing table extraction via `extract_markdown_tables(raw_markdown)`.
  - Existing notice id construction via `_notice_id(...)`.
  - Existing parent provenance fields from `Notice.provenance`.
  - Existing `ExtractedTable.model_copy(...)` or equivalent Pydantic construction to add context fields without mutating unrelated caller-owned tables.

- Side effects:
  - Parser output table objects gain additive extra fields.
  - Envelope and tables bundle JSON shape gains additive table fields.
  - Notice ids, content hashes, notice counts, table counts, and raw/joined artifacts should not change.
  - Checked-in schema may need regeneration because `ExtractedTable` allows extra fields but the desired serialized examples/expectations should include the new additive keys.

- Model fields populated:
  - Existing `ExtractedTable` core fields remain unchanged.
  - Additive `ExtractedTable` extra fields: `notice_no`, `notice_id`, `notice_page_span`, `notice_pages`, `notice_stitched_from`, and optional `source_run_name`.
  - Existing `Notice.notice_id`, `Notice.notice_no`, `Notice.provenance`, `Notice.tables`, and `Notice.table_count` remain authoritative for parent context.

Preferred implementation shape:

```python
notice_id = _notice_id(...)
notice_tables = _with_parent_notice_context(
    extract_markdown_tables(raw_markdown),
    notice_id=notice_id,
    notice_no=header.notice_no,
    provenance=provenance,
    source_run_name=run_name or source_id,
)
notice = Notice(..., notice_id=notice_id, tables=list(notice_tables), ...)
tables.extend(notice_tables)
```

The exact helper name may change, but it should be small, deterministic, and covered by parser tests. If the builder adds a defensive path, it should not duplicate tables or overwrite already-correct parser context.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Nested notice tables carry parent notice links | `tests/test_notice_parsing.py` asserts `notice.tables[*].notice_no` and `notice.tables[*].notice_id` |
| Parser-level flattened tables match nested tables | Parser tests assert `ParsedMarkdownResult.tables` entries have the same context as their corresponding `Notice.tables` entries |
| Envelope-level flattened tables preserve context | `tests/test_envelope_builder.py` asserts `Envelope.tables` entries include the parent notice fields and are not duplicated |
| Tables bundle preserves context | `tests/test_bundle_writer.py` or focused public API test writes selected `tables` bundle and inspects JSON fields |
| Page context is secondary | Unit tests assert multi-page notices keep `notice_no`/`notice_id` as primary links and use `notice_pages`/`notice_stitched_from` only as secondary context |
| No table-granular page promises | Review confirms F17 does not infer exact table pages unless already cheap and deterministic from existing parent notice provenance |
| No live Mistral calls | Tests use inline fixtures, mocked paths, or cached replay only |
| Runtime dependency rule holds | Review confirms no new runtime dependencies |
| Existing counts and IDs remain stable | Regression tests confirm notice counts, table counts, notice ids, and content hashes do not change except for serialized table extras |
| Offline tests pass | Focused tests plus `python -m pytest` pass without API keys or network access |

## 7. Definition Of Done

- [ ] `specs/F17-add-table-notice-provenance.md` is approved before implementation starts.
- [ ] `parse_joined_markdown(...)` stamps parent notice context onto tables attached to parsed notices.
- [ ] `ParsedMarkdownResult.tables`, `Notice.tables`, `Envelope.tables`, and `<run>_tables.json` all expose `notice_no` and `notice_id` for parsed-notice tables.
- [ ] Secondary page/run fields are additive and optional where appropriate, with page context treated as diagnostic rather than table identity.
- [ ] Direct `extract_markdown_tables(...)` remains usable without parent notice context.
- [ ] Envelope flattening preserves enriched fields and does not duplicate tables.
- [ ] JSON Schema resource and schema tests are updated if the checked-in schema or schema metadata needs to reflect the additive fields.
- [ ] Focused parser, envelope, bundle, and offline regression tests cover the matrix above.
- [ ] No live Mistral calls, API-key reads, notebook execution, runtime dependency additions, or unrelated refactors are introduced.
- [ ] `PROGRESS.md` is updated only after implementation and tests pass; spec creation alone does not update it.

## 8. Open Questions And Risks

Q1. Should F17 stamp tables in the parser or only during envelope flattening?

Recommended answer: stamp in the parser. The parser already knows the parent notice number, provenance, run/source name, and can compute `notice_id` into a variable before `Notice` construction. Parser-stage stamping keeps `Notice.tables`, `ParsedMarkdownResult.tables`, `Envelope.tables`, and the tables bundle consistent. The envelope builder may defensively backfill missing context, but it should not be the only source of truth.

Q2. Should `notice_no` be required even though `Notice.notice_no` is optional in the model?

Recommended answer: yes for current parsed gazette notice tables. The current parser creates notices from numbered `GAZETTE NOTICE NO...` headers, so a table attached to a parsed notice should carry that notice number. If a future feature supports unnumbered inferred notices, include `notice_no=None` and keep `notice_id` as the required stable parent link.

Q3. Should F17 add table-level page numbers?

Recommended answer: no, not as a table identity. Tables can span PDF pages, and current markdown table extraction does not deterministically localize each table independently from the parent notice. Add parent notice page context (`notice_pages`, `notice_page_span`, `notice_stitched_from`) as secondary provenance only. Table-granular localization can be a later feature if Mistral coordinates or page-split markdown make it cheap and deterministic.

Q4. Should `source_run_name` be required?

Recommended answer: no. Include it when `run_name`, `source_id`, or `Envelope.source.run_name` is available, but keep it optional and additive. The primary links are `notice_no` for human/legal lookup and `notice_id` for deterministic package identity.

Q5. Does adding extra fields require a schema version change?

Recommended answer: likely yes if the checked-in JSON Schema or downstream contract examples are treated as the published envelope shape. Because `ExtractedTable` already allows extra fields, this should be an additive/minor schema update rather than a breaking output-format change.

Q6. Could stamping table context change notice ids or content hashes?

Recommended answer: it should not. F17 must not alter notice markdown, text, provenance spans, table extraction boundaries, notice counts, or table counts. Only serialized table objects gain additive context fields.

Q7. What is the main implementation risk?

Recommended answer: enriching only the flat `Envelope.tables` list would leave nested `Notice.tables` and `ParsedMarkdownResult.tables` without context, recreating the same problem for consumers that read notices instead of the table bundle. Parser-stage stamping plus builder preservation avoids that split.
