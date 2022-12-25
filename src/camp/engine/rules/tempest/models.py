from __future__ import annotations

from pydantic import Field

from .. import base_models


class CharacterModel(base_models.CharacterModel):
    primary_class: str | None = None
    classes: dict[str, int] = Field(default_factory=dict)
