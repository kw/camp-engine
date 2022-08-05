from __future__ import annotations

from typing import Any
from typing import Literal
from typing import TypeAlias

from pydantic import Field

from camp.engine.models import BaseFeatureDef
from camp.engine.models import BaseRuleset
from camp.engine.models import FeatureId
from camp.engine.models import FeatureIds
from camp.engine.models import ModelDefinition


class ClassDef(BaseFeatureDef):
    type: Literal["class"] = "class"
    grants: FeatureIds = None
    description: str | None = None
    levels = list[dict[str, Any]]


class SkillDef(BaseFeatureDef):
    type: Literal["skill"] = "skill"
    cost: int
    ranks: bool | int = False
    uses: int | None = None
    requires: FeatureIds = None
    description: str | None = None
    bonuses: dict[str, int] | None = None


class FeatDef(BaseFeatureDef):
    type: Literal["feat"] = "feat"
    class_: str = Field(alias="class")
    ranks: bool | int = False
    uses: int | None = None
    requires: FeatureIds = None
    description: str | None = None
    bonuses: dict[str, int] | None = None


class SpellDef(BaseFeatureDef):
    type: Literal["spell"] = "spell"
    class_: str = Field(alias="class")
    level: int
    requires: FeatureIds = None
    call: str
    description: str | None = None


FeatureDefinitions: TypeAlias = ClassDef | SkillDef | FeatDef | SpellDef


class Ruleset(BaseRuleset):
    features: dict[FeatureId, FeatureDefinitions] = Field(default_factory=dict)

    def feature_model_types(self) -> ModelDefinition:
        return FeatureDefinitions  # type: ignore[return-value]
