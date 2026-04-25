"""Mistral OCR request, cache, and replay helpers."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gazette_mistral_pipeline.models import GazetteConfig, MistralMetadata, PdfSource

MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
MISTRAL_FILES_URL = "https://api.mistral.ai/v1/files"


@dataclass(frozen=True)
class MistralOcrResult:
    """Raw Mistral OCR JSON plus package metadata for later pipeline stages."""

    raw_json: Any
    metadata: MistralMetadata


def run_mistral_ocr(
    source: PdfSource,
    *,
    config: GazetteConfig | None = None,
    cache_dir: str | Path,
) -> MistralOcrResult:
    """Call live Mistral OCR or replay cached raw JSON for one resolved source."""

    resolved_config = config or GazetteConfig()

    if resolved_config.runtime.replay_raw_json_path is not None:
        replay_path = Path(resolved_config.runtime.replay_raw_json_path)
        raw_json, raw_bytes = _read_raw_mistral_json(replay_path)
        raw_json_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        metadata = _metadata_from_raw_json(
            raw_json,
            source=source,
            raw_json_path=replay_path,
            raw_json_sha256=raw_json_sha256,
            config=resolved_config,
            document_url=_document_url_for_source(source),
            replay=True,
        )
        return MistralOcrResult(raw_json=raw_json, metadata=metadata)

    if source.source_type not in {"pdf_url", "local_pdf"}:
        raise ValueError(f"Unsupported PDF source type for Mistral OCR: {source.source_type!r}")

    api_key = _resolve_api_key(resolved_config)
    uploaded_file: dict[str, Any] | None = None
    if source.source_type == "local_pdf":
        uploaded_file = upload_local_pdf_to_mistral(
            Path(source.source_value),
            api_key=api_key,
            timeout_seconds=resolved_config.mistral.timeout_seconds,
        )
        body = build_file_id_ocr_body(str(uploaded_file["id"]), model=resolved_config.mistral.model)
    else:
        body = build_document_url_ocr_body(source, model=resolved_config.mistral.model)

    raw_json = _post_json(
        MISTRAL_OCR_URL,
        body,
        api_key=api_key,
        timeout_seconds=resolved_config.mistral.timeout_seconds,
    )
    _validate_supported_raw_json_shape(raw_json)

    raw_json_path = Path(cache_dir) / f"{source.run_name}.raw.json"
    raw_json_sha256 = write_raw_mistral_json(raw_json, raw_json_path)
    metadata = _metadata_from_raw_json(
        raw_json,
        source=source,
        raw_json_path=raw_json_path,
        raw_json_sha256=raw_json_sha256,
        config=resolved_config,
        document_url=source.source_value if source.source_type == "pdf_url" else None,
        replay=False,
        uploaded_file=uploaded_file,
    )
    return MistralOcrResult(raw_json=raw_json, metadata=metadata)


def load_raw_mistral_json(path: str | Path) -> Any:
    """Load cached Mistral raw JSON for replay without normalizing pages."""

    raw_json, _ = _read_raw_mistral_json(Path(path))
    return raw_json


def write_raw_mistral_json(payload: Any, path: str | Path) -> str:
    """Write canonical raw JSON and return the written bytes' SHA-256."""

    raw_json_path = Path(path)
    raw_json_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = _canonical_json_bytes(payload)
    raw_json_path.write_bytes(raw_bytes)
    return hashlib.sha256(raw_bytes).hexdigest()


def build_document_url_ocr_body(source: PdfSource, *, model: str) -> dict[str, Any]:
    """Build the Mistral OCR body for a PDF URL source."""

    if source.source_type != "pdf_url":
        raise ValueError("document_url OCR requests require a pdf_url source")

    return {
        "model": model,
        "document": {
            "type": "document_url",
            "document_url": source.source_value,
        },
    }


def build_file_id_ocr_body(file_id: str, *, model: str) -> dict[str, Any]:
    """Build the Mistral OCR body for a previously uploaded file."""

    if not file_id.strip():
        raise ValueError("file_id OCR requests require a non-empty file_id")

    return {
        "model": model,
        "document": {
            "file_id": file_id,
        },
    }


