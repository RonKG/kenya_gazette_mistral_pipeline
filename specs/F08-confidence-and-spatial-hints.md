# F08 Spec: Confidence and Spatial Hints

## 1. Goal

Replace F07 neutral per-notice confidence placeholders with deterministic, explainable confidence scores and summarize optional Mistral spatial/page metadata into document-level layout hints and warnings without assembling the final envelope.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Rule-based per-notice `ConfidenceScores`, confidence reduction reasons, `DocumentConfidence` aggregation, optional `LayoutInfo` spatial summaries, and useful `PipelineWarning` records for suspicious parser/scoring outputs |
| Out of scope | Envelope assembly, schema export, public `parse_file`/`parse_url`/`parse_source` wiring, final bundle writing, live Mistral calls, notebook edits, full reading-order reconstruction, OCR repair, semantic legal validation, ML/LLM scoring, and geospatial processing |
| Primary module | Add package-internal pure helpers in a narrow module such as `gazette_mistral_pipeline/confidence_scoring.py`; a second narrow helper module for layout summarization is acceptable only if it keeps the API clearer |
| Input source | `ParsedMarkdownResult` from `gazette_mistral_pipeline.notice_parsing.parse_joined_markdown(...)`, or an equivalent sequence of `Notice` models plus flattened `ExtractedTable` models; optional raw Mistral JSON from F05 replay/cache; optional F06 `NormalizedPage` records when already available |
| Output shape | A frozen stdlib result dataclass such as `ScoredParsingResult` containing `scored_notices: tuple[Notice, ...]`, `document_confidence: DocumentConfidence`, `layout_info: LayoutInfo`, `warnings: tuple[PipelineWarning, ...]`, and optional parser/scoring metadata |
| Notice output | Return copied or updated `Notice` models whose `confidence_scores` are no longer the F07 neutral placeholder values and whose `confidence_reasons` explain every score reduction. Do not mutate caller-owned model instances in place unless tests prove Pydantic copy/update behavior is impossible or unnecessarily complex |
| Score range | Every numeric score must be clamped or validated into `0.0 <= score <= 1.0`; invalid helper inputs should fail clearly in tests rather than silently producing out-of-range Pydantic models |
| Confidence bands | Use the documented bands from `docs/data-quality-confidence-scoring.md`: `high` is `0.85` to `1.00`, `medium` is `0.60` to less than `0.85`, and `low` is less than `0.60` |
| Per-notice score groups | Populate `notice_number`, `structure`, `boundary`, optional `table`, optional `spatial`, `composite`, and `band` on `ConfidenceScores` |
| Notice number scoring | High for numeric notice numbers with typical lengths and strict `GAZETTE NOTICE NO.` provenance; reduce for missing/non-numeric values if a caller supplies such notices, single-digit or very long values, recovered OCR headers such as `GRZETTE`, missing raw header lines, or mismatch between `notice_no` and `raw_markdown` |
| Structure scoring | Use deterministic signals from `Notice.raw_markdown`, `Notice.text`, `Notice.title_lines`, `Notice.dates_found`, `Notice.tables`, and legal/body markers such as `IN EXERCISE`, `IT IS NOTIFIED`, `WHEREAS`, and `TAKE NOTICE`; reduce for header-only bodies, very short text, absent title/date/legal markers/signature/table signals, or suspiciously long bodies that may have swallowed another notice |
| Boundary scoring | Use F07 provenance and raw markdown structure: strict/recovered/inferred/none `header_match`, line span presence, page span ambiguity, stitched page hints, body ending, and duplicate notice numbers in the scored batch; reduce for ambiguous provenance, duplicate notice numbers, empty line spans, cross-page ambiguity, or obvious next-notice text inside one notice |
| Table scoring | For notices with tables, score header presence, non-empty rows, consistent column count, records availability, and raw markdown preservation. Leave `table=None` when the notice has no tables rather than penalizing the notice solely for lacking a table |
| OCR/text quality scoring | Fold lightweight OCR/text signals into structure, boundary, and document-level `ocr_quality`: excessive replacement characters, very high punctuation/noise ratio, many broken one-character tokens, markdown image-only pages, repeated garbled header variants, or empty text after markdown stripping |
| Spatial scoring | Spatial hints are optional. If coordinate-like metadata is present, populate per-notice `spatial` only when there is a deterministic relation to page/provenance or page-level metadata; otherwise keep per-notice `spatial=None` and summarize at `LayoutInfo`. Absence of coordinates should not heavily penalize core notice confidence |
| Composite scoring | Use a deterministic weighted average that favors parser-owned notice signals. Recommended starting weights: notice number `0.25`, boundary `0.25`, structure `0.35`, table `0.10` when present, spatial `0.05` when present. If optional table/spatial scores are `None`, renormalize over present components |
| Document confidence | Build `DocumentConfidence` from scored notices, warning count, OCR/text quality signals, and spatial availability. Populate `mean_composite`, `min_composite`, `n_notices`, high/medium/low `counts`, `notice_split`, `ocr_quality`, optional `table_quality`, optional `spatial`, `composite`, and reasons |
| Layout summary | Build `LayoutInfo` from existing raw Mistral JSON/page metadata only. Summarize page dimensions, coordinate-like objects, image/table coordinates if present, `positioned_element_count`, layout confidence, and reasons for absence or partial availability |
| Spatial raw shapes | Accept the raw JSON shapes already supported by F05/F06: a single object with `pages`, a list of block objects with `pages`, and legacy page-list shapes. Unsupported spatial substructures should be ignored with reasons rather than failing if the outer raw JSON shape was otherwise accepted earlier |
| Coordinate detection | Treat dictionaries with numeric coordinate-like keys such as `x`, `y`, `width`, `height`, `top`, `left`, `bottom`, `right`, `bbox`, `bounds`, `polygon`, or `points` as spatial hints. Count and summarize them; do not perform geometric joins or reading-order reconstruction |
| Layout warnings | Missing coordinates alone is usually a `LayoutInfo.reason`, not a `PipelineWarning`. Emit warnings for suspicious outputs such as zero notices, many low-confidence notices, no text-bearing pages, document confidence below a low threshold, or malformed coordinate structures that look present but unusable |
| Error handling | Empty notice input should return no scored notices, low document confidence, unavailable layout info, and a `PipelineWarning` such as `no_notices`. Invalid argument types should fail with clear exceptions. F08 helpers must not read `.env`, require API keys, access the network, execute notebooks, write bundles, update `PROGRESS.md`, or commit changes |
| Runtime dependencies | Stdlib plus existing Pydantic models only. Do not add ML, LLM, Docling, OCR, geospatial, plotting, or Mistral SDK runtime dependencies |

