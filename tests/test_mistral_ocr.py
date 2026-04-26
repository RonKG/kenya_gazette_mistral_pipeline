from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gazette_mistral_pipeline.mistral_ocr import (
    MISTRAL_FILES_URL,
    MISTRAL_OCR_URL,
    MistralPayloadError,
    MistralRequestError,
    build_file_id_ocr_body,
    build_document_url_ocr_body,
    load_raw_mistral_json,
    run_mistral_ocr,
    write_raw_mistral_json,
)
from gazette_mistral_pipeline.models import GazetteConfig, PdfSource

KENYALAW_URL = (
    "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/"
    "eng@2026-04-17/source.pdf"
)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _pdf_url_source() -> PdfSource:
    return PdfSource(
        source_type="pdf_url",
        source_value=KENYALAW_URL,
        run_name="gazette_2026-04-17_68",
        source_sha256="b" * 64,
    )


def _local_pdf_source(tmp_path: Path) -> PdfSource:
    return PdfSource(
        source_type="local_pdf",
        source_value=str(tmp_path / "sample.pdf"),
        run_name="sample",
        source_sha256="c" * 64,
    )


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def test_build_document_url_ocr_body_matches_prototype_shape() -> None:
    body = build_document_url_ocr_body(_pdf_url_source(), model="mistral-ocr-latest")

    assert body == {
        "model": "mistral-ocr-latest",
        "document": {
            "type": "document_url",
            "document_url": KENYALAW_URL,
        },
    }


def test_build_file_id_ocr_body_matches_uploaded_pdf_shape() -> None:
    body = build_file_id_ocr_body("file_abc123", model="mistral-ocr-latest")

    assert body == {
        "model": "mistral-ocr-latest",
        "document": {
            "file_id": "file_abc123",
        },
    }


def test_pdf_url_live_ocr_uses_stdlib_post_and_writes_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": "doc_1",
        "model": "mistral-ocr-latest",
        "pages": [{"index": 0, "markdown": "text"}],
    }
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(_canonical_json_bytes(payload))

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key-123")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    config = GazetteConfig(mistral={
        "api_key_env": "MISTRAL_API_KEY_TEST",
        "timeout_seconds": 12.5,
    })
    result = run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.full_url == MISTRAL_OCR_URL
    assert request.get_method() == "POST"
    assert captured["timeout"] == 12.5
    headers = {key.lower(): value for key, value in request.header_items()}
    assert headers["authorization"] == "Bearer test-key-123"
    assert headers["content-type"] == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {
        "model": "mistral-ocr-latest",
        "document": {
            "type": "document_url",
            "document_url": KENYALAW_URL,
        },
    }

    raw_json_path = tmp_path / "gazette_2026-04-17_68.raw.json"
    raw_bytes = raw_json_path.read_bytes()
    assert raw_bytes == _canonical_json_bytes(payload)
    assert result.raw_json == payload
    assert result.metadata.model == "mistral-ocr-latest"
    assert result.metadata.raw_json_path == str(raw_json_path)
    assert result.metadata.raw_json_sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert result.metadata.document_url == KENYALAW_URL
    assert result.metadata.mistral_doc_ids == ["doc_1"]
    assert result.metadata.page_count == 1
    assert result.metadata.request_options == {
        "source_type": "pdf_url",
        "model": "mistral-ocr-latest",
        "timeout_seconds": 12.5,
        "max_attempts": 3,
        "replay": False,
        "document_type": "document_url",
    }
    assert "test-key-123" not in json.dumps(result.metadata.request_options)


