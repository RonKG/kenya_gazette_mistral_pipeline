"""Notice, table, provenance, and confidence models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from gazette_mistral_pipeline.models.base import StrictBase


class Provenance(StrictBase):
    """Where a parsed notice or corrigendum came from."""

    header_match: Literal["strict", "recovered", "inferred", "none"]
    page_span: tuple[int, int] | None = None
    line_span: tuple[int, int] | None = None
    raw_header_line: str | None = None
    source_markdown_path: str | None = None
    stitched_from: list[str] = Field(default_factory=list)


class ConfidenceScores(StrictBase):
    """Per-notice confidence scores and band."""

    notice_number: float
    structure: float
    boundary: float
    composite: float
    band: Literal["high", "medium", "low"]
    table: float | None = None
    spatial: float | None = None


class ExtractedTable(StrictBase):
    """Markdown-derived table attached to a notice.

    This is the only model that allows extra fields so table extraction can
    evolve without breaking v1 consumers.
    """

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
        str_strip_whitespace=False,
    )

    headers: list[str]
    rows: list[list[str]]
    raw_table_markdown: str
    records: list[dict[str, str]] = Field(default_factory=list)
    source: str = "markdown_table_heuristic"
    column_count: int | None = None


class Corrigendum(StrictBase):
    """Lightweight corrigendum placeholder until F07 extraction."""

    raw_text: str
    target_notice_no: str | None = None
    target_year: int | None = None
    amendment: str | None = None
    provenance: Provenance | None = None


class Notice(StrictBase):
    """Parsed gazette notice."""

    notice_id: str
    text: str
    raw_markdown: str
    table_count: int
    provenance: Provenance
    confidence_scores: ConfidenceScores
    content_sha256: str
    notice_no: str | None = None
    dates_found: list[str] = Field(default_factory=list)
    title_lines: list[str] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    confidence_reasons: list[str] = Field(default_factory=list)
    other_attributes: dict[str, Any] = Field(default_factory=dict)
