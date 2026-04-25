from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest
from pydantic import ValidationError

import gazette_mistral_pipeline as gmp
import gazette_mistral_pipeline.mistral_ocr as mistral_ocr
from gazette_mistral_pipeline.models import Envelope, GazetteConfig, RuntimeOptions

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


def _raw_payload() -> dict[str, object]:
    return {
        "id": "doc_public_api",
        "model": "mistral-ocr-latest",
        "pages": [
            {
                "index": 0,
                "markdown": (
                    "## GAZETTE NOTICE NO. 5969\n\n"
                    "THE LAND REGISTRATION ACT\n\n"
                    "IN EXERCISE of the powers conferred by law, the Registrar gives notice.\n\n"
                    "| Parcel | Owner |\n"
                    "| --- | --- |\n"
                    "| Kajiado/1 | Jane Doe |\n\n"
                    "Dated the 17th April, 2026.\n\n"
                    "REGISTRAR,\n"
                    "Lands Registry."
                ),
                "dimensions": {"width": 719, "height": 1018},
                "images": [{"bbox": [10, 20, 30, 40]}],
            }
        ],
    }


def _write_raw_json(path: Path, payload: object | None = None) -> Path:
    path.write_text(json.dumps(payload or _raw_payload()), encoding="utf-8")
    return path


def _offline_config(replay_path: Path, output_dir: Path | None = None) -> GazetteConfig:
    runtime: dict[str, object] = {"replay_raw_json_path": replay_path}
    if output_dir is not None:
        runtime["output_dir"] = output_dir
    return GazetteConfig(runtime=runtime)


def test_runtime_options_defaults_and_validation(tmp_path: Path) -> None:
    defaults = RuntimeOptions()
    assert defaults.replay_raw_json_path is None
    assert defaults.output_dir is None
    assert defaults.allow_live_mistral is False
    assert defaults.deterministic is True

    config = GazetteConfig(runtime={
        "replay_raw_json_path": str(tmp_path / "cached.raw.json"),
        "output_dir": str(tmp_path / "stage"),
        "allow_live_mistral": True,
    })
    assert config.runtime.replay_raw_json_path == tmp_path / "cached.raw.json"
    assert config.runtime.output_dir == tmp_path / "stage"
    assert config.runtime.allow_live_mistral is True


