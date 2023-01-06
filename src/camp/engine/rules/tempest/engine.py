from __future__ import annotations

import math
from abc import abstractproperty
from functools import cached_property
from typing import Iterable
from typing import Mapping

from camp.engine import utils

from .. import base_engine
from ..base_models import OptionDef
from ..base_models import PropExpression
from ..base_models import Purchase
from ..decision import Decision
from . import defs
from . import models

_MUST_BE_POSITIVE = Decision(success=False, reason="Value must be positive.")
_NO_RESPEND = Decision(success=False, reason="Respend not currently available.")


class TempestCharacter(base_engine.CharacterController):
    model: models.CharacterModel
    engine: TempestEngine
    ruleset: defs.Ruleset
    _classes: dict[str, ClassController] | None = None
    _skills: dict[str, SkillController] | None = None
    _perks: dict[str, PerkController] | None = None
    _flaws: dict[str, FlawController] | None = None

    @property
    def xp(self) -> int:
        """Experience points"""
        return self.model.metadata.awards.get("xp", 0)

    @property
    def xp_level(self) -> int:
        """Experience level.

        This is slightly different than character level - XP level is
        the character level that you're entitled to have, but actual
        character level is the sum of class levels you've selected. The
        "Level Up!" (or equivalent) button will appear when character level
        is less than XP Level, but will cause a validation error if character
        level exceeds XP level.
        """
        # TODO: Calculate XP levels past the max in the table.
        return utils.table_lookup(self.ruleset.xp_table, self.xp)

    @xp_level.setter
    def xp_level(self, value):
        """Set the XP level to a specific level.

        This is a convenience method primarily for testing purposes. If an XP
        level is manually set, the copy of the metadata attached to the sheet will be
        overwritten with the needed XP. Characters in a real app will likely have
        their source of metadata truth stored elsewhere and applied on load, so
        persisting this change will not do what you want for such characters.
        """
        self.model.metadata.awards["xp"] = utils.table_reverse_lookup(
            self.ruleset.xp_table, value
        )

    @property
    def base_cp(self) -> int:
        """CP granted by formula from the ruleset.

        By default, this is 1 + 2 * Level.
        """
        return self.ruleset.cp_baseline + (self.ruleset.cp_per_level * self.xp_level)

    @property
    def awarded_cp(self) -> int:
        """CP granted by fiat (backstory writing, etc)."""
        return self.model.metadata.awards.get("cp", 0)

    @awarded_cp.setter
    def awarded_cp(self, value: int) -> None:
        self.model.metadata.awards["cp"] = value

    @property
    def base_lp(self) -> int:
        return self.ruleset.lp.evaluate(self.xp_level)

    @cached_property
    def lp(self) -> LifePointController:
        return LifePointController("lp", self)

    @property
    def base_spikes(self) -> int:
        return self.ruleset.spikes.evaluate(self.xp_level)

    @property
    def can_respend(self) -> bool:
        """Can the character be freely edited?

        This should be true before the character's first full weekend game, and potentially
        before the second. There may be some other situations where it turns on, such as
        a ritual that allows respend, though many of these may be more specific (e.g. a
        ritual that allows breed options to be edited, or an SP action that allows a single
        class level to be respent). We'll handle those on a case-by-case basis elsewhere.
        """
        # TODO: Actually base this on something
        return True

    @cached_property
    def cp(self) -> CharacterPointController:
        return CharacterPointController("cp", self)

    @cached_property
    def level(self) -> SumAttribute:
        return SumAttribute("level", self, "class")

    @property
    def levels_available(self) -> int:
        return self.xp_level - self.level.value

    @property
    def primary_class(self) -> str | None:
        return self.model.primary_class

    @property
    def starting_class(self) -> str | None:
        return self.model.starting_class

    @property
    def classes(self) -> dict[str, ClassController]:
        """Dict of the character's class controllers.

        The primary class will be first in iteration order.
        """
        if self._classes:
            return self._classes
        classes: dict[str, ClassController] = {}
        primary = self.model.primary_class
        if primary:
            classes[primary] = ClassController(primary, self)

        for id in self.model.classes:
            if id == primary:
                # Already added.
                continue
            classes[id] = ClassController(id, self)
        self._classes = classes
        return classes

    @property
    def skills(self) -> dict[str, SkillController]:
        if self._skills:
            return self._skills
        skills: dict[str, SkillController] = {}
        for id in self.model.skills:
            skills[id] = SkillController(id, self)
        self._skills = skills
        return skills

    @property
    def perks(self) -> dict[str, PerkController]:
        if self._perks:
            return self._perks
        perks: dict[str, PerkController] = {}
        for id in self.model.perks:
            perks[id] = PerkController(id, self)
        self._perks = perks
        return perks

    @property
    def flaws(self) -> dict[str, FlawController]:
        if self._flaws:
            return self._flaws
        flaws: dict[str, FlawController] = {}
        for id in self.model.flaws:
            flaws[id] = FlawController(id, self)
        self._flaws = flaws
        return flaws

    def can_purchase(self, entry: Purchase | str) -> Decision:
        if not isinstance(entry, Purchase):
            entry = Purchase.parse(entry)
        if controller := self._controller_for_feature(entry.expression):
            if entry.ranks > 0:
                return controller.can_increase(entry.ranks)
            elif entry.ranks < 0:
                return controller.can_decrease(-entry.ranks)
        return Decision(
            success=False, reason=f"Purchase not implemented: {entry.expression}"
        )

    def purchase(self, entry: Purchase | str) -> Decision:
        if not isinstance(entry, Purchase):
            entry = Purchase.parse(entry)
        if not isinstance(entry, Purchase):
            entry = Purchase.parse(entry)
        if controller := self._controller_for_feature(entry.expression):
            if entry.ranks > 0:
                return controller.increase(entry.ranks)
            elif entry.ranks < 0:
                return controller.decrease(-entry.ranks)
        return Decision(
            success=False, reason=f"Purchase not implemented: {entry.expression}"
        )

    def has_prop(self, expr: str | PropExpression) -> bool:
        """Check whether the character has _any_ property (feature, attribute, etc) with the given name.

        The base implementation only knows how to check for attributes. Checking for features
        must be added by implementations.
        """
        expr = PropExpression.parse(expr)
        if controller := self._controller_for_feature(expr):
            return controller.value > 0
        return super().has_prop(expr)

    def get_prop(self, expr: str | PropExpression) -> int:
        expr = PropExpression.parse(expr)
        if controller := self._controller_for_feature(expr):
            return controller.value
        return super().get_prop(expr)

    def get_options(self, id: str) -> dict[str, int]:
        if controller := self._controller_for_feature(PropExpression.parse(id)):
            return controller.taken_options
        return super().get_options(id)

    @property
    def features(self) -> Mapping[str, Mapping[str, FeatureController]]:
        return {
            "class": self.classes,
            "skill": self.skills,
            "perk": self.perks,
            "flaw": self.flaws,
        }

    @cached_property
    def martial(self) -> base_engine.AttributeController:
        return SumAttribute("martial", self, "class", "martial")

    @cached_property
    def caster(self) -> base_engine.AttributeController:
        return SumAttribute("caster", self, "class", "caster")

    @cached_property
    def arcane(self) -> base_engine.AttributeController:
        return SumAttribute("arcane", self, "class", "arcane")

    @cached_property
    def divine(self) -> base_engine.AttributeController:
        return SumAttribute("divine", self, "class", "divine")

    def _controller_for_type(self, feature_type: str, id: str) -> FeatureController:
        match feature_type:
            case "class":
                return ClassController(id, self)
            case "skill":
                return SkillController(id, self)
            case "flaw":
                return FlawController(id, self)
            case "perk":
                return PerkController(id, self)
        raise NotImplementedError(
            f"Unknown feature controller {feature_type} for feature {id}"
        )

    def _controller_for_feature(
        self, expr: PropExpression | str, create: bool = True
    ) -> FeatureController | None:
        if isinstance(expr, str):
            expr = PropExpression.parse(expr)
        # Figure out what kind of feature this is. Or if it even is one.
        if not (feature_def := self.ruleset.features.get(expr.prop)):
            return None
        # If this skill is already on the sheet, fetch its controller
        if (controller_dict := self.features.get(feature_def.type)) and (
            controller := controller_dict.get(expr.full_id)
        ) is not None:
            return controller
        # Otherwise, create a controller and ask it.
        if create:
            return self._controller_for_type(feature_def.type, expr.full_id)
        return None

    def _controller_for_property(
        self, expr: PropExpression | str, create: bool = True
    ) -> base_engine.PropertyController | None:
        if isinstance(expr, str):
            expr = PropExpression.parse(expr)
        if expr.prop in self.ruleset.features:
            return self._controller_for_feature(expr, create=create)
        elif expr.prop in self.ruleset.attribute_map:
            controller = self.get_attribute(expr)
            if isinstance(controller, base_engine.PropertyController):
                return controller
        return None

    def clear_caches(self):
        super().clear_caches()
        self._classes = {}
        self._skills = {}
        self._flaws = {}
        self._perks = {}


