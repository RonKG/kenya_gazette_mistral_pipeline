"""Normalize Mistral OCR pages and render joined markdown artifacts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_BOUNDARY_NON_EMPTY_LIMIT = 5
_GAZETTE_TITLE_RE = re.compile(r"^\s*#{0,6}\s*THE\s+KENYA\s+GAZETTE\s*$", re.IGNORECASE)
_GAZETTE_DATE_RE = re.compile(
    r"^\s*\d{1,2}(?:st|nd|rd|th)\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December),\s+"
    r"\d{4}\s*$",
    re.IGNORECASE,
)
_PRINTED_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,5}\s*$")


@dataclass(frozen=True)
class NormalizedPage:
    """One non-empty markdown page normalized from a supported Mistral shape."""

    index: int
    original_page_index: int | None
    document_index: int
    document_id: str | None
    document_url: str | None
    model: str | None
    markdown: str
    raw_page_metadata: dict[str, Any]


@dataclass(frozen=True)
class StitchedMarkdownResult:
    """Joined markdown plus F06-owned counts for later envelope assembly."""

    pages: tuple[NormalizedPage, ...]
    markdown: str
    document_count: int
    page_count: int
    char_count_markdown: int
    output_path: Path | None = None


def load_mistral_blocks(source: str | Path | dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    """Load and shape-check raw Mistral JSON into document-like page blocks."""

    raw_json: Any = source
    if isinstance(source, (str, Path)):
        raw_json = _load_json_file(Path(source))

    if isinstance(raw_json, dict):
        _require_pages_list(raw_json)
        return [raw_json]

    if isinstance(raw_json, list):
        if not raw_json:
            raise ValueError(_unsupported_shape_message())
        if _looks_like_block_list(raw_json):
            for block in raw_json:
                _require_pages_list(block)
            return raw_json
        if _looks_like_legacy_page_list(raw_json):
            return [{"pages": raw_json}]
        if any(isinstance(item, dict) and "pages" in item for item in raw_json):
            for item in raw_json:
                if isinstance(item, dict) and "pages" in item:
                    _require_pages_list(item)
        raise ValueError(_unsupported_shape_message())

    raise ValueError(_unsupported_shape_message())


def normalize_mistral_pages(raw_json: Any) -> tuple[NormalizedPage, ...]:
    """Normalize supported raw Mistral OCR JSON shapes into page records."""

    blocks = load_mistral_blocks(raw_json)
    pages: list[NormalizedPage] = []

    for document_index, block in enumerate(blocks):
        sorted_pages = _sorted_pages(block["pages"])
        for page in sorted_pages:
            if not isinstance(page, dict):
                continue

            markdown = _page_markdown(page)
            if markdown is None:
                continue

            pages.append(
                NormalizedPage(
                    index=len(pages),
                    original_page_index=_parse_page_index(page.get("index")),
                    document_index=document_index,
                    document_id=_first_non_empty(block, ("id", "document_id", "doc_id", "mistral_doc_id")),
                    document_url=_first_non_empty(
                        block,
                        ("pdf_url", "document_url", "source_url", "url", "document_reference"),
                    ),
                    model=_first_non_empty(block, ("model",)),
                    markdown=markdown,
                    raw_page_metadata=_small_page_metadata(page),
                )
            )

    if not pages:
        raise ValueError("No non-empty markdown pages found in supported Mistral raw JSON.")

    return tuple(pages)


def stitch_markdown_pages(
    pages: Sequence[NormalizedPage],
    *,
    add_page_headers: bool = True,
    add_document_headers: bool = True,
    clean_running_headers: bool = True,
) -> str:
    """Render normalized pages into deterministic joined markdown."""

    if not pages:
        raise ValueError("Cannot stitch markdown: no normalized pages provided.")

    chunks: list[str] = []
    last_document_index: int | None = None

    for page in pages:
        if add_document_headers and page.document_index != last_document_index:
            chunks.append(f"---\n\n# Document: {_document_title(page)}")
            last_document_index = page.document_index

        markdown = page.markdown
        if clean_running_headers:
            markdown = clean_page_running_headers(markdown, page_index=page.index)
        markdown = markdown.strip()
        if add_page_headers:
            chunks.append(f"---\n\n## Index {page.index}\n\n{markdown}")
        else:
            chunks.append(markdown)

    return _ensure_one_trailing_newline("\n\n".join(chunks).strip())


def clean_page_running_headers(markdown: str, *, page_index: int) -> str:
    """Remove conservative gazette running header/footer lines from one stitched page."""

    if page_index == 0 or not markdown.strip():
        return markdown

    lines = markdown.splitlines()
    changed = False

    top_span = _boundary_token_span(lines, from_top=True)
    if top_span is not None:
        lines = lines[top_span[1] :]
        lines = _drop_leading_blank_lines(lines)
        changed = True

    bottom_span = _boundary_token_span(lines, from_top=False)
    if bottom_span is not None:
        lines = lines[: bottom_span[0]]
        lines = _drop_trailing_blank_lines(lines)
        changed = True

    if not changed:
        return markdown
    return "\n".join(lines)


def write_joined_markdown(markdown: str, path: str | Path) -> Path:
    """Write one UTF-8 joined markdown artifact and return its path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_ensure_one_trailing_newline(markdown), encoding="utf-8")
    return output_path


