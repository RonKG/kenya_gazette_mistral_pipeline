from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from gazette_mistral_pipeline.confidence_scoring import (
    ScoredParsingResult,
    aggregate_document_confidence,
    score_band,
    score_parsed_notices,
    summarize_layout_hints,
)
from gazette_mistral_pipeline.models import (
    ConfidenceScores,
    DocumentConfidence,
    LayoutInfo,
    Notice,
    PipelineWarning,
    Provenance,
)
from gazette_mistral_pipeline.notice_parsing import (
    PENDING_CONFIDENCE_REASON,
    parse_joined_markdown,
)


def _joined_notice(body: str) -> str:
    return (
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        f"{body}\n"
    )


def _score_result(markdown_body: str) -> ScoredParsingResult:
    return score_parsed_notices(parse_joined_markdown(_joined_notice(markdown_body)))


def _assert_notice_scores_in_range(notice: Notice) -> None:
    scores = notice.confidence_scores
    values = [
        scores.notice_number,
        scores.structure,
        scores.boundary,
        scores.composite,
    ]
    if scores.table is not None:
        values.append(scores.table)
    if scores.spatial is not None:
        values.append(scores.spatial)
    assert all(0.0 <= value <= 1.0 for value in values)


def _scored_notice(
    notice_id: str,
    *,
    composite: float,
    band: str,
    boundary: float | None = None,
    table: float | None = None,
) -> Notice:
    return Notice(
        notice_id=notice_id,
        notice_no=notice_id.rsplit("-", 1)[-1],
        dates_found=["17th April, 2026"],
        title_lines=["THE TEST ACT"],
        text="GAZETTE NOTICE NO. 1000\nTHE TEST ACT\nIN EXERCISE text.",
        raw_markdown="GAZETTE NOTICE NO. 1000\nTHE TEST ACT\nIN EXERCISE text.",
        tables=[],
        table_count=0,
        provenance=Provenance(
            header_match="strict",
            page_span=(0, 0),
            line_span=(1, 4),
            raw_header_line="GAZETTE NOTICE NO. 1000",
            stitched_from=["page:0"],
        ),
        confidence_scores=ConfidenceScores(
            notice_number=composite,
            structure=composite,
            boundary=boundary if boundary is not None else composite,
            table=table,
            spatial=None,
            composite=composite,
            band=band,  # type: ignore[arg-type]
        ),
        confidence_reasons=[],
        content_sha256="a" * 64,
    )


def test_high_confidence_notice_replaces_f07_placeholder_without_mutation() -> None:
    parsed = parse_joined_markdown(
        _joined_notice(
            "## GAZETTE NOTICE NO. 5969\n\n"
            "THE STATE CORPORATIONS ACT\n\n"
            "IN EXERCISE of the powers conferred by law, the Cabinet Secretary appoints Jane Doe.\n\n"
            "Dated the 7th July, 2008.\n\n"
            "JANE DOE,\n"
            "Cabinet Secretary."
        )
    )
    original_notice = parsed.notices[0]

    result = score_parsed_notices(parsed)
    notice = result.scored_notices[0]

    assert isinstance(result, ScoredParsingResult)
    assert notice is not original_notice
    assert original_notice.confidence_scores.composite == 0.5
    assert original_notice.confidence_reasons == [PENDING_CONFIDENCE_REASON]
    assert notice.confidence_scores != original_notice.confidence_scores
    assert notice.confidence_scores.notice_number >= 0.85
    assert notice.confidence_scores.structure >= 0.85
    assert notice.confidence_scores.boundary >= 0.85
    assert notice.confidence_scores.composite >= 0.85
    assert notice.confidence_scores.band == "high"
    assert PENDING_CONFIDENCE_REASON not in notice.confidence_reasons
    _assert_notice_scores_in_range(notice)


def test_recovered_header_scores_medium_and_is_deterministic() -> None:
    markdown = _joined_notice(
        "GRZETTE NOTICE NO. 12171\n"
        "THE COMPANIES ACT\n\n"
        "IN EXERCISE of the powers conferred by law, the Registrar appoints the receiver "
        "for the company and directs that the notice takes effect immediately."
    )

    first = score_parsed_notices(parse_joined_markdown(markdown)).scored_notices[0]
    second = score_parsed_notices(parse_joined_markdown(markdown)).scored_notices[0]

    assert first.confidence_scores == second.confidence_scores
    assert first.confidence_scores.band == "medium"
    assert first.confidence_scores.notice_number < 0.85
    assert first.confidence_scores.boundary < 0.85
    assert any("recovered" in reason or "noisy" in reason for reason in first.confidence_reasons)


def test_low_confidence_weak_body_has_explainable_reasons() -> None:
    notice = _score_result("GAZETTE NOTICE NO. 9\nBody.").scored_notices[0]

    assert notice.confidence_scores.structure < 0.60
    assert notice.confidence_scores.composite < 0.60
    assert notice.confidence_scores.band == "low"
    assert any("very short" in reason for reason in notice.confidence_reasons)
    assert any("legal body markers" in reason for reason in notice.confidence_reasons)


