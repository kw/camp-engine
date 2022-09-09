from __future__ import annotations

from typing import Any
from typing import Iterable
from typing import Literal
from typing import Type
from typing import TypeAlias

from pydantic import Field

from camp.engine.models import BaseCharacter
from camp.engine.models import BaseFeatureDef
from camp.engine.models import BaseRuleset
from camp.engine.models import FeatureEntry
from camp.engine.models import Identifier
from camp.engine.models import Identifiers
from camp.engine.models import ModelDefinition


class ClassDef(BaseFeatureDef):
    type: Literal["class"] = "class"
    grants: Identifiers = None
    levels: list[dict[str, Any]] | None = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(self.grants)


class SkillDef(BaseFeatureDef):
    type: Literal["skill"] = "skill"
    cost: int
    ranks: bool | int = False
    uses: int | None = None
    bonuses: dict[str, int] | None = None
    has_text: bool = False

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        if self.bonuses:
            ruleset.validate_identifiers(list(self.bonuses.keys()))


class FeatDef(BaseFeatureDef):
    type: Literal["feat"] = "feat"
    class_: str = Field(alias="class")
    ranks: bool | int = False
    uses: int | None = None
    bonuses: dict[str, int] | None = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(self.class_)
        if self.bonuses:
            ruleset.validate_identifiers(list(self.bonuses.keys()))


class SpellDef(BaseFeatureDef):
    type: Literal["spell"] = "spell"
    class_: str = Field(alias="class")
    level: int
    call: str

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(self.class_)


FeatureDefinitions: TypeAlias = ClassDef | SkillDef | FeatDef | SpellDef


class Character(BaseCharacter):
    def features(self) -> Iterable[FeatureEntry]:
        return []

    def get_feature(self, id) -> list[FeatureEntry] | None:
        return None


class Ruleset(BaseRuleset):
    features: dict[Identifier, FeatureDefinitions] = Field(default_factory=dict)

    def feature_model_types(self) -> ModelDefinition:
        return FeatureDefinitions  # type: ignore[return-value]

    @property
    def sheet_type(self) -> Type[Character]:
        return Character
