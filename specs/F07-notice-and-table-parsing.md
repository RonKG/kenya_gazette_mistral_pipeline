# F07 Spec: Notice and Table Parsing

## 1. Goal

Parse F06 joined markdown into deterministic `Notice`, `ExtractedTable`, and `Corrigendum` model instances while preserving raw text, lightweight provenance, and neutral confidence placeholders for F08.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Joined-markdown parsing only: notice boundaries, notice numbers, title lines, date strings, markdown tables, corrigendum placeholders, deterministic content hashes, deterministic notice IDs, and parser-owned count context |
| Out of scope | Envelope assembly, document-level confidence scoring, real per-notice confidence scoring, spatial scoring, schema export, public `parse_*` wiring, final bundle writing, semantic corrigendum amendment resolution, notebook cleanup, and live Mistral calls |
| Primary module | Add package-internal helpers in a narrow module such as `gazette_mistral_pipeline/notice_parsing.py` |
| Input source | `str` joined markdown from `stitch_markdown_pages(...)` or `StitchedMarkdownResult.markdown`; optional `source_id`, `run_name`, and `source_markdown_path` metadata supplied by the caller |
| Output shape | A lightweight stdlib result dataclass such as `ParsedMarkdownResult` containing `notices: tuple[Notice, ...]`, `tables: tuple[ExtractedTable, ...]`, `corrigenda: tuple[Corrigendum, ...]`, `notice_count`, `table_count`, and optional parser metadata |
| Model outputs | Construct validated `Notice`, `ExtractedTable`, `Corrigendum`, `Provenance`, and `ConfidenceScores` models from `gazette_mistral_pipeline.models.notice` |
| Notice splitting | Split on Kenya Gazette notice headers such as `GAZETTE NOTICE NO. 5969`, markdown heading variants such as `## GAZETTE NOTICE NO. 5969`, and the observed OCR variant `GRZETTE NOTICE NO. 12171`; matching should be case-insensitive and line-oriented where possible |
| Notice numbers | Populate `Notice.notice_no` from the header when matched; keep it as the digit string without punctuation; skip preamble/content-table text that does not contain a notice header |
| Notice title lines | Populate `Notice.title_lines` from the first meaningful non-empty lines after the header, usually uppercase act/title lines or markdown heading lines, stopping before body markers such as `IN EXERCISE`, `WHEREAS`, `TAKE NOTICE`, `IT IS NOTIFIED`, `Dated`, or the first table |
| Dates | Populate `Notice.dates_found` with deterministic string matches from notice text, including prototype-style dates such as `7th July, 2008`, `17th April, 2026`, and `Dated the 11th July, 2008`; do not normalize to date objects in F07 |
| Raw content | Populate `Notice.raw_markdown` with the exact notice slice after boundary trimming, preserving markdown tables, headings, bold text, and OCR punctuation; populate `Notice.text` with a lightweight markdown-stripped text form suitable for search and downstream review |
| Tables | Extract lightweight markdown pipe tables inside each notice into `ExtractedTable` models with `headers`, `rows`, `records` when column counts allow, `raw_table_markdown`, `source="markdown_table_heuristic"`, and `column_count`; attach tables to the containing notice and include a flattened `ParsedMarkdownResult.tables` tuple |
| Corrigenda | Identify notices or sections containing `CORRIGENDUM`, `CORRIGENDA`, `corrigendum`, `corrigenda`, or phrases such as `IN Gazette Notice No. 3308 of 2008 amend...`; create `Corrigendum` placeholders with `raw_text`, best-effort `target_notice_no`, best-effort `target_year`, optional `provenance`, and `amendment=None` unless a simple raw phrase can be copied without semantic interpretation |
| Provenance | Populate `Provenance.header_match`, `raw_header_line`, `source_markdown_path`, and line spans from joined markdown line positions. Populate `stitched_from` from F06 page headers such as `## Index 0` when the notice slice lies under a known page header. Set `page_span` only when F06 page indexes can be inferred deterministically; otherwise leave it `None` and rely on `line_span` |
| Content hash | Populate `Notice.content_sha256` as SHA-256 of the trimmed notice `raw_markdown` encoded as UTF-8 |
| Notice IDs | Generate deterministic IDs only. Prefer `f"{run_name}:{first_page_or_line}:{order}:{notice_no_or_hash}"` when `run_name` is available; otherwise use a stable prefix such as `joined:{line_start}:{order}:{content_sha256[:12]}`. Do not use UUIDs, timestamps, process randomness, or object ids |
| Confidence placeholders | F07 must satisfy `Notice.confidence_scores` without implementing F08. Use a clearly named internal helper such as `neutral_confidence_scores(reason="pending F08 confidence scoring")` that returns deterministic medium-band placeholder values, for example `notice_number=0.5`, `structure=0.5`, `boundary=0.5`, `table=None`, `spatial=None`, `composite=0.5`, `band="medium"`, and add the same reason to `Notice.confidence_reasons` |
| Other attributes | Use `Notice.other_attributes` only for lightweight parser facts such as `parser_version`, `notice_order`, `header_text`, `is_corrigendum_candidate`, or `source_line_start`; do not add heavy raw metadata or F08 score details |
| Error handling | Empty or whitespace-only joined markdown should return an empty `ParsedMarkdownResult` rather than raising. Malformed markdown tables should preserve `raw_table_markdown`, normalize rows conservatively, and continue parsing. Invalid argument types should fail with clear exceptions |

