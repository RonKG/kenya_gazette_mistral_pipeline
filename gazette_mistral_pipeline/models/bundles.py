"""Output bundle selection model."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from gazette_mistral_pipeline.models.base import StrictBase


class Bundles(StrictBase):
    """Which artifacts `write_envelope` should materialize."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=False,
        populate_by_name=True,
    )

    envelope: bool = True
    joined_markdown: bool = True
    raw_mistral_json: bool = True
    source_metadata: bool = True
    notices: bool = False
    tables: bool = False
    document_index: bool = False
    debug_trace: bool = False
    json_schema: bool = Field(default=False, alias="schema")
