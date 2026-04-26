from __future__ import annotations

import copy
import json
import tomllib
from importlib import resources
from pathlib import Path

import pytest
from pydantic import ValidationError

import gazette_mistral_pipeline as gmp
from gazette_mistral_pipeline.__version__ import LIBRARY_VERSION, SCHEMA_VERSION
from gazette_mistral_pipeline.envelope_builder import OUTPUT_FORMAT_VERSION
from gazette_mistral_pipeline.models import Bundles, Envelope
from gazette_mistral_pipeline.schema import get_envelope_schema_bytes, serialize_schema

ROOT = Path(__file__).resolve().parents[1]
KENYALAW_URL = (
    "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/"
    "eng@2026-04-17/source.pdf"
)


def _raw_payload() -> dict[str, object]:
    return {
        "id": "doc_schema",
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
            }
        ],
    }


def _write_raw_json(path: Path) -> Path:
    path.write_text(json.dumps(_raw_payload()), encoding="utf-8")
    return path


def _parse_replay(tmp_path: Path) -> Envelope:
    replay_path = _write_raw_json(tmp_path / "cached.raw.json")
    return gmp.parse_url(
        KENYALAW_URL,
        config={"runtime": {"replay_raw_json_path": replay_path, "output_dir": tmp_path / "stage"}},
    )


def _bundle_flags(**overrides: bool) -> dict[str, bool]:
    flags = {
        "envelope": False,
        "joined_markdown": False,
        "raw_mistral_json": False,
        "source_metadata": False,
        "notices": False,
        "tables": False,
        "document_index": False,
        "debug_trace": False,
        "schema": False,
    }
    flags.update(overrides)
    return flags


def test_root_schema_helper_loads_checked_in_schema_resource() -> None:
    schema = gmp.get_envelope_schema()

    assert schema == json.loads(get_envelope_schema_bytes().decode("utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == "Envelope"
    assert schema["x-library-version"] == LIBRARY_VERSION
    assert schema["x-schema-version"] == SCHEMA_VERSION
    assert schema["x-output-format-version"] == OUTPUT_FORMAT_VERSION
    for field in [
        "source",
        "mistral",
        "stats",
        "notices",
        "document_confidence",
        "layout_info",
        "warnings",
    ]:
        assert field in schema["properties"]
    mistral_schema = schema["$defs"]["MistralMetadata"]["properties"]
    for field in [
        "usage_info",
        "pages_processed",
        "doc_size_bytes",
        "estimated_ocr_cost_usd",
        "raw_response_bytes",
        "retry_attempts",
        "returned_markdown_estimated_tokens",
    ]:
        assert field in mistral_schema
    assert "$id" not in schema


def test_generated_schema_matches_checked_in_schema_bytes() -> None:
    generated = gmp.get_envelope_schema(use_cache=False)
    resource_bytes = get_envelope_schema_bytes()

    assert generated == gmp.get_envelope_schema()
    assert serialize_schema(generated) == resource_bytes
    assert resource_bytes.endswith(b"\n")
    assert not resource_bytes.endswith(b"\n\n")


def test_validate_envelope_json_accepts_supported_inputs(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path)
    mapping = env.model_dump(mode="json")
    json_text = json.dumps(mapping, ensure_ascii=False)
    json_bytes = json_text.encode("utf-8")
    json_path = tmp_path / "envelope.json"
    json_path.write_bytes(json_bytes)

    assert gmp.validate_envelope_json(env) is env
    for candidate in [mapping, json_text, json_bytes, bytearray(json_bytes), json_path]:
        validated = gmp.validate_envelope_json(candidate)
        assert isinstance(validated, Envelope)
        assert validated.source.run_name == env.source.run_name
        assert validated.schema_version == env.schema_version
        assert validated.stats.notice_count == env.stats.notice_count
        assert [notice.notice_id for notice in validated.notices] == [
            notice.notice_id for notice in env.notices
        ]
        assert validated.stats.warnings_count == env.stats.warnings_count


def test_validate_envelope_json_rejects_bad_inputs_clearly(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path)
    mapping = env.model_dump(mode="json")

    with pytest.raises(ValidationError):
        gmp.validate_envelope_json("{not json")

    missing_required = dict(mapping)
    missing_required.pop("source")
    with pytest.raises(ValidationError):
        gmp.validate_envelope_json(missing_required)

    with_extra = dict(mapping)
    with_extra["unexpected"] = True
    with pytest.raises(ValidationError):
        gmp.validate_envelope_json(with_extra)

    invalid_band = copy.deepcopy(mapping)
    invalid_band["notices"][0]["confidence_scores"]["band"] = "needs_review"
    with pytest.raises(ValidationError):
        gmp.validate_envelope_json(invalid_band)

    with pytest.raises(TypeError):
        gmp.validate_envelope_json(object())  # type: ignore[arg-type]

    with pytest.raises(FileNotFoundError):
        gmp.validate_envelope_json(tmp_path / "missing-envelope.json")

    with pytest.raises(ValidationError):
        gmp.validate_envelope_json(str(tmp_path / "plain-string-is-json-not-path.json"))


def test_schema_bundle_writes_checked_in_schema_only_when_selected(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path)
    out_dir = tmp_path / "schema-only"

    written = gmp.write_envelope(env, out_dir, _bundle_flags(schema=True))

    assert written == {"schema": out_dir / "gazette_2026-04-17_68_schema.json"}
    assert written["schema"].read_bytes() == get_envelope_schema_bytes()
    assert sorted(path.name for path in out_dir.iterdir()) == ["gazette_2026-04-17_68_schema.json"]


def test_schema_bundle_composes_with_default_bundles(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path)
    out_dir = tmp_path / "bundles"
    bundles = Bundles(schema=True)

    first = gmp.write_envelope(env, out_dir, bundles)
    first_bytes = {name: path.read_bytes() for name, path in first.items()}
    second = gmp.write_envelope(env, out_dir, bundles)

    assert set(first) == {
        "envelope",
        "source_metadata",
        "schema",
        "raw_mistral_json",
        "joined_markdown",
    }
    assert first["schema"] == out_dir / "gazette_2026-04-17_68_schema.json"
    assert first["schema"].read_bytes() == get_envelope_schema_bytes()
    assert first_bytes == {name: path.read_bytes() for name, path in second.items()}


def test_package_data_includes_schema_resource() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = data["tool"]["setuptools"]["package-data"]["gazette_mistral_pipeline"]

    assert "py.typed" in package_data
    assert "schemas/*.json" in package_data
    resource = resources.files("gazette_mistral_pipeline").joinpath(
        "schemas",
        "envelope.schema.json",
    )
    assert resource.read_bytes() == get_envelope_schema_bytes()
