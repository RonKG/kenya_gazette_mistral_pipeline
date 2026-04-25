from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DRIVER_NOTEBOOK = ROOT / "examples" / "gazette_package_driver.ipynb"
REPLAY_FIXTURE = ROOT / "examples" / "tiny_replay.raw.json"
PROTOTYPE_NOTEBOOK = ROOT / "examples" / "historical" / "gazette_etl_prototype.ipynb"
README = ROOT / "README.md"
CHECKED_IN_NOTEBOOKS = tuple(
    sorted(
        [
            *ROOT.glob("*.ipynb"),
            *(ROOT / "examples").glob("*.ipynb"),
            *(ROOT / "examples" / "historical").glob("*.ipynb"),
        ]
    )
)

REQUIRED_ROOT_IMPORTS = {
    "parse_url",
    "write_envelope",
    "GazetteConfig",
    "Bundles",
}
OPTIONAL_ROOT_IMPORTS = {"parse_file", "get_envelope_schema", "validate_envelope_json"}

DUPLICATED_HEAVY_MARKERS = {
    "def ocr_pdf_url",
    "def run_mistral_ocr",
    "def load_mistral_blocks",
    "def pages_from_blocks",
    "def join_pages_to_markdown",
    "def markdown_to_envelope",
    "def extract_markdown_tables",
    "def split_table_row",
    "def normalize_row",
    "NOTICE_SPLIT_RE",
    "NOTICE_NO_RE",
    "MISTRAL_OCR_URL",
    "urllib.request.Request",
    "urllib.request.urlopen",
    "json.dumps(final_envelope",
    "write_raw_mistral_json",
}

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_-]{12,}"),
    re.compile(r"MISTRAL_API_KEY\s*=\s*['\"][^'\"]+['\"]"),
)

ENV_READ_MARKERS = {
    "load_dotenv",
    "dotenv_values",
    "find_dotenv",
    "Path(\".env\")",
    "Path('.env')",
    "open(\".env\"",
    "open('.env'",
}

ABSOLUTE_LOCAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/](?:Users|Documents|Windows|ProgramData|Temp)[\\/]", re.IGNORECASE),
    re.compile(r"file:///[A-Za-z]:/", re.IGNORECASE),
    re.compile(r"/Users/[^/\s]+/"),
    re.compile(r"/home/[^/\s]+/"),
)


