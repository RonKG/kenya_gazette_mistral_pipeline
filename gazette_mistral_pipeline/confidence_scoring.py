"""Deterministic F08 confidence scoring and spatial hint summaries."""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from gazette_mistral_pipeline.models.envelope import (
    DocumentConfidence,
    LayoutInfo,
    PipelineWarning,
)
from gazette_mistral_pipeline.models.notice import ConfidenceScores, Notice
from gazette_mistral_pipeline.notice_parsing import ParsedMarkdownResult
from gazette_mistral_pipeline.page_normalization import NormalizedPage

SCORER_VERSION = "F08"

_LEGAL_MARKER_RE = re.compile(
    r"\b(IN\s+EXERCISE|IT\s+IS\s+NOTIFIED|WHEREAS|TAKE\s+NOTICE)\b",
    re.IGNORECASE,
)
_SIGNATURE_RE = re.compile(
    r"\b(Cabinet Secretary|Principal Secretary|Registrar|Director|Chair(?:man|person)?|Governor|Commissioner)\b",
    re.IGNORECASE,
)
_NOTICE_HEADER_RE = re.compile(r"\bG[AR]ZETTE\s+NOTICE\s+NO\.?\s*(\d+)\b", re.IGNORECASE)
_NEXT_NOTICE_RE = re.compile(r"\bG[AR]ZETTE\s+NOTICE\s+NO\.?\s*\d+\b", re.IGNORECASE)
_COORD_KEYS = {
    "x",
    "y",
    "width",
    "height",
    "top",
    "left",
    "bottom",
    "right",
    "bbox",
    "bounds",
    "polygon",
    "points",
}


@dataclass(frozen=True)
class ScoredParsingResult:
    """Package-internal F08 result consumed by later envelope assembly."""

    scored_notices: tuple[Notice, ...]
    document_confidence: DocumentConfidence
    layout_info: LayoutInfo
    warnings: tuple[PipelineWarning, ...]
    scorer_version: str = SCORER_VERSION


@dataclass(frozen=True)
class _LayoutSummary:
    pages: list[dict[str, Any]]
    positioned_element_count: int
    malformed_coordinate_count: int
    page_count: int
    pages_with_dimensions: int
    text_bearing_pages: int | None
    saw_coordinate_like_metadata: bool


def score_band(score: float) -> Literal["high", "medium", "low"]:
    """Return the documented confidence band for a validated score."""

    value = _validate_score(score)
    if value >= 0.85:
        return "high"
    if value >= 0.60:
        return "medium"
    return "low"


def score_parsed_notices(
    parsed: ParsedMarkdownResult,
    *,
    raw_mistral_json: Any | None = None,
    normalized_pages: Sequence[NormalizedPage] | None = None,
) -> ScoredParsingResult:
    """Score parsed notices, summarize layout hints, and emit F08 warnings."""

    if not isinstance(parsed, ParsedMarkdownResult):
        raise TypeError("score_parsed_notices expects a ParsedMarkdownResult.")

    layout_info = summarize_layout_hints(
        raw_mistral_json,
        normalized_pages=normalized_pages,
    )
    all_notice_numbers = [notice.notice_no for notice in parsed.notices]
    scored_notices = tuple(
        _copy_notice_with_scores(
            notice,
            all_notice_numbers=all_notice_numbers,
            layout_info=layout_info,
        )
        for notice in parsed.notices
    )

    warnings = list(generate_pipeline_warnings(scored_notices, layout_info=layout_info))
    document_confidence = aggregate_document_confidence(
        scored_notices,
        layout_info=layout_info,
        warnings=warnings,
    )

    old_warning_count = len(warnings)
    document_warnings = list(
        generate_pipeline_warnings(
            scored_notices,
            layout_info=layout_info,
            document_confidence=document_confidence,
        )
    )
    for warning in document_warnings:
        if warning.kind not in {existing.kind for existing in warnings}:
            warnings.append(warning)

    if len(warnings) != old_warning_count:
        document_confidence = aggregate_document_confidence(
            scored_notices,
            layout_info=layout_info,
            warnings=warnings,
        )

    return ScoredParsingResult(
        scored_notices=scored_notices,
        document_confidence=document_confidence,
        layout_info=layout_info,
        warnings=tuple(warnings),
    )


