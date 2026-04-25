from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from gazette_mistral_pipeline.__version__ import LIBRARY_VERSION, SCHEMA_VERSION
from gazette_mistral_pipeline.confidence_scoring import (
    ScoredParsingResult,
    score_parsed_notices,
)
from gazette_mistral_pipeline.envelope_builder import (
    OUTPUT_FORMAT_VERSION,
    EnvelopeBuildInputs,
    build_envelope,
)
from gazette_mistral_pipeline.models import Envelope, MistralMetadata, PdfSource
from gazette_mistral_pipeline.notice_parsing import ParsedMarkdownResult, parse_joined_markdown
from gazette_mistral_pipeline.page_normalization import (
    NormalizedPage,
    StitchedMarkdownResult,
    stitch_markdown_pages,
)

KENYALAW_URL = (
    "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/"
    "eng@2026-04-17/source.pdf"
)
FIXED_NOW = datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc)


def _joined_notice(body: str) -> str:
    return (
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        f"{body}\n"
    )


def _source_mapping() -> dict[str, object]:
    return {
        "source_type": "pdf_url",
        "source_value": KENYALAW_URL,
        "run_name": "gazette_2026-04-17_68",
        "source_sha256": "b" * 64,
        "source_metadata_path": "gazette_2026-04-17_68_source.json",
    }


def _mistral_mapping(*, page_count: int | None = 1) -> dict[str, object]:
    return {
        "model": "mistral-ocr-latest",
        "raw_json_path": "gazette_2026-04-17_68.raw.json",
        "raw_json_sha256": "c" * 64,
        "document_url": KENYALAW_URL,
        "mistral_doc_ids": ["doc_1"],
        "page_count": page_count,
        "request_options": {"replay": True},
    }


def _parsed_and_scored(markdown_body: str) -> tuple[ParsedMarkdownResult, ScoredParsingResult]:
    parsed = parse_joined_markdown(
        _joined_notice(markdown_body),
        run_name="gazette_2026-04-17_68",
        source_markdown_path="gazette_2026-04-17_68_joined.md",
    )
    return parsed, score_parsed_notices(parsed)


def _happy_markdown_body() -> str:
    return (
        "## CORRIGENDA\n\n"
        "IN Gazette Notice No. 3308 of 2008 amend the second line.\n\n"
        "## GAZETTE NOTICE NO. 5969\n\n"
        "THE LAND REGISTRATION ACT\n\n"
        "IN EXERCISE of the powers conferred by law, the Registrar gives notice.\n\n"
        "| Parcel | Owner |\n"
        "| --- | --- |\n"
        "| Kajiado/1 | Jane Doe |\n"
        "| Kajiado/2 | John Doe |\n\n"
        "Dated the 17th April, 2026.\n\n"
        "REGISTRAR,\n"
        "Lands Registry."
    )


def _inputs(
    *,
    parsed: ParsedMarkdownResult | None = None,
    scored: ScoredParsingResult | None = None,
    f06_stats: dict[str, int] | StitchedMarkdownResult | None = None,
    source: PdfSource | dict[str, object] | None = None,
    mistral: MistralMetadata | dict[str, object] | None = None,
) -> EnvelopeBuildInputs:
    if parsed is None or scored is None:
        default_parsed, default_scored = _parsed_and_scored(_happy_markdown_body())
        parsed = parsed or default_parsed
        scored = scored or default_scored
    if f06_stats is None:
        f06_stats = {
            "document_count": 1,
            "page_count": 1,
            "char_count_markdown": len(_joined_notice(_happy_markdown_body())),
        }
    return EnvelopeBuildInputs(
        source=source or _source_mapping(),
        mistral=mistral or _mistral_mapping(),
        f06_stats=f06_stats,
        parsed=parsed,
        scored=scored,
    )