def _load_notebook(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def _notebook_source(path: Path) -> str:
    notebook = _load_notebook(path)
    return "\n".join(_cell_source(cell) for cell in notebook["cells"])


def _first_markdown_source(notebook: dict[str, Any]) -> str:
    for cell in notebook["cells"]:
        if cell.get("cell_type") == "markdown":
            return _cell_source(cell)
    return ""


def _is_historical_non_default(notebook: dict[str, Any]) -> bool:
    first_markdown = _first_markdown_source(notebook).lower()
    return (
        "historical" in first_markdown
        and "examples/gazette_package_driver.ipynb" in first_markdown
        and (
            "not the current" in first_markdown
            or "not current" in first_markdown
            or "not use this as the current" in first_markdown
            or "not the recommended" in first_markdown
        )
    )


def _non_comment_code_source(path: Path) -> str:
    notebook = _load_notebook(path)
    lines: list[str] = []
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        for line in _cell_source(cell).splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(line)
    return "\n".join(lines)


def _metadata_and_outputs_text(notebook: dict[str, Any]) -> str:
    outputs = []
    for cell in notebook["cells"]:
        outputs.extend(cell.get("outputs", []))
    return json.dumps(
        {
            "metadata": notebook.get("metadata", {}),
            "outputs": outputs,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _assert_no_secret_or_env_reads(text: str) -> None:
    for pattern in SECRET_PATTERNS:
        assert pattern.search(text) is None
    for marker in ENV_READ_MARKERS:
        assert marker not in text


def test_recommended_notebook_imports_package_root_api() -> None:
    source = _notebook_source(DRIVER_NOTEBOOK)

    assert "from gazette_mistral_pipeline import" in source
    for name in REQUIRED_ROOT_IMPORTS:
        assert name in source
    assert OPTIONAL_ROOT_IMPORTS & set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", source))
    assert "from gazette_mistral_pipeline.public_api" not in source
    assert "from gazette_mistral_pipeline.bundle_writer" not in source
    assert "from gazette_mistral_pipeline.mistral_ocr" not in source


def test_recommended_notebook_bootstraps_source_checkout_imports() -> None:
    source = next(
        _cell_source(cell)
        for cell in _load_notebook(DRIVER_NOTEBOOK)["cells"]
        if cell.get("cell_type") == "code" and "import sys" in _cell_source(cell)
    )

    assert "import sys" in source
    assert 'candidate / "gazette_mistral_pipeline" / "__init__.py"' in source
    assert "sys.path.insert(0, str(repo_root))" in source
    assert 'exc.name == "pydantic"' in source
    assert "%pip install -e" in source


def test_recommended_notebook_has_no_duplicated_heavy_pipeline_logic() -> None:
    source = _notebook_source(DRIVER_NOTEBOOK)

    for marker in DUPLICATED_HEAVY_MARKERS:
        assert marker not in source
    assert "write_envelope(" in source
    assert "Bundles(" in source
    assert "json.dump" not in source
    assert "json.dumps" not in source


def test_recommended_notebook_default_is_live_mistral_pdf_url() -> None:
    source = _notebook_source(DRIVER_NOTEBOOK)
    active_code = _non_comment_code_source(DRIVER_NOTEBOOK)

    assert "Live Mistral PDF Smoke Test" in source
    assert "allow_live_mistral" in active_code
    assert "parse_url(PDF_URL, config=live_config)" in source
    assert "_live_mistral_pdf_test" in source
    assert "replay_raw_json_path" not in active_code
    assert "RUN_LIVE_OCR = False" not in active_code


def test_recommended_notebook_documents_local_pdf_upload_gap() -> None:
    source = _notebook_source(DRIVER_NOTEBOOK)

    assert "does not yet upload local PDFs to Mistral" in source
    assert "document_url" in source
    assert 'Path("/path/to/local-gazette.pdf")' not in source


def test_recommended_notebook_cells_emit_status_output() -> None:
    source = _notebook_source(DRIVER_NOTEBOOK)

    assert "## What You Are Testing" in source
    assert "Setup Ready" in source
    assert "Live Test Configuration" in source
    assert "Live Mistral PDF Test Complete" in source
    assert "Live OCR Output Preview" in source
    assert "Raw Mistral cache file" in source


def test_recommended_notebook_saved_outputs_are_live_mistral_outputs_if_present() -> None:
    notebook = _load_notebook(DRIVER_NOTEBOOK)
    outputs = [output for cell in notebook["cells"] for output in cell.get("outputs", [])]
    outputs_text = json.dumps(outputs, ensure_ascii=False)

    if not outputs:
        return

    assert "Live Mistral PDF Test Complete" in outputs_text
    assert "mistral_replay': False" in outputs_text or "Replay mode: `False`" in outputs_text
    assert "_live_mistral_pdf_test" in outputs_text
    assert "Offline Replay Complete" not in outputs_text


def test_recommended_notebook_explains_how_to_judge_live_result() -> None:
    source = _notebook_source(DRIVER_NOTEBOOK)

    assert "## How To Judge The Test" in source
    assert "`Replay mode: False`" in source
    assert "raw JSON cache" in source


def _assert_no_absolute_local_paths_in_metadata_or_outputs(notebook: dict[str, Any]) -> None:
    text = _metadata_and_outputs_text(notebook)
    for pattern in ABSOLUTE_LOCAL_PATH_PATTERNS:
        assert pattern.search(text) is None


def _assert_no_absolute_local_paths_in_source(path: Path) -> None:
    source = _notebook_source(path)
    for pattern in ABSOLUTE_LOCAL_PATH_PATTERNS:
        assert pattern.search(source) is None


def test_checked_in_notebooks_have_no_execution_state_or_local_output_paths() -> None:
    for path in CHECKED_IN_NOTEBOOKS:
        notebook = _load_notebook(path)
        for index, cell in enumerate(notebook["cells"]):
            if path != DRIVER_NOTEBOOK:
                assert cell.get("outputs", []) == [], f"{path.name} cell {index} has checked-in outputs"
            if cell.get("cell_type") == "code" and path != DRIVER_NOTEBOOK:
                assert cell.get("execution_count") is None, (
                    f"{path.name} cell {index} has a checked-in execution_count"
                )
        _assert_no_absolute_local_paths_in_metadata_or_outputs(notebook)


def test_checked_in_notebook_sources_have_no_absolute_local_paths() -> None:
    for path in CHECKED_IN_NOTEBOOKS:
        _assert_no_absolute_local_paths_in_source(path)


def test_duplicated_pipeline_logic_is_only_allowed_in_labeled_historical_notebooks() -> None:
    for path in CHECKED_IN_NOTEBOOKS:
        if path == DRIVER_NOTEBOOK:
            continue

        source = _notebook_source(path)
        markers = [marker for marker in DUPLICATED_HEAVY_MARKERS if marker in source]
        if markers:
            notebook = _load_notebook(path)
            assert _is_historical_non_default(notebook), (
                f"{path.name} has duplicated pipeline markers without a historical/non-default label: {markers}"
            )


def test_notebooks_have_no_secrets_or_env_reads() -> None:
    combined_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CHECKED_IN_NOTEBOOKS
    )
    _assert_no_secret_or_env_reads(combined_text)


def test_replay_fixture_is_tiny_local_and_non_secret() -> None:
    payload = json.loads(REPLAY_FIXTURE.read_text(encoding="utf-8"))
    fixture_text = REPLAY_FIXTURE.read_text(encoding="utf-8")

    assert REPLAY_FIXTURE.stat().st_size < 2_000
    assert payload["pages"][0]["markdown"].startswith("## GAZETTE NOTICE NO.")
    _assert_no_secret_or_env_reads(fixture_text)


def test_docs_point_to_thin_driver_and_offline_policy() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "examples/gazette_package_driver.ipynb" in readme
    assert "offline replay" in readme.lower()
    assert "MISTRAL_API_KEY" in readme
    assert "examples/historical/gazette_etl_prototype.ipynb" in readme
    prototype_mentions = [
        line for line in readme.splitlines() if "examples/historical/gazette_etl_prototype.ipynb" in line
    ]
    assert prototype_mentions
    assert all("historical" in line.lower() for line in prototype_mentions)


def test_historical_prototype_is_retained_as_non_default_context() -> None:
    prototype = _load_notebook(PROTOTYPE_NOTEBOOK)
    first_markdown = _cell_source(prototype["cells"][0]).lower()
    prototype_source = _notebook_source(PROTOTYPE_NOTEBOOK)

    assert _is_historical_non_default(prototype)
    assert "RUN_MISTRAL_OCR = False" in prototype_source
    _assert_no_secret_or_env_reads(prototype_source)
