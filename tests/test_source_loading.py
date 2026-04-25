from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gazette_mistral_pipeline.models import PdfSource
from gazette_mistral_pipeline.source_loading import (
    derive_run_name,
    load_source_manifest,
    resolve_pdf_source,
    resolve_pdf_sources,
    source_sha256,
)


KENYALAW_URL = (
    "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/"
    "eng@2026-04-17/source.pdf"
)


def _write_pdf(path: Path, body: bytes = b"%PDF-1.4\nsample\n") -> Path:
    path.write_bytes(body)
    return path


def test_kenyalaw_url_resolves_to_gazette_run_name() -> None:
    source = resolve_pdf_source(KENYALAW_URL)

    assert source.source_type == "pdf_url"
    assert source.source_value == KENYALAW_URL
    assert source.run_name == "gazette_2026-04-17_68"
    assert source.source_sha256 == hashlib.sha256(KENYALAW_URL.encode("utf-8")).hexdigest()


def test_generic_pdf_url_uses_sanitized_path_stem() -> None:
    url = "https://example.com/files/My Gazette 01.pdf?download=1"

    assert derive_run_name(url) == "My_Gazette_01"

    source = resolve_pdf_source(url)
    assert source.run_name == "My_Gazette_01"
    assert source.source_value == url


def test_local_pdf_resolves_absolute_path_and_file_hash(tmp_path: Path) -> None:
    pdf_path = _write_pdf(tmp_path / "Kenya Gazette 01.pdf", b"%PDF-1.4\nabc\n")

    source = resolve_pdf_source(pdf_path)

    assert source.source_type == "local_pdf"
    assert source.source_value == str(pdf_path.resolve())
    assert source.run_name == "Kenya_Gazette_01"
    assert source.source_sha256 == hashlib.sha256(b"%PDF-1.4\nabc\n").hexdigest()
    assert source.source_sha256 == source_sha256(pdf_path, source_type="local_pdf")


def test_json_manifest_resolves_url_and_relative_local_pdf(tmp_path: Path) -> None:
    pdf_path = _write_pdf(tmp_path / "sample.pdf")
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps({
            "sources": [
                {"source_type": "pdf_url", "source_value": KENYALAW_URL},
                {
                    "source_type": "local_pdf",
                    "source_value": pdf_path.name,
                    "run_name": "local sample",
                },
            ],
        }),
        encoding="utf-8",
    )

    sources = resolve_pdf_sources(manifest_path)

    assert [source.source_type for source in sources] == ["pdf_url", "local_pdf"]
    assert [source.run_name for source in sources] == [
        "gazette_2026-04-17_68",
        "local_sample",
    ]
    assert sources[1].source_value == str(pdf_path.resolve())


def test_manifest_aliases_and_top_level_list_are_supported(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps([
            {"type": "pdf_url", "value": KENYALAW_URL, "run_name": "url alias"},
        ]),
        encoding="utf-8",
    )

    items = load_source_manifest(manifest_path)
    assert items == [{
        "source_type": "pdf_url",
        "source_value": KENYALAW_URL,
        "run_name": "url alias",
    }]
    assert resolve_pdf_sources(manifest_path)[0].run_name == "url_alias"


def test_manifest_pdf_url_type_rejects_local_looking_value(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps({
            "sources": [
                {"source_type": "pdf_url", "source_value": "local-file.pdf"},
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Expected an HTTP\\(S\\) PDF URL"):
        resolve_pdf_sources(manifest_path)


def test_manifest_local_pdf_type_rejects_url_value(tmp_path: Path) -> None:
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(
        json.dumps({
            "sources": [
                {"source_type": "local_pdf", "source_value": KENYALAW_URL},
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Expected local PDF path"):
        resolve_pdf_sources(manifest_path)


def test_existing_pdf_source_is_returned_without_side_effects() -> None:
    prebuilt = PdfSource(
        source_type="pdf_url",
        source_value=KENYALAW_URL,
        run_name="already_done",
        source_sha256="abc123",
    )

    assert resolve_pdf_source(prebuilt) is prebuilt


def test_duplicate_run_names_fail_loudly(tmp_path: Path) -> None:
    first = _write_pdf(tmp_path / "one.pdf")
    second = _write_pdf(tmp_path / "two.pdf")

    with pytest.raises(ValueError, match="Duplicate resolved run_name values: duplicate"):
        resolve_pdf_sources([
            resolve_pdf_source(first, run_name="duplicate"),
            resolve_pdf_source(second, run_name="duplicate"),
        ])


@pytest.mark.parametrize(
    "bad_url",
    [
        "ftp://example.com/file.pdf",
        "https://example.com/file.txt",
    ],
)
def test_invalid_urls_fail(bad_url: str) -> None:
    with pytest.raises(ValueError, match="Expected"):
        resolve_pdf_source(bad_url)


def test_missing_local_pdf_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Local PDF does not exist"):
        resolve_pdf_source(tmp_path / "missing.pdf")


def test_non_pdf_local_file_fails(tmp_path: Path) -> None:
    text_path = tmp_path / "not-a-pdf.txt"
    text_path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected local PDF path"):
        resolve_pdf_source(text_path)


@pytest.mark.parametrize(
    "payload",
    [
        {"items": []},
        {"sources": [{"source_type": "pdf_url"}]},
        {"sources": [{"source_type": "unknown", "source_value": KENYALAW_URL}]},
        {"sources": ["not an object"]},
    ],
)
def test_malformed_manifest_fails(tmp_path: Path, payload) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_source_manifest(manifest_path)


def test_invalid_json_manifest_fails(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON source manifest"):
        load_source_manifest(manifest_path)