def test_table_quality_contributes_without_requiring_tables() -> None:
    with_table = _score_result(
        "GAZETTE NOTICE NO. 3000\n"
        "THE LAND REGISTRATION ACT\n\n"
        "IN EXERCISE of the powers conferred by law.\n\n"
        "| Parcel | Owner |\n"
        "| --- | --- |\n"
        "| Kajiado/1 | Jane Doe |\n"
        "| Kajiado/2 | John Doe |\n\n"
        "Dated the 7th July, 2008."
    ).scored_notices[0]
    without_table = _score_result(
        "GAZETTE NOTICE NO. 3001\n"
        "THE LAND REGISTRATION ACT\n\n"
        "IN EXERCISE of the powers conferred by law.\n\n"
        "Dated the 7th July, 2008."
    ).scored_notices[0]

    assert with_table.confidence_scores.table is not None
    assert with_table.confidence_scores.table >= 0.85
    assert without_table.confidence_scores.table is None
    assert without_table.confidence_scores.composite >= 0.85


def test_ragged_table_reduces_table_score() -> None:
    notice = _score_result(
        "GAZETTE NOTICE NO. 3002\n"
        "THE LAND REGISTRATION ACT\n\n"
        "IN EXERCISE of the powers conferred by law.\n\n"
        "| Name | Notes | Amount |\n"
        "| --- | --- | --- |\n"
        "| Jane | short |\n"
        "| John | has | extra | pipe |\n\n"
        "Dated the 7th July, 2008."
    ).scored_notices[0]

    assert notice.confidence_scores.table is not None
    assert notice.confidence_scores.table < 0.85
    assert any("ragged" in reason or "sparse" in reason for reason in notice.confidence_reasons)


def test_duplicate_notice_numbers_reduce_boundary_confidence_for_both_notices() -> None:
    result = score_parsed_notices(
        parse_joined_markdown(
            _joined_notice(
                "GAZETTE NOTICE NO. 4000\n"
                "THE FIRST ACT\n"
                "IN EXERCISE of the powers conferred by law.\n"
                "Dated the 7th July, 2008.\n"
                "GAZETTE NOTICE NO. 4000\n"
                "THE SECOND ACT\n"
                "IN EXERCISE of the powers conferred by law.\n"
                "Dated the 8th July, 2008."
            )
        )
    )

    assert [notice.notice_no for notice in result.scored_notices] == ["4000", "4000"]
    assert all(notice.confidence_scores.boundary < 0.85 for notice in result.scored_notices)
    assert all(
        any("duplicate notice number" in reason for reason in notice.confidence_reasons)
        for notice in result.scored_notices
    )
    assert result.document_confidence.notice_split < 0.85


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (1.0, "high"),
        (0.85, "high"),
        (0.849, "medium"),
        (0.60, "medium"),
        (0.599, "low"),
        (0.0, "low"),
    ],
)
def test_score_band_boundaries(score: float, band: str) -> None:
    assert score_band(score) == band


@pytest.mark.parametrize("score", [-0.001, 1.001, float("nan"), True])
def test_score_band_rejects_invalid_ranges(score: float) -> None:
    with pytest.raises(ValueError, match="between 0.0 and 1.0|must be a number"):
        score_band(score)  # type: ignore[arg-type]


def test_document_confidence_aggregation_counts_mean_min_and_warning_impact() -> None:
    notices = [
        _scored_notice("notice-1", composite=0.90, band="high", boundary=0.90),
        _scored_notice("notice-2", composite=0.70, band="medium", boundary=0.75),
        _scored_notice("notice-3", composite=0.40, band="low", boundary=0.50),
    ]
    warning = PipelineWarning(kind="test_warning", message="example")
    without_warning = aggregate_document_confidence(
        notices,
        layout_info=LayoutInfo(available=False, reasons=["no coordinate metadata found"]),
        warnings=[],
    )

    confidence = aggregate_document_confidence(
        notices,
        layout_info=LayoutInfo(available=False, reasons=["no coordinate metadata found"]),
        warnings=[warning],
    )

    assert isinstance(confidence, DocumentConfidence)
    assert confidence.counts == {"high": 1, "medium": 1, "low": 1}
    assert confidence.n_notices == 3
    assert confidence.mean_composite == pytest.approx(0.6667)
    assert confidence.min_composite == 0.40
    assert confidence.notice_split == pytest.approx(0.7167)
    assert confidence.composite < without_warning.composite
    assert any("low-confidence" in reason for reason in confidence.reasons)
    assert any("test_warning" in reason for reason in confidence.reasons)


def test_empty_parse_result_returns_low_confidence_and_no_notices_warning() -> None:
    result = score_parsed_notices(parse_joined_markdown(""))

    assert result.scored_notices == ()
    assert result.layout_info.available is False
    assert result.document_confidence.n_notices == 0
    assert result.document_confidence.composite < 0.60
    assert any(warning.kind == "no_notices" for warning in result.warnings)