def score_notice_confidence(
    notice: Notice,
    *,
    all_notice_numbers: Sequence[str | None] = (),
    layout_info: LayoutInfo | None = None,
) -> tuple[ConfidenceScores, list[str]]:
    """Score one notice without mutating the caller-owned model instance."""

    if not isinstance(notice, Notice):
        raise TypeError("score_notice_confidence expects a Notice.")

    reasons: list[str] = []
    notice_number = _score_notice_number(notice, reasons)
    structure = _score_structure(notice, reasons)
    boundary = _score_boundary(notice, all_notice_numbers, reasons)
    table = _score_tables(notice, reasons)
    spatial = _score_spatial(notice, layout_info, reasons) if layout_info else None
    composite = _weighted_composite(
        notice_number=notice_number,
        structure=structure,
        boundary=boundary,
        table=table,
        spatial=spatial,
    )

    scores = ConfidenceScores(
        notice_number=notice_number,
        structure=structure,
        boundary=boundary,
        table=table,
        spatial=spatial,
        composite=composite,
        band=score_band(composite),
    )
    return scores, reasons


def summarize_layout_hints(
    raw_mistral_json: Any | None = None,
    *,
    normalized_pages: Sequence[NormalizedPage] | None = None,
) -> LayoutInfo:
    """Summarize optional Mistral page/spatial metadata without geometry joins."""

    if normalized_pages is not None and not isinstance(normalized_pages, Sequence):
        raise TypeError("normalized_pages must be a sequence of NormalizedPage records.")

    pages = _layout_pages(raw_mistral_json, normalized_pages)
    if not pages:
        return LayoutInfo(
            available=False,
            layout_confidence=None,
            pages=[],
            positioned_element_count=0,
            reasons=["no raw Mistral JSON or normalized page metadata provided"],
        )

    summary = _summarize_layout_pages(pages)
    reasons: list[str] = []
    available = summary.positioned_element_count > 0 or summary.pages_with_dimensions > 0

    if summary.positioned_element_count == 0:
        reasons.append("no coordinate metadata found")
    if summary.pages_with_dimensions < summary.page_count:
        reasons.append("page dimensions missing for some pages")
    if summary.malformed_coordinate_count:
        reasons.append("spatial metadata present but unusable in some coordinate fields")
    if summary.saw_coordinate_like_metadata and summary.positioned_element_count == 0:
        reasons.append("coordinate-like metadata was present but unusable")

    layout_confidence = (
        _layout_confidence(summary) if available and summary.positioned_element_count >= 0 else None
    )
    if not available:
        layout_confidence = None

    return LayoutInfo(
        available=available,
        layout_confidence=layout_confidence,
        pages=summary.pages,
        positioned_element_count=summary.positioned_element_count,
        reasons=_dedupe(reasons),
    )


def aggregate_document_confidence(
    notices: Sequence[Notice],
    *,
    layout_info: LayoutInfo,
    warnings: Sequence[PipelineWarning] = (),
) -> DocumentConfidence:
    """Aggregate scored notices into document-level confidence fields."""

    if not isinstance(layout_info, LayoutInfo):
        raise TypeError("aggregate_document_confidence expects a LayoutInfo.")

    n_notices = len(notices)
    if n_notices == 0:
        warning_penalty = min(0.15, len(warnings) * 0.03)
        composite = _clamp_score(0.20 - warning_penalty)
        return DocumentConfidence(
            ocr_quality=0.20,
            notice_split=0.0,
            composite=composite,
            counts={"high": 0, "medium": 0, "low": 0},
            mean_composite=0.0,
            min_composite=0.0,
            n_notices=0,
            table_quality=None,
            spatial=layout_info.layout_confidence if layout_info.available else None,
            reasons=_dedupe(["no notices parsed", *_warning_reasons(warnings)]),
        )

    composites = [_validate_score(notice.confidence_scores.composite) for notice in notices]
    boundaries = [_validate_score(notice.confidence_scores.boundary) for notice in notices]
    ocr_scores = [_ocr_text_quality_score(notice.raw_markdown or notice.text) for notice in notices]
    table_scores = [
        _validate_score(notice.confidence_scores.table)
        for notice in notices
        if notice.confidence_scores.table is not None
    ]
    counts = Counter(notice.confidence_scores.band for notice in notices)
    mean_composite = round(statistics.fmean(composites), 4)
    min_composite = round(min(composites), 4)
    notice_split = round(statistics.fmean(boundaries), 4)
    ocr_quality = round(statistics.fmean(ocr_scores), 4)
    table_quality = round(statistics.fmean(table_scores), 4) if table_scores else None
    spatial = layout_info.layout_confidence if layout_info.available else None

    components = [
        (mean_composite, 0.65),
        (notice_split, 0.15),
        (ocr_quality, 0.10),
    ]
    if table_quality is not None:
        components.append((table_quality, 0.05))
    if spatial is not None:
        components.append((spatial, 0.05))

    warning_penalty = min(0.15, len(warnings) * 0.03)
    composite = _clamp_score(_weighted_average(components) - warning_penalty)
    reasons: list[str] = []
    if counts["low"]:
        reasons.append(f"{counts['low']} low-confidence notice(s)")
    if min_composite < 0.60:
        reasons.append("minimum notice confidence is low")
    reasons.extend(_warning_reasons(warnings))

    return DocumentConfidence(
        ocr_quality=ocr_quality,
        notice_split=notice_split,
        composite=composite,
        counts={
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
        },
        mean_composite=mean_composite,
        min_composite=min_composite,
        n_notices=n_notices,
        table_quality=table_quality,
        spatial=spatial,
        reasons=_dedupe(reasons),
    )


