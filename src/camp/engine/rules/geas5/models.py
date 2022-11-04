from __future__ import annotations

from typing import ClassVar
from typing import Iterable
from typing import Literal
from typing import Type
from typing import TypeAlias

from pydantic import Field
from pydantic import NonNegativeInt
from pydantic import PositiveInt
from pydantic import PrivateAttr

from camp.engine.models import BaseAttributeDef
from camp.engine.models import BaseCharacter
from camp.engine.models import BaseFeatureDef as _BaseFeatureDef
from camp.engine.models import BaseModel
from camp.engine.models import BaseRuleset
from camp.engine.models import Discount
from camp.engine.models import Identifier
from camp.engine.models import ModelDefinition
from camp.engine.models import OptionDef
from camp.engine.models import Purchase
from camp.engine.models import RulesDecision
from camp.engine.models import Slot
from camp.engine.utils import maybe_iter

from . import aggregator


class GrantsByRank(BaseModel):
    by_rank: dict[PositiveInt, Grantables] = Field(alias="by_level")
    ref: Identifier | None = None
    _max_rank: int = PrivateAttr(default=0)
    _cache: dict[PositiveInt, list[Grantable]] = PrivateAttr(default_factory=dict)

    def grants(self, rank: int) -> list[Grantable]:
        if not self._max_rank:
            self._max_rank = max(self.__root__.keys())
        rank = min(rank, self._max_rank)
        if rank not in self._cache:
            grants = []
            for r, v in self.by_rank.items():
                if r <= rank:
                    for g in maybe_iter(v):
                        grants.append(g)
            self._cache[rank] = grants
        return self._cache[grants]


Grantable: TypeAlias = (
    Identifier | Discount | Slot | GrantsByRank | dict[Identifier, int]
)
Grantables: TypeAlias = list[Grantable] | Grantable | None
GrantsByRank.update_forward_refs()


class BaseFeatureDef(_BaseFeatureDef):
    def compute_grants(self, character: Character) -> Grantables:
        return None

    def aggregate(self, entry: Purchase, agg: aggregator.Aggregator) -> None:
        ranks = entry.ranks if entry.ranks is not None else 1
        if entry.option:
            # Add property on-demand.
            if not agg.has_prop(entry.option_id):
                agg.define_property(
                    aggregator.Property(
                        id=entry.option_id,
                        type="feature",
                        tags=self.tags | {self.id},
                    )
                )
            agg.apply_mod(entry.option_id, ranks)
        else:
            agg.apply_mod(entry.id, ranks)

    def define_property(self, agg: aggregator.Aggregator):
        if not agg.has_prop(self.id):
            if self.option is None:
                # This is a normal feature property.
                agg.define_property(
                    aggregator.Property(
                        id=self.id,
                        type="feature",
                        tags=self.tags,
                    )
                )
            else:
                # We'll define properties for the options on-demand.
                # Create a tag property for the base feature.
                agg.define_property(
                    aggregator.Property(
                        id=self.id,
                        type="feature",
                        is_tag=True,
                    )
                )


class ClassFeatureDef(BaseFeatureDef):
    type: Literal["classfeature"] = "classfeature"
    class_: str | None = Field(alias="class", default=None)
    grants: Grantables = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        if self.grants:
            ruleset.validate_identifiers(_grantable_identifiers(self.grants))

    def compute_grants(self, character: Character) -> Grantables:
        return self.grants


