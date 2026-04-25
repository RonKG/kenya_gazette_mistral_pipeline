"""Deterministic output bundle writer for validated envelopes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from gazette_mistral_pipeline.models import Bundles, Envelope
from gazette_mistral_pipeline.schema import get_envelope_schema_bytes


def write_envelope(
    env: Envelope | dict[str, Any],
    out_dir: str | Path,
    bundles: Bundles | dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Write selected output artifacts and return a path manifest."""

    envelope = _coerce_envelope(env)
    selected = _coerce_bundles(bundles)

    output_dir = Path(out_dir)
    paths = _bundle_paths(envelope, output_dir)
    raw_source = _raw_json_source(envelope) if selected.raw_mistral_json else None
    joined_source = _joined_markdown_source(envelope) if selected.joined_markdown else None

    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    if selected.envelope:
        _write_json(paths["envelope"], envelope.model_dump(mode="json"))
        written["envelope"] = paths["envelope"]
    if selected.source_metadata:
        _write_json(paths["source_metadata"], envelope.source.model_dump(mode="json"))
        written["source_metadata"] = paths["source_metadata"]
    if selected.json_schema:
        paths["schema"].write_bytes(get_envelope_schema_bytes())
        written["schema"] = paths["schema"]
    if selected.raw_mistral_json:
        written["raw_mistral_json"] = _copy_existing_artifact(
            raw_source,
            paths["raw_mistral_json"],
            bundle_name="raw_mistral_json",
        )
    if selected.joined_markdown:
        written["joined_markdown"] = _copy_existing_artifact(
            joined_source,
            paths["joined_markdown"],
            bundle_name="joined_markdown",
        )
    if selected.notices:
        _write_json(
            paths["notices"],
            [notice.model_dump(mode="json") for notice in envelope.notices],
        )
        written["notices"] = paths["notices"]
    if selected.tables:
        _write_json(
            paths["tables"],
            [table.model_dump(mode="json") for table in envelope.tables],
        )
        written["tables"] = paths["tables"]
    if selected.debug_trace:
        _write_json(paths["debug_trace"], _debug_trace(envelope))
        written["debug_trace"] = paths["debug_trace"]
    if selected.document_index:
        written["document_index"] = paths["document_index"]
        index = _document_index(envelope, output_dir=output_dir, artifacts=written)
        _write_json(paths["document_index"], index)

    return written


def _coerce_envelope(env: Envelope | dict[str, Any]) -> Envelope:
    if isinstance(env, Envelope):
        return env
    return Envelope.model_validate(env)


def _coerce_bundles(bundles: Bundles | dict[str, Any] | None) -> Bundles:
    if bundles is None:
        return Bundles()
    if isinstance(bundles, Bundles):
        return bundles
    return Bundles.model_validate(bundles)


def _bundle_paths(env: Envelope, out_dir: Path) -> dict[str, Path]:
    stem = env.source.run_name
    return {
        "envelope": out_dir / f"{stem}_envelope.json",
        "schema": out_dir / f"{stem}_schema.json",
        "joined_markdown": out_dir / f"{stem}_joined.md",
        "raw_mistral_json": out_dir / f"{stem}.raw.json",
        "source_metadata": out_dir / f"{stem}_source.json",
        "notices": out_dir / f"{stem}_notices.json",
        "tables": out_dir / f"{stem}_tables.json",
        "document_index": out_dir / f"{stem}_index.json",
        "debug_trace": out_dir / f"{stem}_trace.json",
    }


def _raw_json_source(env: Envelope) -> Path:
    if not env.mistral.raw_json_path:
        raise ValueError("raw_mistral_json bundle requested but env.mistral.raw_json_path is unavailable.")
    path = Path(env.mistral.raw_json_path)
    if not path.is_file():
        raise FileNotFoundError(f"raw_mistral_json bundle source does not exist: {path}")
    return path


def _joined_markdown_source(env: Envelope) -> Path:
    for notice in env.notices:
        source_path = notice.provenance.source_markdown_path
        if source_path:
            path = Path(source_path)
            if not path.is_file():
                raise FileNotFoundError(f"joined_markdown bundle source does not exist: {path}")
            return path
    for corrigendum in env.corrigenda:
        if corrigendum.provenance and corrigendum.provenance.source_markdown_path:
            path = Path(corrigendum.provenance.source_markdown_path)
            if not path.is_file():
                raise FileNotFoundError(f"joined_markdown bundle source does not exist: {path}")
            return path
    raise ValueError("joined_markdown bundle requested but no provenance source_markdown_path is available.")


def _copy_existing_artifact(source: Path | None, dest: Path, *, bundle_name: str) -> Path:
    if source is None:
        raise ValueError(f"{bundle_name} bundle source is unavailable.")
    if source.resolve() == dest.resolve():
        return source
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return dest


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    path.write_text(f"{text}\n", encoding="utf-8")


def _document_index(env: Envelope, *, output_dir: Path, artifacts: dict[str, Path]) -> dict[str, Any]:
    return {
        "artifacts": {
            name: path.relative_to(output_dir).as_posix() if path.is_relative_to(output_dir) else str(path)
            for name, path in artifacts.items()
        },
        "library_version": env.library_version,
        "schema_version": env.schema_version,
        "output_format_version": env.output_format_version,
        "source": {
            "source_type": env.source.source_type,
            "source_value": env.source.source_value,
            "run_name": env.source.run_name,
            "source_sha256": env.source.source_sha256,
        },
        "stats": env.stats.model_dump(mode="json"),
    }


def _debug_trace(env: Envelope) -> dict[str, Any]:
    return {
        "source": env.source.model_dump(mode="json"),
        "mistral": env.mistral.model_dump(mode="json"),
        "stats": env.stats.model_dump(mode="json"),
        "document_confidence": env.document_confidence.model_dump(mode="json"),
        "layout_info": env.layout_info.model_dump(mode="json"),
        "warnings": [warning.model_dump(mode="json") for warning in env.warnings],
        "notice_ids": [notice.notice_id for notice in env.notices],
        "notice_confidence": {
            notice.notice_id: notice.confidence_scores.model_dump(mode="json")
            for notice in env.notices
        },
    }


__all__ = ["write_envelope"]
