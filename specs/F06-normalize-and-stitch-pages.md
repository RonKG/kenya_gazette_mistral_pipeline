# F06 Spec: Normalize and Stitch Pages

## 1. Goal

Normalize supported Mistral OCR raw JSON shapes into deterministic page records, compute basic markdown/page statistics for later envelope assembly, and write a joined markdown stage artifact.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Page normalization, deterministic page ordering, joined markdown rendering, joined markdown file writing, and basic statistics only |
| Out of scope | Notice parsing, table parsing, confidence scoring, spatial hint summarization, envelope assembly, JSON Schema export, public `parse_*` wiring, and final output bundle writing |
| Primary module | Add package-internal helpers in `gazette_mistral_pipeline/page_normalization.py` or an equivalently narrow module name |
| Model inputs | Raw JSON returned by `gazette_mistral_pipeline.mistral_ocr.run_mistral_ocr(...)` or loaded by `load_raw_mistral_json(...)`; optional source/run metadata supplied by the caller |
| Supported raw shapes | A single object containing `pages`; a list of OCR block objects each containing `pages`; and a legacy list of page objects containing `markdown` |
| Page filtering | Skip non-dict page entries and pages whose `markdown` is missing, `None`, or whitespace-only; fail only when the overall raw JSON shape itself is unsupported |
| Page order | Preserve block/document order from the raw JSON and sort pages within each block by a deterministic page sort key derived from page `index`; ties and missing/non-integer indexes must remain stable by original list order |
| Output page model | A lightweight stdlib dataclass such as `NormalizedPage`, not a Pydantic envelope model |
| Output result model | A lightweight stdlib dataclass such as `StitchedMarkdownResult` or `NormalizedDocument`, containing normalized pages, joined markdown, document count, page count, `char_count_markdown`, and optional output path |
| Joined markdown | UTF-8 text ending with one newline; preserve each page's raw markdown content apart from trimming leading/trailing whitespace at page boundaries; include deterministic page separators/headers; include document separators/headers when multiple documents or block-level source metadata are present |
| Joined markdown path | `write_joined_markdown(...)` writes exactly one helper/stage artifact, normally `<run_name>_joined.md`; F10 remains responsible for final output bundle selection and bundle manifests |
| Error handling | Missing files, empty files, invalid JSON, unsupported raw shapes, non-list `pages`, and zero normalized pages raise clear exceptions naming the problem without API keys or environment values |

Suggested dataclasses:

```python
@dataclass(frozen=True)
class NormalizedPage:
    index: int
    original_page_index: int | None
    document_index: int
    document_id: str | None
    document_url: str | None
    model: str | None
    markdown: str
    raw_page_metadata: dict[str, Any]


@dataclass(frozen=True)
class StitchedMarkdownResult:
    pages: tuple[NormalizedPage, ...]
    markdown: str
    document_count: int
    page_count: int
    char_count_markdown: int
    output_path: Path | None = None
```

Suggested helpers:

```python
def load_mistral_blocks(source: str | Path | dict[str, Any] | list[Any]) -> list[dict[str, Any]]: ...
def normalize_mistral_pages(raw_json: Any) -> tuple[NormalizedPage, ...]: ...
def stitch_markdown_pages(
    pages: Sequence[NormalizedPage],
    *,
    add_page_headers: bool = True,
    add_document_headers: bool = True,
) -> str: ...
def write_joined_markdown(markdown: str, path: str | Path) -> Path: ...
def compute_stats(pages: Sequence[NormalizedPage], markdown: str) -> dict[str, int]: ...
```

`compute_stats(...)` should produce the F06-owned values that later feed `Stats`: `document_count`, `page_count`, and `char_count_markdown`. F09 should combine those with downstream parser counts such as `notice_count`, `table_count`, and `warnings_count` when building the final `Stats` Pydantic model. If F06 directly constructs `Stats` in tests or temporary integration helpers, `notice_count` and `table_count` must remain zero because F06 does not parse notices or tables.

### Normalization Details