def generate_pipeline_warnings(
    notices: Sequence[Notice],
    *,
    layout_info: LayoutInfo,
    document_confidence: DocumentConfidence | None = None,
) -> tuple[PipelineWarning, ...]:
    """Generate bounded F08 warnings for suspicious parser/scorer outputs."""

    warnings: list[PipelineWarning] = []
    if len(notices) == 0:
        warnings.append(
            PipelineWarning(
                kind="no_notices",
                message="No gazette notices were parsed from the joined markdown.",
            )
        )

    low_count = sum(1 for notice in notices if notice.confidence_scores.band == "low")
    if notices and low_count >= 3 and low_count / len(notices) >= 0.5:
        warnings.append(
            PipelineWarning(
                kind="many_low_confidence_notices",
                message="Many parsed notices have low confidence scores.",
                where={"low_count": low_count, "notice_count": len(notices)},
            )
        )

    if document_confidence is not None and document_confidence.composite < 0.45:
        warnings.append(
            PipelineWarning(
                kind="very_low_document_confidence",
                message="Document confidence is very low; manual review is recommended.",
                where={"composite": document_confidence.composite},
            )
        )

    if any("unusable" in reason or "malformed" in reason for reason in layout_info.reasons):
        warnings.append(
            PipelineWarning(
                kind="unusable_spatial_metadata",
                message="Coordinate-like spatial metadata was present but could not be used.",
            )
        )

    if any(page.get("has_text") is False for page in layout_info.pages) and not any(
        page.get("has_text") is True for page in layout_info.pages
    ):
        warnings.append(
            PipelineWarning(
                kind="no_text_pages",
                message="Raw page metadata did not contain any text-bearing pages.",
            )
        )

    deduped: list[PipelineWarning] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning.kind in seen:
            continue
        seen.add(warning.kind)
        deduped.append(warning)
    return tuple(deduped)


def _copy_notice_with_scores(
    notice: Notice,
    *,
    all_notice_numbers: Sequence[str | None],
    layout_info: LayoutInfo,
) -> Notice:
    scores, reasons = score_notice_confidence(
        notice,
        all_notice_numbers=all_notice_numbers,
        layout_info=layout_info,
    )
    return notice.model_copy(
        update={
            "confidence_scores": scores,
            "confidence_reasons": reasons,
        },
        deep=True,
    )


def _score_notice_number(notice: Notice, reasons: list[str]) -> float:
    score = 1.0
    notice_no = notice.notice_no
    raw_header = notice.provenance.raw_header_line or ""

    if not notice_no:
        reasons.append("notice number is missing")
        return 0.20
    if not notice_no.isdigit():
        reasons.append("notice number is not numeric")
        score -= 0.45
    if notice_no.isdigit() and len(notice_no) == 1:
        reasons.append("notice number has atypical single-digit length")
        score -= 0.25
    if len(notice_no) > 6:
        reasons.append("notice number is unusually long")
        score -= 0.25

    header_match = notice.provenance.header_match
    if header_match == "recovered":
        reasons.append("notice header was recovered from noisy OCR")
        score -= 0.20
    elif header_match == "inferred":
        reasons.append("notice header was inferred rather than matched")
        score -= 0.35
    elif header_match == "none":
        reasons.append("notice header provenance is missing")
        score -= 0.50

    if not raw_header:
        reasons.append("raw notice header line is missing")
        score -= 0.15
    elif "GRZETTE" in raw_header.upper():
        reasons.append("raw notice header contains OCR spelling variant")
        score -= 0.10

    header_numbers = _NOTICE_HEADER_RE.findall(raw_header)
    if header_numbers and notice_no not in header_numbers:
        reasons.append("notice number does not match raw header line")
        score -= 0.30

    return _clamp_score(score)