class ClassDef(BaseFeatureDef):
    type: Literal["class"] = "class"
    sphere: Literal["arcane", "divine", "martial"] = "martial"
    starting_features: Grantables = None
    multiclass_features: Grantables = None
    bonus_features: dict[int, Grantables] | None = None
    level_table_columns: dict[str, dict]
    levels: dict[int, dict]
    # By default, any number of levels can be taken in a class.
    ranks: bool | int = True

    def compute_grants(self, character: Character) -> Grantables:
        # Grants for a class depend on whether this is the first class taken,
        # or a subsequent class.
        ...

    def aggregate(self, entry: Purchase, agg: aggregator.Aggregator) -> None:
        super().aggregate(entry, agg)
        level = entry.ranks if entry.ranks is not None else 1

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
                    class_attr = f"{attr}#{self.id}"
                    sphere_attr = f"{attr}#{self.sphere}"
                    agg.define_property(
                        aggregator.Property(
                            id=class_attr,
                            type="attribute",
                            tags={attr, sphere_attr},
                        )
                    )
                    if not agg.has_prop(sphere_attr):
                        agg.define_property(
                            aggregator.Property(
                                id=sphere_attr,
                                type="attribute",
                                is_tag=True,
                            )
                        )
                    agg.apply_mod(class_attr, value)
                case "power_slots":
                    # These are local attributes whose value is specified as a list.
                    # Each value is for a different tier of power slots, so we use the
                    # attr@N "tier" syntax to seperately aggregate each tier's value.
                    # Like other locals, we also add aggregations for the class ID and
                    # the sphere type.
                    if not agg.has_prop(attr):
                        agg.define_property(
                            aggregator.Property(
                                id=attr,
                                type="attribute",
                                is_tag=True,
                            )
                        )
                    for i, slot_value in enumerate(value):
                        tier_id = f"{attr}@{i+1}"
                        class_tier = f"{tier_id}#{self.id}"
                        sphere_tier = f"{tier_id}#{self.sphere}"
                        agg.define_property(
                            aggregator.Property(
                                id=class_tier,
                                type="attribute",
                                tags={attr, tier_id, sphere_tier},
                            )
                        )
                        if not agg.has_prop(tier_id):
                            agg.define_property(
                                aggregator.Property(
                                    id=tier_id,
                                    type="attribute",
                                    is_tag=True,
                                )
                            )
                        if not agg.has_prop(sphere_tier):
                            agg.define_property(
                                aggregator.Property(
                                    id=sphere_tier,
                                    type="attribute",
                                    is_tag=True,
                                )
                            )
                        agg.apply_mod(class_tier, slot_value)
                case _:
                    # Basic attributes, currencies, etc.
                    agg.apply_mod(attr, value)

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        if self.starting_features:
            ruleset.validate_identifiers(_grantable_identifiers(self.starting_features))
        if self.multiclass_features:
            ruleset.validate_identifiers(
                _grantable_identifiers(self.multiclass_features)
            )
        if self.bonus_features:
            ruleset.validate_identifiers(
                _grantable_identifiers(list(self.bonus_features.values()))
            )
        self.tags |= {self.sphere, "level"}
        if self.sphere != "martial":
            self.tags.add("caster")


class CostByValue(BaseModel):
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
    option: OptionDef | None = None
    grants: Grantables = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
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
    grants: Grantables = None

    def post_validate(self, ruleset: BaseRuleset) -> None:
        super().post_validate(ruleset)
        ruleset.validate_identifiers(self.class_)
        ruleset.validate_identifiers(_grantable_identifiers(self.grants))


FeatureDefinitions: TypeAlias = ClassDef | ClassFeatureDef | SkillDef | PowerDef


class Character(BaseCharacter):
    _aggregate: aggregator.Aggregator = PrivateAttr(
        default_factory=aggregator.Aggregator
    )
    _aggregate_dirty: bool = PrivateAttr(default=True)

    def can_purchase(self, entry: Purchase | str) -> RulesDecision:
        if isinstance(entry, str):
            entry = Purchase(id=entry)

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

        # There are no negative or zero ranks allowed in Geas at present.
        if entry.ranks < 1:
            return RulesDecision(
                success=False,
                reason=f"Positive number of ranks required, but {entry.ranks} ranks given.",
            )

        # Check that the specified number of ranks matches the spec.
        match feature.ranks:
            case True:
                pass
            case False:
                if entry.ranks != 1:
                    return RulesDecision(
                        success=False,
                        reason=f"Ranks not allowed here, but {entry.ranks} ranks given.",
                    )
            case int():
                if entry.ranks > feature.ranks:
                    return RulesDecision(
                        success=False,
                        reason=f"At most {feature.ranks} ranks allowed, but {entry.ranks} ranks given.",
                    )

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

    def purchase(self, entry: Purchase | str) -> RulesDecision:
        if isinstance(entry, str):
            entry = Purchase(id=entry)

        if not (rd := super().purchase(entry)):
            return rd

        # Check if this results in any new feature grants.
        # feature = self._ruleset.features[entry.id]
        self._aggregate_dirty = True
        return rd

    def get_prop(self, id: str) -> int:
        return self._get_aggregator().get_prop(id)

    def get_prop_max(self, id: str) -> int:
        return self._get_aggregator().get_prop_max(id)

    def has_prop(self, id: str) -> bool:
        return self._get_aggregator().has_prop(id)

    def _get_aggregator(self) -> aggregator.Aggregator:
        if not self._aggregate_dirty:
            return self._aggregate
        agg = self._make_aggregator()
        for entry in self.purchases:
            if feature_def := self._ruleset.features.get(entry.id):
                feature_def.aggregate(entry, agg)
        self._aggregate_dirty = False
        self._aggregate = agg
        return self._aggregate

    def _make_aggregator(self) -> aggregator.Aggregator:
        agg = aggregator.Aggregator()
        for feature in self._ruleset.features.values():
            feature.define_property(agg)
        for attribute in self._ruleset.attributes:
            # TODO: Handle scoped somehow?
            if not attribute.scoped:
                agg.define_property(
                    aggregator.Property(
                        id=attribute.id,
                        type="attribute",
                        base=attribute.default_value or 0,
                        min_value=attribute.min_value,
                        max_value=attribute.max_value,
                        is_tag=attribute.is_tag,
                    )
                )
        return agg