class FeatureController(base_engine.FeatureController):
    character: TempestCharacter
    definition: defs.BaseFeatureDef
    expression: PropExpression
    full_id: str
    _effective_ranks: int | None
    _granted_ranks: int
    _discount: int

    def __init__(self, full_id: str, character: TempestCharacter):
        self.expression = PropExpression.parse(full_id)
        self.full_id = full_id
        super().__init__(self.expression.prop, character)
        self.definition = character.ruleset.features[self.id]
        self._effective_ranks = None
        self._granted_ranks = 0
        self._discount = 0

    @cached_property
    def feature_type(self) -> str:
        return self.definition.type

    @property
    def option(self) -> str | None:
        return self.expression.option

    @property
    def option_def(self) -> OptionDef | None:
        return self.definition.option

    @property
    def taken_options(self) -> dict[str, int]:
        options = {}
        for controller in self.character.features[self.feature_type].values():
            if controller.id == self.id and controller.option and controller.value > 0:
                options[controller.option] = controller.value
        return options

    @abstractproperty
    def purchased_ranks(self) -> int:
        ...

    @purchased_ranks.setter
    def purchased_ranks(self, value: int):
        ...

    @property
    def granted_ranks(self) -> int:
        return self._granted_ranks

    @property
    def paid_ranks(self) -> int:
        """Number of ranks purchased that actually need to be paid for with some currency.

        This is generally equal to `purchased_ranks`, but when grants push the total over the
        feature's maximum, these start to be refunded. They remain on the sheet in case the
        grants are revoked in the future due to an undo, a sellback, a class level swap, etc.
        """
        total = self.purchased_ranks + self.granted_ranks
        max_ranks = self.max_ranks
        if total <= max_ranks:
            return self.purchased_ranks
        # The feature is at maximum. Only pay for ranks that haven't been granted.
        # Note that the total grants could also exceed max_ranks. This is more likely
        # to happen with single-rank features like weapon proficiencies that a character
        # might receive from multiple classes.
        if self.granted_ranks < max_ranks:
            return max_ranks - self.granted_ranks
        return 0

    @property
    def value(self) -> int:
        if self.option_def and not self.option:
            # This is an aggregate controller for the feature.
            # Sum any ranks the character has in instances of it.
            total: int = 0
            for feat, controller in self.character.features[self.feature_type].items():
                if feat.startswith(f"{self.id}#"):
                    total += controller.value
            return total
        if self._effective_ranks is None:
            self.reconcile()
        return self._effective_ranks

    @property
    def max_value(self) -> int:
        if self.option_def and not self.option:
            # This is an aggregate controller for the feature.
            # Return the value of the highest instance.
            current: int = 0
            for feat, controller in self.character.features[self.feature_type].items():
                if feat.startswith(f"{self.id}#"):
                    new_value = controller.value
                    if new_value > current:
                        current = new_value
            return current
        return super().max_value

    def _link_to_character(self):
        feats = self.character.features[self.definition.type]
        if self.full_id not in feats:
            feats[self.full_id] = self

    def can_increase(self, value: int) -> Decision:
        if value <= 0:
            return _MUST_BE_POSITIVE
        current = self.value
        if current >= self.definition.ranks:
            return Decision(success=False)
        # Is the purchase within defined range?
        if (current + value) > self.definition.ranks:
            max_increase = self.definition.ranks - current
            return Decision(
                success=False,
                reason=f"Max is {self.definition.ranks}, so can't increase to {current + value}",
                amount=max_increase,
            )
        # Does the character meet the prerequisites?
        if not (rd := self.character.meets_requirements(self.definition.requires)):
            return rd
        # Is this an option skill without an option specified?
        if self.option_def and not self.option:
            return Decision(success=False, needs_option=True)
        elif (
            self.option_def
            and self.option
            and not self.definition.option.freeform
            and self.purchased_ranks == 0
        ):
            # The player is trying to buy a new option. Verify that it's legal.
            options_available = self.character.options_values_for_feature(
                self.id, exclude_taken=True
            )
            if self.option not in options_available:
                return Decision(
                    success=False,
                    reason=f"'{self.option}' not a valid option for {self.id}",
                )
        # Is this a non-option skill and an option was specified anyway?
        if not self.option_def and self.option:
            return Decision(
                success=False, reason=f"Feature {self.id} does not accept options."
            )
        return Decision.SUCCESS

    def can_decrease(self, value: int) -> Decision:
        if not self.character.can_respend:
            return _NO_RESPEND
        if value < 1:
            return _MUST_BE_POSITIVE
        purchases = self.purchased_ranks
        if value > purchases:
            return Decision(
                success=False,
                reason=f"Can't sell back {value} ranks when you've only purchased {purchases} ranks.",
                amount=(value - purchases),
            )
        return Decision.SUCCESS

    def propagate(self, data: base_engine.PropagationData) -> None:
        if not data:
            return
        self._granted_ranks += data.grants
        self._discount += data.discount
        self.reconcile()

    def reconcile(self) -> None:
        """If this controller's value has been updated (or on an initial pass on character load), update grants.

        Grants represent any feature (or feature ranks) gained simply by possessing this feature (or a number of ranks of it).
        All features in this model have a `grants` field in their definition that specify one or more features to grant one or
        more ranks of, and this will be processed whenever any ranks of this feature are possessed.

        Subclasses may have more specific grants. For example, classes may automatically grant certain features at specific levels.

        """
        previous_ranks = self._effective_ranks or 0
        self._effective_ranks = min(
            self.granted_ranks + self.purchased_ranks, self.max_ranks
        )

        self._link_to_character()
        self._perform_propagation(previous_ranks, self._effective_ranks)

    def _perform_propagation(self, from_ranks: int, to_ranks: int) -> None:
        props = self._gather_propagation(from_ranks, to_ranks)
        for id, data in props.items():
            if controller := self.character._controller_for_property(id):
                controller.propagate(data)

    def _gather_propagation(
        self, from_ranks: int, to_ranks: int
    ) -> dict[str, base_engine.PropagationData]:
        if not (from_ranks == 0 or to_ranks == 0) or (from_ranks == to_ranks):
            # At the moment, all grants only happen at the boundary of 0, so skip
            # all this if we're not coming from or going to 0.
            return {}
        grants = dict(self._gather_grants(self.definition.grants, from_ranks, to_ranks))
        discounts = dict(
            self._gather_discounts(self.definition.discounts, from_ranks, to_ranks)
        )
        props: dict[str, base_engine.PropagationData] = {}
        all_keys = set(grants.keys()).union(discounts.keys())
        for id in all_keys:
            props[id] = base_engine.PropagationData()
            if g := grants.get(id):
                props[id].grants = g
            if d := discounts.get(id):
                props[id].discount = d
        return props

    def _gather_grants(
        self, grants: defs.Grantable, from_ranks: int, to_ranks: int
    ) -> Iterable[tuple[str, int]]:
        if not grants:
            return
        elif isinstance(grants, str):
            expr = PropExpression.parse(grants)
            value = expr.value or 1
            if to_ranks <= 0:
                value = -value
            yield expr.full_id, value
        elif isinstance(grants, list):
            for grant in grants:
                yield from self._gather_grants(grant, from_ranks, to_ranks)
        elif isinstance(grants, dict):
            for key, value in grants.items():
                if to_ranks <= 0 and from_ranks > 0:
                    value = -value
                yield key, value
        else:
            raise NotImplementedError(f"Unexpected grant value: {grants}")

    def _gather_discounts(
        self, discounts: defs.Discounts, from_ranks: int, to_ranks: int
    ):
        if not discounts:
            return
        elif isinstance(discounts, dict):
            for key, value in discounts.items():
                if to_ranks <= 0:
                    value = -value
                yield key, value
        else:
            raise NotImplementedError(f"Unexpected discount value: {discounts}")


