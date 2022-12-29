from __future__ import annotations

import math
from typing import ClassVar
from typing import Iterable
from typing import Literal
from typing import Type
from typing import TypeAlias

from pydantic import Field
from pydantic import NonNegativeInt

from camp.engine.rules import base_models
from camp.engine.utils import maybe_iter

from . import models

Attribute: TypeAlias = base_models.Attribute
Grantable: TypeAlias = str | list[str] | dict[str, int]


class BaseFeatureDef(base_models.BaseFeatureDef):
    grants: Grantable | None = None


class ClassFeatureDef(BaseFeatureDef):
    type: Literal["classfeature"] = "classfeature"
    class_: str | None = Field(alias="class", default=None)

    def post_validate(self, ruleset: base_models.BaseRuleset) -> None:
        super().post_validate(ruleset)
        if self.grants:
            ruleset.validate_identifiers(_grantable_identifiers(self.grants))


class ClassDef(BaseFeatureDef):
    type: Literal["class"] = "class"
    sphere: Literal["arcane", "divine", "martial"] = "martial"
    starting_features: Grantable | None = None
    multiclass_features: Grantable | None = None
    bonus_features: dict[int, Grantable] | None = None
    level_table_columns: dict[str, dict]
    levels: dict[int, dict]
    # By default, classes have 10 levels.
    max_ranks: int = 10

    def post_validate(self, ruleset: base_models.BaseRuleset) -> None:
        super().post_validate(ruleset)
        if self.starting_features:
            ruleset.validate_identifiers(_grantable_identifiers(self.starting_features))
        if self.multiclass_features:
            ruleset.validate_identifiers(
                _grantable_identifiers(self.multiclass_features)
            )
        if self.bonus_features:
            grantables = list(self.bonus_features.values())
            ruleset.validate_identifiers(_grantable_identifiers(grantables))
        self.tags |= {self.sphere, "level"}
        if self.sphere != "martial":
            self.tags.add("caster")


class CostByValue(base_models.BaseModel):
    """For when the cost of something depends on something.

    Attributes:
        prop: What property does it depend on? Common cases:
            None: The rank of this thing. Use when the cost
                of a thing depends on how many of it you have.
            'level': The level of the character when you purchased
                the thing.
        value: Map of rank/level/whatevers to costs. Any value that
            isn't map assumes the next lowest cost. For example:
                1: 1
                5: 3
                10: 5
            means: Ranks from 1-4 cost 1 point. Ranks from 5-9 cost 3.
                Ranks 10+ cost 5.
        locked: The cost depends on the value at the time when the
            purchase is made. It does not fluctuate as the character
            levels up or whatever. This will cause the locked value to
            be recorded with the purchase.
    """

    prop: str | None = None
    value: dict[int, int]
    locked: bool = True


class SkillDef(BaseFeatureDef):
    type: Literal["skill"] = "skill"
    category: str = "General"
    cost: int | CostByValue
    uses: int | None = None
    option: base_models.OptionDef | None = None
    grants: Grantable = None

    def post_validate(self, ruleset: base_models.BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(_grantable_identifiers(self.grants))


class PowerDef(BaseFeatureDef):
    type: Literal["power"] = "power"
    sphere: Literal["arcane", "divine", "martial", None] = None
    tier: NonNegativeInt | None = None
    class_: str | None = Field(alias="class", default=None)
    incant_prefix: str | None = None
    incant: str | None = None
    call: str | None = None
    accent: str | None = None
    target: str | None = None
    duration: str | None = None
    delivery: str | None = None
    refresh: str | None = None
    effect: str | None = None
    grants: Grantable = None

    def post_validate(self, ruleset: base_models.BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(self.class_)
        ruleset.validate_identifiers(_grantable_identifiers(self.grants))


FeatureDefinitions: TypeAlias = ClassDef | ClassFeatureDef | SkillDef | PowerDef


class AttributeScaling(base_models.BaseModel):
    base: int
    factor: float
    rounding: Literal["up", "down", "nearest"] = "nearest"

    def evaluate(self, value: float) -> int:
        x = self.base + (value / self.factor)
        match self.rounding:
            case "up":
                return math.ceil(x)
            case "down":
                return math.floor(x)
            case _:
                return round(x)


class Ruleset(base_models.BaseRuleset):
    engine_class = "camp.engine.rules.tempest.engine.TempestEngine"
    features: dict[str, FeatureDefinitions] = Field(default_factory=dict)
    breedcap: int = 2
    flaw_cap: int = 5
    flaw_overcome: int = 2
    xp_table: dict[int, int]
    lp: AttributeScaling = AttributeScaling(base=2, factor=10, rounding="up")
    spikes: AttributeScaling = AttributeScaling(base=2, factor=8, rounding="down")

    attributes: ClassVar[Iterable[Attribute]] = [
        Attribute(id="xp", name="Experience Points", abbrev="XP", default_value=0),
        Attribute(id="xp_level", name="Experience Level", hidden=True, default_value=2),
        Attribute(id="level", name="Character Level", is_tag=True),
        Attribute(id="lp", name="Life Points", abbrev="LP", default_value=2),
        Attribute(id="cp", name="Character Points", abbrev="CP", default_value=0),
        Attribute(id="breedcap", name="Max Breeds", default_value=2, hidden=True),
        Attribute(id="bp", name="Breed Points", scoped=True, default_value=0),
        Attribute(id="spikes", name="Spikes", default_value=0),
        Attribute(id="bonus_utilities", name="Utilities"),
        Attribute(id="bonus_cantrips", name="Cantrips"),
        Attribute(id="active_pool", name="Active Powers / Spells Prepared"),
        Attribute(id="utility_pool", name="Utility Powers / Cantrips"),
        Attribute(
            id="spell_slots",
            name="Spells",
            scoped=True,
            tiered=True,
            tier_names=["Novice", "Intermediate", "Greater", "Master"],
        ),
        Attribute(
            id="powers",
            name="Powers",
            scoped=True,
            tiered=True,
            tier_names=["Basic", "Advanced", "Veteran", "Champion"],
        ),
        Attribute(
            id="arcane",
            name="Arcane Caster Levels",
            is_tag=True,
            hidden=True,
        ),
        Attribute(
            id="divine",
            name="Divine Caster Levels",
            is_tag=True,
            hidden=True,
        ),
        Attribute(
            id="martial",
            name="Martial Class Levels",
            is_tag=True,
            hidden=True,
        ),
        Attribute(
            id="caster",
            name="Caster Levels",
            is_tag=True,
            hidden=True,
        ),
    ]

    def feature_model_types(self) -> base_models.ModelDefinition:
        return FeatureDefinitions  # type: ignore[return-value]

    @property
    def sheet_type(self) -> Type[base_models.CharacterModel]:
        return models.CharacterModel


def _grantable_identifiers(grantables: Grantable | Iterable[Grantable]) -> set[str]:
    id_set = set()
    for g in maybe_iter(grantables):
        match g:  # type: ignore
            case list():
                id_set.update(_grantable_identifiers(g))
            case dict():
                id_set.update(list(g.keys()))
            case str():
                id_set.add(g)
            case None:
                pass
            case _:
                raise NotImplementedError(f"Unexpected grantable type {type(g)}")
    return id_set
