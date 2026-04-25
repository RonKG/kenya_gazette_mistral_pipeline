"""Parse F06 joined markdown into notice, table, and corrigendum models."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from gazette_mistral_pipeline.models.notice import (
    ConfidenceScores,
    Corrigendum,
    ExtractedTable,
    Notice,
    Provenance,
)

PARSER_VERSION = "F07"
PENDING_CONFIDENCE_REASON = "pending F08 confidence scoring"

_NOTICE_HEADER_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(?P<kind>GAZETTE|GRZETTE)\s+NOTICE\s+NO\.?\s*(?P<notice_no>\d+)\b.*$",
    re.IGNORECASE,
)
_PAGE_HEADER_RE = re.compile(r"^\s*##\s+Index\s+(?P<page_index>\d+)\s*$", re.IGNORECASE)
_CORRIGENDUM_RE = re.compile(r"\bCORRIGEND(?:UM|A)\b", re.IGNORECASE)
_CORRIGENDUM_TARGET_RE = re.compile(
    r"\bGazette\s+Notice\s+No\.?\s*(?P<notice_no>\d+)(?:\s+of\s+(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+,\s+\d{4}\b")
_BODY_MARKER_RE = re.compile(
    r"^(?:IN\s+EXERCISE|WHEREAS|TAKE\s+NOTICE|IT\s+IS\s+NOTIFIED|Dated\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedMarkdownResult:
    """Package-internal F07 parser output for later envelope assembly."""

    notices: tuple[Notice, ...]
    tables: tuple[ExtractedTable, ...]
    corrigenda: tuple[Corrigendum, ...]
    notice_count: int
    table_count: int
    parser_version: str = PARSER_VERSION
    source_id: str | None = None


@dataclass(frozen=True)
class _NoticeHeader:
    line_index: int
    raw_line: str
    notice_no: str
    header_match: str


@dataclass(frozen=True)
class _PageContext:
    page_by_line: dict[int, int]
    page_header_lines: dict[int, int]


def parse_joined_markdown(
    markdown: str,
    *,
    source_id: str | None = None,
    run_name: str | None = None,
    source_markdown_path: str | Path | None = None,
) -> ParsedMarkdownResult:
    """Parse joined markdown into notices, tables, and corrigendum placeholders."""

    if not isinstance(markdown, str):
        raise TypeError("parse_joined_markdown expects markdown to be a str.")

    if not markdown.strip():
        return ParsedMarkdownResult(
            notices=(),
            tables=(),
            corrigenda=(),
            notice_count=0,
            table_count=0,
            source_id=source_id,
        )

    lines = markdown.splitlines()
    page_context = _page_context(lines)
    headers = tuple(_iter_notice_headers(lines))
    source_path = str(source_markdown_path) if source_markdown_path is not None else None

    notices: list[Notice] = []
    tables: list[ExtractedTable] = []
    corrigenda: list[Corrigendum] = []

    first_notice_line = headers[0].line_index if headers else len(lines)
    corrigenda.extend(
        _corrigenda_from_preamble(
            lines[:first_notice_line],
            source_path=source_path,
            page_context=page_context,
        )
    )

    for order, header in enumerate(headers, start=1):
        next_start = headers[order].line_index if order < len(headers) else len(lines)
        start, end = _trim_line_span(lines, header.line_index, next_start)
        raw_markdown = "\n".join(lines[start:end])
        content_sha256 = _sha256(raw_markdown)
        notice_tables = extract_markdown_tables(raw_markdown)
        provenance = _provenance(
            start=start,
            end=end,
            header_match=header.header_match,
            raw_header_line=header.raw_line.strip(),
            source_markdown_path=source_path,
            page_context=page_context,
        )
        is_corrigendum_candidate = _is_corrigendum_candidate(raw_markdown)
        notice = Notice(
            notice_id=_notice_id(
                run_name=run_name or source_id,
                line_start=start + 1,
                notice_order=order,
                notice_no=header.notice_no,
                content_sha256=content_sha256,
                provenance=provenance,
            ),
            notice_no=header.notice_no,
            dates_found=_dates_found(raw_markdown),
            title_lines=_title_lines(raw_markdown),
            text=_markdown_to_text(raw_markdown),
            raw_markdown=raw_markdown,
            tables=list(notice_tables),
            table_count=len(notice_tables),
            provenance=provenance,
            confidence_scores=neutral_confidence_scores(),
            confidence_reasons=[PENDING_CONFIDENCE_REASON],
            content_sha256=content_sha256,
            other_attributes={
                "parser_version": PARSER_VERSION,
                "notice_order": order,
                "header_text": header.raw_line.strip(),
                "is_corrigendum_candidate": is_corrigendum_candidate,
                "source_line_start": start + 1,
            },
        )
        notices.append(notice)
        tables.extend(notice_tables)

        if is_corrigendum_candidate:
            corrigenda.append(_corrigendum_from_notice(raw_markdown, provenance))

    return ParsedMarkdownResult(
        notices=tuple(notices),
        tables=tuple(tables),
        corrigenda=tuple(corrigenda),
        notice_count=len(notices),
        table_count=len(tables),
        source_id=source_id,
    )


def extract_markdown_tables(text: str) -> tuple[ExtractedTable, ...]:
    """Extract simple markdown pipe tables while preserving raw table text."""

    if not isinstance(text, str):
        raise TypeError("extract_markdown_tables expects text to be a str.")

    lines = text.splitlines()
    tables: list[ExtractedTable] = []
    i = 0

    while i < len(lines) - 1:
        header_line = lines[i].rstrip()
        separator_line = lines[i + 1].rstrip()
        if not (header_line.lstrip().startswith("|") and _is_separator_row(separator_line)):
            i += 1
            continue

        header_cells = _split_table_row(header_line)
        width = max(len(header_cells), len(_split_table_row(separator_line)), 1)
        headers = [
            cell or f"column_{idx}"
            for idx, cell in enumerate(_normalize_row(header_cells, width), start=1)
        ]
        raw_lines = [header_line, separator_line]
        rows: list[list[str]] = []
        i += 2

        while i < len(lines) and lines[i].lstrip().startswith("|"):
            raw_line = lines[i].rstrip()
            raw_lines.append(raw_line)
            if not _is_separator_row(raw_line):
                row = _normalize_row(_split_table_row(raw_line), width)
                if any(cell.strip() for cell in row):
                    rows.append(row)
            i += 1

        tables.append(
            ExtractedTable(
                headers=headers,
                rows=rows,
                records=[dict(zip(headers, row)) for row in rows],
                raw_table_markdown="\n".join(raw_lines),
                source="markdown_table_heuristic",
                column_count=width,
            )
        )

    return tuple(tables)


def neutral_confidence_scores(
    *,
    reason: str = PENDING_CONFIDENCE_REASON,
) -> ConfidenceScores:
    """Return deterministic medium-band placeholders until F08 scoring lands."""

    _ = reason
    return ConfidenceScores(
        notice_number=0.5,
        structure=0.5,
        boundary=0.5,
        table=None,
        spatial=None,
        composite=0.5,
        band="medium",
    )


def _iter_notice_headers(lines: list[str]) -> tuple[_NoticeHeader, ...]:
    headers: list[_NoticeHeader] = []
    for line_index, line in enumerate(lines):
        match = _NOTICE_HEADER_RE.match(line)
        if not match:
            continue
        kind = match.group("kind").upper()
        headers.append(
            _NoticeHeader(
                line_index=line_index,
                raw_line=line,
                notice_no=match.group("notice_no"),
                header_match="strict" if kind == "GAZETTE" else "recovered",
            )
        )
    return tuple(headers)


def _page_context(lines: list[str]) -> _PageContext:
    page_by_line: dict[int, int] = {}
    page_header_lines: dict[int, int] = {}
    current_page: int | None = None

    for line_index, line in enumerate(lines):
        match = _PAGE_HEADER_RE.match(line)
        if match:
            current_page = int(match.group("page_index"))
            page_header_lines[line_index] = current_page
        if current_page is not None:
            page_by_line[line_index] = current_page

    return _PageContext(page_by_line=page_by_line, page_header_lines=page_header_lines)


def _trim_line_span(lines: list[str], start: int, stop: int) -> tuple[int, int]:
    while start < stop and not lines[start].strip():
        start += 1
    while stop > start and not lines[stop - 1].strip():
        stop -= 1
    return start, stop


def _provenance(
    *,
    start: int,
    end: int,
    header_match: str,
    raw_header_line: str | None,
    source_markdown_path: str | None,
    page_context: _PageContext,
) -> Provenance:
    pages = _pages_for_span(start, end, page_context)
    page_span = (pages[0], pages[0]) if len(pages) == 1 else None
    return Provenance(
        header_match=header_match,  # type: ignore[arg-type]
        page_span=page_span,
        line_span=(start + 1, end),
        raw_header_line=raw_header_line,
        source_markdown_path=source_markdown_path,
        stitched_from=[f"page:{page_index}" for page_index in pages],
    )


def _pages_for_span(start: int, end: int, page_context: _PageContext) -> list[int]:
    pages: list[int] = []

    start_page = page_context.page_by_line.get(start)
    if start_page is not None:
        pages.append(start_page)

    for line_index, page_index in sorted(page_context.page_header_lines.items()):
        if start <= line_index < end and page_index not in pages:
            pages.append(page_index)

    return pages


def _notice_id(
    *,
    run_name: str | None,
    line_start: int,
    notice_order: int,
    notice_no: str | None,
    content_sha256: str,
    provenance: Provenance,
) -> str:
    first_page = None
    if provenance.stitched_from:
        first_page = provenance.stitched_from[0].split(":", 1)[1]
    location = f"page:{first_page}" if first_page is not None else f"line:{line_start}"
    suffix = notice_no or content_sha256[:12]
    if run_name:
        return f"{run_name}:{location}:{notice_order}:{suffix}"
    return f"joined:{line_start}:{notice_order}:{content_sha256[:12]}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dates_found(text: str) -> list[str]:
    return [match.group(0) for match in _DATE_RE.finditer(text)]


def _title_lines(raw_markdown: str) -> list[str]:
    lines = raw_markdown.splitlines()[1:]
    titles: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if titles:
                break
            continue
        if _is_f06_header_line(stripped) or _is_image_line(stripped):
            continue
        if stripped.startswith("|") or _BODY_MARKER_RE.match(stripped):
            break

        title = _strip_markdown_inline(stripped)
        if title:
            titles.append(title)
        if len(titles) >= 5:
            break

    return titles


def _markdown_to_text(raw_markdown: str) -> str:
    text_lines: list[str] = []
    for line in raw_markdown.splitlines():
        stripped = line.strip()
        if not stripped or _is_f06_header_line(stripped) or _is_separator_row(stripped):
            continue
        if stripped.startswith("|"):
            cells = _split_table_row(stripped)
            if cells:
                text_lines.append(" ".join(cell for cell in cells if cell))
            continue
        text_lines.append(_strip_markdown_inline(stripped))
    return "\n".join(line for line in text_lines if line)


def _strip_markdown_inline(text: str) -> str:
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text.strip())
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("*", "").replace("`", "")
    return text.strip()


def _is_f06_header_line(line: str) -> bool:
    return line == "---" or line.startswith("# Document:") or bool(_PAGE_HEADER_RE.match(line))


def _is_image_line(line: str) -> bool:
    return line.startswith("![")


def _is_corrigendum_candidate(text: str) -> bool:
    return bool(_CORRIGENDUM_RE.search(text) or _CORRIGENDUM_TARGET_RE.search(_body_without_header(text)))


def _corrigendum_from_notice(raw_markdown: str, provenance: Provenance) -> Corrigendum:
    target_notice_no, target_year = _corrigendum_target(_body_without_header(raw_markdown))
    return Corrigendum(
        raw_text=raw_markdown,
        target_notice_no=target_notice_no,
        target_year=target_year,
        amendment=None,
        provenance=provenance,
    )


def _corrigenda_from_preamble(
    lines: list[str],
    *,
    source_path: str | None,
    page_context: _PageContext,
) -> tuple[Corrigendum, ...]:
    for start, line in enumerate(lines):
        if _CORRIGENDUM_RE.search(line):
            raw_lines = lines[start:]
            raw_text = "\n".join(raw_lines).strip()
            if not raw_text:
                return ()
            target_notice_no, target_year = _corrigendum_target(raw_text)
            end = len(lines)
            provenance = _provenance(
                start=start,
                end=end,
                header_match="none",
                raw_header_line=line.strip(),
                source_markdown_path=source_path,
                page_context=page_context,
            )
            return (
                Corrigendum(
                    raw_text=raw_text,
                    target_notice_no=target_notice_no,
                    target_year=target_year,
                    amendment=None,
                    provenance=provenance,
                ),
            )
    return ()


def _corrigendum_target(text: str) -> tuple[str | None, int | None]:
    match = _CORRIGENDUM_TARGET_RE.search(text)
    if not match:
        return None, None
    year_text = match.group("year")
    return match.group("notice_no"), int(year_text) if year_text else None


def _body_without_header(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(lines[1:]) if len(lines) > 1 else ""


def _split_table_row(line: str) -> list[str]:
    row = line.strip()
    if not row.startswith("|"):
        return []
    row = row[1:-1] if row.endswith("|") else row[1:]
    return [cell.strip() for cell in row.split("|")]


def _is_separator_row(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(
        not cell.strip() or re.fullmatch(r":?-{3,}:?", cell.strip().replace(" ", ""))
        for cell in cells
    )


def _normalize_row(cells: list[str], width: int) -> list[str]:
    normalized = list(cells)
    if len(normalized) < width:
        normalized.extend([""] * (width - len(normalized)))
    elif len(normalized) > width:
        normalized = normalized[: width - 1] + [" | ".join(normalized[width - 1 :])]
    return normalized


__all__ = [
    "ParsedMarkdownResult",
    "extract_markdown_tables",
    "neutral_confidence_scores",
    "parse_joined_markdown",
]