def test_local_pdf_live_ocr_uploads_file_then_posts_file_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = b"%PDF-1.4\nlocal pdf\n"
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(pdf_bytes)
    payload = {
        "id": "doc_from_uploaded_file",
        "model": "mistral-ocr-latest",
        "pages": [{"index": 0, "markdown": "text"}],
    }
    source = PdfSource(
        source_type="local_pdf",
        source_value=str(pdf_path),
        run_name="sample",
        source_sha256="c" * 64,
    )
    requests: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        requests.append(request)
        assert timeout == 12.5
        if request.full_url == MISTRAL_FILES_URL:
            headers = {key.lower(): value for key, value in request.header_items()}
            assert headers["authorization"] == "Bearer test-key-123"
            assert headers["content-type"].startswith("multipart/form-data; boundary=")
            body = request.data or b""
            assert b'name="purpose"' in body
            assert b"ocr" in body
            assert b'name="file"; filename="sample.pdf"' in body
            assert b"Content-Type: application/pdf" in body
            assert pdf_bytes in body
            return _FakeResponse(
                _canonical_json_bytes(
                    {
                        "id": "file_abc123",
                        "filename": "sample.pdf",
                        "bytes": len(pdf_bytes),
                        "purpose": "ocr",
                    }
                )
            )
        if request.full_url == MISTRAL_OCR_URL:
            assert json.loads(request.data.decode("utf-8")) == {
                "model": "mistral-ocr-latest",
                "document": {
                    "file_id": "file_abc123",
                },
            }
            return _FakeResponse(_canonical_json_bytes(payload))
        raise AssertionError(f"unexpected URL: {request.full_url}")

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key-123")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    config = GazetteConfig(mistral={
        "api_key_env": "MISTRAL_API_KEY_TEST",
        "timeout_seconds": 12.5,
    })
    result = run_mistral_ocr(source, config=config, cache_dir=tmp_path)

    assert [request.full_url for request in requests] == [MISTRAL_FILES_URL, MISTRAL_OCR_URL]
    raw_json_path = tmp_path / "sample.raw.json"
    raw_bytes = raw_json_path.read_bytes()
    assert result.raw_json == payload
    assert result.metadata.raw_json_path == str(raw_json_path)
    assert result.metadata.raw_json_sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert result.metadata.document_url is None
    assert result.metadata.mistral_doc_ids == ["doc_from_uploaded_file"]
    assert result.metadata.page_count == 1
    assert result.metadata.request_options == {
        "source_type": "local_pdf",
        "model": "mistral-ocr-latest",
        "timeout_seconds": 12.5,
        "max_attempts": 3,
        "replay": False,
        "document_type": "file_id",
        "uploaded_file_id": "file_abc123",
        "uploaded_file_name": "sample.pdf",
        "uploaded_file_bytes": len(pdf_bytes),
    }


def test_replay_mode_bypasses_network_and_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": "doc_replay",
        "model": "mistral-ocr-latest",
        "pages": [{"index": 0, "markdown": "cached text"}],
    }
    replay_path = tmp_path / "cached.raw.json"
    replay_bytes = json.dumps(payload).encode("utf-8")
    replay_path.write_bytes(replay_bytes)

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay mode must not call urlopen")

    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    config = GazetteConfig(runtime={"replay_raw_json_path": replay_path})
    result = run_mistral_ocr(_local_pdf_source(tmp_path), config=config, cache_dir=tmp_path)

    assert result.raw_json == payload
    assert result.metadata.raw_json_path == str(replay_path)
    assert result.metadata.raw_json_sha256 == hashlib.sha256(replay_bytes).hexdigest()
    assert result.metadata.document_url is None
    assert result.metadata.mistral_doc_ids == ["doc_replay"]
    assert result.metadata.page_count == 1
    assert result.metadata.request_options["replay"] is True
    assert result.metadata.request_options["source_type"] == "local_pdf"


def test_write_raw_mistral_json_is_deterministic(tmp_path: Path) -> None:
    first = {"b": 2, "a": [{"z": 1}]}
    second = {"a": [{"z": 1}], "b": 2}
    first_path = tmp_path / "first.raw.json"
    second_path = tmp_path / "second.raw.json"

    first_hash = write_raw_mistral_json(first, first_path)
    second_hash = write_raw_mistral_json(second, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_hash == second_hash
    assert first_hash == hashlib.sha256(first_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("payload", "expected_ids", "expected_pages"),
    [
        (
            {"id": "doc_object", "model": "mistral-ocr-latest", "pages": [{}, {}]},
            ["doc_object"],
            2,
        ),
        (
            [
                {"id": "block_1", "model": "mistral-ocr-latest", "pages": [{}]},
                {"id": "block_2", "pages": [{}, {}]},
            ],
            ["block_1", "block_2"],
            3,
        ),
        (
            [{"markdown": "page one"}, {"markdown": "page two"}],
            [],
            2,
        ),
    ],
)
def test_replay_metadata_supports_known_raw_json_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
    expected_ids: list[str],
    expected_pages: int,
) -> None:
    replay_path = tmp_path / "shape.raw.json"
    replay_path.write_bytes(json.dumps(payload).encode("utf-8"))

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay mode must not call urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    config = GazetteConfig(runtime={"replay_raw_json_path": replay_path})
    result = run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    assert result.metadata.mistral_doc_ids == expected_ids
    assert result.metadata.page_count == expected_pages
    assert result.metadata.document_url == KENYALAW_URL


