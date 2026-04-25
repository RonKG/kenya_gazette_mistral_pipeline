from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import gazette_mistral_pipeline as gmp
from gazette_mistral_pipeline.models import (
    Bundles,
    ConfidenceScores,
    DocumentConfidence,
    Envelope,
    ExtractedTable,
    GazetteConfig,
    LayoutInfo,
    MistralMetadata,
    Notice,
    PdfSource,
    PipelineWarning,
    Provenance,
    Stats,
)


def _confidence(band: str = "high") -> dict:
    return {
        "notice_number": 1.0,
        "structure": 0.9,
        "boundary": 0.95,
        "table": None,
        "spatial": None,
        "composite": 0.95,
        "band": band,
    }


def _notice() -> dict:
    return {
        "notice_id": "gazette_2026-04-17_68:5567",
        "notice_no": "5567",
        "dates_found": ["17th April, 2026"],
        "title_lines": ["THE ENERGY ACT"],
        "text": "GAZETTE NOTICE NO. 5567\nTHE ENERGY ACT",
        "raw_markdown": "GAZETTE NOTICE NO. 5567\n\nTHE ENERGY ACT",
        "tables": [],
        "table_count": 0,
        "provenance": {
            "header_match": "strict",
            "page_span": [1, 1],
            "line_span": [10, 20],
            "raw_header_line": "GAZETTE NOTICE NO. 5567",
            "source_markdown_path": "gazette_2026-04-17_68_joined.md",
            "stitched_from": ["page:1"],
        },
        "confidence_scores": _confidence(),
        "confidence_reasons": [],
        "content_sha256": "a" * 64,
        "other_attributes": {},
    }


def _envelope(layout_info: dict | None = None) -> dict:
    return {
        "library_version": "0.1.0",
        "schema_version": "0.1",
        "output_format_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "source_type": "pdf_url",
            "source_value": "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/eng@2026-04-17/source.pdf",
            "run_name": "gazette_2026-04-17_68",
            "source_sha256": "b" * 64,
            "source_metadata_path": "gazette_2026-04-17_68_source.json",
        },
        "mistral": {
            "model": "mistral-ocr-latest",
            "raw_json_path": "gazette_2026-04-17_68.raw.json",
            "raw_json_sha256": "c" * 64,
            "document_url": "https://new.kenyalaw.org/akn/ke/officialGazette/2026-04-17/68/eng@2026-04-17/source.pdf",
            "mistral_doc_ids": ["doc-1"],
            "page_count": 1,
            "request_options": {"include_image_base64": False},
        },
        "stats": {
            "document_count": 1,
            "page_count": 1,
            "notice_count": 1,
            "table_count": 0,
            "char_count_markdown": 42,
            "warnings_count": 0,
        },
        "notices": [_notice()],
        "tables": [],
        "corrigenda": [],
        "document_confidence": {
            "ocr_quality": 0.98,
            "notice_split": 0.95,
            "table_quality": None,
            "spatial": None,
            "composite": 0.96,
            "counts": {"high": 1, "medium": 0, "low": 0},
            "mean_composite": 0.95,
            "min_composite": 0.95,
            "n_notices": 1,
            "reasons": [],
        },
        "layout_info": layout_info
        or {
            "available": False,
            "layout_confidence": None,
            "pages": [],
            "positioned_element_count": 0,
            "reasons": ["no positioned elements in response"],
        },
        "warnings": [],
    }


def test_model_imports_and_root_exports() -> None:
    expected = {
        "Envelope",
        "PdfSource",
        "MistralMetadata",
        "Notice",
        "ExtractedTable",
        "ConfidenceScores",
        "Provenance",
        "Stats",
        "LayoutInfo",
        "DocumentConfidence",
        "PipelineWarning",
        "Bundles",
        "GazetteConfig",
    }
    assert expected.issubset(set(gmp.__all__))
    assert gmp.Envelope is Envelope
    assert gmp.Bundles is Bundles
    assert gmp.GazetteConfig is GazetteConfig


def test_valid_minimal_envelope_round_trips_to_json() -> None:
    env = Envelope.model_validate(_envelope())
    dumped = env.model_dump(mode="json")
    assert dumped["source"]["run_name"] == "gazette_2026-04-17_68"
    assert dumped["notices"][0]["notice_no"] == "5567"
    assert dumped["layout_info"]["available"] is False


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (Envelope, lambda: {**_envelope(), "unexpected": True}),
        (Notice, lambda: {**_notice(), "unexpected": True}),
        (
            PdfSource,
            lambda: {
                "source_type": "pdf_url",
                "source_value": "https://example.com/source.pdf",
                "run_name": "example",
                "unexpected": True,
            },
        ),
    ],
)
def test_strict_models_reject_extra_fields(model, payload) -> None:
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate(payload())
    assert "extra_forbidden" in str(excinfo.value)


def test_extracted_table_allows_future_fields() -> None:
    table = ExtractedTable.model_validate({
        "headers": ["Name", "Role"],
        "rows": [["Jane", "Chair"]],
        "records": [{"Name": "Jane", "Role": "Chair"}],
        "raw_table_markdown": "| Name | Role |\n| --- | --- |\n| Jane | Chair |",
        "future_cell_spans": [{"row": 0, "col": 1}],
    })
    dumped = table.model_dump()
    assert dumped["future_cell_spans"] == [{"row": 0, "col": 1}]


def test_config_and_bundle_defaults_are_safe() -> None:
    config = GazetteConfig()
    assert config.mistral.model == "mistral-ocr-latest"
    assert config.mistral.api_key_env == "MISTRAL_API_KEY"
    assert config.runtime.deterministic is True
    assert config.bundles.envelope is True
    assert config.bundles.raw_mistral_json is True
    assert config.bundles.debug_trace is False
    assert config.bundles.json_schema is False
    assert Bundles(schema=True).json_schema is True


def test_confidence_band_validation() -> None:
    valid = ConfidenceScores.model_validate(_confidence("medium"))
    assert valid.band == "medium"

    invalid = {**_confidence(), "band": "needs_review"}
    with pytest.raises(ValidationError):
        ConfidenceScores.model_validate(invalid)


def test_spatial_hints_are_optional_but_supported() -> None:
    no_spatial = Envelope.model_validate(_envelope())
    assert no_spatial.layout_info.available is False

    with_spatial = Envelope.model_validate(_envelope({
        "available": True,
        "layout_confidence": 0.75,
        "pages": [{
            "page_index": 0,
            "width": 719,
            "height": 1018,
            "positioned_elements": 1,
        }],
        "positioned_element_count": 1,
        "reasons": [],
    }))
    assert with_spatial.layout_info.available is True
    assert with_spatial.layout_info.positioned_element_count == 1


def test_supporting_models_validate_independently() -> None:
    assert Stats(
        document_count=1,
        page_count=2,
        notice_count=3,
        table_count=4,
        char_count_markdown=100,
    ).warnings_count == 0
    assert MistralMetadata(model="mistral-ocr-latest").mistral_doc_ids == []
    assert PipelineWarning(kind="test", message="example").where is None
    assert DocumentConfidence(
        ocr_quality=1.0,
        notice_split=1.0,
        composite=1.0,
        counts={"high": 1, "medium": 0, "low": 0},
        mean_composite=1.0,
        min_composite=1.0,
        n_notices=1,
    ).reasons == []
    assert LayoutInfo().available is False
