"""Assemble F04-F08 outputs into a validated envelope."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from gazette_mistral_pipeline.__version__ import LIBRARY_VERSION, SCHEMA_VERSION
from gazette_mistral_pipeline.confidence_scoring import ScoredParsingResult
from gazette_mistral_pipeline.models.envelope import Envelope, PipelineWarning, Stats
from gazette_mistral_pipeline.models.notice import ExtractedTable, Notice
from gazette_mistral_pipeline.models.source import MistralMetadata, PdfSource
from gazette_mistral_pipeline.notice_parsing import ParsedMarkdownResult
from gazette_mistral_pipeline.page_normalization import StitchedMarkdownResult

OUTPUT_FORMAT_VERSION = 1

_F06_STAT_KEYS = ("document_count", "page_count", "char_count_markdown")


@dataclass(frozen=True)
class EnvelopeBuildInputs:
    """Narrow package-internal input shape for F09 envelope assembly."""

    source: PdfSource | Mapping[str, Any]
    mistral: MistralMetadata | Mapping[str, Any]
    f06_stats: Mapping[str, int] | StitchedMarkdownResult
    parsed: ParsedMarkdownResult
    scored: ScoredParsingResult


def build_envelope(
    inputs: EnvelopeBuildInputs,
    *,
    now: datetime | Callable[[], datetime] | None = None,
) -> Envelope:
    """Build and validate an ``Envelope`` from already-produced stage outputs."""

    if not isinstance(inputs, EnvelopeBuildInputs):
        raise TypeError("build_envelope expects an EnvelopeBuildInputs instance.")

    source = _validate_source(inputs.source)
    mistral = _validate_mistral(inputs.mistral)
    f06_stats = _extract_f06_stats(inputs.f06_stats)
    parsed = _validate_parsed(inputs.parsed)
    scored = _validate_scored(inputs.scored)
    generated_at_utc = _generated_at_utc(now)

    _validate_notice_counts(parsed, scored)
    notices = list(scored.scored_notices)
    _validate_notice_table_counts(parsed.notices)
    _validate_notice_table_counts(notices)

    tables = _flatten_scored_notice_tables(notices)
    _validate_table_counts(parsed, tables)

    warnings = list(scored.warnings)
    warnings.extend(_assembly_warnings(mistral=mistral, page_count=f06_stats["page_count"]))

    stats = Stats(
        document_count=f06_stats["document_count"],
        page_count=f06_stats["page_count"],
        notice_count=len(notices),
        table_count=len(tables),
        char_count_markdown=f06_stats["char_count_markdown"],
        warnings_count=len(warnings),
    )

    return Envelope(
        library_version=LIBRARY_VERSION,
        schema_version=SCHEMA_VERSION,
        output_format_version=OUTPUT_FORMAT_VERSION,
        generated_at_utc=generated_at_utc,
        source=source,
        mistral=mistral,
        stats=stats,
        notices=notices,
        tables=tables,
        corrigenda=list(parsed.corrigenda),
        document_confidence=scored.document_confidence,
        layout_info=scored.layout_info,
        warnings=warnings,
    )


def _validate_source(value: PdfSource | Mapping[str, Any]) -> PdfSource:
    if isinstance(value, PdfSource):
        return value
    if isinstance(value, Mapping):
        return PdfSource.model_validate(value)
    raise TypeError("source must be a PdfSource or mapping.")


def _validate_mistral(value: MistralMetadata | Mapping[str, Any]) -> MistralMetadata:
    if isinstance(value, MistralMetadata):
        return value
    if isinstance(value, Mapping):
        return MistralMetadata.model_validate(value)
    raise TypeError("mistral must be a MistralMetadata or mapping.")


def _extract_f06_stats(value: Mapping[str, int] | StitchedMarkdownResult) -> dict[str, int]:
    if isinstance(value, StitchedMarkdownResult):
        raw_stats = {
            "document_count": value.document_count,
            "page_count": value.page_count,
            "char_count_markdown": value.char_count_markdown,
        }
    elif isinstance(value, Mapping):
        raw_stats = dict(value)
    else:
        raise TypeError("f06_stats must be a StitchedMarkdownResult or mapping.")

    stats: dict[str, int] = {}
    for key in _F06_STAT_KEYS:
        if key not in raw_stats:
            raise ValueError(f"f06_stats is missing required count: {key}")
        count = raw_stats[key]
        if not isinstance(count, int) or isinstance(count, bool):
            raise ValueError(f"f06_stats {key} must be an integer.")
        if count < 0:
            raise ValueError(f"f06_stats {key} must be non-negative.")
        stats[key] = count
    return stats


def _validate_parsed(value: ParsedMarkdownResult) -> ParsedMarkdownResult:
    if not isinstance(value, ParsedMarkdownResult):
        raise TypeError("parsed must be a ParsedMarkdownResult.")
    return value


def _validate_scored(value: ScoredParsingResult) -> ScoredParsingResult:
    if not isinstance(value, ScoredParsingResult):
        raise TypeError("scored must be a ScoredParsingResult.")
    return value


def _generated_at_utc(
    now: datetime | Callable[[], datetime] | None,
) -> datetime:
    if now is None:
        value = datetime.now(timezone.utc)
    elif callable(now):
        value = now()
    else:
        value = now

    if not isinstance(value, datetime):
        raise TypeError("now must be None, a datetime, or a callable returning a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at_utc/now must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _validate_notice_counts(parsed: ParsedMarkdownResult, scored: ScoredParsingResult) -> None:
    parsed_notice_count = len(parsed.notices)
    scored_notice_count = len(scored.scored_notices)
    if parsed.notice_count != parsed_notice_count:
        raise ValueError(
            "notice_count mismatch: "
            f"parsed.notice_count={parsed.notice_count} but len(parsed.notices)={parsed_notice_count}."
        )
    if parsed.notice_count != scored_notice_count:
        raise ValueError(
            "notice_count mismatch: "
            f"parsed.notice_count={parsed.notice_count} but len(scored.scored_notices)={scored_notice_count}."
        )


def _validate_notice_table_counts(notices: tuple[Notice, ...] | list[Notice]) -> None:
    for notice in notices:
        actual_table_count = len(notice.tables)
        if notice.table_count != actual_table_count:
            raise ValueError(
                "table_count mismatch for notice "
                f"{notice.notice_id!r}: notice.table_count={notice.table_count} "
                f"but len(notice.tables)={actual_table_count}."
            )


def _flatten_scored_notice_tables(notices: list[Notice]) -> list[ExtractedTable]:
    return [table for notice in notices for table in notice.tables]


def _validate_table_counts(
    parsed: ParsedMarkdownResult,
    scored_tables: list[ExtractedTable],
) -> None:
    parsed_table_count = len(parsed.tables)
    scored_table_count = len(scored_tables)
    if parsed.table_count != parsed_table_count:
        raise ValueError(
            "table_count mismatch: "
            f"parsed.table_count={parsed.table_count} but len(parsed.tables)={parsed_table_count}."
        )
    if parsed.table_count != scored_table_count:
        raise ValueError(
            "table_count mismatch: "
            f"parsed.table_count={parsed.table_count} but scored notices contain {scored_table_count} tables."
        )


def _assembly_warnings(
    *,
    mistral: MistralMetadata,
    page_count: int,
) -> tuple[PipelineWarning, ...]:
    if mistral.page_count is None or mistral.page_count == page_count:
        return ()
    return (
        PipelineWarning(
            kind="page_count_mismatch",
            message=(
                "Mistral raw page count differs from normalized markdown page count; "
                "envelope stats use the normalized F06 page count."
            ),
            where={
                "mistral_page_count": mistral.page_count,
                "normalized_page_count": page_count,
            },
        ),
    )


__all__ = [
    "OUTPUT_FORMAT_VERSION",
    "EnvelopeBuildInputs",
    "build_envelope",
]