class ClassController(FeatureController):
    definition: defs.ClassDef

    def __init__(self, id: str, character: TempestCharacter):
        super().__init__(id, character)
        if not isinstance(self.definition, defs.ClassDef):
            raise ValueError(
                f"Expected {id} to be a class, but was {type(self.definition)}"
            )

    @property
    def primary(self) -> bool:
        return self.character.model.primary_class == self.id

    @property
    def starting_class(self) -> bool:
        return self.character.model.starting_class == self.id

    @property
    def sphere(self) -> str:
        return self.definition.sphere

    @property
    def martial(self) -> bool:
        return self.definition.sphere == "martial"

    @property
    def arcane(self) -> bool:
        return self.definition.sphere == "arcane"

    @property
    def divine(self) -> bool:
        return self.definition.sphere == "divine"

    @property
    def caster(self) -> bool:
        return self.definition.sphere != "martial"

    @property
    def purchased_ranks(self) -> int:
        return self.character.model.classes.get(self.id, 0)

    @purchased_ranks.setter
    def purchased_ranks(self, value: int):
        self.character.model.classes[self.full_id] = value

    def can_increase(self, value: int = 1) -> Decision:
        if not (rd := super().can_increase(value)):
            return rd
        character_available = self.character.levels_available
        class_available = self.max_ranks - self.value
        available = min(character_available, class_available)
        return Decision(success=available >= value, amount=available)

    def increase(self, value: int) -> Decision:
        if self.character.level == 0 and value < 2:
            # This is the character's first class. Ensure at least 2 ranks are purchased.
            value = 2
        if not (rd := self.can_increase(value)):
            return rd
        current = self.value
        new_value = current + value
        if (
            not self.primary
            and max(self.character.model.classes.values(), default=0) < new_value
        ):
            self.character.model.primary_class = self.id
        self.character.model.classes[self.id] = new_value
        if current == 0:
            # This is a new class for this character. Cache this controller.
            self._link_to_character()
        if self.character.model.starting_class is None:
            self.character.model.starting_class = self.id
        self.reconcile()
        return Decision(success=True, amount=self.value)

    def can_decrease(self, value: int = 1) -> Decision:
        if not (rd := super().can_decrease(value)):
            return rd
        current = self.purchased_ranks
        # If this is the starting class, it can't be reduced below level 2
        # unless it's the only class on the sheet.
        if (
            self.character.model.starting_class == self.id
            and len(self.character.model.classes) > 1
        ):
            if current - value < 2:
                return Decision(
                    success=False,
                    amount=(current - 2),
                    reason="Can't reduce starting class levels below 2 while multiclassed.",
                )
        return Decision(success=current >= value, amount=current)

    def decrease(self, value: int) -> Decision:
        if value <= 0:
            return _MUST_BE_POSITIVE
        if not (rd := self.can_decrease(value)):
            return rd
        current = self.purchased_ranks
        new_value = current - value
        if self.id == self.character.model.starting_class and new_value < 2:
            new_value = 0
        if new_value > 0:
            self.purchased_ranks = new_value
        else:
            del self.character.model.classes[self.id]
        if (
            self.primary
            and max(self.character.model.classes.values(), default=0) < new_value
        ):
            # TODO: Auto-set to the new highest
            self.character.model.primary_class = None
        if not self.character.model.classes:
            self.character.model.primary_class = None
            self.character.model.starting_class = None
        self.reconcile()
        return Decision(success=True, amount=self.value)