def upload_local_pdf_to_mistral(
    path: str | Path,
    *,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Upload a local PDF to Mistral Files API and return the JSON file object."""

    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Local PDF does not exist: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected local PDF path to end with .pdf, got: {pdf_path}")

    response = _post_multipart_file(
        MISTRAL_FILES_URL,
        pdf_path,
        fields={"purpose": "ocr"},
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    if not isinstance(response, dict):
        raise ValueError("Mistral file upload response was not a JSON object")
    file_id = response.get("id")
    if not isinstance(file_id, str) or not file_id.strip():
        raise ValueError("Mistral file upload response did not include a file id")
    return response


def _resolve_api_key(config: GazetteConfig) -> str:
    env_name = config.mistral.api_key_env
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        raise OSError(
            f"Missing Mistral API key in environment variable {env_name!r}; "
            "set it for live OCR or configure runtime.replay_raw_json_path."
        )
    return api_key


def _post_json(
    url: str,
    body: dict[str, Any],
    *,
    api_key: str,
    timeout_seconds: float,
) -> Any:
    request = urllib.request.Request(
        url,
        data=_canonical_json_bytes(body),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_bytes = response.read()
    except urllib.error.HTTPError as exc:
        error_body = _sanitize_error_text(_read_http_error_body(exc), api_key=api_key)
        detail = f": {error_body}" if error_body else ""
        raise RuntimeError(f"Mistral OCR HTTP error {exc.code}{detail}") from exc
    except urllib.error.URLError as exc:
        reason = _sanitize_error_text(str(exc.reason), api_key=api_key)
        raise RuntimeError(f"Mistral OCR request failed: {reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Mistral OCR request timed out") from exc

    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Mistral OCR response was not valid UTF-8 JSON") from exc


def _post_multipart_file(
    url: str,
    file_path: Path,
    *,
    fields: dict[str, str],
    api_key: str,
    timeout_seconds: float,
) -> Any:
    boundary = f"gazette-mistral-{uuid.uuid4().hex}"
    body = _multipart_form_data_bytes(
        fields=fields,
        file_field_name="file",
        file_path=file_path,
        boundary=boundary,
    )
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_bytes = response.read()
    except urllib.error.HTTPError as exc:
        error_body = _sanitize_error_text(_read_http_error_body(exc), api_key=api_key)
        detail = f": {error_body}" if error_body else ""
        raise RuntimeError(f"Mistral file upload HTTP error {exc.code}{detail}") from exc
    except urllib.error.URLError as exc:
        reason = _sanitize_error_text(str(exc.reason), api_key=api_key)
        raise RuntimeError(f"Mistral file upload request failed: {reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Mistral file upload request timed out") from exc

    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Mistral file upload response was not valid UTF-8 JSON") from exc


def _multipart_form_data_bytes(
    *,
    fields: dict[str, str],
    file_field_name: str,
    file_path: Path,
    boundary: str,
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{_escape_multipart_name(name)}"\r\n\r\n'.encode("ascii"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    filename = _escape_multipart_name(file_path.name)
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("ascii"),
            (
                f'Content-Disposition: form-data; name="{_escape_multipart_name(file_field_name)}"; '
                f'filename="{filename}"\r\n'
            ).encode("ascii"),
            b"Content-Type: application/pdf\r\n\r\n",
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("ascii"),
        ]
    )
    return b"".join(chunks)


def _escape_multipart_name(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _read_raw_mistral_json(path: Path) -> tuple[Any, bytes]:
    if not path.is_file():
        raise FileNotFoundError(f"Mistral replay raw JSON does not exist: {path}")

    raw_bytes = path.read_bytes()
    if not raw_bytes.strip():
        raise ValueError(f"Mistral replay raw JSON is empty: {path}")

    try:
        raw_json = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"Mistral replay raw JSON is not UTF-8: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Mistral replay raw JSON: {path}: {exc}") from exc

    _validate_supported_raw_json_shape(raw_json)
    return raw_json, raw_bytes


def _canonical_json_bytes(payload: Any) -> bytes:
    try:
        text = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Mistral raw JSON payload is not JSON serializable: {exc}") from exc
    return f"{text}\n".encode("utf-8")


def _metadata_from_raw_json(
    raw_json: Any,
    *,
    source: PdfSource,
    raw_json_path: Path,
    raw_json_sha256: str,
    config: GazetteConfig,
    document_url: str | None,
    replay: bool,
    uploaded_file: dict[str, Any] | None = None,
) -> MistralMetadata:
    _validate_supported_raw_json_shape(raw_json)

    request_options: dict[str, Any] = {
        "source_type": source.source_type,
        "model": config.mistral.model,
        "timeout_seconds": config.mistral.timeout_seconds,
        "replay": replay,
    }
    if source.source_type == "pdf_url":
        request_options["document_type"] = "document_url"
    elif source.source_type == "local_pdf":
        request_options["document_type"] = "file_id"
        if uploaded_file is not None:
            request_options["uploaded_file_id"] = uploaded_file.get("id")
            request_options["uploaded_file_name"] = uploaded_file.get("filename")
            request_options["uploaded_file_bytes"] = uploaded_file.get("bytes")

    return MistralMetadata(
        model=_extract_model(raw_json, fallback=config.mistral.model),
        raw_json_path=str(raw_json_path),
        raw_json_sha256=raw_json_sha256,
        document_url=document_url,
        mistral_doc_ids=_extract_mistral_doc_ids(raw_json),
        page_count=_count_pages(raw_json),
        request_options=request_options,
    )


def _document_url_for_source(source: PdfSource) -> str | None:
    if source.source_type == "pdf_url":
        return source.source_value
    return None


def _validate_supported_raw_json_shape(raw_json: Any) -> None:
    if isinstance(raw_json, dict) and _is_pages_object(raw_json):
        return
    if isinstance(raw_json, list):
        if _is_block_list_with_pages(raw_json) or _is_legacy_page_list(raw_json):
            return
    raise ValueError(
        "Unsupported Mistral raw JSON shape; expected an object with pages, "
        "a list of objects with pages, or a legacy page list with markdown."
    )


def _is_pages_object(value: dict[str, Any]) -> bool:
    return isinstance(value.get("pages"), list)


def _is_block_list_with_pages(value: list[Any]) -> bool:
    return bool(value) and all(isinstance(item, dict) and isinstance(item.get("pages"), list) for item in value)


def _is_legacy_page_list(value: list[Any]) -> bool:
    return bool(value) and all(isinstance(item, dict) and "markdown" in item for item in value)


def _count_pages(raw_json: Any) -> int | None:
    if isinstance(raw_json, dict) and _is_pages_object(raw_json):
        return len(raw_json["pages"])
    if isinstance(raw_json, list) and _is_block_list_with_pages(raw_json):
        return sum(len(item["pages"]) for item in raw_json)
    if isinstance(raw_json, list) and _is_legacy_page_list(raw_json):
        return len(raw_json)
    return None


def _extract_model(raw_json: Any, *, fallback: str) -> str:
    if isinstance(raw_json, dict) and isinstance(raw_json.get("model"), str) and raw_json["model"]:
        return raw_json["model"]
    if isinstance(raw_json, list):
        for item in raw_json:
            if isinstance(item, dict) and isinstance(item.get("model"), str) and item["model"]:
                return item["model"]
    return fallback


def _extract_mistral_doc_ids(raw_json: Any) -> list[str]:
    ids: list[str] = []
    items: list[Any] = [raw_json]
    if isinstance(raw_json, list):
        items = list(raw_json)

    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("id", "document_id", "doc_id", "mistral_doc_id"):
            value = item.get(key)
            if value is None:
                continue
            doc_id = str(value)
            if doc_id and doc_id not in ids:
                ids.append(doc_id)
    return ids


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _sanitize_error_text(text: str, *, api_key: str) -> str:
    sanitized = text.replace(api_key, "[redacted]") if api_key else text
    sanitized = sanitized.replace("Authorization", "[redacted-header]")
    sanitized = sanitized.replace("authorization", "[redacted-header]")
    return sanitized[:1000]


__all__ = [
    "MISTRAL_OCR_URL",
    "MISTRAL_FILES_URL",
    "MistralOcrResult",
    "run_mistral_ocr",
    "load_raw_mistral_json",
    "write_raw_mistral_json",
    "build_document_url_ocr_body",
    "build_file_id_ocr_body",
    "upload_local_pdf_to_mistral",
]