- For a single raw object with `pages`, treat it as one document block.
- For a raw list where every item is a dict with `pages`, treat each item as one document block in list order.
- For a legacy raw list where every item is a dict with `markdown`, wrap it as one synthetic document block with `pages` equal to that list.
- `NormalizedPage.index` is a zero-based global index assigned after filtering and sorting.
- `NormalizedPage.original_page_index` is the integer form of the raw page `index` when present and parseable; otherwise `None`.
- `NormalizedPage.document_index` is the zero-based index of the source block after shape normalization.
- `NormalizedPage.document_id` comes from block keys such as `id`, `document_id`, `doc_id`, or `mistral_doc_id`, using the first present non-empty value.
- `NormalizedPage.document_url` should prefer block-level `pdf_url`; if unavailable, use a safe block-level document URL/reference only when already present in raw JSON or passed by the caller.
- `NormalizedPage.raw_page_metadata` should carry small non-markdown page metadata needed later for provenance, such as dimensions and counts of images/tables/hyperlinks. It must not duplicate the full `markdown` string and must not attempt F08 spatial scoring.

### Joined Markdown Format

F06 should keep the joined markdown close to the prototype:

```markdown
---

# Document: <document url or document id or document index>

---

## Index 0

<raw page markdown>
```

Document headers may appear once per document when `add_document_headers=True`. Page headers should use the deterministic global `NormalizedPage.index`. The header may also include compact provenance metadata, such as original page index and document index, as long as it remains deterministic and tests assert the exact output. Existing raw page markdown must not be rewritten to repair OCR, parse notices, normalize tables, remove image references, or infer layout.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F06 as the current `Next` feature and limits the work to page normalization and joined markdown |
| `docs/library-contract-v1.md` | Defines the pipeline stages, joined markdown artifact, `Stats` fields, and F10 bundle boundary |
| `docs/library-roadmap-v1.md` | Places normalized pages and joined markdown between F05 raw OCR and F07 notice/table parsing |
| `docs/known-issues.md` | Requires support for known Mistral raw JSON shapes and loud failures for unsupported shapes |
| `specs/SOP.md` | Requires spec-first implementation, test matrix, integration points, pass/fail criteria, and no feature completion before tests pass |
| `specs/F05-mistral-api-pass.md` | Leaves raw JSON in Mistral's native shape and defines F06 as the consumer of `MistralOcrResult.raw_json` |
| `gazette_mistral_pipeline/mistral_ocr.py` | Provides `load_raw_mistral_json(...)`, shape validation precedent, and metadata page counting from F05 |
| `gazette_mistral_pipeline/models/envelope.py` | Defines `Stats`, whose `document_count`, `page_count`, and `char_count_markdown` are seeded by F06 |
| `examples/historical/gazette_etl_prototype.ipynb` | Provides prototype behavior for `load_mistral_blocks`, page sorting, page metadata, document headers, page headers, and joined markdown writing |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Single object with pages | Inline raw JSON object: `{"id": "doc_1", "model": "mistral-ocr-latest", "pages": [{"index": 1, "markdown": "Page 2"}, {"index": 0, "markdown": "Page 1"}]}` | Normalization returns two `NormalizedPage` records ordered by raw page index `0`, `1`; global indexes are `0`, `1`; document count is `1`; joined markdown contains one document header and two page headers |
| TC2 | Block list with multiple documents | Inline raw JSON list with two block dicts, each with `id`, optional `pdf_url`, and one or more pages | Block order is preserved; pages are sorted only within each block; `document_index` and `document_id` are populated; joined markdown emits deterministic document headers when document identity changes |
| TC3 | Legacy page-list shape | Inline list of page dicts such as `[{"index": "2", "markdown": "two"}, {"index": "1", "markdown": "one"}]` | Shape is accepted as one synthetic document; output pages are ordered by parsed integer index; `document_id` and `document_url` are `None`; document count is `1` |
| TC4 | Stable handling of missing or duplicate page indexes | Inline pages with missing, non-integer, and duplicate `index` values mixed with valid ones | Sort key is deterministic and stable; missing/non-integer indexes do not crash; repeated runs produce identical page order, joined markdown bytes, and stats |
| TC5 | Empty and non-markdown pages are skipped | Inline block with pages containing `"markdown": ""`, `"markdown": "   "`, `markdown=None`, a non-dict entry, and one valid page | Only the valid page is normalized; page count and char count reflect the rendered joined markdown; no notice/table parsing occurs |
| TC6 | Unsupported shapes fail loudly | `{}`, `[]`, `{"pages": {}}`, `[{"not_pages": []}]`, or a scalar JSON value | Raises `ValueError` with a message explaining the supported shapes; no joined markdown file is written |
| TC7 | Joined markdown preserves page markdown | Inline page markdown containing headings, image links, tables, mixed case `Gazette Notice`, and blank lines | Output contains the raw page markdown content without notice parsing, table parsing, OCR repair, or image link removal; only deterministic F06 separators/headers are added |
| TC8 | Joined markdown writer writes one stage artifact | Normalized pages and `tmp_path / "sample_joined.md"` | File is written as UTF-8, parent directories are created if needed, return path matches the requested path, content ends with one newline, and no envelope/bundle JSON files are written |
| TC9 | Stats feed later envelope assembly | Two normalized documents with three pages and rendered joined markdown | `compute_stats(...)` returns `document_count=2`, `page_count=3`, `char_count_markdown=len(markdown)`; any temporary `Stats` construction uses `notice_count=0` and `table_count=0` |
| TC10 | Cached raw JSON regression fixture | Prefer a small checked-in fixture copied from or modeled after `prototype_outputs/gazette_2026-04-17_68/gazette_2026-04-17_68.raw.json`, containing a block-list shape with realistic page metadata | Normalization accepts the cached shape, returns the expected page count for the fixture, preserves representative markdown text, and renders deterministic joined markdown. If copying the full cached response is too large, create a minimal representative fixture under `tests/fixtures/` with two pages and the same outer shape |
| TC11 | Public API remains stubbed | Import package root `parse_file`, `parse_url`, and `parse_source` after F06 implementation | Public parse functions still raise the existing `NotImplementedError` until F10; F06 tests call package-internal helpers directly |

