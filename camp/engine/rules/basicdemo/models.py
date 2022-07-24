from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import Field

from camp.engine.base import BaseFeature
from camp.engine.base import FeatureIds


class ClassDef(BaseFeature):
    type: Literal["class"]
    grants: FeatureIds = None
    description: str | None = None
    levels = list[dict[str, Any]]

    class Config:
        allow_mutation = False


class SkillDef(BaseFeature):
    type: Literal["skill"]
    cost: int
    ranks: bool | int = False
    uses: int | None = None
    requires: FeatureIds = None
    description: str | None = None
    bonuses: dict[str, int] | None = None

    class Config:
        allow_mutation = False


class FeatDef(BaseFeature):
    type: Literal["feat"]
    class_: str = Field(alias="class")
    ranks: bool | int = False
    uses: int | None = None
    requires: FeatureIds = None
    description: str | None = None
    bonuses: dict[str, int] | None = None

    class Config:
        allow_mutation = False


class SpellDef(BaseFeature):
    type: Literal["spell"]
    class_: str = Field(alias="class")
    level: int
    requires: FeatureIds = None
    call: str
    description: str | None = None


FeatureDefinitions = ClassDef | SkillDef | FeatDef | SpellDef
