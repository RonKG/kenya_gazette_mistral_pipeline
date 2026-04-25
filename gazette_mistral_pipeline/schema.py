"""JSON Schema export and envelope JSON validation helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from gazette_mistral_pipeline.__version__ import LIBRARY_VERSION, SCHEMA_VERSION
from gazette_mistral_pipeline.envelope_builder import OUTPUT_FORMAT_VERSION
from gazette_mistral_pipeline.models import Envelope

SCHEMA_FILENAME = "envelope.schema.json"
SCHEMA_PACKAGE_DIR = "schemas"
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def get_envelope_schema(*, use_cache: bool = True) -> dict[str, Any]:
    """Return the deterministic JSON Schema for the package envelope."""

    if use_cache:
        return json.loads(get_envelope_schema_bytes().decode("utf-8"))
    return build_envelope_schema()


def validate_envelope_json(
    data: Envelope | Mapping[str, Any] | str | bytes | bytearray | Path,
) -> Envelope:
    """Validate supported JSON/envelope inputs and return an ``Envelope``."""

    if isinstance(data, Envelope):
        return data
    if isinstance(data, Path):
        return Envelope.model_validate_json(data.read_bytes())
    if isinstance(data, Mapping):
        return Envelope.model_validate(data)
    if isinstance(data, str):
        return Envelope.model_validate_json(data)
    if isinstance(data, (bytes, bytearray)):
        return Envelope.model_validate_json(bytes(data))
    raise TypeError(
        "validate_envelope_json expects an Envelope, mapping, JSON str, "
        "bytes, bytearray, or pathlib.Path."
    )


def build_envelope_schema() -> dict[str, Any]:
    """Generate the normalized in-memory schema from the Pydantic model."""

    schema = Envelope.model_json_schema()
    schema["$schema"] = JSON_SCHEMA_DRAFT
    schema["title"] = "Envelope"
    schema["x-library-version"] = LIBRARY_VERSION
    schema["x-schema-version"] = SCHEMA_VERSION
    schema["x-output-format-version"] = OUTPUT_FORMAT_VERSION
    return schema


def get_envelope_schema_bytes() -> bytes:
    """Return checked-in schema bytes from package resources."""

    return _cached_schema_bytes()


def serialize_schema(schema: Mapping[str, Any]) -> bytes:
    """Serialize schema JSON deterministically for checked-in resources."""

    text = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    return f"{text}\n".encode("utf-8")


@lru_cache(maxsize=1)
def _cached_schema_bytes() -> bytes:
    resource = resources.files("gazette_mistral_pipeline").joinpath(
        SCHEMA_PACKAGE_DIR,
        SCHEMA_FILENAME,
    )
    return resource.read_bytes()


__all__ = [
    "JSON_SCHEMA_DRAFT",
    "SCHEMA_FILENAME",
    "SCHEMA_PACKAGE_DIR",
    "build_envelope_schema",
    "get_envelope_schema",
    "get_envelope_schema_bytes",
    "serialize_schema",
    "validate_envelope_json",
]