Suggested dataclasses and helpers:

```python
@dataclass(frozen=True)
class ParsedMarkdownResult:
    notices: tuple[Notice, ...]
    tables: tuple[ExtractedTable, ...]
    corrigenda: tuple[Corrigendum, ...]
    notice_count: int
    table_count: int


def parse_joined_markdown(
    markdown: str,
    *,
    run_name: str | None = None,
    source_markdown_path: str | Path | None = None,
) -> ParsedMarkdownResult: ...


def extract_markdown_tables(text: str) -> tuple[ExtractedTable, ...]: ...
def neutral_confidence_scores() -> ConfidenceScores: ...
```

The helper names are suggestions; the implementation may choose equivalent names if tests document the public package-internal contract.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F07 as the current `Next` feature and limits the work to notice/table/corrigendum parsing |
| `docs/library-contract-v1.md` | Defines the pipeline step from joined markdown to parsed notices/tables and the required `Notice` fields |
| `docs/library-roadmap-v1.md` | Places F07 between F06 page stitching and F08 confidence/spatial hints |
| `docs/data-quality-confidence-scoring.md` | Defines the future confidence groups and requires raw markdown preservation; F07 only supplies neutral placeholders |
| `docs/known-issues.md` | Calls out regex parser limits, OCR order issues, and the need for later confidence visibility |
| `specs/SOP.md` | Requires spec-first implementation, test matrix, integration point, pass/fail criteria, and no feature completion before tests pass |
| `specs/F06-normalize-and-stitch-pages.md` | Defines joined markdown headers and F06 stats consumed by F07 |
| `gazette_mistral_pipeline/page_normalization.py` | Provides `StitchedMarkdownResult.markdown` and deterministic page/document headers used for parser provenance |
| `gazette_mistral_pipeline/models/notice.py` | Defines `Notice`, `ExtractedTable`, `Corrigendum`, `Provenance`, and `ConfidenceScores` fields F07 must populate |
| `gazette_mistral_pipeline/models/envelope.py` | Defines `Stats` context; F07 produces notice/table counts for F09 but does not assemble `Stats` or `Envelope` |
| `examples/historical/gazette_etl_prototype.ipynb` | Provides prototype regexes for `GAZETTE`/`GRZETTE NOTICE NO.`, date extraction, markdown table heuristics, and envelope parsing behavior |
| `tests/test_page_normalization.py` | Shows the F06 joined markdown shape, page header format, and offline fixture style F07 tests should follow |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Strict notice header happy path | Inline joined markdown with F06 document/page headers and `## GAZETTE NOTICE NO. 5969` followed by title, body, and `Dated the 7th July, 2008.` | One `Notice`; `notice_no=="5969"`; `title_lines` includes the act/title line; `dates_found` includes `7th July, 2008`; `raw_markdown` preserves the slice; `text` contains readable body text; `provenance.header_match=="strict"` |
| TC2 | Multiple adjacent notices | Inline markdown containing `GAZETTE NOTICE NO. 5982` and `GAZETTE NOTICE NO. 5983` without markdown heading markers between them | Two notices in source order; each slice stops before the next header; deterministic IDs and content hashes are stable across two parse calls |
| TC3 | OCR header variant | Inline markdown with `GRZETTE NOTICE NO. 12171` from the prototype regex family | One notice with `notice_no=="12171"`; `provenance.header_match=="recovered"`; `raw_header_line` preserves the OCR spelling |
| TC4 | Preamble and contents table are ignored | Inline joined markdown beginning with gazette cover content and a contents pipe table before the first notice header | Preamble is not emitted as a notice; contents table is not included in result tables unless it appears inside a parsed notice |
| TC5 | Markdown table extraction | Notice body containing a pipe table with header row, separator row, and two data rows such as land parcel rows | One `ExtractedTable`; headers and rows are stripped; `records` maps headers to row values; `raw_table_markdown` preserves the original table block; `source=="markdown_table_heuristic"`; notice `table_count==1` |
| TC6 | Ragged markdown table rows | Notice table with shorter and longer rows than the header, including an extra pipe in the final cell | Parser normalizes rows to `column_count`, pads missing cells with empty strings, folds extra cells into the final cell, preserves `raw_table_markdown`, and does not raise |
| TC7 | Date extraction variants | Notice text containing `Dated the 11th July, 2008.`, `31st July, July, 2008`, and another body date | `dates_found` returns deterministic string matches in source order for supported patterns; the malformed repeated-month example is preserved as text but not forcibly repaired |
| TC8 | Corrigenda heading section | Inline markdown with `## CORRIGENDA` followed by lines such as `IN Gazette Notice No. 3308 of 2008 amend...` before normal notice headers | A `Corrigendum` placeholder is emitted with `raw_text`, `target_notice_no=="3308"`, `target_year==2008`, and provenance; no semantic amendment resolution is attempted |
| TC9 | Corrigendum notice candidate | Inline notice whose title line or body contains `Corrigendum`/`Corrigenda` | Notice is still emitted normally, `other_attributes["is_corrigendum_candidate"]` is true, and a corresponding placeholder may be emitted if enough raw target text exists |
| TC10 | Provenance from F06 headers | Joined markdown with `# Document: ...`, `## Index 0`, and `## Index 1`, with a notice crossing no page boundary | `Provenance.line_span` is populated from joined markdown line numbers; `stitched_from` contains the page header such as `page:0`; `page_span==(0, 0)` when deterministically inferred |
| TC11 | Deferred page-span provenance | Joined markdown where a notice crosses a page header or page inference is ambiguous | Parser keeps `line_span`, includes all deterministic `stitched_from` page ids, and leaves `page_span` as `None` rather than guessing |
| TC12 | Empty input | `""` and whitespace-only markdown | Returns `ParsedMarkdownResult` with empty tuples and zero counts; no envelope, files, or warnings are written |
| TC13 | Notice model completeness | Minimal parsed notice with no table and no dates | Notice validates against the Pydantic model, including `confidence_scores` medium-band neutral placeholder, `confidence_reasons` containing the pending-F08 reason, `content_sha256`, `provenance`, `table_count=0`, and empty `other_attributes` or documented parser facts |
| TC14 | Representative Kenya Gazette regression snippet | Small checked-in or inline snippet copied from representative joined markdown, including `## GAZETTE NOTICE NO. 5969`, title line, legal marker, date line, and signature | Parser returns expected notice number, first title line, date, line provenance, and stable content hash without requiring the full `prototype_outputs` file |
| TC15 | Public API remains unwired | Import package root `parse_file`, `parse_url`, and `parse_source` after F07 implementation | Public parse functions still raise the existing `NotImplementedError` until F10; F07 tests call package-internal helpers directly |