class CostsCharacterPointsController(FeatureController):
    @property
    def cost_def(self) -> defs.CostDef:
        if not hasattr(self.definition, "cost"):
            raise NotImplementedError(f"{self} does not have a cost definition.")
        return self.definition.cost

    @property
    def cp_cost(self) -> int:
        return self.cost_for(self.paid_ranks)

    def cost_for(self, ranks: int) -> int:
        cd = self.cost_def
        if isinstance(cd, int):
            cd = max(cd - self._discount, 1)
            return cd * ranks
        elif isinstance(cd, defs.CostByRank):
            return cd.total_cost(ranks, discount=self._discount)
        else:
            raise NotImplementedError(f"Don't know how to compute cost with {cd}")

    def max_rank_increase(self, available_cp: int = -1) -> int:
        if available_cp < 0:
            available_cp = self.character.cp.value
        available_ranks = self.max_ranks - self.value
        current_cost = self.cp_cost
        if available_ranks < 1:
            return 0
        match cd := self.cost_def:
            case int():
                # Relatively trivial case
                return min(available_ranks, math.floor(available_cp / cd))
            case defs.CostByRank():
                while available_ranks > 0:
                    cp_delta = (
                        self.cost_for(self.paid_ranks + available_ranks) - current_cost
                    )
                    if cp_delta <= available_cp:
                        return available_ranks
                    available_ranks -= 1
                return 0
            case _:
                raise NotImplementedError(f"Don't know how to compute cost with {cd}")

    def can_increase(self, value: int) -> Decision:
        if not (rd := super().can_increase(value)):
            return rd
        # Can the character afford the purchase?
        current_cp = self.character.cp
        cp_delta = self.cost_for(self.paid_ranks + value) - self.cp_cost
        if current_cp < cp_delta:
            return Decision(
                success=False,
                reason=f"Need {cp_delta} CP to purchase, but only have {current_cp}",
                amount=self.max_rank_increase(current_cp.value),
            )
        return Decision.SUCCESS

    def increase(self, value: int) -> Decision:
        if not (rd := self.can_increase(value)):
            return rd
        current = self.purchased_ranks
        self.purchased_ranks = current + value
        if current == 0:
            # This is a new feature for this character. Cache this controller.
            self._link_to_character()
        self.reconcile()
        return Decision(success=True, amount=self.value)

    def decrease(self, value: int) -> Decision:
        if not (rd := self.can_decrease(value)):
            return rd
        current = self.purchased_ranks
        self.purchased_ranks = current - value
        self.reconcile()
        return Decision.SUCCESS


