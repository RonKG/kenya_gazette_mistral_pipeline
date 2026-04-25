from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gazette_mistral_pipeline.mistral_ocr import (
    MISTRAL_OCR_URL,
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
        "replay": False,
        "document_type": "document_url",
    }
    assert "test-key-123" not in json.dumps(result.metadata.request_options)


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


def test_live_local_pdf_is_explicitly_unsupported_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("live local unsupported path must not call urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(NotImplementedError, match="local_pdf sources is not supported in F05"):
        run_mistral_ocr(_local_pdf_source(tmp_path), cache_dir=tmp_path)

    assert not list(tmp_path.glob("*.raw.json"))