def compute_stats(pages: Sequence[NormalizedPage], markdown: str) -> dict[str, int]:
    """Return F06-owned markdown/page counts for later Stats assembly."""

    return {
        "document_count": len({page.document_index for page in pages}),
        "page_count": len(pages),
        "char_count_markdown": len(markdown),
    }


def _load_json_file(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Mistral raw JSON file does not exist: {path}")

    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError(f"Mistral raw JSON file is empty: {path}")

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Mistral raw JSON: {path}: {exc}") from exc


def _require_pages_list(block: dict[str, Any]) -> None:
    if "pages" not in block:
        raise ValueError(_unsupported_shape_message())
    if not isinstance(block["pages"], list):
        raise ValueError("Mistral raw JSON pages field must be a list.")


def _looks_like_block_list(items: list[Any]) -> bool:
    return all(isinstance(item, dict) and "pages" in item for item in items)


def _looks_like_legacy_page_list(items: list[Any]) -> bool:
    return all(isinstance(item, dict) and "markdown" in item for item in items)


def _unsupported_shape_message() -> str:
    return (
        "Unsupported Mistral raw JSON shape; expected an object with pages, "
        "a list of objects with pages, or a legacy page list with markdown."
    )


def _sorted_pages(pages: list[Any]) -> list[Any]:
    decorated = []
    for position, page in enumerate(pages):
        parsed_index = _parse_page_index(page.get("index")) if isinstance(page, dict) else None
        sort_group = 0 if parsed_index is not None else 1
        sort_index = parsed_index if parsed_index is not None else 0
        decorated.append((sort_group, sort_index, position, page))
    return [page for _, _, _, page in sorted(decorated)]


def _parse_page_index(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _page_markdown(page: dict[str, Any]) -> str | None:
    markdown = page.get("markdown")
    if not isinstance(markdown, str):
        return None
    if not markdown.strip():
        return None
    return markdown


def _boundary_token_span(lines: Sequence[str], *, from_top: bool) -> tuple[int, int] | None:
    token_lines: list[tuple[int, str]] = []
    indexes = range(len(lines)) if from_top else range(len(lines) - 1, -1, -1)

    for index in indexes:
        line = lines[index]
        if not line.strip():
            continue

        if len(token_lines) >= _BOUNDARY_NON_EMPTY_LIMIT:
            break

        token_kind = _running_header_token_kind(line)
        if token_kind is None:
            break

        token_lines.append((index, token_kind))

    if not _looks_like_running_header_block(token_lines):
        return None

    token_indexes = [index for index, _ in token_lines]
    return min(token_indexes), max(token_indexes) + 1


def _running_header_token_kind(line: str) -> str | None:
    if _GAZETTE_TITLE_RE.match(line):
        return "title"
    if _GAZETTE_DATE_RE.match(line):
        return "date"
    if _PRINTED_PAGE_NUMBER_RE.match(line):
        return "page_number"
    return None


def _looks_like_running_header_block(token_lines: Sequence[tuple[int, str]]) -> bool:
    token_kinds = {kind for _, kind in token_lines}
    if "title" not in token_kinds:
        return False
    return "date" in token_kinds or "page_number" in token_kinds


def _drop_leading_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    return lines[start:]


def _drop_trailing_blank_lines(lines: list[str]) -> list[str]:
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    return lines[:end]


def _first_non_empty(block: dict[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = block.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _small_page_metadata(page: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key, value in page.items():
        if key == "markdown":
            continue
        if _is_json_scalar(value):
            metadata[key] = value
        elif isinstance(value, Mapping):
            if key in {"dimensions", "bbox", "bounds", "size"}:
                metadata[key] = dict(value)
            else:
                metadata[f"{key}_keys"] = sorted(str(item_key) for item_key in value.keys())
        elif _is_sequence_metadata(value):
            metadata[f"{key}_count"] = len(value)
    return metadata


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _is_sequence_metadata(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _document_title(page: NormalizedPage) -> str:
    if page.document_url:
        return page.document_url
    if page.document_id:
        return page.document_id
    return f"document_index={page.document_index}"


def _ensure_one_trailing_newline(text: str) -> str:
    return text.rstrip("\n") + "\n"


__all__ = [
    "NormalizedPage",
    "StitchedMarkdownResult",
    "clean_page_running_headers",
    "load_mistral_blocks",
    "normalize_mistral_pages",
    "stitch_markdown_pages",
    "write_joined_markdown",
    "compute_stats",
]
