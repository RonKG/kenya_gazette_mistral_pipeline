# F03 Spec: Pydantic Models

## 1. Goal

Define the lightweight Pydantic model layer for the Mistral-based gazette envelope, including source metadata, Mistral metadata, notices, tables, confidence, warnings, bundles, config, and optional spatial hints.

## 2. Input/Output Contract

| Aspect | Specification |
|--------|---------------|
| Feature scope | Models only; no Mistral API calls, markdown parsing, bundle writing, or schema export |
| Runtime dependency added | `pydantic>=2.0` |
| Package modules created | `gazette_mistral_pipeline/models/` with `base.py`, `source.py`, `notice.py`, `envelope.py`, `bundles.py`, `config.py`, `__init__.py` |
| Root exports updated | Export `Envelope`, `PdfSource`, `GazetteConfig`, `Bundles`, and key model classes from package root |
| Validation behavior | Strict by default with `extra="forbid"`, assignment validation enabled, no automatic whitespace stripping |
| Table evolution rule | `ExtractedTable` may allow extra fields so table parsing can improve later without breaking the v1 model |
| Public API stubs | `parse_file`, `parse_url`, `parse_source`, `write_envelope`, schema helpers remain stubs |
| Tests | Model import, valid envelope construction, extra-field rejection, table extra-field allowance, config/bundles defaults |

F03 must not modify notebooks, call Mistral, write output bundles, or generate JSON Schema. JSON Schema export lands in F11.

## 3. Links To Canonical Docs

| Doc | Why it matters |
|-----|----------------|
| `PROGRESS.md` | F03 is the current `⬜ Next` feature |
| `docs/library-contract-v1.md` | Defines envelope top-level fields, source, Mistral metadata, notices, bundles, and API expectations |
| `docs/library-roadmap-v1.md` | Places models before source loading, Mistral API, parsing, and envelope assembly |
| `docs/data-quality-confidence-scoring.md` | Defines confidence groups, bands, warning/trace needs, and spatial hint expectations |
| `docs/known-issues.md` | Requires optional spatial metadata, strict Mistral response boundaries, and no API keys in fixtures |
| `specs/SOP.md` | Requires spec-first implementation and measurable tests |

## 4. Test Case Matrix

| ID | Scenario | Input | Expected |
|----|----------|-------|----------|
| TC1 | Model import smoke | Import all public model classes from `gazette_mistral_pipeline.models` and selected root exports | Imports succeed; `__all__` includes the expected names |
| TC2 | Valid minimal envelope | Small hand-built envelope dict with one PDF URL source, one notice, no tables | `Envelope.model_validate(...)` succeeds; `model_dump(mode="json")` serializes cleanly |
| TC3 | Strict model rejection | Add unknown key to `Envelope`, `Notice`, or `PdfSource` | `pydantic.ValidationError` with `extra_forbidden` |
| TC4 | Table forward compatibility | Add a future table field to `ExtractedTable` | Validation succeeds and extra field is preserved |
| TC5 | Config and bundle defaults | `GazetteConfig()` and `Bundles()` | Defaults are deterministic and no live API values are required |
| TC6 | Confidence validation | Composite and band fields populated with valid values, then invalid band tested | Valid data succeeds; invalid band fails |
| TC7 | Spatial hints optional | Envelope with `layout_info.available=False` and one with positioned element summary | Both validate |

## 5. Integration Point

Called by later features:

- F04 source loading populates `PdfSource`.
- F05 Mistral API pass populates `MistralMetadata`.
- F06 page normalization populates `Stats` and joined markdown paths.
- F07 parser populates `Notice`, `ExtractedTable`, and `Corrigendum`.
- F08 scoring populates `ConfidenceScores`, `DocumentConfidence`, and `LayoutInfo`.
- F09 validates final `Envelope`.
- F10 uses `Bundles` and `GazetteConfig`.
- F11 generates JSON Schema from these models.

Target module layout:

```text
gazette_mistral_pipeline/models/
  __init__.py
  base.py
  bundles.py
  config.py
  envelope.py
  notice.py
  source.py
```

### `base.py`

Create:

