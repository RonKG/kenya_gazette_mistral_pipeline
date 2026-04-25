"""Resolve PDF inputs into deterministic source metadata."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from gazette_mistral_pipeline.models import PdfSource

SourceType = Literal["pdf_url", "local_pdf"]
SourceInput = str | Path | PdfSource

_KENYALAW_GAZETTE_RE = re.compile(
    r"/(?:akn/[^/]+/)?officialGazette/(\d{4}-\d{2}-\d{2})/(\d+)/",
    re.IGNORECASE,
)
_RUN_NAME_INVALID_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_RUN_NAME_UNDERSCORES_RE = re.compile(r"_+")


def derive_run_name(source_value: str | Path, *, source_type: str | None = None) -> str:
    """Return a stable sanitized run name for a PDF URL or local PDF path."""

    resolved_type = _coerce_source_type(source_value, source_type=source_type)

    if resolved_type == "pdf_url":
        url = _validate_pdf_url(str(source_value))
        parsed = urlparse(url)
        match = _KENYALAW_GAZETTE_RE.search(parsed.path)
        if match:
            return _sanitize_run_name(f"gazette_{match.group(1)}_{match.group(2)}")
        stem = Path(unquote(parsed.path)).stem
        return _sanitize_run_name(stem)

    path = Path(source_value)
    return _sanitize_run_name(path.stem)


def source_sha256(source_value: str | Path, *, source_type: str) -> str:
    """Hash local PDF bytes, or hash the normalized URL/source string."""

    resolved_type = _coerce_source_type(source_value, source_type=source_type)

    if resolved_type == "pdf_url":
        url = _validate_pdf_url(str(source_value))
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    path = _validate_local_pdf_path(source_value)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_pdf_source(
    source: SourceInput,
    *,
    run_name: str | None = None,
) -> PdfSource:
    """Resolve one PDF source into a validated ``PdfSource``."""

    if isinstance(source, PdfSource):
        if run_name is not None:
            data = source.model_dump()
            data["run_name"] = _sanitize_run_name(run_name)
            return PdfSource.model_validate(data)
        return source

    source_type = _coerce_source_type(source)

    if source_type == "pdf_url":
        source_value = _validate_pdf_url(str(source))
    else:
        source_value = str(_validate_local_pdf_path(source).resolve())

    resolved_run_name = (
        _sanitize_run_name(run_name)
        if run_name is not None
        else derive_run_name(source_value, source_type=source_type)
    )

    return PdfSource(
        source_type=source_type,
        source_value=source_value,
        run_name=resolved_run_name,
        source_sha256=source_sha256(source_value, source_type=source_type),
    )


def resolve_pdf_sources(
    sources: Iterable[SourceInput] | SourceInput,
) -> list[PdfSource]:
    """Resolve multiple PDF sources, or one JSON manifest path, into unique sources."""

    if isinstance(sources, PdfSource):
        resolved = [resolve_pdf_source(sources)]
    elif _looks_like_manifest_path(sources):
        manifest_path = Path(sources)
        manifest_items = load_source_manifest(manifest_path)
        resolved = []
        for item in manifest_items:
            source_value: str | Path = item["source_value"]
            if item["source_type"] == "local_pdf":
                if not _looks_like_url(item["source_value"]):
                    local_path = Path(item["source_value"])
                    source_value = local_path if local_path.is_absolute() else manifest_path.parent / local_path
            resolved.append(
                _resolve_pdf_source_with_type(
                    source_value,
                    source_type=item["source_type"],  # type: ignore[arg-type]
                    run_name=item.get("run_name"),
                )
            )
    elif isinstance(sources, (str, Path)):
        resolved = [resolve_pdf_source(sources)]
    else:
        resolved = [resolve_pdf_source(source) for source in sources]

    _ensure_unique_run_names(resolved)
    return resolved


def load_source_manifest(path: str | Path) -> list[dict[str, str]]:
    """Load and normalize a JSON source manifest."""

    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Source manifest does not exist: {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON source manifest: {manifest_path}: {exc}") from exc

    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        if "sources" not in data:
            raise ValueError(f"Source manifest must contain a 'sources' list: {manifest_path}")
        raw_items = data["sources"]
    else:
        raise ValueError(f"Source manifest must be an object or list: {manifest_path}")

    if not isinstance(raw_items, list):
        raise ValueError(f"Source manifest 'sources' must be a list: {manifest_path}")

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError(f"Source manifest item {index} must be an object")

        source_type = item.get("source_type", item.get("type"))
        source_value = item.get("source_value", item.get("value"))
        run_name = item.get("run_name")

        if source_type not in {"pdf_url", "local_pdf"}:
            raise ValueError(
                f"Source manifest item {index} has unsupported source_type: {source_type!r}"
            )
        if not isinstance(source_value, str) or not source_value.strip():
            raise ValueError(f"Source manifest item {index} is missing source_value")
        if run_name is not None and (not isinstance(run_name, str) or not run_name.strip()):
            raise ValueError(f"Source manifest item {index} has invalid run_name")

        output = {
            "source_type": source_type,
            "source_value": source_value.strip(),
        }
        if run_name is not None:
            output["run_name"] = run_name.strip()
        normalized.append(output)

    return normalized


def _resolve_pdf_source_with_type(
    source_value: str | Path,
    *,
    source_type: SourceType,
    run_name: str | None = None,
) -> PdfSource:
    if source_type == "pdf_url":
        resolved_value = _validate_pdf_url(str(source_value))
    else:
        resolved_value = str(_validate_local_pdf_path(source_value).resolve())

    resolved_run_name = (
        _sanitize_run_name(run_name)
        if run_name is not None
        else derive_run_name(resolved_value, source_type=source_type)
    )

    return PdfSource(
        source_type=source_type,
        source_value=resolved_value,
        run_name=resolved_run_name,
        source_sha256=source_sha256(resolved_value, source_type=source_type),
    )


def _coerce_source_type(
    source_value: str | Path,
    *,
    source_type: str | None = None,
) -> SourceType:
    if source_type is not None:
        if source_type not in {"pdf_url", "local_pdf"}:
            raise ValueError(f"Unsupported source_type: {source_type!r}")
        return source_type  # type: ignore[return-value]

    if isinstance(source_value, str) and _looks_like_url(source_value):
        return "pdf_url"
    return "local_pdf"


def _validate_pdf_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Expected an HTTP(S) PDF URL, got: {value}")
    if not parsed.path.lower().endswith(".pdf"):
        raise ValueError(f"Expected URL path to end with .pdf, got: {value}")
    return url


def _validate_local_pdf_path(value: str | Path) -> Path:
    if isinstance(value, str) and _looks_like_url(value):
        raise ValueError(f"Expected local PDF path, got URL: {value}")
    path = Path(value)
    if not path.is_file():
        raise FileNotFoundError(f"Local PDF does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected local PDF path to end with .pdf, got: {path}")
    return path


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return bool(parsed.scheme and parsed.netloc)


def _sanitize_run_name(value: str) -> str:
    sanitized = _RUN_NAME_INVALID_RE.sub("_", value.strip())
    sanitized = _RUN_NAME_UNDERSCORES_RE.sub("_", sanitized).strip("_")
    if not sanitized:
        raise ValueError(f"Could not derive a run name from: {value!r}")
    return sanitized


def _looks_like_manifest_path(value: Any) -> bool:
    return isinstance(value, (str, Path)) and Path(value).suffix.lower() == ".json"


def _ensure_unique_run_names(sources: list[PdfSource]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for source in sources:
        if source.run_name in seen:
            duplicates.add(source.run_name)
        seen.add(source.run_name)

    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate resolved run_name values: {names}")


__all__ = [
    "derive_run_name",
    "source_sha256",
    "resolve_pdf_source",
    "resolve_pdf_sources",
    "load_source_manifest",
]