def _score_structure(notice: Notice, reasons: list[str]) -> float:
    score = 1.0
    raw = notice.raw_markdown or notice.text
    body = _body_without_header(raw)
    readable_body = _readable_text(body)

    if not readable_body:
        reasons.append("notice body is empty after markdown stripping")
        score -= 0.60
    elif len(readable_body) < 40:
        reasons.append("notice body is very short")
        score -= 0.45
    elif len(readable_body) < 120 and not _LEGAL_MARKER_RE.search(readable_body):
        reasons.append("notice body is short and lacks a legal marker")
        score -= 0.25

    if not notice.title_lines:
        reasons.append("notice title lines are missing")
        score -= 0.15
    if not notice.dates_found:
        reasons.append("notice date markers are missing")
        score -= 0.10
    if not _LEGAL_MARKER_RE.search(raw):
        reasons.append("notice lacks common legal body markers")
        score -= 0.20
    if not (notice.tables or _SIGNATURE_RE.search(raw) or notice.dates_found):
        reasons.append("notice lacks signature, date, or table ending signals")
        score -= 0.10
    if len(readable_body) > 8000:
        reasons.append("notice body is unusually long and may include another notice")
        score -= 0.20

    score -= _ocr_quality_penalty(raw, reasons)
    return _clamp_score(score)


def _score_boundary(
    notice: Notice,
    all_notice_numbers: Sequence[str | None],
    reasons: list[str],
) -> float:
    score = 1.0
    provenance = notice.provenance

    if provenance.header_match == "recovered":
        reasons.append("notice boundary starts from a recovered/noisy header")
        score -= 0.20
    elif provenance.header_match == "inferred":
        reasons.append("notice boundary starts from an inferred header")
        score -= 0.35
    elif provenance.header_match == "none":
        reasons.append("notice boundary lacks a matched header")
        score -= 0.50

    if provenance.line_span is None:
        reasons.append("notice line span is missing")
        score -= 0.20
    else:
        start, end = provenance.line_span
        if end <= start:
            reasons.append("notice line span is empty or invalid")
            score -= 0.30

    if provenance.page_span is None and len(provenance.stitched_from) > 1:
        reasons.append("notice crosses pages without deterministic page span")
        score -= 0.15

    if notice.notice_no and all_notice_numbers.count(notice.notice_no) > 1:
        reasons.append("duplicate notice number appears in parsed batch")
        score -= 0.25

    raw_header_count = len(_NEXT_NOTICE_RE.findall(notice.raw_markdown))
    if raw_header_count > 1:
        reasons.append("notice body contains another notice header")
        score -= 0.30

    body = _readable_text(_body_without_header(notice.raw_markdown))
    if len(body) < 40:
        reasons.append("short body weakens notice boundary confidence")
        score -= 0.15
    if _contains_stitched_page_marker(_body_without_header(notice.raw_markdown)):
        reasons.append("stitched page marker appears inside notice body")
        score -= 0.10
    if body and not _has_clean_ending_signal(notice):
        reasons.append("notice ending lacks date, signature, table, or punctuation signal")
        score -= 0.10

    return _clamp_score(score)


def _score_tables(notice: Notice, reasons: list[str]) -> float | None:
    if not notice.tables:
        return None

    table_scores: list[float] = []
    for index, table in enumerate(notice.tables, start=1):
        score = 1.0
        prefix = f"table {index}"
        if not table.headers:
            reasons.append(f"{prefix} has no header row")
            score -= 0.30
        if not table.rows:
            reasons.append(f"{prefix} has no data rows")
            score -= 0.30
        if table.rows and not table.records:
            reasons.append(f"{prefix} has rows but no records")
            score -= 0.20
        if not table.raw_table_markdown.strip():
            reasons.append(f"{prefix} raw markdown is missing")
            score -= 0.20

        expected_columns = table.column_count or len(table.headers)
        if expected_columns:
            if any(len(row) != expected_columns for row in table.rows):
                reasons.append(f"{prefix} has inconsistent normalized column counts")
                score -= 0.25
            raw_widths = _raw_table_widths(table.raw_table_markdown)
            if raw_widths and any(width != expected_columns for width in raw_widths[2:]):
                reasons.append(f"{prefix} has ragged markdown rows")
                score -= 0.25

        cells = [cell for row in table.rows for cell in row]
        if cells:
            empty_ratio = sum(1 for cell in cells if not cell.strip()) / len(cells)
            if empty_ratio >= 0.25:
                reasons.append(f"{prefix} has sparse empty cells")
                score -= 0.20

        table_scores.append(_clamp_score(score))

    return round(statistics.fmean(table_scores), 4)