class SkillController(CostsCharacterPointsController):
    definition: defs.SkillDef

    def __init__(self, full_id: str, character: TempestCharacter):
        super().__init__(full_id, character)
        if not isinstance(self.definition, defs.SkillDef):
            raise ValueError(
                f"Expected {full_id} to be a skill, but was {type(self.definition)}"
            )

    @property
    def purchased_ranks(self) -> int:
        # Unlike `value`, we don't care about whether this is an option skill.
        # Raw option skills never have purchases.
        return self.character.model.skills.get(self.full_id, 0)

    @purchased_ranks.setter
    def purchased_ranks(self, value):
        self.character.model.skills[self.full_id] = value


class PerkController(CostsCharacterPointsController):
    definition: defs.PerkDef

    def __init__(self, full_id: str, character: TempestCharacter):
        super().__init__(full_id, character)
        if not isinstance(self.definition, defs.PerkDef):
            raise ValueError(
                f"Expected {full_id} to be a skill, but was {type(self.definition)}"
            )

    @property
    def purchased_ranks(self) -> int:
        return self.character.model.perks.get(self.full_id, 0)

    @purchased_ranks.setter
    def purchased_ranks(self, value):
        self.character.model.perks[self.full_id] = value


class FlawController(FeatureController):
    definition: defs.FlawDef

    def __init__(self, full_id: str, character: TempestCharacter):
        super().__init__(full_id, character)
        if not isinstance(self.definition, defs.FlawDef):
            raise ValueError(
                f"Expected {full_id} to be a flaw, but was {type(self.definition)}"
            )

    @property
    def option(self) -> str | None:
        return self.expression.option

    @property
    def overcame(self) -> bool:
        if m := self.model:
            return m.overcame
        return False

    @overcame.setter
    def overcame(self, value: bool):
        if m := self.model:
            m.overcame = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def cp_awarded(self) -> bool:
        if m := self.model:
            return m.cp_awarded
        return False

    @cp_awarded.setter
    def cp_awarded(self, value: bool):
        if m := self.model:
            m.cp_awarded = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def removed(self) -> bool:
        if m := self.model:
            return m.removed
        return False

    @removed.setter
    def removed(self, value: bool):
        if m := self.model:
            m.removed = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def added_by_player(self) -> bool:
        if m := self.model:
            return m.added_by_player
        return False

    @added_by_player.setter
    def added_by_player(self, value: bool):
        if m := self.model:
            m.added_by_player = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def can_overcome(self) -> bool:
        if m := self.model:
            return m.can_overcome
        return False

    @can_overcome.setter
    def can_overcome(self, value: bool):
        if m := self.model:
            m.can_overcome = value
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @cached_property
    def award_options(self) -> dict[str, int] | None:
        if not isinstance(self.definition.award, dict):
            return None
        award_dict: dict[str, int] = {}
        flags_to_eval: dict[str, int] = {}
        for option, value in self.definition.award.items():
            if not option.startswith("$"):
                award_dict[option] = value
            else:
                flags_to_eval[option[1:]] = value
        for flag, value in flags_to_eval.items():
            for f in utils.maybe_iter(self.character.flags.get(flag, [])):
                if not isinstance(f, str):
                    f = str(f)
                # Negative flag. Remove from awards *if* it has the matching value.
                if f.startswith("-"):
                    f = f[1:]
                    if f in award_dict and award_dict[f] == value:
                        del award_dict[f]
                else:
                    award_dict[f] = value
        return award_dict

    @property
    def model(self) -> models.FlawModel | None:
        return self.character.model.flaws.get(self.id)

    @property
    def purchased_ranks(self) -> int:
        # No flaws currently have ranks, so we just check whether there's a model
        # for it and whether that model is "active" (not overcome or removed).
        if m := self.model:
            return int(not (m.overcame or m.removed))
        return 0

    @purchased_ranks.setter
    def purchased_ranks(self, value: int):
        if self.purchased_ranks == 0 and value > 0:
            self.character.model.flaws[self.id] = models.FlawModel()
        elif self.purchased_ranks > 0 and value <= 0:
            del self.character.model.flaws[self.id]

    @property
    def award_cp(self):
        """CP awarded for having the flaw.

        Zero if no CP was awarded for the flaw.
        """
        if m := self.model:
            if not m.cp_awarded:
                return 0
            return self.hypothetical_award_value
        return 0

    @property
    def overcome_cp(self):
        """CP spent in overcoming the flaw.

        Zero if not overcome.
        """
        if m := self.model:
            if m.overcame and not m.removed:
                return (
                    self.hypothetical_award_value + self.character.ruleset.flaw_overcome
                )
        return 0

    @property
    def hypothetical_award_value(self) -> int:
        """Amount of CP that would be awarded, assuming this flaw was taken at character creation."""
        award: int = 0
        if isinstance(self.definition.award, int):
            award = self.definition.award
        else:
            award = self.award_options.get(self.option, 0)
        # The award value can be modified if other features are present.
        if self.definition.award_mods:
            for flaw, mod in self.definition.award_mods.items():
                if self.character.get_prop(flaw) > 0:
                    award += mod
        return max(award, 0)

    def can_increase(self, value: int) -> Decision:
        # Players can't take flaws after character creation, except by asking plot.
        if not self.character.can_respend:
            return _NO_RESPEND
        return super().can_increase(value)

    def increase(self, value: int) -> Decision:
        if not (rd := self.can_increase(value)):
            return rd
        self.purchased_ranks = value
        self.reconcile()
        return Decision.SUCCESS

    def decrease(self, value: int) -> Decision:
        if not (rd := self.can_decrease(value)):
            return rd
        # TODO: Implement Overcome, here or by some other action.
        # For the moment, this is just the character creation action, which
        # drops the model entirely.
        del self.character.model.flaws[self.id]
        self.reconcile()
        return Decision.SUCCESS


