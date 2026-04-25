from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from gazette_mistral_pipeline.models import Stats
from gazette_mistral_pipeline.page_normalization import (
    NormalizedPage,
    StitchedMarkdownResult,
    compute_stats,
    load_mistral_blocks,
    normalize_mistral_pages,
    stitch_markdown_pages,
    write_joined_markdown,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_single_object_pages_are_sorted_and_stitched() -> None:
    raw = {
        "id": "doc_1",
        "model": "mistral-ocr-latest",
        "pages": [
            {"index": 1, "markdown": "Page 2"},
            {"index": 0, "markdown": "Page 1"},
        ],
    }

    pages = normalize_mistral_pages(raw)
    markdown = stitch_markdown_pages(pages)

    assert [page.markdown for page in pages] == ["Page 1", "Page 2"]
    assert [page.index for page in pages] == [0, 1]
    assert [page.original_page_index for page in pages] == [0, 1]
    assert {page.document_index for page in pages} == {0}
    assert pages[0].document_id == "doc_1"
    assert pages[0].model == "mistral-ocr-latest"
    assert markdown == (
        "---\n\n"
        "# Document: doc_1\n\n"
        "---\n\n"
        "## Index 0\n\n"
        "Page 1\n\n"
        "---\n\n"
        "## Index 1\n\n"
        "Page 2\n"
    )
    assert compute_stats(pages, markdown) == {
        "document_count": 1,
        "page_count": 2,
        "char_count_markdown": len(markdown),
    }


def test_block_list_preserves_document_order_and_sorts_within_each_block() -> None:
    raw = [
        {
            "id": "doc_a",
            "pdf_url": "https://example.com/a.pdf",
            "pages": [
                {"index": 2, "markdown": "a2"},
                {"index": 1, "markdown": "a1"},
            ],
        },
        {
            "document_id": "doc_b",
            "document_url": "https://example.com/b.pdf",
            "pages": [{"index": 0, "markdown": "b0"}],
        },
    ]

    pages = normalize_mistral_pages(raw)
    markdown = stitch_markdown_pages(pages)

    assert [(page.document_index, page.original_page_index, page.markdown) for page in pages] == [
        (0, 1, "a1"),
        (0, 2, "a2"),
        (1, 0, "b0"),
    ]
    assert [page.index for page in pages] == [0, 1, 2]
    assert [page.document_id for page in pages] == ["doc_a", "doc_a", "doc_b"]
    assert [page.document_url for page in pages] == [
        "https://example.com/a.pdf",
        "https://example.com/a.pdf",
        "https://example.com/b.pdf",
    ]
    assert markdown.count("# Document:") == 2
    assert "# Document: https://example.com/a.pdf" in markdown
    assert "# Document: https://example.com/b.pdf" in markdown


def test_legacy_page_list_shape_is_supported() -> None:
    raw = [
        {"index": "2", "markdown": "two"},
        {"index": "1", "markdown": "one"},
    ]

    pages = normalize_mistral_pages(raw)

    assert [(page.original_page_index, page.markdown) for page in pages] == [
        (1, "one"),
        (2, "two"),
    ]
    assert all(page.document_id is None for page in pages)
    assert all(page.document_url is None for page in pages)


def test_missing_non_integer_and_duplicate_indexes_are_deterministic() -> None:
    raw = {
        "pages": [
            {"index": "x", "markdown": "bad first"},
            {"index": 2, "markdown": "two first"},
            {"index": 1, "markdown": "one"},
            {"index": 2, "markdown": "two second"},
            {"markdown": "missing"},
        ]
    }

    first = normalize_mistral_pages(raw)
    second = normalize_mistral_pages(raw)

    assert [page.markdown for page in first] == [
        "one",
        "two first",
        "two second",
        "bad first",
        "missing",
    ]
    assert [page.original_page_index for page in first] == [1, 2, 2, None, None]
    assert stitch_markdown_pages(first) == stitch_markdown_pages(second)


def test_blank_and_non_markdown_pages_are_skipped() -> None:
    raw = {
        "id": "doc_skip",
        "pages": [
            {"index": 0, "markdown": ""},
            {"index": 1, "markdown": "   "},
            {"index": 2, "markdown": None},
            {"index": 3},
            "not a page",
            {"index": 4, "markdown": "\nValid page\n"},
        ],
    }

    pages = normalize_mistral_pages(raw)
    markdown = stitch_markdown_pages(pages)

    assert len(pages) == 1
    assert pages[0].index == 0
    assert pages[0].original_page_index == 4
    assert pages[0].markdown == "\nValid page\n"
    assert markdown.endswith("Valid page\n")
    assert compute_stats(pages, markdown)["page_count"] == 1


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ({}, "Unsupported Mistral raw JSON shape"),
        ([], "Unsupported Mistral raw JSON shape"),
        ({"pages": {}}, "pages field must be a list"),
        ([{"not_pages": []}], "Unsupported Mistral raw JSON shape"),
        (42, "Unsupported Mistral raw JSON shape"),
    ],
)
def test_unsupported_shapes_fail_loudly(raw: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        load_mistral_blocks(raw)  # type: ignore[arg-type]


def test_zero_normalized_pages_fails_loudly() -> None:
    with pytest.raises(ValueError, match="No non-empty markdown pages"):
        normalize_mistral_pages({"pages": [{"markdown": "   "}, "not a page"]})


def test_markdown_content_is_preserved_apart_from_boundary_trimming() -> None:
    raw_markdown = (
        "\n\n# Heading\n\n"
        "![img-0.jpeg](img-0.jpeg)\n\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| Gazette Notice | text |\n\n"
        "GAZETTE NOTICE NO. 12\n\n"
    )
    pages = normalize_mistral_pages({"pages": [{"index": 0, "markdown": raw_markdown}]})
    markdown = stitch_markdown_pages(pages)

    assert pages[0].markdown == raw_markdown
    assert "![img-0.jpeg](img-0.jpeg)" in markdown
    assert "| Gazette Notice | text |" in markdown
    assert "GAZETTE NOTICE NO. 12" in markdown
    assert markdown.endswith("GAZETTE NOTICE NO. 12\n")


def test_write_joined_markdown_writes_only_requested_stage_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "sample_joined.md"
    returned = write_joined_markdown("joined\n\n", output_path)

    assert returned == output_path
    assert output_path.read_text(encoding="utf-8") == "joined\n"
    assert list((tmp_path / "nested").iterdir()) == [output_path]
    assert not list(tmp_path.glob("*_envelope.json"))
    assert not list(tmp_path.glob("*_index.json"))


def test_stats_and_result_dataclass_align_with_later_envelope_counts() -> None:
    pages = normalize_mistral_pages([
        {"id": "doc_a", "pages": [{"index": 0, "markdown": "a0"}, {"index": 1, "markdown": "a1"}]},
        {"id": "doc_b", "pages": [{"index": 0, "markdown": "b0"}]},
    ])
    markdown = stitch_markdown_pages(pages)
    stats = compute_stats(pages, markdown)
    result = StitchedMarkdownResult(
        pages=pages,
        markdown=markdown,
        output_path=None,
        **stats,
    )
    envelope_stats = Stats(notice_count=0, table_count=0, **stats)

    assert result.document_count == 2
    assert result.page_count == 3
    assert result.char_count_markdown == len(markdown)
    assert envelope_stats.notice_count == 0
    assert envelope_stats.table_count == 0


def test_dataclasses_are_frozen() -> None:
    page = normalize_mistral_pages({"pages": [{"index": 0, "markdown": "text"}]})[0]

    with pytest.raises(FrozenInstanceError):
        page.index = 99  # type: ignore[misc]


def test_representative_cached_block_fixture_is_normalized() -> None:
    fixture_path = FIXTURE_DIR / "page_normalization_block_list.raw.json"
    blocks = load_mistral_blocks(fixture_path)
    pages = normalize_mistral_pages(blocks)
    markdown = stitch_markdown_pages(pages)

    assert len(blocks) == 2
    assert len(pages) == 3
    assert pages[0].markdown.startswith("![img-0.jpeg]")
    assert pages[0].raw_page_metadata["dimensions"] == {"width": 719, "height": 1018}
    assert pages[0].raw_page_metadata["images_count"] == 0
    assert pages[0].raw_page_metadata["tables_count"] == 1
    assert "# Document: https://new.kenyalaw.org/" in markdown
    assert "# Document: mistral_doc_2026_68_b" in markdown
    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")


@pytest.mark.parametrize(
    ("filename", "body", "match"),
    [
        ("missing.raw.json", None, "does not exist"),
        ("empty.raw.json", "   ", "empty"),
        ("invalid.raw.json", "{", "Invalid Mistral raw JSON"),
    ],
)
def test_load_mistral_blocks_file_errors_are_clear(
    tmp_path: Path,
    filename: str,
    body: str | None,
    match: str,
) -> None:
    path = tmp_path / filename
    if body is not None:
        path.write_text(body, encoding="utf-8")

    with pytest.raises((FileNotFoundError, ValueError), match=match):
        load_mistral_blocks(path)


def test_json_file_input_accepts_same_shape_as_loaded_object(tmp_path: Path) -> None:
    payload = {"pages": [{"index": 0, "markdown": "from file"}]}
    path = tmp_path / "sample.raw.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert normalize_mistral_pages(path)[0].markdown == "from file"
