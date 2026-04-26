from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from gazette_mistral_pipeline.notice_parsing import (
    PENDING_CONFIDENCE_REASON,
    ParsedMarkdownResult,
    extract_markdown_tables,
    neutral_confidence_scores,
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


def test_strict_notice_header_happy_path() -> None:
    markdown = _joined_notice(
        "## GAZETTE NOTICE NO. 5969\n\n"
        "THE LAND ACT\n\n"
        "IN EXERCISE of the powers conferred by law.\n\n"
        "Dated the 7th July, 2008."
    )

    result = parse_joined_markdown(
        markdown,
        run_name="gazette_2008_53",
        source_markdown_path="sample_joined.md",
    )

    assert isinstance(result, ParsedMarkdownResult)
    assert result.notice_count == 1
    notice = result.notices[0]
    assert notice.notice_no == "5969"
    assert notice.title_lines == ["THE LAND ACT"]
    assert notice.dates_found == ["7th July, 2008"]
    assert "## GAZETTE NOTICE NO. 5969" in notice.raw_markdown
    assert "IN EXERCISE of the powers" in notice.text
    assert notice.provenance.header_match == "strict"
    assert notice.provenance.raw_header_line == "## GAZETTE NOTICE NO. 5969"
    assert notice.provenance.source_markdown_path == "sample_joined.md"
    assert notice.provenance.stitched_from == ["page:0"]
    assert notice.provenance.page_span == (0, 0)


def test_adjacent_notices_have_stable_ids_hashes_and_slices() -> None:
    markdown = _joined_notice(
        "GAZETTE NOTICE NO. 5982\n"
        "THE FIRST ACT\n"
        "Body one.\n"
        "GAZETTE NOTICE NO. 5983\n"
        "THE SECOND ACT\n"
        "Body two."
    )

    first = parse_joined_markdown(markdown)
    second = parse_joined_markdown(markdown)

    assert [notice.notice_no for notice in first.notices] == ["5982", "5983"]
    assert first.notice_count == 2
    assert first.notices[0].raw_markdown.endswith("Body one.")
    assert first.notices[1].raw_markdown.startswith("GAZETTE NOTICE NO. 5983")
    assert [notice.notice_id for notice in first.notices] == [
        notice.notice_id for notice in second.notices
    ]
    assert [notice.content_sha256 for notice in first.notices] == [
        notice.content_sha256 for notice in second.notices
    ]


def test_ocr_header_variant_is_recovered() -> None:
    result = parse_joined_markdown(
        _joined_notice("GRZETTE NOTICE NO. 12171\nTHE COMPANIES ACT\nBody.")
    )

    notice = result.notices[0]
    assert notice.notice_no == "12171"
    assert notice.provenance.header_match == "recovered"
    assert notice.provenance.raw_header_line == "GRZETTE NOTICE NO. 12171"


def test_preamble_and_contents_table_are_ignored_before_first_notice() -> None:
    markdown = (
        "# THE KENYA GAZETTE\n\n"
        "| Contents | Page |\n"
        "| --- | --- |\n"
        "| GAZETTE NOTICE NO. 1111 | 20 |\n\n"
        "GAZETTE NOTICE NO. 2222\n"
        "THE REAL NOTICE\n"
        "Body."
    )

    result = parse_joined_markdown(markdown)

    assert result.notice_count == 1
    assert result.notices[0].notice_no == "2222"
    assert result.table_count == 0


def test_markdown_table_extraction_and_notice_attachment() -> None:
    markdown = _joined_notice(
        "GAZETTE NOTICE NO. 3000\n"
        "THE LAND REGISTRATION ACT\n\n"
        "| Parcel | Owner |\n"
        "| --- | --- |\n"
        "| Kajiado/1 | Jane Doe |\n"
        "| Kajiado/2 | John Doe |\n"
    )

    result = parse_joined_markdown(markdown, run_name="gazette_test_3000")

    table = result.tables[0]
    assert result.table_count == 1
    assert result.notices[0].table_count == 1
    assert result.notices[0].tables[0] == table
    assert table.notice_no == "3000"
    assert table.notice_id == result.notices[0].notice_id
    assert table.notice_page_span == (0, 0)
    assert table.notice_pages == [0]
    assert table.notice_stitched_from == ["page:0"]
    assert table.source_run_name == "gazette_test_3000"
    assert table.headers == ["Parcel", "Owner"]
    assert table.rows == [["Kajiado/1", "Jane Doe"], ["Kajiado/2", "John Doe"]]
    assert table.records == [
        {"Parcel": "Kajiado/1", "Owner": "Jane Doe"},
        {"Parcel": "Kajiado/2", "Owner": "John Doe"},
    ]
    assert table.raw_table_markdown == (
        "| Parcel | Owner |\n"
        "| --- | --- |\n"
        "| Kajiado/1 | Jane Doe |\n"
        "| Kajiado/2 | John Doe |"
    )
    assert table.source == "markdown_table_heuristic"
    assert table.column_count == 2


def test_ragged_markdown_table_rows_are_normalized() -> None:
    tables = extract_markdown_tables(
        "| Name | Notes | Amount |\n"
        "| --- | --- | --- |\n"
        "| Jane | short |\n"
        "| John | has | extra | pipe |\n"
    )

    table = tables[0]
    assert table.column_count == 3
    assert table.model_extra == {}
    assert table.rows == [
        ["Jane", "short", ""],
        ["John", "has", "extra | pipe"],
    ]
    assert "| John | has | extra | pipe |" in table.raw_table_markdown


def test_multiple_notice_tables_keep_their_parent_notice_context() -> None:
    markdown = _joined_notice(
        "GAZETTE NOTICE NO. 3100\n"
        "THE FIRST ACT\n\n"
        "| Parcel | Owner |\n"
        "| --- | --- |\n"
        "| First/1 | Jane Doe |\n\n"
        "GAZETTE NOTICE NO. 3101\n"
        "THE SECOND ACT\n\n"
        "| Parcel | Owner |\n"
        "| --- | --- |\n"
        "| Second/1 | John Doe |\n"
    )

    result = parse_joined_markdown(markdown, run_name="gazette_test_multi")

    assert [notice.notice_no for notice in result.notices] == ["3100", "3101"]
    assert [table.notice_no for table in result.tables] == ["3100", "3101"]
    assert [table.notice_id for table in result.tables] == [
        result.notices[0].notice_id,
        result.notices[1].notice_id,
    ]


def test_table_notice_context_keeps_multi_page_notice_pages_secondary() -> None:
    markdown = (
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        "GAZETTE NOTICE NO. 3200\n"
        "THE CROSS PAGE ACT\n\n"
        "| Parcel | Owner |\n"
        "| --- | --- |\n"
        "| Cross/1 | Jane Doe |\n\n"
        "---\n\n"
        "## Index 1\n\n"
        "Continuation on page one."
    )

    result = parse_joined_markdown(markdown, run_name="gazette_test_cross_page")

    table = result.tables[0]
    assert table.notice_no == "3200"
    assert table.notice_id == result.notices[0].notice_id
    assert table.notice_page_span is None
    assert table.notice_pages == [0, 1]
    assert table.notice_stitched_from == ["page:0", "page:1"]


def test_date_extraction_variants_keep_source_order() -> None:
    result = parse_joined_markdown(
        _joined_notice(
            "GAZETTE NOTICE NO. 4000\n"
            "THE DATES ACT\n"
            "Dated the 11th July, 2008.\n"
            "Malformed 31st July, July, 2008 should remain body text.\n"
            "Heard on 17th April, 2026."
        )
    )

    assert result.notices[0].dates_found == ["11th July, 2008", "17th April, 2026"]
    assert "31st July, July, 2008" in result.notices[0].text


def test_corrigenda_heading_section_before_notices_emits_placeholder() -> None:
    markdown = (
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        "## CORRIGENDA\n\n"
        "IN Gazette Notice No. 3308 of 2008 amend the second line.\n\n"
        "GAZETTE NOTICE NO. 5000\n"
        "THE NEXT NOTICE\n"
        "Body."
    )

    result = parse_joined_markdown(markdown)

    corrigendum = result.corrigenda[0]
    assert result.notice_count == 1
    assert corrigendum.target_notice_no == "3308"
    assert corrigendum.target_year == 2008
    assert corrigendum.amendment is None
    assert "## CORRIGENDA" in corrigendum.raw_text
    assert corrigendum.provenance is not None
    assert corrigendum.provenance.header_match == "none"
    assert corrigendum.provenance.stitched_from == ["page:0"]


def test_corrigendum_notice_candidate_still_emits_notice() -> None:
    markdown = _joined_notice(
        "GAZETTE NOTICE NO. 5100\n"
        "CORRIGENDUM\n\n"
        "IN Gazette Notice No. 3308 of 2008 amend the parcel number."
    )

    result = parse_joined_markdown(markdown)

    notice = result.notices[0]
    assert notice.notice_no == "5100"
    assert notice.other_attributes["is_corrigendum_candidate"] is True
    assert result.corrigenda[0].target_notice_no == "3308"
    assert result.corrigenda[0].target_year == 2008


def test_provenance_page_span_only_when_deterministic() -> None:
    single_page = parse_joined_markdown(
        _joined_notice("GAZETTE NOTICE NO. 6000\nTHE SINGLE PAGE ACT\nBody.")
    )
    assert single_page.notices[0].provenance.line_span == (9, 11)
    assert single_page.notices[0].provenance.stitched_from == ["page:0"]
    assert single_page.notices[0].provenance.page_span == (0, 0)

    crossing = parse_joined_markdown(
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        "GAZETTE NOTICE NO. 6001\n"
        "THE CROSS PAGE ACT\n"
        "Body on page zero.\n\n"
        "---\n\n"
        "## Index 1\n\n"
        "Continuation on page one."
    )
    assert crossing.notices[0].provenance.stitched_from == ["page:0", "page:1"]
    assert crossing.notices[0].provenance.page_span is None


@pytest.mark.parametrize("markdown", ["", "   \n\t"])
def test_empty_input_returns_empty_result(markdown: str) -> None:
    result = parse_joined_markdown(markdown)

    assert result.notices == ()
    assert result.tables == ()
    assert result.corrigenda == ()
    assert result.notice_count == 0
    assert result.table_count == 0


def test_notice_model_completeness_and_neutral_confidence() -> None:
    result = parse_joined_markdown(_joined_notice("GAZETTE NOTICE NO. 7000\nBody only."))
    notice = result.notices[0]

    assert notice.table_count == 0
    assert notice.tables == []
    assert len(notice.content_sha256) == 64
    assert notice.confidence_scores == neutral_confidence_scores()
    assert notice.confidence_scores.notice_number == 0.5
    assert notice.confidence_scores.structure == 0.5
    assert notice.confidence_scores.boundary == 0.5
    assert notice.confidence_scores.table is None
    assert notice.confidence_scores.spatial is None
    assert notice.confidence_scores.composite == 0.5
    assert notice.confidence_scores.band == "medium"
    assert notice.confidence_reasons == [PENDING_CONFIDENCE_REASON]
    assert result.parser_version == "F16"
    assert notice.other_attributes["parser_version"] == "F16"


def test_final_notice_excludes_sales_tail_at_page_boundary() -> None:
    markdown = (
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        "GAZETTE NOTICE NO. 8000\n"
        "CHANGE OF NAME\n\n"
        "NOTICE is given that Jane Doe has changed her name.\n\n"
        "Dated the 1st January, 2026.\n\n"
        "DOE & COMPANY,\n"
        "Advocates.\n\n"
        "---\n\n"
        "## Index 1\n\n"
        "# NOW ON SALE\n\n"
        "CATALOGUE OF GOVERNMENT PUBLICATIONS\n\n"
        "Price: KSh. 200\n"
    )

    result = parse_joined_markdown(markdown)
    notice = result.notices[0]

    assert result.notice_count == 1
    assert "DOE & COMPANY" in notice.raw_markdown
    assert "NOW ON SALE" not in notice.raw_markdown
    assert "CATALOGUE OF GOVERNMENT PUBLICATIONS" not in notice.text
    assert notice.provenance.stitched_from == ["page:0"]
    assert notice.provenance.page_span == (0, 0)
    assert notice.table_count == 0
    assert "# NOW ON SALE" in markdown


def test_final_notice_excludes_subscriber_tail_at_page_boundary() -> None:
    markdown = (
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        "GAZETTE NOTICE NO. 8001\n"
        "THE LAND REGISTRATION ACT\n\n"
        "WHEREAS the certificate of title has been lost.\n\n"
        "Dated the 2nd January, 2026.\n\n"
        "A. REGISTRAR,\n"
        "Land Registrar.\n\n"
        "---\n\n"
        "## Index 1\n\n"
        "# IMPORTANT NOTICE TO SUBSCRIBERS TO THE KENYA GAZETTE\n\n"
        "## SUBSCRIPTION AND ADVERTISEMENT CHARGES\n\n"
        "Government Printer.\n"
    )

    notice = parse_joined_markdown(markdown).notices[0]

    assert "Land Registrar" in notice.text
    assert "IMPORTANT NOTICE TO SUBSCRIBERS" not in notice.raw_markdown
    assert "SUBSCRIPTION AND ADVERTISEMENT CHARGES" not in notice.text


def test_final_change_of_name_notice_is_preserved() -> None:
    result = parse_joined_markdown(
        _joined_notice(
            "GAZETTE NOTICE NO. 8002\n"
            "CHANGE OF NAME\n\n"
            "NOTICE is given that by a deed poll, Jane Doe formerly known as Jane Roe "
            "has changed her name.\n\n"
            "Dated the 3rd January, 2026.\n\n"
            "JANE DOE,\n"
            "Formerly known as Jane Roe."
        )
    )

    notice = result.notices[0]

    assert notice.title_lines == ["CHANGE OF NAME"]
    assert "Formerly known as Jane Roe" in notice.text
    assert notice.raw_markdown.endswith("Formerly known as Jane Roe.")


def test_commercial_looking_official_notice_text_is_preserved() -> None:
    result = parse_joined_markdown(
        _joined_notice(
            "GAZETTE NOTICE NO. 8003\n"
            "THE TRANSFER OF BUSINESS ACT\n\n"
            "TAKE NOTICE that the transfer includes advertisement charges and other costs.\n\n"
            "Dated the 4th January, 2026.\n\n"
            "A. DIRECTOR,\n"
            "Director."
        )
    )

    assert "advertisement charges and other costs" in result.notices[0].text


def test_body_mentioning_government_printer_is_preserved() -> None:
    result = parse_joined_markdown(
        _joined_notice(
            "GAZETTE NOTICE NO. 8006\n"
            "THE PUBLICATIONS ACT\n\n"
            "Dated the 6th January, 2026.\n\n"
            "Copies are available from the Government Printer.\n\n"
            "Government Printer."
        )
    )

    notice = result.notices[0]

    assert "Copies are available from the Government Printer." in notice.text
    assert notice.raw_markdown.endswith("Government Printer.")


def test_same_page_tail_marker_is_cut_only_after_completed_notice_body() -> None:
    markdown = _joined_notice(
        "GAZETTE NOTICE NO. 8004\n"
        "THE COMPLETED NOTICE\n\n"
        "Dated the 5th January, 2026.\n\n"
        "A. REGISTRAR,\n"
        "Registrar.\n\n"
        "# NOW ON SALE\n\n"
        "Price: KSh. 200"
    )

    notice = parse_joined_markdown(markdown).notices[0]

    assert "Registrar." in notice.raw_markdown
    assert "NOW ON SALE" not in notice.raw_markdown
    assert "Price: KSh. 200" not in notice.text


def test_ambiguous_same_page_tail_marker_is_preserved() -> None:
    markdown = _joined_notice(
        "GAZETTE NOTICE NO. 8005\n"
        "THE INCOMPLETE NOTICE\n\n"
        "# NOW ON SALE\n\n"
        "Price: KSh. 200"
    )

    notice = parse_joined_markdown(markdown).notices[0]

    assert "NOW ON SALE" in notice.raw_markdown
    assert "Price: KSh. 200" in notice.text


def test_representative_kenya_gazette_snippet() -> None:
    result = parse_joined_markdown(
        _joined_notice(
            "## GAZETTE NOTICE NO. 5969\n\n"
            "THE STATE CORPORATIONS ACT\n"
            "(Cap. 446)\n\n"
            "IN EXERCISE of the powers conferred by section 6 (1) (e), the Cabinet Secretary appoints...\n\n"
            "Dated the 7th July, 2008.\n\n"
            "JANE DOE,\n"
            "Cabinet Secretary."
        )
    )

    notice = result.notices[0]
    assert notice.notice_no == "5969"
    assert notice.title_lines[0] == "THE STATE CORPORATIONS ACT"
    assert notice.dates_found == ["7th July, 2008"]
    assert notice.provenance.line_span == (9, 19)
    assert notice.content_sha256 == parse_joined_markdown(
        _joined_notice(
            "## GAZETTE NOTICE NO. 5969\n\n"
            "THE STATE CORPORATIONS ACT\n"
            "(Cap. 446)\n\n"
            "IN EXERCISE of the powers conferred by section 6 (1) (e), the Cabinet Secretary appoints...\n\n"
            "Dated the 7th July, 2008.\n\n"
            "JANE DOE,\n"
            "Cabinet Secretary."
        )
    ).notices[0].content_sha256


def test_invalid_argument_types_fail_clearly() -> None:
    with pytest.raises(TypeError, match="markdown to be a str"):
        parse_joined_markdown(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="text to be a str"):
        extract_markdown_tables(None)  # type: ignore[arg-type]


def test_result_dataclass_is_frozen() -> None:
    result = parse_joined_markdown("")

    with pytest.raises(FrozenInstanceError):
        result.notice_count = 1  # type: ignore[misc]