def _score_spatial(
    notice: Notice,
    layout_info: LayoutInfo | None,
    reasons: list[str],
) -> float | None:
    if layout_info is None or not layout_info.available:
        return None

    page_indexes = _notice_page_indexes(notice)
    if not page_indexes:
        return None

    layout_page_indexes = {
        page.get("page_index")
        for page in layout_info.pages
        if isinstance(page.get("page_index"), int)
    }
    if page_indexes.isdisjoint(layout_page_indexes):
        return None

    score = layout_info.layout_confidence if layout_info.layout_confidence is not None else 0.65
    score = _clamp_score(score)
    if score < 0.85:
        reasons.append("spatial hint is available but partial")
    return score


def _weighted_composite(
    *,
    notice_number: float,
    structure: float,
    boundary: float,
    table: float | None,
    spatial: float | None,
) -> float:
    components = [
        (notice_number, 0.25),
        (boundary, 0.25),
        (structure, 0.35),
    ]
    if table is not None:
        components.append((table, 0.10))
    if spatial is not None:
        components.append((spatial, 0.05))
    return _clamp_score(_weighted_average(components))


def _weighted_average(components: Sequence[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in components)
    if total_weight <= 0:
        raise ValueError("weighted average requires positive weights.")
    total = sum(_validate_score(score) * weight for score, weight in components)
    return round(total / total_weight, 4)


def _layout_pages(
    raw_mistral_json: Any | None,
    normalized_pages: Sequence[NormalizedPage] | None,
) -> list[dict[str, Any]]:
    if raw_mistral_json is not None:
        return _raw_pages(raw_mistral_json)
    if normalized_pages is None:
        return []

    pages: list[dict[str, Any]] = []
    for page in normalized_pages:
        if not isinstance(page, NormalizedPage):
            raise TypeError("normalized_pages must contain NormalizedPage records.")
        pages.append(
            {
                **page.raw_page_metadata,
                "index": page.original_page_index if page.original_page_index is not None else page.index,
                "markdown": page.markdown,
                "document_index": page.document_index,
            }
        )
    return pages


def _raw_pages(raw_json: Any) -> list[dict[str, Any]]:
    if isinstance(raw_json, Mapping):
        pages = raw_json.get("pages")
        if isinstance(pages, list):
            return [page for page in pages if isinstance(page, dict)]
    if isinstance(raw_json, list):
        if all(isinstance(item, Mapping) and isinstance(item.get("pages"), list) for item in raw_json):
            pages: list[dict[str, Any]] = []
            for item in raw_json:
                pages.extend(page for page in item["pages"] if isinstance(page, dict))
            return pages
        if all(isinstance(item, Mapping) and "markdown" in item for item in raw_json):
            return [page for page in raw_json if isinstance(page, dict)]
    raise ValueError(
        "Unsupported Mistral raw JSON shape for layout hints; expected pages object, "
        "block list, or legacy page list."
    )


def _summarize_layout_pages(pages: Sequence[dict[str, Any]]) -> _LayoutSummary:
    summaries: list[dict[str, Any]] = []
    total_positioned = 0
    total_malformed = 0
    pages_with_dimensions = 0
    text_flags: list[bool] = []
    saw_coordinate_like = False

    for fallback_index, page in enumerate(pages):
        page_index = _page_index(page, fallback_index)
        dimensions = _extract_dimensions(page)
        if dimensions is not None:
            pages_with_dimensions += 1

        positioned, malformed, saw_coordinate = _count_spatial_objects(page, is_page_root=True)
        total_positioned += positioned
        total_malformed += malformed
        saw_coordinate_like = saw_coordinate_like or saw_coordinate

        markdown = page.get("markdown")
        has_text = _has_text(markdown) if isinstance(markdown, str) else None
        if has_text is not None:
            text_flags.append(has_text)

        summary: dict[str, Any] = {
            "page_index": page_index,
            "positioned_elements": positioned,
        }
        if dimensions is not None:
            summary.update(dimensions)
        if has_text is not None:
            summary["has_text"] = has_text
        if malformed:
            summary["malformed_spatial_fields"] = malformed
        summaries.append(summary)

    return _LayoutSummary(
        pages=summaries,
        positioned_element_count=total_positioned,
        malformed_coordinate_count=total_malformed,
        page_count=len(pages),
        pages_with_dimensions=pages_with_dimensions,
        text_bearing_pages=sum(1 for flag in text_flags if flag) if text_flags else None,
        saw_coordinate_like_metadata=saw_coordinate_like,
    )


def _layout_confidence(summary: _LayoutSummary) -> float:
    if summary.page_count == 0:
        return 0.0
    dimension_coverage = summary.pages_with_dimensions / summary.page_count
    score = 0.45
    if summary.positioned_element_count:
        score += 0.30
    if dimension_coverage == 1:
        score += 0.20
    elif dimension_coverage > 0:
        score += 0.10
    if summary.malformed_coordinate_count:
        score -= 0.20
    return _clamp_score(score)


def _count_spatial_objects(value: Any, *, is_page_root: bool = False) -> tuple[int, int, bool]:
    if isinstance(value, Mapping):
        keys = {str(key) for key in value.keys()}
        dimension_only = _is_dimension_only(value)
        has_coordinate_key = bool(keys & _COORD_KEYS) and not dimension_only
        valid_coordinate = _is_valid_coordinate_object(value, is_page_root=is_page_root)
        count = 1 if valid_coordinate else 0
        malformed = 1 if has_coordinate_key and not valid_coordinate else 0
        saw_coordinate = has_coordinate_key

        if valid_coordinate:
            return count, malformed, saw_coordinate

        for child_key, child_value in value.items():
            if child_key == "markdown":
                continue
            child_count, child_malformed, child_saw = _count_spatial_objects(child_value)
            count += child_count
            malformed += child_malformed
            saw_coordinate = saw_coordinate or child_saw
        return count, malformed, saw_coordinate

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        count = 0
        malformed = 0
        saw_coordinate = False
        for item in value:
            child_count, child_malformed, child_saw = _count_spatial_objects(item)
            count += child_count
            malformed += child_malformed
            saw_coordinate = saw_coordinate or child_saw
        return count, malformed, saw_coordinate

    return 0, 0, False


def _is_valid_coordinate_object(value: Mapping[str, Any], *, is_page_root: bool = False) -> bool:
    if is_page_root and _is_dimension_only(value):
        return False
    if _valid_box(value.get("bbox")) or _valid_box(value.get("bounds")):
        return True
    if _valid_points(value.get("polygon")) or _valid_points(value.get("points")):
        return True

    numeric = {key for key in ("x", "y", "width", "height", "top", "left", "bottom", "right") if _is_number(value.get(key))}
    has_position = {"x", "y"}.issubset(numeric) or {"top", "left"}.issubset(numeric)
    has_extent = {"width", "height"}.issubset(numeric) or {"bottom", "right"}.issubset(numeric)
    return has_position and has_extent


def _is_dimension_only(value: Mapping[str, Any]) -> bool:
    keys = {str(key) for key in value.keys()}
    spatial_keys = keys & _COORD_KEYS
    return bool(spatial_keys) and spatial_keys <= {"width", "height"} and _is_number(value.get("width")) and _is_number(value.get("height"))


def _extract_dimensions(page: Mapping[str, Any]) -> dict[str, float] | None:
    for key in ("dimensions", "size"):
        value = page.get(key)
        if isinstance(value, Mapping) and _is_number(value.get("width")) and _is_number(value.get("height")):
            return {"width": float(value["width"]), "height": float(value["height"])}
    if _is_number(page.get("width")) and _is_number(page.get("height")):
        return {"width": float(page["width"]), "height": float(page["height"])}
    return None


def _valid_box(value: Any) -> bool:
    if isinstance(value, Mapping):
        if _is_number(value.get("x")) and _is_number(value.get("y")) and _is_number(value.get("width")) and _is_number(value.get("height")):
            return True
        if _is_number(value.get("left")) and _is_number(value.get("top")) and _is_number(value.get("right")) and _is_number(value.get("bottom")):
            return True
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) >= 4 and all(_is_number(item) for item in value[:4])
    return False


