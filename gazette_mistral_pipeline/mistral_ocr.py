"""Mistral OCR request, cache, and replay helpers."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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


@dataclass(frozen=True)
class _JsonResponse:
    payload: Any
    raw_bytes: bytes
    attempts: int


class MistralRequestError(RuntimeError):
    """Sanitized Mistral request failure with retry context."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        attempts: int,
        retryable: bool,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.attempts = attempts
        self.retryable = retryable
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class MistralPayloadError(ValueError):
    """Sanitized Mistral response/replay payload failure."""


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
            raw_response_bytes=len(raw_bytes),
            retry_attempts=0,
        )
        return MistralOcrResult(raw_json=raw_json, metadata=metadata)

    if source.source_type not in {"pdf_url", "local_pdf"}:
        raise ValueError(f"Unsupported PDF source type for Mistral OCR: {source.source_type!r}")

    api_key = _resolve_api_key(resolved_config)
    uploaded_file: dict[str, Any] | None = None
    upload_attempts = 1
    if source.source_type == "local_pdf":
        upload_response = _upload_local_pdf_to_mistral_response(
            Path(source.source_value),
            api_key=api_key,
            config=resolved_config,
        )
        uploaded_file = _validate_uploaded_file_response(upload_response.payload)
        upload_attempts = upload_response.attempts
        body = build_file_id_ocr_body(str(uploaded_file["id"]), model=resolved_config.mistral.model)
    else:
        body = build_document_url_ocr_body(source, model=resolved_config.mistral.model)

    ocr_response = _post_json(
        MISTRAL_OCR_URL,
        body,
        api_key=api_key,
        config=resolved_config,
    )
    raw_json = ocr_response.payload
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
        raw_response_bytes=len(ocr_response.raw_bytes),
        retry_attempts=(upload_attempts - 1) + (ocr_response.attempts - 1),
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
    config: GazetteConfig | None = None,
) -> dict[str, Any]:
    """Upload a local PDF to Mistral Files API and return the JSON file object."""

    resolved_config = config or GazetteConfig(mistral={"timeout_seconds": timeout_seconds})
    response = _upload_local_pdf_to_mistral_response(
        path,
        api_key=api_key,
        config=resolved_config,
    )
    return _validate_uploaded_file_response(response.payload)


def _upload_local_pdf_to_mistral_response(
    path: str | Path,
    *,
    api_key: str,
    config: GazetteConfig,
) -> _JsonResponse:
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Local PDF does not exist: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected local PDF path to end with .pdf, got: {pdf_path}")

    return _post_multipart_file(
        MISTRAL_FILES_URL,
        pdf_path,
        fields={"purpose": "ocr"},
        api_key=api_key,
        config=config,
    )