@pytest.mark.parametrize(
    ("filename", "body", "error_match"),
    [
        ("missing.raw.json", None, "does not exist"),
        ("empty.raw.json", b"   ", "empty"),
        ("invalid.raw.json", b"{", "Invalid Mistral replay raw JSON"),
        ("unsupported.raw.json", b'{"not_pages": []}', "Unsupported Mistral raw JSON shape"),
    ],
)
def test_invalid_replay_json_fails_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    body: bytes | None,
    error_match: str,
) -> None:
    replay_path = tmp_path / filename
    if body is not None:
        replay_path.write_bytes(body)

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("invalid replay must not call urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    config = GazetteConfig(runtime={"replay_raw_json_path": replay_path})

    with pytest.raises((FileNotFoundError, ValueError), match=error_match):
        run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)


def test_load_raw_mistral_json_validates_shape(tmp_path: Path) -> None:
    replay_path = tmp_path / "cached.raw.json"
    payload = {"model": "mistral-ocr-latest", "pages": [{"markdown": "text"}]}
    replay_path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_raw_mistral_json(replay_path) == payload


@pytest.mark.parametrize("env_value", [None, "   "])
def test_missing_api_key_for_live_url_fails_before_network_or_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
) -> None:
    if env_value is None:
        monkeypatch.delenv("MISTRAL_API_KEY_TEST", raising=False)
    else:
        monkeypatch.setenv("MISTRAL_API_KEY_TEST", env_value)

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("missing key must not call urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    config = GazetteConfig(mistral={"api_key_env": "MISTRAL_API_KEY_TEST"})

    with pytest.raises(OSError, match="MISTRAL_API_KEY_TEST") as excinfo:
        run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    assert "test-key" not in str(excinfo.value)
    assert not list(tmp_path.glob("*.raw.json"))


def test_http_errors_are_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> None:
        _ = (request, timeout)
        raise urllib.error.HTTPError(
            MISTRAL_OCR_URL,
            401,
            "Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error":"Authorization failed for Bearer secret-token"}'),
        )

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "secret-token")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    config = GazetteConfig(mistral={"api_key_env": "MISTRAL_API_KEY_TEST"})

    with pytest.raises(RuntimeError) as excinfo:
        run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    message = str(excinfo.value)
    assert "HTTP error 401" in message
    assert "secret-token" not in message
    assert "Authorization" not in message
    assert not list(tmp_path.glob("*.raw.json"))


def test_missing_api_key_for_live_local_pdf_fails_before_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nlocal\n")
    source = PdfSource(
        source_type="local_pdf",
        source_value=str(pdf_path),
        run_name="sample",
        source_sha256="c" * 64,
    )

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("missing key must not call urlopen")

    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(OSError, match="MISTRAL_API_KEY"):
        run_mistral_ocr(source, cache_dir=tmp_path)

    assert not list(tmp_path.glob("*.raw.json"))


def test_retryable_ocr_http_error_retries_and_records_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": "doc_retry",
        "model": "mistral-ocr-latest",
        "pages": [{"index": 0, "markdown": "text"}],
        "usage_info": {"pages_processed": 52, "doc_size_bytes": 12345},
    }
    calls: list[urllib.request.Request] = []
    sleeps: list[float] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        _ = timeout
        calls.append(request)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                MISTRAL_OCR_URL,
                429,
                "Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b'{"error":"rate limit"}'),
            )
        return _FakeResponse(_canonical_json_bytes(payload))

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key-123")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("gazette_mistral_pipeline.mistral_ocr.time.sleep", sleeps.append)
    config = GazetteConfig(mistral={
        "api_key_env": "MISTRAL_API_KEY_TEST",
        "retry_base_delay_seconds": 0,
        "ocr_cost_per_1000_pages_usd": 1.0,
    })

    result = run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    assert len(calls) == 2
    assert sleeps == []
    assert result.metadata.retry_attempts == 1
    assert result.metadata.usage_info == {"pages_processed": 52, "doc_size_bytes": 12345}
    assert result.metadata.pages_processed == 52
    assert result.metadata.doc_size_bytes == 12345
    assert result.metadata.estimated_ocr_cost_usd == pytest.approx(0.052)
    assert result.metadata.raw_response_bytes == len(_canonical_json_bytes(payload))
    assert Path(result.metadata.raw_json_path).is_file()


