"""Shared strict Pydantic base models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Strict base for package models."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=False,
    )
