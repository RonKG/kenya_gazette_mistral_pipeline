"""Source and Mistral OCR metadata models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from gazette_mistral_pipeline.models.base import StrictBase


class PdfSource(StrictBase):
    """Resolved PDF source for one pipeline run."""

    source_type: Literal["pdf_url", "local_pdf"]
    source_value: str
    run_name: str
    source_sha256: str | None = None
    source_metadata_path: str | None = None


class MistralMetadata(StrictBase):
    """Metadata for the Mistral OCR request and cached response."""

    model: str
    raw_json_path: str | None = None
    raw_json_sha256: str | None = None
    document_url: str | None = None
    mistral_doc_ids: list[str] = Field(default_factory=list)
    page_count: int | None = None
    request_options: dict[str, Any] = Field(default_factory=dict)