Suggested dataclasses and helpers:

```python
@dataclass(frozen=True)
class ScoredParsingResult:
    scored_notices: tuple[Notice, ...]
    document_confidence: DocumentConfidence
    layout_info: LayoutInfo
    warnings: tuple[PipelineWarning, ...]
    scorer_version: str = "F08"


def score_parsed_notices(
    parsed: ParsedMarkdownResult,
    *,
    raw_mistral_json: Any | None = None,
    normalized_pages: Sequence[NormalizedPage] | None = None,
) -> ScoredParsingResult: ...


def score_notice_confidence(
    notice: Notice,
    *,
    all_notice_numbers: Sequence[str | None] = (),
    layout_info: LayoutInfo | None = None,
) -> tuple[ConfidenceScores, list[str]]: ...


def summarize_layout_hints(
    raw_mistral_json: Any | None = None,
    *,
    normalized_pages: Sequence[NormalizedPage] | None = None,
) -> LayoutInfo: ...


def aggregate_document_confidence(
    notices: Sequence[Notice],
    *,
    layout_info: LayoutInfo,
    warnings: Sequence[PipelineWarning] = (),
) -> DocumentConfidence: ...
```

Helper names are suggestions. The implementation may choose equivalent names if tests document the package-internal contract and keep F09/F10 integration straightforward.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | Identifies F08 as the current `Next` feature and defines the simple explanation: score notices and summarize optional Mistral coordinate metadata |
| `docs/library-contract-v1.md` | Defines the target pipeline step that adds confidence scores, warnings, and optional spatial hints before envelope assembly |
| `docs/library-roadmap-v1.md` | Places F08 after F07 notice/table parsing and before F09 validated envelope assembly |
| `docs/data-quality-confidence-scoring.md` | Defines deterministic scoring principles, score groups, optional spatial hints, document aggregation, confidence bands, and regression expectations |
| `docs/known-issues.md` | Clarifies that Mistral spatial metadata is optional, word-level coordinates may be absent, parser limits should be surfaced, and live/API-key behavior must stay out of normal tests |
| `specs/SOP.md` | Requires spec-first implementation, test matrix, integration point, pass/fail criteria, and no completion update before tests pass |
| `specs/F06-normalize-and-stitch-pages.md` | Defines supported raw JSON shapes, `NormalizedPage.raw_page_metadata`, joined markdown headers, and the explicit handoff of `LayoutInfo` to F08 |
| `specs/F07-notice-and-table-parsing.md` | Defines F07 neutral placeholder confidence scores that F08 must replace or augment with real deterministic scores |
| `gazette_mistral_pipeline/notice_parsing.py` | Provides `ParsedMarkdownResult`, F07 provenance, raw markdown preservation, tables, dates, title lines, and placeholder confidence helper behavior |
| `gazette_mistral_pipeline/page_normalization.py` | Provides `NormalizedPage`, raw page metadata preservation, and F06 raw shape handling patterns for layout summaries |
| `gazette_mistral_pipeline/models/notice.py` | Defines `ConfidenceScores`, `Notice`, `ExtractedTable`, and `Provenance` fields that F08 updates or reads |
| `gazette_mistral_pipeline/models/envelope.py` | Defines `DocumentConfidence`, `LayoutInfo`, and `PipelineWarning` models F08 should produce without constructing `Envelope` |
| `gazette_mistral_pipeline/mistral_ocr.py` | Shows raw JSON replay/cache context and supported raw shapes; F08 may consume raw JSON but must not call live OCR |
| `tests/test_notice_parsing.py` | Contains the F07 placeholder confidence regression that F08 should supersede with scored notice tests |
| `tests/test_page_normalization.py` | Contains representative raw JSON/page metadata fixtures and offline test style for spatial summaries |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | High-confidence notice replaces F07 placeholder | Inline F07 parsed markdown with strict `GAZETTE NOTICE NO. 5969`, title line, legal marker, date, clean provenance, and no table | Returned notice has non-placeholder `ConfidenceScores`; `notice_number`, `structure`, `boundary`, and `composite` are high-band appropriate; `band=="high"`; `confidence_reasons` does not contain only `pending F08 confidence scoring` |
| TC2 | Medium-confidence recovered header | Notice parsed from `GRZETTE NOTICE NO. 12171` with useful body, title, and date but `provenance.header_match=="recovered"` | Notice number or boundary score is reduced with a reason mentioning recovered/noisy header; composite falls in the documented medium band unless other signals are strong enough to offset it; output remains deterministic across repeated runs |
| TC3 | Low-confidence weak body | Notice with strict header but header-only or very short body, no title, no dates, no legal markers, no signature, and no tables | Structure and composite are low; `band=="low"`; reasons identify short/empty body and missing structure signals |
| TC4 | Table quality contributes without requiring tables | One notice with a well-formed markdown table and one otherwise similar notice without tables | Table-bearing notice has `table` score populated and table-related reasons only if reduced; no-table notice has `table is None`; lack of a table alone does not force a low composite |
| TC5 | Ragged table reduces table score | Notice with an extracted ragged table where rows were normalized, some records are missing or empty, and raw table markdown is preserved | `table` score is medium or low depending on severity; composite reflects the reduced optional component; reasons mention ragged or sparse table quality |
| TC6 | Duplicate notice numbers reduce boundary confidence | Parsed result with two notices sharing the same `notice_no` but different content hashes | Both duplicate notices receive reduced boundary confidence and reasons; document `notice_split` and composite are reduced; deterministic IDs and original notice order remain unchanged |
| TC7 | Score helper validates ranges and bands | Direct helper tests around scores at `1.0`, `0.85`, `0.849`, `0.60`, `0.599`, and `0.0`, plus an intentionally invalid internal score if exposed | Bands map exactly to high/medium/low thresholds; out-of-range values are clamped or raise clear errors according to the chosen helper contract, with tests documenting the behavior |
| TC8 | Document confidence aggregation | Three scored notices with high, medium, and low composites plus one warning | `DocumentConfidence.counts == {"high": 1, "medium": 1, "low": 1}`; `mean_composite`, `min_composite`, `n_notices`, `notice_split`, and `composite` are deterministic; reasons include low-confidence notice or warning impact where applicable |
| TC9 | Empty parse result warning | Empty `ParsedMarkdownResult` from empty joined markdown and no raw JSON | Returns `scored_notices == ()`; `LayoutInfo.available is False`; `DocumentConfidence.n_notices == 0`; emits a `PipelineWarning` with kind such as `no_notices`; no exception, network, files, or notebook execution |
| TC10 | Layout unavailable without warning spam | Valid parsed notice and raw JSON/pages with markdown but no dimensions, images, tables, bbox, bounds, polygon, or coordinate-like fields | `LayoutInfo.available is False`; `positioned_element_count == 0`; reasons explain no coordinate metadata found; no warning is emitted solely because coordinates are absent |
| TC11 | Page dimensions and positioned elements summarized | Small inline raw JSON object with two pages containing dimensions plus image/table objects with bbox/bounds or x/y/width/height | `LayoutInfo.available is True`; `pages` contains compact page summaries with page index and dimensions; `positioned_element_count` equals counted coordinate-like objects; `layout_confidence` is medium or high based on coverage; reasons are empty or note partial coverage |
| TC12 | Raw JSON block-list and legacy shapes share layout behavior | Inline single-object, block-list, and legacy page-list raw JSON snippets with equivalent coordinate-like page metadata | Layout summarization returns equivalent positioned-element counts and dimension coverage for all supported outer shapes |
| TC13 | Malformed coordinate-like metadata is nonfatal | Raw JSON with an image/table entry containing nonnumeric bbox/points or an unexpected coordinate container | Summarizer ignores unusable coordinates, records a reason for malformed spatial metadata, and may emit a `PipelineWarning` only when metadata looked present but entirely unusable |
| TC14 | Spatial availability can inform document confidence lightly | Two otherwise identical scored outputs, one with useful layout coordinates and one without coordinates | Spatial score or document `spatial` differs, but missing coordinates do not drop a high-quality parse below medium solely because spatial data is absent |
| TC15 | F08 remains package-internal | Import package root `parse_file`, `parse_url`, and `parse_source` after F08 implementation | Public parse functions still raise the existing `NotImplementedError` until F10; F08 tests call package-internal helpers directly |

