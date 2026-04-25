"""Gate 1 + Gate 2 regression tests against real cached Mistral OCR JSON.

Gate 1 - Regression checks pass on selected cached Mistral OCR JSON fixtures:
    For each committed fixture, run the full replay pipeline (F04-F09),
    validate the envelope, assert stats are in the known range, confirm
    write_envelope produces valid bundles, and confirm schema validation passes.

Gate 2 - Re-running the same cached response is deterministic:
    For each fixture, run parse_url twice and assert that source IDs, run IDs,
    and all notice IDs are identical across both runs.

No network calls, no Mistral API key required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import gazette_mistral_pipeline as gmp
from gazette_mistral_pipeline.models import GazetteConfig

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

FIXTURE_SPECS: list[dict] = [
    {
        "run_name": "gazette_2026-04-17_68",
        "raw_json": FIXTURES_DIR / "gazette_2026-04-17_68.raw.json",
        "url": "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/eng@2026-04-17/source.pdf",
        "expected_pages": 52,
        "expected_notices_min": 200,
        "expected_notices_max": 280,
        "expected_tables_min": 20,
        # Pinned from first live run - must not change if pipeline is rerun on the same fixture
        "source_sha256": "0edcfc5fd75e5a4edc1935e8b14f8521a5bb6606169d7c9106247bf995f98c9e",
        "raw_json_sha256": "268ee25b511b392e143ab8aa8b0146c0c11a275989b28446da17a9add3353e44",
    },
    {
        "run_name": "gazette_2009-12-11_103",
        "raw_json": FIXTURES_DIR / "gazette_2009-12-11_103.raw.json",
        "url": "https://new.kenyalaw.org/akn/ke/officialGazette/2009-12-11/103/eng@2009-12-11/source.pdf",
        "expected_pages": 64,
        "expected_notices_min": 280,
        "expected_notices_max": 380,
        "expected_tables_min": 20,
        # Pinned from first live run
        "source_sha256": "a7cf85dd1726afb7ef971fee46abecd078bcf6a467ba6eaf7bc692f1d6cfc184",
        "raw_json_sha256": "24733ca8ffb2bd3b38f99e14fd6a48fd0753c366cae15b5c3b7b828274cd8745",
    },
]


def _replay_config(spec: dict, output_dir: Path) -> GazetteConfig:
    return GazetteConfig(
        runtime={
            "replay_raw_json_path": spec["raw_json"],
            "output_dir": output_dir,
        }
    )


def test_f15_2009_running_headers_are_excluded_from_joined_markdown_and_notice_text(tmp_path: Path) -> None:
    """F15: page running headers should not become the previous notice tail."""

    spec = next(item for item in FIXTURE_SPECS if item["run_name"] == "gazette_2009-12-11_103")
    raw_before = spec["raw_json"].read_bytes()
    stage_dir = tmp_path / "stage"

    env = gmp.parse_url(spec["url"], config=_replay_config(spec, stage_dir))
    joined_markdown = (stage_dir / f"{spec['run_name']}_joined.md").read_text(encoding="utf-8")

    assert spec["raw_json"].read_bytes() == raw_before
    assert "\n## Index 2\n\nGAZETTE NOTICE NO. 13176" in joined_markdown
    assert "\n## Index 2\n\n11th December, 2009\nTHE KENYA GAZETTE\n3509" not in joined_markdown

    notice_13175 = next(notice for notice in env.notices if notice.notice_no == "13175")
    assert "11th December, 2009\nTHE KENYA GAZETTE\n3509" not in notice_13175.raw_markdown
    assert "THE KENYA GAZETTE 3509" not in notice_13175.text


def test_f16_2009_post_notice_tail_is_excluded_from_final_notice(tmp_path: Path) -> None:
    """F16: catalogue and subscriber tail pages stay out of the final notice."""

    spec = next(item for item in FIXTURE_SPECS if item["run_name"] == "gazette_2009-12-11_103")
    raw_before = spec["raw_json"].read_bytes()
    stage_dir = tmp_path / "stage"

    env = gmp.parse_url(spec["url"], config=_replay_config(spec, stage_dir))
    joined_markdown = (stage_dir / f"{spec['run_name']}_joined.md").read_text(encoding="utf-8")

    assert spec["raw_json"].read_bytes() == raw_before
    assert "NATIONAL DEVELOPMENT PLAN 2002-2008" in joined_markdown
    assert "NOW ON SALE" in joined_markdown
    assert "SUBSCRIPTION AND ADVERTISEMENT CHARGES" in joined_markdown

    final_notice = env.notices[-1]
    assert final_notice.notice_no == "13493"
    assert "MOSI &amp; COMPANY" in final_notice.raw_markdown
    assert "formerly known as Hellen Lily Namvua Mbelle" in final_notice.text
    assert "NATIONAL DEVELOPMENT PLAN 2002-2008" not in final_notice.raw_markdown
    assert "NOW ON SALE" not in final_notice.text
    assert "SUBSCRIPTION AND ADVERTISEMENT CHARGES" not in final_notice.text
    assert final_notice.other_attributes["parser_version"] == "F16"


@pytest.mark.parametrize("spec", FIXTURE_SPECS, ids=[s["run_name"] for s in FIXTURE_SPECS])
def test_gate1_cached_fixture_processes_and_validates(
    spec: dict,
    tmp_path: Path,
) -> None:
    """Gate 1: full pipeline runs on cached fixture and produces a valid envelope."""
    assert spec["raw_json"].is_file(), (
        f"Fixture not found: {spec['raw_json']}. "
        "Commit the raw JSON under tests/fixtures/ to enable this regression test."
    )

    env = gmp.parse_url(spec["url"], config=_replay_config(spec, tmp_path / "stage"))

    # Source and replay metadata
    assert env.source.run_name == spec["run_name"]
    assert env.source.source_type == "pdf_url"
    assert env.mistral.request_options["replay"] is True

    # Pinned SHA256s must not drift (any change in source or raw JSON is a regression)
    assert env.source.source_sha256 == spec["source_sha256"]
    assert env.mistral.raw_json_sha256 == spec["raw_json_sha256"]

    # Page count must match exactly (same file, same normalisation)
    assert env.stats.page_count == spec["expected_pages"], (
        f"Page count changed: expected {spec['expected_pages']}, got {env.stats.page_count}"
    )

    # Notice count within expected range (parser may improve; range absorbs small fixes)
    assert spec["expected_notices_min"] <= env.stats.notice_count <= spec["expected_notices_max"], (
        f"Notice count {env.stats.notice_count} outside expected range "
        f"[{spec['expected_notices_min']}, {spec['expected_notices_max']}]"
    )

    # At least some tables must be found
    assert env.stats.table_count >= spec["expected_tables_min"], (
        f"Table count {env.stats.table_count} dropped below minimum {spec['expected_tables_min']}"
    )

    # Envelope schema validation must pass
    bundle_dir = tmp_path / "bundles"
    written = gmp.write_envelope(
        env,
        bundle_dir,
        gmp.Bundles(notices=True, tables=True, document_index=True, schema=True),
    )
    validated = gmp.validate_envelope_json(written["envelope"])
    assert validated.source.run_name == spec["run_name"]
    assert validated.stats.notice_count == env.stats.notice_count


@pytest.mark.parametrize("spec", FIXTURE_SPECS, ids=[s["run_name"] for s in FIXTURE_SPECS])
def test_gate2_same_cached_fixture_is_deterministic(
    spec: dict,
    tmp_path: Path,
) -> None:
    """Gate 2: running the same cached fixture twice gives identical stable identifiers."""
    assert spec["raw_json"].is_file(), (
        f"Fixture not found: {spec['raw_json']}. "
        "Commit the raw JSON under tests/fixtures/ to enable this determinism test."
    )

    stage_a = tmp_path / "run_a"
    stage_b = tmp_path / "run_b"

    env_a = gmp.parse_url(spec["url"], config=_replay_config(spec, stage_a))
    env_b = gmp.parse_url(spec["url"], config=_replay_config(spec, stage_b))

    # Source-level stability
    assert env_a.source.run_name == env_b.source.run_name
    assert env_a.source.source_type == env_b.source.source_type
    assert env_a.source.source_sha256 == env_b.source.source_sha256

    # Stats must be identical across runs
    assert env_a.stats.page_count == env_b.stats.page_count
    assert env_a.stats.notice_count == env_b.stats.notice_count
    assert env_a.stats.table_count == env_b.stats.table_count

    # Every notice ID must be identical and in the same order
    ids_a = [n.notice_id for n in env_a.notices]
    ids_b = [n.notice_id for n in env_b.notices]
    assert ids_a == ids_b, (
        f"Notice IDs differ between runs: first diff at index "
        f"{next(i for i,(a,b) in enumerate(zip(ids_a,ids_b)) if a!=b)}"
        if ids_a != ids_b else ""
    )

    # Every notice content hash must be stable
    hashes_a = [n.content_sha256 for n in env_a.notices]
    hashes_b = [n.content_sha256 for n in env_b.notices]
    assert hashes_a == hashes_b

    # Mistral metadata fields that must be stable
    assert env_a.mistral.model == env_b.mistral.model
    assert env_a.mistral.page_count == env_b.mistral.page_count
    assert env_a.mistral.raw_json_sha256 == env_b.mistral.raw_json_sha256