Normal F07 tests must be offline. Use small inline markdown fixtures and, if useful, small representative snippets from joined markdown. They must not read `.env`, require `MISTRAL_API_KEY`, call live Mistral, execute notebooks, or depend on full historical output directories.

## 5. Integration Point

Called by later features:

- F09 uses `ParsedMarkdownResult.notices`, flattened `tables`, `corrigenda`, `notice_count`, and `table_count` when assembling `Envelope.notices`, `Envelope.tables`, `Envelope.corrigenda`, and `Envelope.stats`.
- F08 may replace or update F07 neutral placeholder confidence scores with real rule-based scores and reasons.
- F10 public `parse_file`, `parse_url`, and `parse_source` will connect F04 source loading, F05 OCR/replay, F06 normalization/stitching, F07 parsing, F08 scoring, F09 envelope assembly, and final bundle writing.

Calls:

- `gazette_mistral_pipeline.page_normalization.StitchedMarkdownResult.markdown` or equivalent joined markdown text.
- Pydantic models from `gazette_mistral_pipeline.models.notice`.
- Stdlib only for parsing helpers: `re`, `hashlib`, dataclasses, pathlib, and typing helpers.

Side effects:

- F07 parser helpers are pure and do not read environment variables, call Mistral, write files, update notebooks, update `PROGRESS.md`, or commit changes.
- Tests may create temporary files only when exercising optional source path metadata; no output bundles are written.

Model fields populated:

- `Notice.notice_id`, `notice_no`, `dates_found`, `title_lines`, `text`, `raw_markdown`, `tables`, `table_count`, `provenance`, `confidence_scores`, `confidence_reasons`, `content_sha256`, and `other_attributes`.
- `ExtractedTable.headers`, `rows`, `records`, `raw_table_markdown`, `source`, and `column_count`.
- `Corrigendum.raw_text`, best-effort `target_notice_no`, best-effort `target_year`, `amendment` only when copied as raw non-semantic text, and `provenance`.
- F07 produces counts later used for `Stats.notice_count` and `Stats.table_count`; it does not construct `Stats`, `DocumentConfidence`, `LayoutInfo`, or `Envelope`.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| F07 module imports cleanly | `python -m pytest tests/test_notice_parsing.py` imports the parser module without importing notebooks |
| Current feature scope is respected | Review confirms no changes to public `parse_*` wiring, envelope assembly, scoring logic, schema export, bundle writing, notebooks, or `PROGRESS.md` completion state |
| Notice splitting works for representative Kenya Gazette headers | Unit tests cover markdown heading headers, plain headers, adjacent notices, and the observed `GRZETTE` OCR variant |
| Notice models are valid and complete | Unit tests instantiate Pydantic `Notice` models and assert all required model fields are populated |
| Confidence handling is explicitly preliminary | Unit tests assert deterministic medium-band neutral placeholders and pending-F08 reasons; no scoring heuristics beyond placeholder construction are introduced |
| Tables are extracted lightly and preserved | Unit tests cover normal and ragged pipe tables, `records`, `column_count`, and `raw_table_markdown` preservation |
| Corrigenda placeholders are detected | Unit tests cover a `CORRIGENDA` section and a corrigendum notice candidate without semantic amendment resolution |
| Provenance is deterministic | Unit tests assert line spans, raw header lines, page hints from F06 headers where available, and no guessed page spans when ambiguous |
| IDs and hashes are deterministic | Unit tests parse the same markdown twice and compare notice IDs, order, and `content_sha256` values |
| Offline tests pass | `python -m pytest tests/test_notice_parsing.py` and `python -m pytest` pass without `.env`, API keys, network access, live Mistral calls, or notebook execution |

## 7. Definition Of Done

- [x] `specs/F07-notice-and-table-parsing.md` is approved before implementation starts.
- [x] A package-internal F07 parser module exists with pure helpers for joined markdown parsing, notice splitting, date extraction, title extraction, markdown table extraction, corrigendum placeholder detection, provenance, content hashing, deterministic ID generation, and neutral confidence placeholder construction.
- [x] F07 consumes F06 joined markdown text and understands deterministic F06 document/page headers for best-effort provenance.
- [x] Parsed notices validate as `Notice` models and include required neutral `ConfidenceScores` placeholders plus clear pending-F08 reasons.
- [x] Parsed tables validate as `ExtractedTable` models, remain attached to their notice, and are also available as a flattened result collection.
- [x] Corrigenda placeholders validate as `Corrigendum` models and identify likely target notice numbers/years when present without resolving legal amendments.
- [x] Notice IDs and content hashes are deterministic across repeated parses of the same input.
- [x] Unit tests cover at least the matrix above using inline fixtures or small checked-in snippets.
- [x] Existing F02-F06 tests still pass.
- [x] F07 does not implement envelope assembly, confidence scoring, spatial scoring, schema export, public `parse_*` wiring, bundle writing, notebook edits, or feature completion updates in `PROGRESS.md`.

## 8. Open Questions And Risks

Q1. Should F07 return Pydantic models directly or lightweight dicts for F09 to validate?

Recommended answer: return validated Pydantic `Notice`, `ExtractedTable`, and `Corrigendum` models inside a lightweight stdlib result dataclass. This catches contract drift early while still leaving final envelope assembly to F09.

Q2. How should F07 satisfy `Notice.confidence_scores` before F08?

Recommended answer: use deterministic neutral medium-band placeholders from a clearly named helper such as `neutral_confidence_scores()`, and add `pending F08 confidence scoring` to `confidence_reasons`. Do not add parser-quality heuristics until F08.

Q3. Should `Corrigendum.amendment` be parsed in F07?

Recommended answer: no semantic amendment parsing in F07. Emit `raw_text`, best-effort target notice/year, and provenance. Only copy an obvious raw amendment phrase if it can be done without interpretation; otherwise leave `amendment=None`.

Q4. Should page spans be mandatory?

Recommended answer: no. `line_span` should be mandatory when the notice comes from joined markdown, while `page_span` should be populated only when F06 page headers make the mapping deterministic. Ambiguous cross-page notices should keep page span `None` and list page hints in `stitched_from`.

Q5. Should F07 parse every possible Kenya Gazette notice header variant?

Recommended answer: start with strict `GAZETTE NOTICE NO.` plus observed OCR variants such as `GRZETTE NOTICE NO.` and optional markdown heading markers. Add future variants through regression tests when real samples show them, rather than broad patterns that risk false positives.

Q6. Should contents-page tables be included in extracted tables?

Recommended answer: not in F07 result tables unless they fall inside a parsed notice. F07 is notice-centric, and document-level tables or indexes can be revisited in a later feature if needed.

Q7. What is the main parser risk?

Recommended answer: regex boundaries can miss or merge notices when OCR order is damaged or headers are corrupted. Preserve raw markdown, deterministic provenance, and stable IDs so F08/F09 can surface review risk and future regressions can be added cheaply.
