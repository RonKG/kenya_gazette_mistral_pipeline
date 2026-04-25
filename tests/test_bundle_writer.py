from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import gazette_mistral_pipeline as gmp
from gazette_mistral_pipeline.models import Bundles, Envelope
from gazette_mistral_pipeline.schema import get_envelope_schema_bytes

KENYALAW_URL = (
    "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/"
    "eng@2026-04-17/source.pdf"
)


def _raw_payload() -> dict[str, object]:
    return {
        "id": "doc_bundle",
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
            }
        ],
    }


def _write_raw_json(path: Path, payload: object | None = None) -> Path:
    path.write_text(json.dumps(payload or _raw_payload()), encoding="utf-8")
    return path


def _parse_replay(tmp_path: Path, *, stage_dir: Path | None = None, raw_path: Path | None = None) -> Envelope:
    replay_path = raw_path or _write_raw_json(tmp_path / "cached.raw.json")
    runtime: dict[str, object] = {"replay_raw_json_path": replay_path}
    if stage_dir is not None:
        runtime["output_dir"] = stage_dir
    return gmp.parse_url(KENYALAW_URL, config={"runtime": runtime})


def test_default_writer_materializes_available_default_bundles_deterministically(
    tmp_path: Path,
) -> None:
    env = _parse_replay(tmp_path, stage_dir=tmp_path / "stage")
    out_dir = tmp_path / "bundles"

    first = gmp.write_envelope(env, out_dir)
    first_bytes = {name: path.read_bytes() for name, path in first.items()}
    second = gmp.write_envelope(env, out_dir)
    second_bytes = {name: path.read_bytes() for name, path in second.items()}

    assert first == second
    assert set(first) == {"envelope", "source_metadata", "raw_mistral_json", "joined_markdown"}
    assert first["envelope"] == out_dir / "gazette_2026-04-17_68_envelope.json"
    assert first["source_metadata"] == out_dir / "gazette_2026-04-17_68_source.json"
    assert first["raw_mistral_json"] == out_dir / "gazette_2026-04-17_68.raw.json"
    assert first["joined_markdown"] == out_dir / "gazette_2026-04-17_68_joined.md"
    assert first_bytes == second_bytes
    assert first["envelope"].read_text(encoding="utf-8").endswith("\n")
    assert json.loads(first["envelope"].read_text(encoding="utf-8"))["source"]["run_name"] == (
        "gazette_2026-04-17_68"
    )
    assert first["raw_mistral_json"].read_bytes() == Path(env.mistral.raw_json_path).read_bytes()
    assert first["joined_markdown"].read_text(encoding="utf-8") == Path(
        env.notices[0].provenance.source_markdown_path
    ).read_text(encoding="utf-8")


def test_optional_writer_outputs_and_document_index_are_deterministic(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path, stage_dir=tmp_path / "stage")
    out_dir = tmp_path / "optional"
    bundles = Bundles(
        joined_markdown=False,
        raw_mistral_json=False,
        notices=True,
        tables=True,
        document_index=True,
        debug_trace=True,
    )

    first = gmp.write_envelope(env, out_dir, bundles)
    first_bytes = {name: path.read_bytes() for name, path in first.items()}
    second = gmp.write_envelope(env, out_dir, bundles)

    assert set(first) == {
        "envelope",
        "source_metadata",
        "notices",
        "tables",
        "debug_trace",
        "document_index",
    }
    assert "raw_mistral_json" not in first
    assert "joined_markdown" not in first
    assert first_bytes == {name: path.read_bytes() for name, path in second.items()}
    notices = json.loads(first["notices"].read_text(encoding="utf-8"))
    tables = json.loads(first["tables"].read_text(encoding="utf-8"))
    index = json.loads(first["document_index"].read_text(encoding="utf-8"))
    trace = json.loads(first["debug_trace"].read_text(encoding="utf-8"))
    assert len(notices) == env.stats.notice_count
    assert len(tables) == env.stats.table_count
    assert set(index["artifacts"]) == set(first)
    assert index["artifacts"]["notices"] == "gazette_2026-04-17_68_notices.json"
    assert index["artifacts"]["document_index"] == "gazette_2026-04-17_68_index.json"
    assert index["source"]["run_name"] == env.source.run_name
    assert trace["notice_ids"] == [notice.notice_id for notice in env.notices]


def test_writer_returns_same_paths_without_self_copy_for_existing_stage_artifacts(
    tmp_path: Path,
) -> None:
    run_name = "gazette_2026-04-17_68"
    raw_path = _write_raw_json(tmp_path / f"{run_name}.raw.json")
    env = _parse_replay(tmp_path, stage_dir=tmp_path, raw_path=raw_path)
    joined_path = tmp_path / f"{run_name}_joined.md"
    raw_before = raw_path.read_bytes()
    joined_before = joined_path.read_bytes()

    written = gmp.write_envelope(env, tmp_path)

    assert written["raw_mistral_json"] == raw_path
    assert written["joined_markdown"] == joined_path
    assert raw_path.read_bytes() == raw_before
    assert joined_path.read_bytes() == joined_before


def test_missing_selected_external_artifacts_fail_clearly(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path, stage_dir=tmp_path / "stage")
    missing_raw = env.model_copy(
        update={"mistral": env.mistral.model_copy(update={"raw_json_path": None})},
        deep=True,
    )

    with pytest.raises(ValueError, match="raw_mistral_json"):
        gmp.write_envelope(missing_raw, tmp_path / "out")

    no_joined = _parse_replay(tmp_path, stage_dir=None)
    with pytest.raises(ValueError, match="joined_markdown"):
        gmp.write_envelope(
            no_joined,
            tmp_path / "joined-only",
            {"envelope": False, "source_metadata": False, "raw_mistral_json": False, "joined_markdown": True},
        )


def test_schema_bundle_request_writes_checked_in_schema(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path, stage_dir=tmp_path / "stage")
    out_dir = tmp_path / "schema"

    written = gmp.write_envelope(
        env,
        out_dir,
        {
            "schema": True,
            "envelope": False,
            "source_metadata": False,
            "raw_mistral_json": False,
            "joined_markdown": False,
        },
    )

    assert written == {"schema": out_dir / "gazette_2026-04-17_68_schema.json"}
    assert written["schema"].read_bytes() == get_envelope_schema_bytes()


def test_writer_validates_envelope_mapping_and_bundle_dicts(tmp_path: Path) -> None:
    env = _parse_replay(tmp_path, stage_dir=tmp_path / "stage")

    written = gmp.write_envelope(
        env.model_dump(mode="json"),
        tmp_path / "mapping",
        {"joined_markdown": False, "raw_mistral_json": False},
    )
    assert set(written) == {"envelope", "source_metadata"}

    with pytest.raises(ValidationError):
        gmp.write_envelope(env, tmp_path / "bad", {"unknown_bundle": True})
