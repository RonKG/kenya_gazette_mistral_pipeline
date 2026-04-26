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
    usage_info: dict[str, Any] = Field(default_factory=dict)
    pages_processed: int | None = None
    doc_size_bytes: int | None = None
    estimated_ocr_cost_usd: float | None = None
    raw_response_bytes: int | None = None
    retry_attempts: int = 0
    returned_markdown_char_count: int | None = None
    returned_markdown_estimated_tokens: int | None = None
    returned_markdown_token_estimate_method: str | None = None
    request_options: dict[str, Any] = Field(default_factory=dict)