def test_layout_unavailable_without_warning_when_coordinates_are_absent() -> None:
    result = score_parsed_notices(
        parse_joined_markdown(
            _joined_notice(
                "GAZETTE NOTICE NO. 5000\n"
                "THE CLEAN ACT\n\n"
                "IN EXERCISE of the powers conferred by law.\n\n"
                "Dated the 7th July, 2008."
            )
        ),
        raw_mistral_json={"pages": [{"index": 0, "markdown": "Text-only page"}]},
    )

    assert result.layout_info.available is False
    assert result.layout_info.positioned_element_count == 0
    assert any("no coordinate metadata" in reason for reason in result.layout_info.reasons)
    assert result.warnings == ()


def test_layout_summary_counts_page_dimensions_and_positioned_elements() -> None:
    layout = summarize_layout_hints({
        "pages": [
            {
                "index": 0,
                "markdown": "Page 0 text",
                "dimensions": {"width": 719, "height": 1018},
                "images": [{"bbox": [10, 20, 30, 40]}],
                "tables": [{"bounds": {"left": 50, "top": 60, "right": 150, "bottom": 200}}],
            },
            {
                "index": 1,
                "markdown": "Page 1 text",
                "width": 719,
                "height": 1018,
                "words": [{"x": 1, "y": 2, "width": 3, "height": 4}],
            },
        ]
    })

    assert layout.available is True
    assert layout.positioned_element_count == 3
    assert layout.layout_confidence is not None
    assert layout.layout_confidence >= 0.85
    assert layout.pages == [
        {"page_index": 0, "positioned_elements": 2, "width": 719.0, "height": 1018.0, "has_text": True},
        {"page_index": 1, "positioned_elements": 1, "width": 719.0, "height": 1018.0, "has_text": True},
    ]


def test_supported_raw_json_shapes_share_layout_behavior() -> None:
    page = {
        "index": 0,
        "markdown": "Text",
        "dimensions": {"width": 100, "height": 200},
        "images": [{"bbox": [1, 2, 3, 4]}],
    }
    layouts = [
        summarize_layout_hints({"pages": [page]}),
        summarize_layout_hints([{"id": "doc", "pages": [page]}]),
        summarize_layout_hints([page]),
    ]

    assert {layout.positioned_element_count for layout in layouts} == {1}
    assert {layout.layout_confidence for layout in layouts} == {0.95}
    assert all(layout.available for layout in layouts)


def test_malformed_coordinate_metadata_is_nonfatal_and_warns_when_unusable() -> None:
    result = score_parsed_notices(
        parse_joined_markdown(
            _joined_notice(
                "GAZETTE NOTICE NO. 6000\n"
                "THE SPATIAL ACT\n\n"
                "IN EXERCISE of the powers conferred by law.\n\n"
                "Dated the 7th July, 2008."
            )
        ),
        raw_mistral_json={
            "pages": [
                {
                    "index": 0,
                    "markdown": "Page text",
                    "images": [{"bbox": ["left", "top", "right", "bottom"]}],
                }
            ]
        },
    )

    assert result.layout_info.available is False
    assert result.layout_info.positioned_element_count == 0
    assert any("unusable" in reason for reason in result.layout_info.reasons)
    assert any(warning.kind == "unusable_spatial_metadata" for warning in result.warnings)


def test_spatial_availability_informs_document_confidence_lightly() -> None:
    parsed = parse_joined_markdown(
        _joined_notice(
            "GAZETTE NOTICE NO. 7000\n"
            "THE SPATIAL ACT\n\n"
            "IN EXERCISE of the powers conferred by law.\n\n"
            "Dated the 7th July, 2008."
        )
    )
    without_coordinates = score_parsed_notices(
        parsed,
        raw_mistral_json={"pages": [{"index": 0, "markdown": "Page text"}]},
    )
    with_coordinates = score_parsed_notices(
        parsed,
        raw_mistral_json={
            "pages": [
                {
                    "index": 0,
                    "markdown": "Page text",
                    "dimensions": {"width": 719, "height": 1018},
                    "images": [{"bbox": [10, 20, 30, 40]}],
                }
            ]
        },
    )

    assert without_coordinates.document_confidence.spatial is None
    assert without_coordinates.document_confidence.composite >= 0.85
    assert with_coordinates.scored_notices[0].confidence_scores.spatial is not None
    assert with_coordinates.document_confidence.spatial is not None
    assert with_coordinates.document_confidence.composite >= 0.85
    assert (
        with_coordinates.document_confidence.spatial
        != without_coordinates.document_confidence.spatial
    )


def test_result_dataclass_is_frozen() -> None:
    result = score_parsed_notices(parse_joined_markdown(""))

    with pytest.raises(FrozenInstanceError):
        result.scorer_version = "changed"  # type: ignore[misc]