def _valid_points(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    if len(value) < 2:
        return False
    for item in value:
        if isinstance(item, Mapping):
            if not (_is_number(item.get("x")) and _is_number(item.get("y"))):
                return False
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            if len(item) < 2 or not (_is_number(item[0]) and _is_number(item[1])):
                return False
        else:
            return False
    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _notice_page_indexes(notice: Notice) -> set[int]:
    if notice.provenance.page_span is not None:
        start, end = notice.provenance.page_span
        return set(range(start, end + 1))

    indexes: set[int] = set()
    for stitched in notice.provenance.stitched_from:
        if not stitched.startswith("page:"):
            continue
        try:
            indexes.add(int(stitched.split(":", 1)[1]))
        except ValueError:
            continue
    return indexes


def _page_index(page: Mapping[str, Any], fallback: int) -> int:
    for key in ("index", "page_index", "pageNumber", "page_number"):
        value = page.get(key)
        if isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return fallback


def _has_text(markdown: str) -> bool:
    text = _readable_text(markdown)
    return bool(text.strip())


def _body_without_header(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(lines[1:]) if len(lines) > 1 else ""


def _readable_text(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---" or stripped.startswith("# Document:"):
            continue
        if stripped.startswith("!["):
            continue
        stripped = re.sub(r"^\s{0,3}#{1,6}\s*", "", stripped)
        stripped = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", stripped)
        stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
        stripped = stripped.replace("**", "").replace("__", "").replace("*", "").replace("`", "")
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _contains_stitched_page_marker(text: str) -> bool:
    return bool(re.search(r"^\s*##\s+Index\s+\d+\s*$", text, re.IGNORECASE | re.MULTILINE))


def _has_clean_ending_signal(notice: Notice) -> bool:
    if notice.tables or notice.dates_found:
        return True
    text = notice.raw_markdown.rstrip()
    return bool(_SIGNATURE_RE.search(text) or text.endswith((".", ")", "]")))


def _raw_table_widths(raw_table_markdown: str) -> list[int]:
    widths: list[int] = []
    for line in raw_table_markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        row = stripped[1:-1] if stripped.endswith("|") else stripped[1:]
        widths.append(len(row.split("|")))
    return widths


def _ocr_quality_penalty(text: str, reasons: list[str]) -> float:
    penalty = 0.0
    if "\ufffd" in text:
        reasons.append("text contains replacement characters")
        penalty += 0.20

    compact = re.sub(r"\s+", "", text)
    if compact:
        punctuation_ratio = sum(1 for char in compact if not char.isalnum()) / len(compact)
        if punctuation_ratio > 0.45:
            reasons.append("text has a high punctuation or OCR noise ratio")
            penalty += 0.15

    tokens = re.findall(r"\b\w+\b", text)
    if len(tokens) >= 20:
        one_char_ratio = sum(1 for token in tokens if len(token) == 1) / len(tokens)
        if one_char_ratio > 0.35:
            reasons.append("text has many broken one-character tokens")
            penalty += 0.15

    if text.strip() and not _readable_text(text).strip():
        reasons.append("markdown appears image-only after stripping")
        penalty += 0.25

    return penalty


def _ocr_text_quality_score(text: str) -> float:
    reasons: list[str] = []
    return _clamp_score(1.0 - _ocr_quality_penalty(text, reasons))


def _warning_reasons(warnings: Sequence[PipelineWarning]) -> list[str]:
    if not warnings:
        return []
    return [f"pipeline warning: {warning.kind}" for warning in warnings]


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _validate_score(score: float | None) -> float:
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ValueError("confidence score must be a number between 0.0 and 1.0.")
    if not math.isfinite(score) or score < 0.0 or score > 1.0:
        raise ValueError("confidence score must be between 0.0 and 1.0.")
    return float(score)


def _clamp_score(score: float) -> float:
    if not math.isfinite(score):
        raise ValueError("confidence score must be finite.")
    return round(max(0.0, min(1.0, score)), 4)


__all__ = [
    "SCORER_VERSION",
    "ScoredParsingResult",
    "aggregate_document_confidence",
    "generate_pipeline_warnings",
    "score_band",
    "score_notice_confidence",
    "score_parsed_notices",
    "summarize_layout_hints",
]
