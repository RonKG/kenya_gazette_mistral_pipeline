from __future__ import annotations

import inspect
import tomllib
from pathlib import Path

import pytest

import gazette_mistral_pipeline as gmp


ROOT = Path(__file__).resolve().parents[1]


def test_public_imports_and_version() -> None:
    assert gmp.__version__ == "0.1.0"
    for name in [
        "__version__",
        "parse_file",
        "parse_url",
        "parse_source",
        "write_envelope",
        "get_envelope_schema",
        "validate_envelope_json",
    ]:
        assert name in gmp.__all__
        assert hasattr(gmp, name)


@pytest.mark.parametrize(
    ("name", "args", "kwargs", "future_feature"),
    [
        ("parse_file", ("example.pdf",), {}, "F10 after F04-F09"),
        ("parse_url", ("https://example.com/source.pdf",), {}, "F10 after F04-F09"),
        ("parse_source", ("example.pdf",), {}, "F10 after F04-F09"),
        ("write_envelope", ({}, "out"), {}, "F10"),
        ("get_envelope_schema", (), {}, "F11"),
        ("validate_envelope_json", ({},), {}, "F11"),
    ],
)
def test_public_stubs_raise_clear_not_implemented(
    name: str,
    args: tuple,
    kwargs: dict,
    future_feature: str,
) -> None:
    fn = getattr(gmp, name)
    with pytest.raises(NotImplementedError) as excinfo:
        fn(*args, **kwargs)
    message = str(excinfo.value)
    assert "F02 package skeleton stub" in message
    assert future_feature in message


def test_public_stub_signatures_are_stable() -> None:
    parse_file_sig = inspect.signature(gmp.parse_file)
    assert list(parse_file_sig.parameters) == ["path", "config"]
    assert parse_file_sig.parameters["config"].kind is inspect.Parameter.KEYWORD_ONLY

    parse_url_sig = inspect.signature(gmp.parse_url)
    assert list(parse_url_sig.parameters) == ["url", "config"]
    assert parse_url_sig.parameters["config"].kind is inspect.Parameter.KEYWORD_ONLY

    parse_source_sig = inspect.signature(gmp.parse_source)
    assert list(parse_source_sig.parameters) == ["source", "config"]
    assert parse_source_sig.parameters["config"].kind is inspect.Parameter.KEYWORD_ONLY


def test_pyproject_metadata_has_expected_runtime_dependencies() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["name"] == "gazette-mistral-pipeline"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.10"
    assert project["license"]["text"] == "Apache-2.0"
    assert project.get("dependencies", []) == ["pydantic>=2.0"]


def test_type_marker_and_license_exist() -> None:
    assert (ROOT / "gazette_mistral_pipeline" / "py.typed").is_file()
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0" in license_text