```python
class StrictBase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=False,
    )
```

### `source.py`

Create:

- `PdfSource`
- `MistralMetadata`

Suggested fields:

```python
class PdfSource(StrictBase):
    source_type: Literal["pdf_url", "local_pdf"]
    source_value: str
    run_name: str
    source_sha256: str | None = None
    source_metadata_path: str | None = None


class MistralMetadata(StrictBase):
    model: str
    raw_json_path: str | None = None
    raw_json_sha256: str | None = None
    document_url: str | None = None
    mistral_doc_ids: list[str] = Field(default_factory=list)
    page_count: int | None = None
    request_options: dict[str, Any] = Field(default_factory=dict)
```

### `notice.py`

Create:

- `Provenance`
- `ConfidenceScores`
- `ExtractedTable`
- `Notice`
- `Corrigendum`

Suggested fields:

```python
class Provenance(StrictBase):
    header_match: Literal["strict", "recovered", "inferred", "none"]
    page_span: tuple[int, int] | None = None
    line_span: tuple[int, int] | None = None
    raw_header_line: str | None = None
    source_markdown_path: str | None = None
    stitched_from: list[str] = Field(default_factory=list)


class ConfidenceScores(StrictBase):
    notice_number: float
    structure: float
    boundary: float
    table: float | None = None
    spatial: float | None = None
    composite: float
    band: Literal["high", "medium", "low"]


class ExtractedTable(StrictBase):
    model_config = ConfigDict(extra="allow", validate_assignment=True, str_strip_whitespace=False)
    headers: list[str]
    rows: list[list[str]]
    records: list[dict[str, str]] = Field(default_factory=list)
    raw_table_markdown: str
    source: str = "markdown_table_heuristic"
    column_count: int | None = None


class Notice(StrictBase):
    notice_id: str
    notice_no: str | None = None
    dates_found: list[str] = Field(default_factory=list)
    title_lines: list[str] = Field(default_factory=list)
    text: str
    raw_markdown: str
    tables: list[ExtractedTable] = Field(default_factory=list)
    table_count: int
    provenance: Provenance
    confidence_scores: ConfidenceScores
    confidence_reasons: list[str] = Field(default_factory=list)
    content_sha256: str
    other_attributes: dict[str, Any] = Field(default_factory=dict)
```

`Corrigendum` can be a lightweight placeholder in F03, because real parsing lands in F07:

```python
class Corrigendum(StrictBase):
    raw_text: str
    target_notice_no: str | None = None
    target_year: int | None = None
    amendment: str | None = None
    provenance: Provenance | None = None
```

### `envelope.py`

Create:

- `Stats`
- `LayoutInfo`
- `DocumentConfidence`
- `PipelineWarning`
- `Envelope`

Suggested fields:

```python
class Stats(StrictBase):
    document_count: int
    page_count: int
    notice_count: int
    table_count: int
    char_count_markdown: int
    warnings_count: int = 0


class LayoutInfo(StrictBase):
    available: bool = False
    layout_confidence: float | None = None
    pages: list[dict[str, Any]] = Field(default_factory=list)
    positioned_element_count: int = 0
    reasons: list[str] = Field(default_factory=list)


class DocumentConfidence(StrictBase):
    ocr_quality: float
    notice_split: float
    table_quality: float | None = None
    spatial: float | None = None
    composite: float
    counts: dict[Literal["high", "medium", "low"], int]
    mean_composite: float
    min_composite: float
    n_notices: int
    reasons: list[str] = Field(default_factory=list)


class PipelineWarning(StrictBase):
    kind: str
    message: str
    where: dict[str, Any] | None = None


class Envelope(StrictBase):
    library_version: str
    schema_version: str
    output_format_version: int
    generated_at_utc: datetime
    source: PdfSource
    mistral: MistralMetadata
    stats: Stats
    notices: list[Notice]
    tables: list[ExtractedTable] = Field(default_factory=list)
    corrigenda: list[Corrigendum] = Field(default_factory=list)
    document_confidence: DocumentConfidence
    layout_info: LayoutInfo
    warnings: list[PipelineWarning] = Field(default_factory=list)
```