def test_retry_after_header_controls_retry_sleep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": "doc_retry_after",
        "model": "mistral-ocr-latest",
        "pages": [{"index": 0, "markdown": "text"}],
    }
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        nonlocal calls
        _ = (request, timeout)
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(
                MISTRAL_OCR_URL,
                503,
                "Unavailable",
                hdrs={"Retry-After": "2"},
                fp=io.BytesIO(b"temporary"),
            )
        return _FakeResponse(_canonical_json_bytes(payload))

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key-123")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("gazette_mistral_pipeline.mistral_ocr.time.sleep", sleeps.append)
    config = GazetteConfig(mistral={
        "api_key_env": "MISTRAL_API_KEY_TEST",
        "retry_base_delay_seconds": 99,
        "retry_max_delay_seconds": 10,
    })

    run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    assert sleeps == [2.0]


def test_non_retryable_http_error_fails_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> None:
        nonlocal calls
        _ = (request, timeout)
        calls += 1
        raise urllib.error.HTTPError(
            MISTRAL_OCR_URL,
            400,
            "Bad Request",
            hdrs={},
            fp=io.BytesIO(b'{"error":"bad request for secret-token"}'),
        )

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "secret-token")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    config = GazetteConfig(mistral={"api_key_env": "MISTRAL_API_KEY_TEST"})

    with pytest.raises(MistralRequestError) as excinfo:
        run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    assert calls == 1
    assert excinfo.value.status_code == 400
    assert excinfo.value.retryable is False
    assert excinfo.value.attempts == 1
    assert "secret-token" not in str(excinfo.value)
    assert not list(tmp_path.glob("*.raw.json"))


def test_network_errors_retry_then_raise_structured_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> None:
        nonlocal calls
        _ = (request, timeout)
        calls += 1
        raise urllib.error.URLError("temporary dns failure")

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key-123")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("gazette_mistral_pipeline.mistral_ocr.time.sleep", lambda _: None)
    config = GazetteConfig(mistral={
        "api_key_env": "MISTRAL_API_KEY_TEST",
        "max_attempts": 2,
        "retry_base_delay_seconds": 0,
    })

    with pytest.raises(MistralRequestError) as excinfo:
        run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    assert calls == 2
    assert excinfo.value.retryable is True
    assert excinfo.value.attempts == 2
    assert "temporary dns failure" in str(excinfo.value)
    assert not list(tmp_path.glob("*.raw.json"))


def test_empty_live_ocr_payload_fails_without_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        _ = (request, timeout)
        return _FakeResponse(b"   ")

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key-123")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    config = GazetteConfig(mistral={"api_key_env": "MISTRAL_API_KEY_TEST"})

    with pytest.raises(MistralPayloadError, match="empty"):
        run_mistral_ocr(_pdf_url_source(), config=config, cache_dir=tmp_path)

    assert not list(tmp_path.glob("*.raw.json"))


def test_local_pdf_upload_retries_before_ocr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nlocal pdf\n")
    source = PdfSource(
        source_type="local_pdf",
        source_value=str(pdf_path),
        run_name="sample",
        source_sha256="c" * 64,
    )
    payload = {
        "id": "doc_uploaded",
        "model": "mistral-ocr-latest",
        "pages": [{"index": 0, "markdown": "text"}],
    }
    urls: list[str] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        _ = timeout
        urls.append(request.full_url)
        if request.full_url == MISTRAL_FILES_URL and urls.count(MISTRAL_FILES_URL) == 1:
            raise urllib.error.HTTPError(
                MISTRAL_FILES_URL,
                503,
                "Unavailable",
                hdrs={},
                fp=io.BytesIO(b"temporary upload failure"),
            )
        if request.full_url == MISTRAL_FILES_URL:
            return _FakeResponse(
                _canonical_json_bytes(
                    {
                        "id": "file_retry_123",
                        "filename": "sample.pdf",
                        "bytes": pdf_path.stat().st_size,
                    }
                )
            )
        if request.full_url == MISTRAL_OCR_URL:
            assert json.loads((request.data or b"").decode("utf-8")) == {
                "model": "mistral-ocr-latest",
                "document": {"file_id": "file_retry_123"},
            }
            return _FakeResponse(_canonical_json_bytes(payload))
        raise AssertionError(f"unexpected URL: {request.full_url}")

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key-123")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("gazette_mistral_pipeline.mistral_ocr.time.sleep", lambda _: None)
    config = GazetteConfig(mistral={
        "api_key_env": "MISTRAL_API_KEY_TEST",
        "retry_base_delay_seconds": 0,
    })

    result = run_mistral_ocr(source, config=config, cache_dir=tmp_path)

    assert urls == [MISTRAL_FILES_URL, MISTRAL_FILES_URL, MISTRAL_OCR_URL]
    assert result.metadata.retry_attempts == 1
    assert result.metadata.request_options["uploaded_file_id"] == "file_retry_123"


