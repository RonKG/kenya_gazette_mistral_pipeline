"""Lightweight Mistral OCR pipeline for Kenya Gazette PDFs.

F02 creates the installable package skeleton. The real pipeline lands across
F04-F10 after models and source handling are in place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gazette_mistral_pipeline.__version__ import (
    LIBRARY_VERSION,
    SCHEMA_VERSION,
    __version__,
)
from gazette_mistral_pipeline.models import (
    Bundles,
    ConfidenceScores,
    Corrigendum,
    DocumentConfidence,
    Envelope,
    ExtractedTable,
    GazetteConfig,
    LayoutInfo,
    MistralMetadata,
    MistralOptions,
    Notice,
    PdfSource,
    PipelineWarning,
    Provenance,
    RuntimeOptions,
    Stats,
)

__all__ = [
    "__version__",
    "parse_file",
    "parse_url",
    "parse_source",
    "write_envelope",
    "get_envelope_schema",
    "validate_envelope_json",
    "Envelope",
    "PdfSource",
    "MistralMetadata",
    "Notice",
    "ExtractedTable",
    "Corrigendum",
    "ConfidenceScores",
    "Provenance",
    "Stats",
    "LayoutInfo",
    "DocumentConfidence",
    "PipelineWarning",
    "Bundles",
    "GazetteConfig",
    "MistralOptions",
    "RuntimeOptions",
]


def _stub_message(name: str, feature: str) -> str:
    return (
        f"{name} is an F02 package skeleton stub; real implementation lands "
        f"in {feature}."
    )


def parse_file(path: str | Path, *, config: Any | None = None) -> Any:
    """Send a local PDF file through Mistral and return a validated envelope."""
    _ = (path, config)
    raise NotImplementedError(_stub_message("parse_file", "F10 after F04-F09"))


def parse_url(url: str, *, config: Any | None = None) -> Any:
    """Send a PDF URL through Mistral and return a validated envelope."""
    _ = (url, config)
    raise NotImplementedError(_stub_message("parse_url", "F10 after F04-F09"))


def parse_source(source: Any, *, config: Any | None = None) -> Any:
    """Resolve a PDF source, call Mistral, and return a validated envelope."""
    _ = (source, config)
    raise NotImplementedError(_stub_message("parse_source", "F10 after F04-F09"))


def write_envelope(
    env: Any,
    out_dir: str | Path,
    bundles: Any | None = None,
) -> dict[str, Path]:
    """Write selected output artifacts and return their paths."""
    _ = (env, out_dir, bundles)
    raise NotImplementedError(_stub_message("write_envelope", "F10"))


def get_envelope_schema(*, use_cache: bool = True) -> dict[str, Any]:
    """Return the JSON Schema for the envelope model."""
    _ = use_cache
    raise NotImplementedError(_stub_message("get_envelope_schema", "F11"))


def validate_envelope_json(data: dict[str, Any]) -> bool:
    """Validate a raw envelope dict against the package JSON Schema."""
    _ = data
    raise NotImplementedError(_stub_message("validate_envelope_json", "F11"))