Normal F08 tests must be offline. Use small inline parsed markdown fixtures, inline raw JSON snippets, and the existing small representative page-normalization fixture when useful. They must not read `.env`, require `MISTRAL_API_KEY`, call live Mistral, execute notebooks, depend on full historical `prototype_outputs`, write final bundles, or update `PROGRESS.md`.

## 5. Integration Point

Called by later features:

- F09 consumes `ScoredParsingResult.scored_notices`, `document_confidence`, `layout_info`, and `warnings` when assembling the validated `Envelope`.
- F10 public `parse_file`, `parse_url`, and `parse_source` will connect F04 source loading, F05 OCR/replay, F06 normalization/stitching, F07 parsing, F08 scoring/layout hints, F09 envelope assembly, and final bundle writing.

Calls:

- `gazette_mistral_pipeline.notice_parsing.ParsedMarkdownResult` and `Notice`/`ExtractedTable` model instances produced by F07.
- Optional raw Mistral JSON from `gazette_mistral_pipeline.mistral_ocr.MistralOcrResult.raw_json` or `load_raw_mistral_json(...)`.
- Optional F06 `NormalizedPage.raw_page_metadata` when pages have already been normalized.
- Pydantic models from `gazette_mistral_pipeline.models.notice` and `gazette_mistral_pipeline.models.envelope`.
- Stdlib helpers only, such as `dataclasses`, `statistics`, `re`, `math`, and typing utilities.

