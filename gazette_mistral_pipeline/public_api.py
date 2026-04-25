"""Public parse API wiring for the completed F04-F09 stages."""

from __future__ import annotations

from pathlib import Path

from gazette_mistral_pipeline.confidence_scoring import score_parsed_notices
from gazette_mistral_pipeline.envelope_builder import EnvelopeBuildInputs, build_envelope
from gazette_mistral_pipeline.mistral_ocr import run_mistral_ocr
from gazette_mistral_pipeline.models import Envelope, GazetteConfig, PdfSource
from gazette_mistral_pipeline.notice_parsing import parse_joined_markdown
from gazette_mistral_pipeline.page_normalization import (
    StitchedMarkdownResult,
    compute_stats,
    normalize_mistral_pages,
    stitch_markdown_pages,
    write_joined_markdown,
)
from gazette_mistral_pipeline.source_loading import resolve_pdf_source


def parse_file(path: str | Path, *, config: GazetteConfig | None = None) -> Envelope:
    """Parse a local PDF file through replay OCR and return a validated envelope."""

    return parse_source(Path(path), config=config)


def parse_url(url: str, *, config: GazetteConfig | None = None) -> Envelope:
    """Parse a PDF URL and return a validated envelope."""

    return parse_source(url, config=config)


def parse_source(
    source: PdfSource | str | Path,
    *,
    config: GazetteConfig | None = None,
) -> Envelope:
    """Resolve one PDF source, run F04-F09, and return a validated envelope."""

    resolved_config = _coerce_config(config)
    resolved_source = resolve_pdf_source(source)
    _validate_runtime_mode(resolved_source, resolved_config)

    stage_dir = _stage_dir(resolved_config)
    ocr_result = run_mistral_ocr(
        resolved_source,
        config=resolved_config,
        cache_dir=stage_dir or Path("."),
    )

    pages = normalize_mistral_pages(ocr_result.raw_json)
    markdown = stitch_markdown_pages(pages)
    joined_path = None
    if stage_dir is not None:
        joined_path = write_joined_markdown(
            markdown,
            stage_dir / f"{resolved_source.run_name}_joined.md",
        )

    stats = compute_stats(pages, markdown)
    stitched = StitchedMarkdownResult(
        pages=pages,
        markdown=markdown,
        output_path=joined_path,
        **stats,
    )
    parsed = parse_joined_markdown(
        markdown,
        source_id=resolved_source.run_name,
        run_name=resolved_source.run_name,
        source_markdown_path=joined_path,
    )
    scored = score_parsed_notices(
        parsed,
        raw_mistral_json=ocr_result.raw_json,
        normalized_pages=pages,
    )

    return build_envelope(
        EnvelopeBuildInputs(
            source=resolved_source,
            mistral=ocr_result.metadata,
            f06_stats=stitched,
            parsed=parsed,
            scored=scored,
        )
    )


def _coerce_config(config: GazetteConfig | None) -> GazetteConfig:
    if config is None:
        return GazetteConfig()
    if isinstance(config, GazetteConfig):
        return config
    return GazetteConfig.model_validate(config)


def _stage_dir(config: GazetteConfig) -> Path | None:
    if config.runtime.output_dir is None:
        return None
    return Path(config.runtime.output_dir)


def _validate_runtime_mode(source: PdfSource, config: GazetteConfig) -> None:
    if config.runtime.replay_raw_json_path is not None:
        return

    if source.source_type == "local_pdf":
        raise NotImplementedError(
            "Live Mistral OCR for local PDF sources is not supported in F10; "
            "configure runtime.replay_raw_json_path for local PDF parsing."
        )

    if not config.runtime.allow_live_mistral:
        raise RuntimeError(
            "Live Mistral OCR is disabled by default; set "
            "runtime.allow_live_mistral=True and runtime.output_dir for live URL OCR."
        )

    if config.runtime.output_dir is None:
        raise ValueError(
            "Live Mistral OCR requires runtime.output_dir so raw OCR cache artifacts "
            "are written to an explicit stage directory."
        )


__all__ = [
    "parse_file",
    "parse_url",
    "parse_source",
]