class AttributeController(base_engine.AttributeController):
    character: TempestCharacter
    _granted_ranks: int = 0

    def __init__(self, prop_id: str, character: TempestCharacter):
        super().__init__(prop_id, character)

    def propagate(self, data: base_engine.PropagationData):
        self._granted_ranks += data.grants

    @property
    def value(self):
        return self._granted_ranks


class LifePointController(AttributeController):
    @property
    def value(self):
        return super().value + self.character.base_lp


class SumAttribute(AttributeController):
    """Represents an attribute that aggregates over particular types of features.

    For example, the "caster" attribute measures the number of levels of spellcasting
    classes the character has taken, usually for requirements specified like
    "At least 5 levels in spellcasting classes" (and written "caster:5" in definition files).
    The `max_value` field implements requirements like "At least 5 levels in a spellcasting class",

    """

    character: TempestCharacter
    _condition: str | None
    _feature_type: str

    def __init__(
        self,
        prop_id: str,
        character: TempestCharacter,
        feature_type: str,
        condition: str | None = None,
    ):
        super().__init__(prop_id, character)
        self._condition = condition
        self._feature_type = feature_type

    @property
    def value(self) -> int:
        total: int = super().value
        for fc in self.character.features[self._feature_type].values():
            if self._condition is None or getattr(fc, self._condition, True):
                total += fc.value
        return total

    @property
    def max_value(self) -> int:
        current: int = 0
        for fc in self.character.features[self._feature_type].values():
            if (self._condition is None or getattr(fc, self._condition, True)) and (
                v := fc.value
            ) > current:
                current = v
        return current