def _validate_uploaded_file_response(response: Any) -> dict[str, Any]:
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
    config: GazetteConfig,
) -> _JsonResponse:
    request = urllib.request.Request(
        url,
        data=_canonical_json_bytes(body),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    return _send_json_request(
        request,
        api_key=api_key,
        config=config,
        endpoint_label="Mistral OCR",
    )


def _post_multipart_file(
    url: str,
    file_path: Path,
    *,
    fields: dict[str, str],
    api_key: str,
    config: GazetteConfig,
) -> _JsonResponse:
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

    return _send_json_request(
        request,
        api_key=api_key,
        config=config,
        endpoint_label="Mistral file upload",
    )


def _send_json_request(
    request: urllib.request.Request,
    *,
    api_key: str,
    config: GazetteConfig,
    endpoint_label: str,
) -> _JsonResponse:
    attempts = 0
    last_exc: BaseException | None = None

    while attempts < config.mistral.max_attempts:
        attempts += 1
        try:
            with urllib.request.urlopen(request, timeout=config.mistral.timeout_seconds) as response:
                raw_bytes = response.read()
            return _decode_json_response(raw_bytes, endpoint_label=endpoint_label, attempts=attempts)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            retryable = exc.code in config.mistral.retry_status_codes
            error_body = _sanitize_error_text(_read_http_error_body(exc), api_key=api_key)
            if retryable and attempts < config.mistral.max_attempts:
                _sleep_before_retry(exc, attempts=attempts, config=config)
                continue
            raise _request_error(
                endpoint_label,
                attempts=attempts,
                retryable=retryable,
                status_code=exc.code,
                detail=error_body,
                api_key=api_key,
            ) from exc
        except urllib.error.URLError as exc:
            last_exc = exc
            reason = _sanitize_error_text(str(exc.reason), api_key=api_key)
            if attempts < config.mistral.max_attempts:
                _sleep_before_retry(None, attempts=attempts, config=config)
                continue
            raise _request_error(
                endpoint_label,
                attempts=attempts,
                retryable=True,
                detail=reason,
                api_key=api_key,
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            last_exc = exc
            if attempts < config.mistral.max_attempts:
                _sleep_before_retry(None, attempts=attempts, config=config)
                continue
            raise _request_error(
                endpoint_label,
                attempts=attempts,
                retryable=True,
                detail="request timed out",
                api_key=api_key,
            ) from exc

    raise RuntimeError(f"{endpoint_label} request failed unexpectedly: {last_exc!r}")


def _decode_json_response(raw_bytes: bytes, *, endpoint_label: str, attempts: int) -> _JsonResponse:
    if not raw_bytes.strip():
        raise MistralPayloadError(f"{endpoint_label} response was empty")
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise MistralPayloadError(f"{endpoint_label} response was not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise MistralPayloadError(f"{endpoint_label} response was not valid JSON: {exc}") from exc
    return _JsonResponse(payload=payload, raw_bytes=raw_bytes, attempts=attempts)


def _request_error(
    endpoint_label: str,
    *,
    attempts: int,
    retryable: bool,
    api_key: str,
    status_code: int | None = None,
    detail: str | None = None,
) -> MistralRequestError:
    sanitized_detail = _sanitize_error_text(detail or "", api_key=api_key)
    status = f" HTTP error {status_code}" if status_code is not None else " request failed"
    retry_text = "retryable" if retryable else "non-retryable"
    detail_text = f": {sanitized_detail}" if sanitized_detail else ""
    message = f"{endpoint_label}{status} after {attempts} attempt(s) ({retry_text}){detail_text}"
    return MistralRequestError(
        message,
        endpoint=endpoint_label,
        attempts=attempts,
        retryable=retryable,
        status_code=status_code,
        detail=sanitized_detail or None,
    )


def _sleep_before_retry(
    exc: urllib.error.HTTPError | None,
    *,
    attempts: int,
    config: GazetteConfig,
) -> None:
    delay = _retry_delay_seconds(exc, attempts=attempts, config=config)
    if delay > 0:
        time.sleep(delay)


def _retry_delay_seconds(
    exc: urllib.error.HTTPError | None,
    *,
    attempts: int,
    config: GazetteConfig,
) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return min(retry_after, config.mistral.retry_max_delay_seconds)

    base = config.mistral.retry_base_delay_seconds
    delay = base * (2 ** max(attempts - 1, 0))
    return min(delay, config.mistral.retry_max_delay_seconds)


def _retry_after_seconds(exc: urllib.error.HTTPError | None) -> float | None:
    if exc is None or exc.headers is None:
        return None
    value = exc.headers.get("Retry-After")
    if value is None:
        return None

    stripped = value.strip()
    try:
        seconds = float(stripped)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(stripped)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
    return max(seconds, 0.0)


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
        raise MistralPayloadError(f"Mistral replay raw JSON is empty: {path}")

    try:
        raw_json = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise MistralPayloadError(f"Mistral replay raw JSON is not UTF-8: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MistralPayloadError(f"Invalid Mistral replay raw JSON: {path}: {exc}") from exc

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
    raw_response_bytes: int | None,
    retry_attempts: int,
    uploaded_file: dict[str, Any] | None = None,
) -> MistralMetadata:
    _validate_supported_raw_json_shape(raw_json)
    usage_info = _extract_usage_info(raw_json)
    pages_processed = _usage_int(usage_info, "pages_processed")
    doc_size_bytes = _usage_int(usage_info, "doc_size_bytes")

    request_options: dict[str, Any] = {
        "source_type": source.source_type,
        "model": config.mistral.model,
        "timeout_seconds": config.mistral.timeout_seconds,
        "max_attempts": config.mistral.max_attempts,
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
        usage_info=usage_info,
        pages_processed=pages_processed,
        doc_size_bytes=doc_size_bytes,
        estimated_ocr_cost_usd=_estimate_ocr_cost_usd(
            pages_processed,
            cost_per_1000_pages_usd=config.mistral.ocr_cost_per_1000_pages_usd,
        ),
        raw_response_bytes=raw_response_bytes,
        retry_attempts=retry_attempts,
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
    raise MistralPayloadError(
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


def _extract_usage_info(raw_json: Any) -> dict[str, Any]:
    if isinstance(raw_json, dict):
        usage = raw_json.get("usage_info")
        return dict(usage) if isinstance(usage, dict) else {}

    if not isinstance(raw_json, list):
        return {}

    usage_blocks = [
        dict(item["usage_info"])
        for item in raw_json
        if isinstance(item, dict) and isinstance(item.get("usage_info"), dict)
    ]
    if not usage_blocks:
        return {}
    if len(usage_blocks) == 1:
        return usage_blocks[0]

    usage_info: dict[str, Any] = {"blocks": usage_blocks}
    for key in ("pages_processed", "doc_size_bytes"):
        values = [block.get(key) for block in usage_blocks]
        numeric_values = [value for value in values if isinstance(value, int) and not isinstance(value, bool)]
        if numeric_values:
            usage_info[key] = sum(numeric_values)
    return usage_info


def _usage_int(usage_info: dict[str, Any], key: str) -> int | None:
    value = usage_info.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _estimate_ocr_cost_usd(
    pages_processed: int | None,
    *,
    cost_per_1000_pages_usd: float,
) -> float | None:
    if pages_processed is None:
        return None
    return pages_processed * cost_per_1000_pages_usd / 1000


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
    "MistralRequestError",
    "MistralPayloadError",
    "run_mistral_ocr",
    "load_raw_mistral_json",
    "write_raw_mistral_json",
    "build_document_url_ocr_body",
    "build_file_id_ocr_body",
    "upload_local_pdf_to_mistral",
]
