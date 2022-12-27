from __future__ import annotations

from pydantic import Field

from .. import base_models


class CharacterModel(base_models.CharacterModel):
    primary_class: str | None = None
    starting_class: str | None = None
    classes: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)

    # Computed fields. In principal, it should be possible to
    # clear and recompute these based on the e
    skill_grants: dict[str, int] = Field(default_factory=dict)