class Ruleset(BaseRuleset):
    features: dict[Identifier, FeatureDefinitions] = Field(default_factory=dict)
    breedcap: int = 2
    flaw_cap: int = 10
    flaw_overcome: int = 2
    xp_table: dict[int, int]
    lp_table: dict[int, int]
    attributes: ClassVar[Iterable[BaseAttributeDef]] = [
        BaseAttributeDef(
            id="xp", name="Experience Points", abbrev="XP", default_value=0
        ),
        BaseAttributeDef(
            id="xp_level", name="Experience Level", hidden=True, default_value=2
        ),
        BaseAttributeDef(id="level", name="Character Level", is_tag=True),
        BaseAttributeDef(id="lp", name="Life Points", abbrev="LP", default_value=2),
        BaseAttributeDef(
            id="cp", name="Character Points", abbrev="CP", default_value=0
        ),
        BaseAttributeDef(
            id="breedcap", name="Max Breeds", default_value=2, hidden=True
        ),
        BaseAttributeDef(id="bp", name="Breed Points", scoped=True, default_value=0),
        BaseAttributeDef(id="spikes", name="Spikes", default_value=0),
        BaseAttributeDef(id="utilities", name="Utilities", scoped=True),
        BaseAttributeDef(id="cantrips", name="Cantrips", scoped=True),
        BaseAttributeDef(
            id="spells",
            name="Spells",
            scoped=True,
            tiered=True,
            tier_names=["Novice", "Intermediate", "Greater", "Master"],
        ),
        BaseAttributeDef(
            id="powers",
            name="Powers",
            scoped=True,
            tiered=True,
            tier_names=["Basic", "Advanced", "Veteran", "Champion"],
        ),
        BaseAttributeDef(
            id="arcane",
            name="Arcane Caster Levels",
            is_tag=True,
            hidden=True,
        ),
        BaseAttributeDef(
            id="divine",
            name="Divine Caster Levels",
            is_tag=True,
            hidden=True,
        ),
        BaseAttributeDef(
            id="martial",
            name="Martial Class Levels",
            is_tag=True,
            hidden=True,
        ),
        BaseAttributeDef(
            id="caster",
            name="Caster Levels",
            is_tag=True,
            hidden=True,
        ),
    ]
    # Attribute-like values that are probably only used internally.
    # Promote them to attributes if players might need to see them.
    builtin_identifiers: ClassVar[set[Identifier]] = {
        "armor",
    }

    def feature_model_types(self) -> ModelDefinition:
        return FeatureDefinitions  # type: ignore[return-value]

    @property
    def sheet_type(self) -> Type[BaseCharacter]:
        return Character


def _grantable_identifiers(grantables: Grantables) -> set[Identifier]:
    id_set = set()
    for g in maybe_iter(grantables):
        match g:  # type: ignore
            case Discount():  # type: ignore
                id_set.update(_grantable_identifiers(g.id))
            case Slot():  # type: ignore
                id_set.update(_grantable_identifiers(g.discount))
                id_set.update(_grantable_identifiers(g.choices))
                id_set.update(_grantable_identifiers(g.feature_type))
            case GrantsByRank():
                if g.ref:
                    id_set.update(g.ref)
                id_set.update(_grantable_identifiers(list(g.by_rank.values())))
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
