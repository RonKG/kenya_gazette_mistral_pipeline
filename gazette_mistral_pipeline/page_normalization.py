"""Normalize Mistral OCR pages and render joined markdown artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

        markdown = page.markdown.strip()
        if add_page_headers:
            chunks.append(f"---\n\n## Index {page.index}\n\n{markdown}")
        else:
            chunks.append(markdown)

    return _ensure_one_trailing_newline("\n\n".join(chunks).strip())


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
    "load_mistral_blocks",
    "normalize_mistral_pages",
    "stitch_markdown_pages",
    "write_joined_markdown",
    "compute_stats",
]