def test_valid_envelope_happy_path_preserves_versions_counts_and_ordering() -> None:
    parsed, scored = _parsed_and_scored(_happy_markdown_body())

    env = build_envelope(_inputs(parsed=parsed, scored=scored), now=FIXED_NOW)

    assert isinstance(env, Envelope)
    assert env.library_version == LIBRARY_VERSION
    assert env.schema_version == SCHEMA_VERSION
    assert env.output_format_version == OUTPUT_FORMAT_VERSION
    assert env.generated_at_utc == FIXED_NOW
    assert env.source.run_name == "gazette_2026-04-17_68"
    assert env.mistral.model == "mistral-ocr-latest"
    assert env.stats.document_count == 1
    assert env.stats.page_count == 1
    assert env.stats.char_count_markdown == len(_joined_notice(_happy_markdown_body()))
    assert env.stats.notice_count == len(env.notices) == 1
    assert env.stats.table_count == len(env.tables) == 1
    assert env.stats.warnings_count == len(env.warnings) == 0
    assert [notice.notice_id for notice in env.notices] == [
        notice.notice_id for notice in scored.scored_notices
    ]
    assert env.tables == list(env.notices[0].tables)
    assert env.tables == list(parsed.tables)
    assert env.corrigenda == list(parsed.corrigenda)
    assert env.model_dump(mode="json")["generated_at_utc"]


def test_degraded_parse_preserves_warnings_and_document_confidence_reasons() -> None:
    parsed = parse_joined_markdown("")
    scored = score_parsed_notices(parsed)

    env = build_envelope(_inputs(parsed=parsed, scored=scored), now=FIXED_NOW)

    assert env.notices == []
    assert [warning.kind for warning in env.warnings] == [
        warning.kind for warning in scored.warnings
    ]
    assert env.stats.warnings_count == len(env.warnings)
    assert env.document_confidence.reasons == scored.document_confidence.reasons
    assert env.document_confidence.composite < 0.60


def test_missing_optional_source_and_mistral_metadata_remains_valid() -> None:
    parsed, scored = _parsed_and_scored(
        "GAZETTE NOTICE NO. 7000\n"
        "THE CLEAN ACT\n\n"
        "IN EXERCISE of the powers conferred by law.\n\n"
        "Dated the 17th April, 2026."
    )
    source = PdfSource(
        source_type="pdf_url",
        source_value=KENYALAW_URL,
        run_name="gazette_2026-04-17_68",
        source_sha256=None,
        source_metadata_path=None,
    )
    mistral = MistralMetadata(
        model="mistral-ocr-latest",
        raw_json_path=None,
        raw_json_sha256=None,
        document_url=None,
        mistral_doc_ids=[],
        page_count=1,
        request_options={},
    )

    env = build_envelope(
        _inputs(parsed=parsed, scored=scored, source=source, mistral=mistral),
        now=FIXED_NOW,
    )

    assert env.source.source_sha256 is None
    assert env.source.source_metadata_path is None
    assert env.mistral.raw_json_path is None
    assert env.mistral.raw_json_sha256 is None
    assert env.mistral.document_url is None
    assert env.mistral.mistral_doc_ids == []
    assert env.layout_info.available is False
    assert env.model_dump(mode="json")


def test_deterministic_generated_time_and_collection_ordering() -> None:
    parsed, scored = _parsed_and_scored(
        "GAZETTE NOTICE NO. 8001\n"
        "THE FIRST ACT\n"
        "IN EXERCISE of the powers conferred by law.\n"
        "Dated the 17th April, 2026.\n"
        "GAZETTE NOTICE NO. 8002\n"
        "THE SECOND ACT\n"
        "IN EXERCISE of the powers conferred by law.\n"
        "Dated the 18th April, 2026."
    )

    first = build_envelope(_inputs(parsed=parsed, scored=scored), now=FIXED_NOW)
    second = build_envelope(_inputs(parsed=parsed, scored=scored), now=FIXED_NOW)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert [notice.notice_no for notice in first.notices] == ["8001", "8002"]
    assert [warning.kind for warning in first.warnings] == [
        warning.kind for warning in scored.warnings
    ]


def test_default_generated_time_is_current_utc() -> None:
    before = datetime.now(timezone.utc)
    env = build_envelope(_inputs())
    after = datetime.now(timezone.utc)

    assert env.generated_at_utc.tzinfo is timezone.utc
    assert before <= env.generated_at_utc <= after


def test_aware_non_utc_callable_clock_is_normalized_to_utc() -> None:
    plus_three = timezone(timedelta(hours=3))

    env = build_envelope(
        _inputs(),
        now=lambda: datetime(2026, 4, 25, 15, 30, tzinfo=plus_three),
    )

    assert env.generated_at_utc == FIXED_NOW
    assert env.generated_at_utc.tzinfo is timezone.utc


