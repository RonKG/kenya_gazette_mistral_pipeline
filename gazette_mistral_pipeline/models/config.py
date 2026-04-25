"""Runtime configuration models."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from gazette_mistral_pipeline.models.base import StrictBase
from gazette_mistral_pipeline.models.bundles import Bundles


class MistralOptions(StrictBase):
    """Mistral API options without storing secrets."""

    model: str = "mistral-ocr-latest"
    api_key_env: str = "MISTRAL_API_KEY"
    timeout_seconds: float = 180.0


class RuntimeOptions(StrictBase):
    """Runtime controls for deterministic and replayed runs."""

    replay_raw_json_path: Path | None = None
    output_dir: Path | None = None
    allow_live_mistral: bool = False
    deterministic: bool = True


class GazetteConfig(StrictBase):
    """Top-level configuration for parse functions and bundle writing."""

    mistral: MistralOptions = Field(default_factory=MistralOptions)
    runtime: RuntimeOptions = Field(default_factory=RuntimeOptions)
    bundles: Bundles = Field(default_factory=Bundles)
