from __future__ import annotations

from typing import Iterable
from typing import Literal
from typing import TypeAlias

from pydantic import Field

from camp.engine.models import BaseFeatureDef
from camp.engine.models import BaseModel
from camp.engine.models import BaseRuleset
from camp.engine.models import CharacterSheet
from camp.engine.models import Identifier
from camp.engine.models import Identifiers
from camp.engine.models import ModelDefinition
from camp.engine.utils import maybe_iter


class GrantAttribute(BaseModel):
    attribute: str
    bonus: int


Grantable: TypeAlias = Identifier | GrantAttribute
Grantables: TypeAlias = Identifier | GrantAttribute | list[Grantable] | None


class ClassFeatureDef(BaseFeatureDef):
    type: Literal["classfeature"] = "classfeature"
    grants: Grantables = None


class ClassDef(BaseFeatureDef):
    type: Literal["class"] = "class"
    starting_features: Identifiers = None
    multiclass_features: Identifiers = None
    bonus_features: dict[int, Identifiers] | None = None
    class_features: list[ClassFeatureDef] = Field(default_factory=[])
    level_table_columns: dict[str, dict]
    levels: dict[int, dict]

    @property
    def subfeatures(self) -> Iterable[BaseFeatureDef]:
        return self.class_features

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        if self.starting_features:
            ruleset.validate_identifiers(self.starting_features)
        if self.multiclass_features:
            ruleset.validate_identifiers(self.multiclass_features)
        if self.bonus_features:
            ruleset.validate_identifiers(self.bonus_features.values())


class SkillOptionDef(BaseModel):
    multiple: bool = False
    freeform: Literal["short", "long", None] = None
    values: list[str] | None = None
    grants: list[Identifier | GrantAttribute] | None = None


class SkillDef(BaseFeatureDef):
    type: Literal["skill"] = "skill"
    category: str = "General"
    cost: int
    ranks: bool | int = False
    uses: int | None = None
    requires: Identifiers = None
    option: SkillOptionDef | None = None
    grants: Grantables = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        for grant in maybe_iter(self.grants):
            if isinstance(grant, GrantAttribute):
                ruleset.validate_identifiers(grant.attribute)
            elif isinstance(grant, str):
                ruleset.validate_identifiers(grant)


class SpellDef(BaseFeatureDef):
    type: Literal["spell"] = "spell"
    class_: str = Field(alias="class")

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(self.class_)


FeatureDefinitions: TypeAlias = ClassDef | ClassFeatureDef | SkillDef | SpellDef


class Ruleset(BaseRuleset):
    features: dict[Identifier, FeatureDefinitions] = Field(default_factory=dict)
    base_xp: int = 0
    base_cp: int = 0
    breedcap: int = 2
    flaw_cap: int = 10
    flaw_overcome: int = 2
    xp_table: dict[int, int]
    lp_table: dict[int, int]

    def feature_model_types(self) -> ModelDefinition:
        return FeatureDefinitions  # type: ignore[return-value]

    def new_character(self, *args, **attributes) -> CharacterSheet:
        return super().new_character(*args, **attributes)