### `bundles.py`

Create:

```python
class Bundles(StrictBase):
    envelope: bool = True
    joined_markdown: bool = True
    raw_mistral_json: bool = True
    source_metadata: bool = True
    notices: bool = False
    tables: bool = False
    document_index: bool = False
    debug_trace: bool = False
    json_schema: bool = Field(default=False, alias="schema")
```

`json_schema` keeps the external `schema` bundle alias while avoiding a field-name collision with Pydantic's inherited schema method.

### `config.py`

Create lightweight runtime config with no secrets stored in model defaults:

```python
class MistralOptions(StrictBase):
    model: str = "mistral-ocr-latest"
    api_key_env: str = "MISTRAL_API_KEY"
    timeout_seconds: float = 180.0


class RuntimeOptions(StrictBase):
    replay_raw_json_path: Path | None = None
    deterministic: bool = True


class GazetteConfig(StrictBase):
    mistral: MistralOptions = Field(default_factory=MistralOptions)
    runtime: RuntimeOptions = Field(default_factory=RuntimeOptions)
    bundles: Bundles = Field(default_factory=Bundles)
```

### Root exports

Update `gazette_mistral_pipeline/__init__.py` to re-export:

- `Envelope`
- `PdfSource`
- `MistralMetadata`
- `Notice`
- `ExtractedTable`
- `Corrigendum`
- `ConfidenceScores`
- `Provenance`
- `Stats`
- `LayoutInfo`
- `DocumentConfidence`
- `PipelineWarning`
- `Bundles`
- `GazetteConfig`
- `MistralOptions`
- `RuntimeOptions`

The parse/write functions stay stubs until F10, but type hints may use these models where practical.

## 6. Pass/Fail Criteria

| Check | How to verify |
|-------|---------------|
| Pydantic dependency present | `pyproject.toml` includes `pydantic>=2.0` |
| Imports work | `from gazette_mistral_pipeline.models import Envelope, Notice, Bundles, GazetteConfig` |
| Root exports work | `from gazette_mistral_pipeline import Envelope, Bundles, GazetteConfig` |
| Valid envelope validates | `Envelope.model_validate(valid_payload)` succeeds |
| Strict extras rejected | `pytest` confirms `extra_forbidden` on strict models |
| Table extras preserved | `ExtractedTable.model_validate(...)` keeps an extra future field |
| No live Mistral dependency | Tests do not require `MISTRAL_API_KEY` or network |

## 7. Definition Of Done

- [x] `pydantic>=2.0` added to runtime dependencies.
- [x] `gazette_mistral_pipeline/models/` package created.
- [x] Strict base model implemented.
- [x] Source, Mistral metadata, notice, table, confidence, warning, layout, stats, envelope, bundles, and config models implemented.
- [x] Root package exports F03 model classes.
- [x] Existing F02 stubs still raise `NotImplementedError`.
- [x] Tests added in `tests/test_models.py`.
- [x] Existing `tests/test_package_skeleton.py` still passes.
- [x] `python -m pytest tests/test_package_skeleton.py tests/test_models.py` passes.
- [x] `PROGRESS.md` updated only after tests pass: F03 complete, F04 next, session log row added.

## 8. Open Questions And Risks

Q1. Should the model class be named `PipelineWarning` instead of `Warning`?

Recommended answer: yes. It avoids shadowing Python's built-in `Warning` while still serializing under the `warnings` envelope field.

Q2. Should `ExtractedTable` allow extra fields?

Recommended answer: yes. Table extraction will evolve, and this mirrors the Docling package's forward-compatible table model.

Q3. Should F03 add `jsonschema` now?

Recommended answer: no. F03 should add only `pydantic`; JSON Schema export and `jsonschema` land in F11.

Q4. Should `GazetteConfig` store an API key value?

Recommended answer: no. Store only `api_key_env`, defaulting to `MISTRAL_API_KEY`; the actual secret is read at runtime in F05.

Q5. Should local PDF upload details be modeled now?

Recommended answer: keep F03 generic. `PdfSource.source_type` and `MistralMetadata.request_options` are enough for F04/F05 to fill in the correct API path later.