def test_naive_generated_time_fails_clearly() -> None:
    with pytest.raises(ValueError, match="generated_at_utc|timezone-aware"):
        build_envelope(_inputs(), now=datetime(2026, 4, 25, 12, 30))


def test_notice_count_mismatch_fails_without_partial_envelope() -> None:
    parsed, scored = _parsed_and_scored(_happy_markdown_body())
    bad_parsed = replace(parsed, notice_count=2)

    with pytest.raises(ValueError, match="notice_count"):
        build_envelope(_inputs(parsed=bad_parsed, scored=scored), now=FIXED_NOW)


def test_scored_notice_count_mismatch_fails_without_partial_envelope() -> None:
    parsed, scored = _parsed_and_scored(_happy_markdown_body())
    bad_scored = replace(scored, scored_notices=())

    with pytest.raises(ValueError, match="notice_count"):
        build_envelope(_inputs(parsed=parsed, scored=bad_scored), now=FIXED_NOW)


def test_table_count_mismatch_fails_for_parsed_and_notice_counts() -> None:
    parsed, scored = _parsed_and_scored(_happy_markdown_body())
    bad_parsed = replace(parsed, table_count=0)

    with pytest.raises(ValueError, match="table_count"):
        build_envelope(_inputs(parsed=bad_parsed, scored=scored), now=FIXED_NOW)

    bad_notice = scored.scored_notices[0].model_copy(update={"table_count": 99}, deep=True)
    bad_scored = replace(scored, scored_notices=(bad_notice,))

    with pytest.raises(ValueError, match=f"table_count.*{bad_notice.notice_id}"):
        build_envelope(_inputs(parsed=parsed, scored=bad_scored), now=FIXED_NOW)


def test_tables_are_flattened_once_from_scored_notices() -> None:
    parsed, scored = _parsed_and_scored(_happy_markdown_body())

    env = build_envelope(_inputs(parsed=parsed, scored=scored), now=FIXED_NOW)

    assert parsed.table_count == 1
    assert len(env.notices[0].tables) == 1
    assert env.tables == [env.notices[0].tables[0]]
    assert len(env.tables) == 1


def test_warning_count_uses_final_warning_list_after_assembly_warning() -> None:
    env = build_envelope(
        _inputs(mistral=_mistral_mapping(page_count=5)),
        now=FIXED_NOW,
    )

    assert env.stats.page_count == 1
    assert [warning.kind for warning in env.warnings] == ["page_count_mismatch"]
    assert env.stats.warnings_count == len(env.warnings) == 1


def test_pydantic_validation_catches_bad_source_and_mistral_shapes() -> None:
    bad_source = {
        "source_type": "pdf_url",
        "source_value": KENYALAW_URL,
    }
    with pytest.raises(ValidationError):
        build_envelope(_inputs(source=bad_source), now=FIXED_NOW)

    bad_mistral = {"raw_json_path": "missing-model.raw.json"}
    with pytest.raises(ValidationError):
        build_envelope(_inputs(mistral=bad_mistral), now=FIXED_NOW)


def test_stitched_markdown_result_can_supply_f06_stats() -> None:
    page = NormalizedPage(
        index=0,
        original_page_index=0,
        document_index=0,
        document_id="doc_1",
        document_url=KENYALAW_URL,
        model="mistral-ocr-latest",
        markdown="Page text",
        raw_page_metadata={},
    )
    markdown = stitch_markdown_pages((page,))
    stitched = StitchedMarkdownResult(
        pages=(page,),
        markdown=markdown,
        document_count=1,
        page_count=1,
        char_count_markdown=len(markdown),
        output_path=Path("gazette_2026-04-17_68_joined.md"),
    )

    env = build_envelope(_inputs(f06_stats=stitched), now=FIXED_NOW)

    assert env.stats.document_count == stitched.document_count
    assert env.stats.page_count == stitched.page_count
    assert env.stats.char_count_markdown == stitched.char_count_markdown


def test_input_dataclass_is_frozen() -> None:
    inputs = _inputs()

    with pytest.raises(FrozenInstanceError):
        inputs.source = _source_mapping()  # type: ignore[misc]
