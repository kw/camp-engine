from __future__ import annotations

from typing import ClassVar
from typing import Literal
from typing import Type
from typing import TypeAlias

from pydantic import Field

from camp.engine.models import BaseCharacter
from camp.engine.models import BaseFeatureDef
from camp.engine.models import BaseModel
from camp.engine.models import BaseRuleset
from camp.engine.models import FeatureEntry
from camp.engine.models import Identifier
from camp.engine.models import Identifiers
from camp.engine.models import ModelDefinition
from camp.engine.models import OptionDef
from camp.engine.models import RulesDecision
from camp.engine.utils import Aggregator
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
    sphere: Literal["arcane", "divine", "martial"] = "martial"
    starting_features: Identifiers = None
    multiclass_features: Identifiers = None
    bonus_features: dict[int, Identifiers] | None = None
    class_features: dict[Identifier, ClassFeatureDef] = Field(default_factory=dict)
    level_table_columns: dict[str, dict]
    levels: dict[int, dict]

    def aggregate(self, entry: FeatureEntry, agg: Aggregator) -> None:
        super().aggregate(entry, agg)
        level = entry.ranks if entry.ranks is not None else 1

        # Aggregate caster/martial/sphere counters
        agg.aggregate(self.sphere, level)
        if self.sphere != "martial":
            agg.aggregate("caster", level)

        # Character level aggregate. Note that the "max" aggregation
        # is also done, so 'level$N' can test the highest level in
        # a single class.
        agg.aggregate("level", level)

        # Attributes by level
        if level in self.levels:
            row = self.levels[level]
        else:
            row = self.levels[max(self.levels.keys())]
        for attr, value in row.items():
            meta = self.level_table_columns[attr]
            match meta["type"]:
                case "local":
                    # For "local" attributes such as the number of prepared
                    # spells, we want to keep each class's prepared spells
                    # separated. However, we me also want to know whether the
                    # character has, for example, arcane prepared spells,
                    # or any prepared spells at all. So we aggregate using
                    # the class ID and the class sphere as extra options.
                    agg.aggregate(f"{attr}#{self.id}", value, do_max=False)
                    agg.aggregate(f"{attr}#{self.sphere}", value)
                    agg.aggregate(attr, value)
                case "power_slots":
                    # These are local attributes whose value is specified as a list.
                    # Each value is for a different tier of power slots, so we use the
                    # attr@N "tier" syntax to seperately aggregate each tier's value.
                    # Like other locals, we also add aggregations for the class ID and
                    # the sphere type.
                    for i, slot_value in enumerate(value):
                        tier_id = f"{attr}@{i+1}"
                        agg.aggregate(f"{tier_id}#{self.id}", slot_value, do_max=False)
                        agg.aggregate(
                            f"{tier_id}#{self.sphere}", slot_value, do_max=False
                        )
                        agg.aggregate(tier_id, slot_value)
                        agg.aggregate(attr, slot_value)
                case _:
                    # Basic attributes, currencies, etc.
                    agg.aggregate(attr, value, do_max=False)

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        if self.starting_features:
            ruleset.validate_identifiers(self.starting_features)
        if self.multiclass_features:
            ruleset.validate_identifiers(self.multiclass_features)
        if self.bonus_features:
            ruleset.validate_identifiers(self.bonus_features.values())


class SkillDef(BaseFeatureDef):
    type: Literal["skill"] = "skill"
    category: str = "General"
    cost: int
    uses: int | None = None
    option: OptionDef | None = None
    grants: Grantables = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        for grant in maybe_iter(self.grants):
            if isinstance(grant, GrantAttribute):
                ruleset.validate_identifiers(grant.attribute)
            elif isinstance(grant, str):
                ruleset.validate_identifiers(grant)


class PowerDef(BaseFeatureDef):
    type: Literal["power"] = "power"
    sphere: Literal["arcane", "divine", "martial"]
    tier: Literal[0, 1, 2, 3, 4]
    class_: str = Field(alias="class")
    incant_prefix: str | None = None
    incant: str | None = None
    call: str | None = None
    accent: str | None = None
    target: str | None = None
    duration: str | None = None
    delivery: str | None = None
    refresh: str | None = None
    effect: str | None = None
    grants: Grantables = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(self.class_)


FeatureDefinitions: TypeAlias = ClassDef | ClassFeatureDef | SkillDef | PowerDef


class Character(BaseCharacter):
    def can_add_feature(self, entry: FeatureEntry | str) -> RulesDecision:
        if isinstance(entry, str):
            entry = FeatureEntry(id=entry)

        ruleset = self._ruleset
        if entry.id not in ruleset.features:
            return RulesDecision(success=False, reason="Feature not defined")

        feature = ruleset.features[entry.id]
        entries = self.features.get(entry.id)

        # Skills are the only feature in Geas that can
        # potentially have multiple instances. Probably.
        if entries:
            if feature.option and not feature.multiple:
                return RulesDecision(success=False, reason="Already have this feature")
            elif any(e for e in entries if e.option == entry.option):
                return RulesDecision(
                    success=False, reason="Already have this feature with this option"
                )
            elif not feature.option:
                return RulesDecision(success=False, reason="Already have this feature.")

        if feature.option and not entry.option:
            # The feature requires an option, but one was not provided. This happens
            # during preliminary scans of purchasable features. As long as there are
            # any options available for purchase, report true, but mark it appropriately.
            if feature.option.freeform or self.options_values_for_feature(
                feature.id, exclude_taken=True
            ):
                return RulesDecision(success=True, needs_option=True)
        if not self.option_satisfies_definition(
            feature.id, entry.option, exclude_taken=True
        ):
            return RulesDecision(
                success=False, reason="Option does not satisfy requirements"
            )

        # TODO: Lots of other checks, like:
        # * Enforce build order, maybe (Starting Class -> Breeds -> Other)?
        # * Enforce currencies (CP, XP, BP, etc)
        # * Etc?

        if not (rd := self.meets_requirements(feature.requires)):
            return rd

        return RulesDecision(success=True)


class Ruleset(BaseRuleset):
    features: dict[Identifier, FeatureDefinitions] = Field(default_factory=dict)
    breedcap: int = 2
    flaw_cap: int = 10
    flaw_overcome: int = 2
    xp_table: dict[int, int]
    lp_table: dict[int, int]
    builtin_identifiers: ClassVar[set[Identifier]] = {
        "xp",
        "lp",
        "cp",
        "breedcap",
        "armor",
        "arcane",
        "divine",
        "martial",
        "caster",
        "level",
        "spells",
        "powers",
        "utilities",
        "cantrips",
    }

    def feature_model_types(self) -> ModelDefinition:
        return FeatureDefinitions  # type: ignore[return-value]

    @property
    def sheet_type(self) -> Type[BaseCharacter]:
        return Character