Side effects:

- F08 scoring and layout helpers are pure.
- F08 does not read environment variables, call Mistral, read `.env`, write files, update notebooks, update `PROGRESS.md`, commit changes, write final bundles, export schemas, or construct the final `Envelope`.

Model fields populated:

- `Notice.confidence_scores` with deterministic non-placeholder `ConfidenceScores`.
- `Notice.confidence_reasons` with explainable score-reduction reasons.
- `DocumentConfidence.ocr_quality`, `notice_split`, `composite`, `counts`, `mean_composite`, `min_composite`, `n_notices`, optional `table_quality`, optional `spatial`, and `reasons`.
- `LayoutInfo.available`, optional `layout_confidence`, `pages`, `positioned_element_count`, and `reasons`.
- `PipelineWarning.kind`, `message`, and optional `where` for suspicious outputs such as no notices, many low-confidence notices, very low document confidence, or unusable present spatial metadata.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| F08 module imports cleanly | `python -m pytest tests/test_confidence_scoring.py` imports the new package-internal module without importing notebooks |
| Placeholder regression is replaced | Unit tests assert notices from F07 no longer retain the all-`0.5` pending-F08 placeholder after F08 scoring |
| Score bands are correct | Unit tests cover exact boundaries for high, medium, and low bands from `docs/data-quality-confidence-scoring.md` |
| Score ranges are safe | Unit tests verify every emitted numeric score is between `0.0` and `1.0`, including aggregate and layout scores |
| Reasons are explainable | Degraded notice/table/layout cases assert meaningful `confidence_reasons`, `DocumentConfidence.reasons`, or `LayoutInfo.reasons` |
| Document confidence aggregates notice scores | Unit tests verify counts, mean, minimum, warning impact, and zero-notice behavior |
| Spatial hints are optional and bounded | Unit tests cover absent coordinates, present dimensions, present image/table coordinates, malformed coordinate objects, and supported raw JSON outer shapes |
| Scope is respected | Review confirms no public `parse_*` wiring, envelope assembly, schema export, final bundle writing, live Mistral calls, notebook edits, or `PROGRESS.md` completion update |
| Runtime stays lightweight | Review confirms no new runtime dependencies beyond stdlib and existing Pydantic models |
| Offline tests pass | `python -m pytest tests/test_confidence_scoring.py` and `python -m pytest` pass without `.env`, API keys, network access, live Mistral calls, or notebook execution |