Normal F06 tests must use small inline fixtures or small checked-in fixtures. They must not call live Mistral, read `.env`, require `MISTRAL_API_KEY`, or depend on notebook execution state.

## 5. Integration Point

Called by later features:

- F07 consumes joined markdown from `stitch_markdown_pages(...)` or `StitchedMarkdownResult.markdown` to parse notices and tables.
- F09 uses F06 `document_count`, `page_count`, and `char_count_markdown` when assembling `Envelope.stats`.
- F10 public `parse_file`, `parse_url`, and `parse_source` will connect F04 source loading, F05 OCR/replay, F06 normalization/stitching, F07-F09 parsing/envelope assembly, and final bundle writing.
- F10 `write_envelope(...)` remains the owner of final bundle writing; it may reuse the F06 joined markdown helper for the default `joined_markdown` artifact.

Calls:

- `gazette_mistral_pipeline.mistral_ocr.MistralOcrResult.raw_json` or `load_raw_mistral_json(...)`.
- `json.loads`, `pathlib.Path`, dataclasses, and typing helpers from stdlib.
- `Stats` context from `gazette_mistral_pipeline.models.envelope` only for field alignment; F06 should not assemble a full `Envelope`.

Side effects:

- `normalize_mistral_pages(...)`, `stitch_markdown_pages(...)`, and `compute_stats(...)` are pure.
- `load_mistral_blocks(...)` may read one raw JSON file when passed a path.
- `write_joined_markdown(...)` writes exactly one markdown file and creates parent directories as needed.
- F06 does not read environment variables, call Mistral, write raw JSON, write envelope JSON, write bundle manifests, update notebooks, update `PROGRESS.md`, or commit changes.

Model fields populated:

- No Pydantic envelope fields are populated in the final envelope during F06.
- F06 produces values later used by `Stats.document_count`, `Stats.page_count`, and `Stats.char_count_markdown`.
- `Stats.notice_count`, `Stats.table_count`, and `Stats.warnings_count` are owned by later parser/envelope stages.
- `MistralMetadata.page_count` from F05 remains raw-shape metadata; F06 page count should be the count of normalized non-empty markdown pages. Tests should make any intentional difference explicit.
- `LayoutInfo` remains F08 scope; F06 may preserve raw page metadata for future provenance but does not score or summarize spatial layout.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| F06 module imports cleanly | `python -m pytest tests/test_page_normalization.py` imports the new module without importing notebooks |
| Known raw JSON shapes are accepted | Unit tests cover single object with `pages`, block list with `pages`, and legacy page-list shapes |
| Unsupported raw JSON shapes fail loudly | Unit tests assert `ValueError` for unsupported objects/lists/scalars and invalid `pages` shapes |
| Page ordering is deterministic | Unit tests verify valid, missing, non-integer, and duplicate page indexes produce repeatable page order |
| Markdown preservation is explicit | Unit tests verify page markdown content is preserved apart from boundary trimming and deterministic headers/separators |
| Joined markdown writer is scoped | Unit test verifies only the requested markdown path is written; no envelope or bundle artifacts are created |
| Basic stats are correct | Unit tests assert `document_count`, `page_count`, and `char_count_markdown` from F06 output |
| Regression fixture is covered | Unit test uses either a small checked-in cached raw JSON fixture or a minimal representative fixture matching an observed `prototype_outputs` shape |
| Public parse API remains unwired | Existing package skeleton behavior still raises `NotImplementedError` for root `parse_*` functions until F10 |
| Normal tests are offline | `python -m pytest` passes without `.env`, `MISTRAL_API_KEY`, network access, or live Mistral calls |

## 7. Definition Of Done

- [x] `specs/F06-normalize-and-stitch-pages.md` is approved before implementation starts.
- [x] A package-internal F06 module exists with lightweight dataclasses and helpers for raw shape loading, page normalization, markdown stitching, markdown writing, and basic stats.
- [x] The implementation supports the three known raw JSON shapes listed in `docs/known-issues.md` and F05 tests.
- [x] Page ordering is deterministic across repeated runs for valid, missing, non-integer, and duplicate page indexes.
- [x] Joined markdown includes deterministic separators/headers, preserves raw page markdown, ends with one newline, and writes as UTF-8.
- [x] F06 writes only the joined markdown stage artifact/helper file; F10 remains responsible for output bundle writing.
- [x] F06 does not implement notice parsing, table parsing, confidence scoring, spatial summarization, envelope assembly, schema export, or public `parse_*` wiring.
- [x] Unit tests cover at least the test cases in this spec, using inline fixtures or small checked-in fixtures.
- [x] A regression-oriented test covers a cached raw JSON shape from `prototype_outputs` or a small representative fixture if the cached response is too large.
- [x] Existing F02-F05 tests still pass.
- [x] `python -m pytest` passes without `.env`, API keys, or live Mistral calls.
- [x] `PROGRESS.md` is updated only by the builder after implementation and tests pass, not during spec creation.

## 8. Open Questions And Risks

Q1. Should `NormalizedPage` be a stdlib dataclass or a Pydantic model?

Recommended answer: use a frozen stdlib dataclass for F06. It keeps this stage lightweight and package-internal, while F09 remains responsible for validated Pydantic envelope assembly.

Q2. Should F06 skip blank pages or preserve them as empty page records?

Recommended answer: skip pages whose markdown is missing or whitespace-only, matching the prototype. Record any meaningful raw page count difference later as a warning in F09/F10 if needed.

Q3. Should joined markdown include document/page headers by default?

Recommended answer: yes. Default to deterministic document and page headers because they preserve enough provenance for F07 parsing and later debugging. Keep flags available for tests or downstream callers that need raw concatenation.

Q4. Should F06 copy full cached raw JSON files into `tests/fixtures/`?

Recommended answer: no, unless a cached response is already small enough to keep tests fast and readable. Prefer a tiny representative fixture that preserves the observed outer shape, page metadata fields, and two realistic markdown pages.

Q5. Should F06 populate `Stats` directly?

Recommended answer: return a small stats dict or result dataclass with `document_count`, `page_count`, and `char_count_markdown`. Let F09 construct the final `Stats` model after notice, table, and warning counts exist.

Q6. Should F06 preserve Mistral spatial/page metadata?

Recommended answer: preserve small raw page metadata needed for later provenance, such as dimensions and element counts, but do not compute `LayoutInfo`, coordinate summaries, confidence scores, or reading-order repairs until F08.
