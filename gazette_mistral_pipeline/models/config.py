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
    max_attempts: int = Field(default=3, ge=1)
    retry_base_delay_seconds: float = Field(default=1.0, ge=0)
    retry_max_delay_seconds: float = Field(default=30.0, ge=0)
    retry_status_codes: tuple[int, ...] = (408, 429, 500, 502, 503, 504)
    ocr_cost_per_1000_pages_usd: float = Field(default=1.0, ge=0)
    estimate_returned_markdown_tokens: bool = True
    markdown_token_estimate_chars_per_token: float = Field(default=4.0, gt=0)


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