## 7. Definition Of Done

- [x] `specs/F08-confidence-and-spatial-hints.md` is approved before implementation starts.
- [x] A package-internal F08 module exists with pure helpers for notice scoring, score range/band behavior, document confidence aggregation, layout hint summarization, and warning generation.
- [x] F08 replaces or augments F07 neutral `ConfidenceScores` placeholders with deterministic, explainable per-notice scores.
- [x] F08 returns copied/updated `Notice` models or an equivalent scored result dataclass; caller-owned F07 parser results are not unexpectedly mutated.
- [x] F08 produces a valid `DocumentConfidence` aggregate for normal, degraded, and zero-notice inputs.
- [x] F08 produces a valid `LayoutInfo` summary for absent, partial, and present Mistral coordinate/page metadata.
- [x] F08 emits useful `PipelineWarning` records for suspicious outputs without warning on every normal coordinate absence.
- [x] Unit tests cover at least the matrix above using inline fixtures or existing small test fixtures.
- [x] Existing F02-F07 tests still pass.
- [x] F08 does not implement envelope assembly, schema export, public `parse_*` wiring, final bundle writing, live Mistral calls, notebook edits, feature completion updates in `PROGRESS.md`, or commits.

## 8. Open Questions And Risks

Q1. Should F08 mutate existing `Notice` instances or return copied/updated notices?

Recommended answer: return copied/updated `Notice` models inside a frozen `ScoredParsingResult`. This keeps F07 parser output reproducible and makes F08 behavior easier to test.

Q2. Should missing spatial coordinates lower confidence?

Recommended answer: only lightly at document/spatial-summary level, if at all. `docs/data-quality-confidence-scoring.md` says coordinates are optional and should not heavily penalize the core parser. Record absence in `LayoutInfo.reasons`.

Q3. Should F08 add Pydantic validators to `ConfidenceScores` for score ranges?

Recommended answer: prefer F08 helper-level range validation or clamping tests first to avoid changing shared model behavior in a scoring feature. Add model validators only if implementation reveals repeated risk of invalid scores escaping helper boundaries.

Q4. How precise should the initial scoring weights be?

Recommended answer: start with documented deterministic weights and tests around bands, not calibration claims. The first implementation should be explainable and stable; real gazette calibration can adjust weights later through regression tests.

Q5. Should coordinate summaries attempt notice-to-coordinate matching?

Recommended answer: no full matching in F08. Only populate per-notice `spatial` when provenance makes a page-level relation deterministic. Do not infer reading order or geometry joins from limited Mistral metadata.

Q6. When should F08 emit warnings?

Recommended answer: warn for suspicious extraction quality, such as no notices, many low-confidence notices, very low document confidence, no text-bearing pages if detectable, or present-but-unusable spatial metadata. Do not warn simply because optional coordinates are absent.

Q7. What is the main implementation risk?

Recommended answer: overfitting scoring to tiny fixtures. Keep rules simple, reason strings explicit, and regression tests focused on stable bands, counts, and warnings rather than exact decimals for every signal unless the decimal is part of the contract.
