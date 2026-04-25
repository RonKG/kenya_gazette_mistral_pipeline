"""Top-level envelope and supporting models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from gazette_mistral_pipeline.models.base import StrictBase
from gazette_mistral_pipeline.models.notice import Corrigendum, ExtractedTable, Notice
from gazette_mistral_pipeline.models.source import MistralMetadata, PdfSource


class Stats(StrictBase):
    """Document-level extraction counts."""

    document_count: int
    page_count: int
    notice_count: int
    table_count: int
    char_count_markdown: int
    warnings_count: int = 0


class LayoutInfo(StrictBase):
    """Optional spatial hints derived from Mistral response JSON."""

    available: bool = False
    layout_confidence: float | None = None
    pages: list[dict[str, Any]] = Field(default_factory=list)
    positioned_element_count: int = 0
    reasons: list[str] = Field(default_factory=list)


class DocumentConfidence(StrictBase):
    """Aggregated confidence for one parsed gazette."""

    ocr_quality: float
    notice_split: float
    composite: float
    counts: dict[Literal["high", "medium", "low"], int]
    mean_composite: float
    min_composite: float
    n_notices: int
    table_quality: float | None = None
    spatial: float | None = None
    reasons: list[str] = Field(default_factory=list)


class PipelineWarning(StrictBase):
    """Structured pipeline warning."""

    kind: str
    message: str
    where: dict[str, Any] | None = None


class Envelope(StrictBase):
    """Validated output envelope for the Mistral pipeline."""

    library_version: str
    schema_version: str
    output_format_version: int
    generated_at_utc: datetime
    source: PdfSource
    mistral: MistralMetadata
    stats: Stats
    notices: list[Notice]
    document_confidence: DocumentConfidence
    layout_info: LayoutInfo
    tables: list[ExtractedTable] = Field(default_factory=list)
    corrigenda: list[Corrigendum] = Field(default_factory=list)
    warnings: list[PipelineWarning] = Field(default_factory=list)