class CharacterPointController(AttributeController):
    character: TempestCharacter

    @property
    def value(self) -> int:
        base = self.character.awarded_cp + self.character.base_cp + super().value

        return base + self.flaw_award_cp - self.spent_cp

    @property
    def spent_cp(self) -> int:
        return self.skill_spent_cp + self.perk_spent_cp + self.flaw_overcome_cp

    @property
    def skill_spent_cp(self) -> int:
        spent: int = 0
        for skill in list(self.character.skills.values()):
            spent += skill.cp_cost
        return spent

    @property
    def perk_spent_cp(self) -> int:
        spent: int = 0
        for perk in list(self.character.perks.values()):
            spent += perk.cp_cost
        return spent

    @property
    def flaw_award_cp(self) -> int:
        total: int = 0
        for flaw in list(self.character.flaws.values()):
            total += flaw.award_cp
        return min(total, self.character.ruleset.flaw_cp_cap)

    @property
    def flaw_overcome_cp(self) -> int:
        total: int = 0
        for flaw in list(self.character.flaws.values()):
            total += flaw.overcome_cp
        return total


class TempestEngine(base_engine.Engine):
    ruleset: defs.Ruleset
    sheet_type = models.CharacterModel
    character_controller = TempestCharacter

    @cached_property
    def class_defs(self) -> dict[str, defs.ClassDef]:
        return {
            k: f for (k, f) in self.feature_defs.items() if isinstance(f, defs.ClassDef)
        }

    @cached_property
    def skill_defs(self) -> dict[str, defs.SkillDef]:
        return {
            k: f for (k, f) in self.feature_defs.items() if isinstance(f, defs.SkillDef)
        }