def test_parse_url_replay_orchestrates_f04_to_f09_without_network_or_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_path = _write_raw_json(tmp_path / "cached.raw.json")
    stage_dir = tmp_path / "stage"

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay mode must not call network")

    def fail_api_key(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay mode must not resolve API keys")

    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(mistral_ocr, "_resolve_api_key", fail_api_key)

    env = gmp.parse_url(KENYALAW_URL, config=_offline_config(replay_path, stage_dir))

    assert isinstance(env, Envelope)
    assert env.source.source_type == "pdf_url"
    assert env.source.run_name == "gazette_2026-04-17_68"
    assert env.mistral.raw_json_path == str(replay_path)
    assert env.mistral.request_options["replay"] is True
    assert env.stats.document_count == 1
    assert env.stats.page_count == 1
    assert env.stats.notice_count == 1
    assert env.stats.table_count == 1
    assert env.notices[0].notice_no == "5969"
    assert env.tables == list(env.notices[0].tables)
    joined_path = stage_dir / "gazette_2026-04-17_68_joined.md"
    assert joined_path.is_file()
    assert env.notices[0].provenance.source_markdown_path == str(joined_path)


def test_parse_url_replay_without_output_dir_keeps_stage_markdown_in_memory(
    tmp_path: Path,
) -> None:
    replay_path = _write_raw_json(tmp_path / "cached.raw.json")

    env = gmp.parse_url(KENYALAW_URL, config=_offline_config(replay_path))

    assert env.stats.notice_count == 1
    assert env.notices[0].provenance.source_markdown_path is None
    assert not list(tmp_path.glob("*_joined.md"))
    assert not list(tmp_path.glob("*_envelope.json"))


def test_parse_file_local_pdf_replay_uses_file_hash_and_no_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "Local Gazette.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nlocal\n")
    replay_path = _write_raw_json(tmp_path / "cached.raw.json")

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("local replay must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    env = gmp.parse_file(pdf_path, config=_offline_config(replay_path, tmp_path / "stage"))

    assert env.source.source_type == "local_pdf"
    assert env.source.source_value == str(pdf_path.resolve())
    assert env.source.run_name == "Local_Gazette"
    assert env.source.source_sha256 is not None
    assert env.mistral.document_url is None
    assert env.mistral.request_options["replay"] is True


def test_parse_url_without_replay_requires_live_opt_in_before_env_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("disabled live mode must not call network")

    def fail_api_key(*args: object, **kwargs: object) -> None:
        raise AssertionError("disabled live mode must not resolve API keys")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(mistral_ocr, "_resolve_api_key", fail_api_key)

    with pytest.raises(RuntimeError, match="allow_live_mistral"):
        gmp.parse_url(KENYALAW_URL)


def test_live_url_opt_in_requires_output_dir_before_env_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("missing output dir must not call network")

    def fail_api_key(*args: object, **kwargs: object) -> None:
        raise AssertionError("missing output dir must not resolve API keys")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(mistral_ocr, "_resolve_api_key", fail_api_key)
    config = GazetteConfig(runtime={"allow_live_mistral": True})

    with pytest.raises(ValueError, match="runtime.output_dir"):
        gmp.parse_url(KENYALAW_URL, config=config)


def test_live_url_with_mocked_http_writes_raw_cache_and_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(json.dumps(_raw_payload()).encode("utf-8"))

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    config = GazetteConfig(
        mistral={"api_key_env": "MISTRAL_API_KEY_TEST", "timeout_seconds": 8.0},
        runtime={"allow_live_mistral": True, "output_dir": tmp_path / "stage"},
    )

    env = gmp.parse_url(KENYALAW_URL, config=config)

    assert env.stats.notice_count == 1
    assert env.mistral.request_options["replay"] is False
    assert env.mistral.raw_json_path == str(tmp_path / "stage" / "gazette_2026-04-17_68.raw.json")
    assert Path(env.mistral.raw_json_path).is_file()
    assert (tmp_path / "stage" / "gazette_2026-04-17_68_joined.md").is_file()
    assert isinstance(captured["request"], urllib.request.Request)
    assert captured["timeout"] == 8.0


def test_live_local_pdf_uploads_then_ocr_by_file_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = b"%PDF-1.4\nsample local gazette\n"
    pdf_path = tmp_path / "Local Gazette.pdf"
    pdf_path.write_bytes(pdf_bytes)
    requests: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        requests.append(request)
        assert timeout == 8.0
        if request.full_url == mistral_ocr.MISTRAL_FILES_URL:
            body = request.data or b""
            assert b'name="purpose"' in body
            assert b"ocr" in body
            assert b'name="file"; filename="Local Gazette.pdf"' in body
            assert pdf_bytes in body
            return _FakeResponse(
                json.dumps(
                    {
                        "id": "file_local_pdf_123",
                        "object": "file",
                        "bytes": len(pdf_bytes),
                        "filename": "Local Gazette.pdf",
                        "purpose": "ocr",
                    }
                ).encode("utf-8")
            )

        if request.full_url == mistral_ocr.MISTRAL_OCR_URL:
            body = json.loads((request.data or b"").decode("utf-8"))
            assert body == {
                "document": {"file_id": "file_local_pdf_123"},
                "model": "mistral-ocr-latest",
            }
            return _FakeResponse(json.dumps(_raw_payload()).encode("utf-8"))

        raise AssertionError(f"unexpected URL: {request.full_url}")

    monkeypatch.setenv("MISTRAL_API_KEY_TEST", "test-key")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    config = GazetteConfig(
        mistral={"api_key_env": "MISTRAL_API_KEY_TEST", "timeout_seconds": 8.0},
        runtime={"allow_live_mistral": True, "output_dir": tmp_path / "stage"},
    )

    env = gmp.parse_file(pdf_path, config=config)

    assert len(requests) == 2
    assert env.source.source_type == "local_pdf"
    assert env.source.source_value == str(pdf_path.resolve())
    assert env.source.run_name == "Local_Gazette"
    assert env.mistral.document_url is None
    assert env.mistral.request_options["replay"] is False
    assert env.mistral.request_options["document_type"] == "file_id"
    assert env.mistral.request_options["uploaded_file_id"] == "file_local_pdf_123"
    assert env.mistral.request_options["uploaded_file_name"] == "Local Gazette.pdf"
    assert env.mistral.request_options["uploaded_file_bytes"] == len(pdf_bytes)
    assert env.mistral.raw_json_path == str(tmp_path / "stage" / "Local_Gazette.raw.json")
    assert Path(env.mistral.raw_json_path).is_file()
    assert (tmp_path / "stage" / "Local_Gazette_joined.md").is_file()


def test_live_local_pdf_requires_live_opt_in_before_upload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nsample\n")

    def fail_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("disabled live local mode must not call network")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(RuntimeError, match="allow_live_mistral"):
        gmp.parse_file(pdf_path)

    assert not (tmp_path / "stage").exists()


def test_schema_helpers_are_real_public_callables() -> None:
    schema = gmp.get_envelope_schema()

    assert schema["title"] == "Envelope"
    assert "source" in schema["properties"]
    with pytest.raises(ValidationError):
        gmp.validate_envelope_json({})
