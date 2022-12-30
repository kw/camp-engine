from __future__ import annotations

import math
from abc import abstractmethod
from abc import abstractproperty
from functools import cached_property
from typing import Mapping

from camp.engine import utils

from .. import base_engine
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
    def cp(self) -> base_engine.AttributeController:
        return CharacterPointController("cp", self)

    @cached_property
    def level(self) -> base_engine.AttributeController:
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

    def clear_caches(self):
        super().clear_caches()
        self._classes = {}
        self._skills = {}


class FeatureController(base_engine.FeatureController):
    character: TempestCharacter
    definition: defs.BaseFeatureDef
    expression: PropExpression
    full_id: str
    _effective_ranks: int | None
    _granted_ranks: int

    def __init__(self, full_id: str, character: TempestCharacter):
        self.expression = PropExpression.parse(full_id)
        self.full_id = full_id
        super().__init__(self.expression.prop, character)
        self.definition = character.ruleset.features[self.id]
        self._effective_ranks = None
        self._granted_ranks = 0

    @abstractproperty
    def purchased_ranks(self) -> int:
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
        max_ranks = self.definition.max_ranks
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
        if self._effective_ranks is None:
            self.reconcile()
        return self._effective_ranks

    @abstractmethod
    def _link_to_character(self):
        ...

    def update_grants(self, delta: int) -> None:
        self._granted_ranks += delta
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
            self._granted_ranks + self.purchased_ranks, self.definition.max_ranks
        )

        if previous_ranks <= 0 and self._effective_ranks > 0:
            # The feature has been gained. All feature definitions have a `grants` field
            # that should be distributed whenever the feature is gained, regardless of how
            # many ranks are involved.
            self._link_to_character()
            if self.definition.grants:
                self._distribute_grants(self.definition.grants)
        if previous_ranks > 0 and self._effective_ranks <= 0 and self.definition.grants:
            self._revoke_grants(self.definition.grants)
        elif previous_ranks < self._effective_ranks:
            # The feature has increased but not been removed.
            # Most features do not support varying levels of grants,
            # so nothing happens most of the time.
            pass
        elif previous_ranks > self._effective_ranks:
            # The feature has decreased but not been removed.
            # Most features do not support varying levels of grants,
            # so nothing happens most of the time.
            pass

    def _distribute_grants(self, grants: defs.Grantable):
        if isinstance(grants, str):
            expr = PropExpression.parse(grants)
            if controller := self.character._controller_for_feature(expr):
                controller.update_grants(expr.value or 1)
        elif isinstance(grants, list):
            for grant in grants:
                self._distribute_grants(grant)
        elif isinstance(grants, dict):
            for id, value in grants.items():
                if controller := self.character._controller_for_feature(id):
                    controller.update_grants(value)
        else:
            raise NotImplementedError(f"Unexpected grant value: {grants}")

    def _revoke_grants(self, grants: defs.Grantable):
        if isinstance(grants, str):
            expr = PropExpression.parse(grants)
            if controller := self.character._controller_for_feature(expr):
                value = expr.value or 1
                controller.update_grants(-value)
        elif isinstance(grants, list):
            for grant in grants:
                self._revoke_grants(grant)
        elif isinstance(grants, dict):
            for id, value in grants.items():
                if controller := self.character._controller_for_feature(id):
                    controller.update_grants(-value)
        else:
            raise NotImplementedError(f"Unexpected grant value: {grants}")


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
        if value <= 0:
            return _MUST_BE_POSITIVE
        character_available = self.character.levels_available
        class_available = self.definition.max_ranks - self.value
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
        if not self.character.can_respend:
            return _NO_RESPEND
        if value <= 0:
            return _MUST_BE_POSITIVE
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

    def _link_to_character(self):
        self.character._classes[self.id] = self


class SkillController(FeatureController):
    definition: defs.SkillDef

    def __init__(self, full_id: str, character: TempestCharacter):
        super().__init__(full_id, character)
        if not isinstance(self.definition, defs.SkillDef):
            raise ValueError(
                f"Expected {full_id} to be a skill, but was {type(self.definition)}"
            )

    @property
    def option(self) -> str | None:
        return self.expression.option

    @property
    def is_option_skill(self) -> bool:
        return self.definition.option is not None

    @property
    def purchased_ranks(self) -> int:
        # Unlike `value`, we don't care about whether this is an option skill.
        # Raw option skills never have purchases.
        return self.character.model.skills.get(self.full_id, 0)

    @purchased_ranks.setter
    def purchased_ranks(self, value):
        self.character.model.skills[self.full_id] = value

    @property
    def value(self) -> int:
        if self.is_option_skill and not self.option:
            # This is an aggregate controller for the skill.
            # Sum any ranks the character has in instances of it.
            total: int = 0
            for skill in self.character.model.skills:
                if skill.startswith(f"{self.id}#"):
                    # Note that we don't need to iterate over the keys in the
                    # grants dictionary. If a grant is provided for a skill with
                    # no ranks, we always add a 0 entry to the 'skills' dict for it
                    # so that it always represents the skills on the sheet.
                    if controller := self.character._controller_for_feature(
                        PropExpression.parse(skill)
                    ):
                        total += controller.value
            return total
        return super().value

    @property
    def max_value(self) -> int:
        if self.is_option_skill and not self.option:
            # This is an aggregate controller for the skill.
            # Return the value of the highest instance.
            current: int = 0
            for skill in self.character.model.skills:
                if skill.startswith(f"{self.id}#"):
                    # Note that we don't need to iterate over the keys in the
                    # grants dictionary. If a grant is provided for a skill with
                    # no ranks, we always add a 0 entry to the 'skills' dict for it
                    # so that it always represents the skills on the sheet.
                    if controller := self.character._controller_for_feature(skill):
                        new_value = controller.value
                        if new_value > current:
                            current = new_value
            return current
        return super().max_value

    @property
    def taken_options(self) -> dict[str, int]:
        options = {}
        for controller in self.character.skills.values():
            if controller.id == self.id and controller.option:
                options[controller.option] = controller.value
        return options

    @property
    def cp_cost(self) -> int:
        return self.cost_for(self.paid_ranks)

    def cost_for(self, ranks: int) -> int:
        match self.definition.cost:
            case int():
                return self.definition.cost * ranks
            case defs.CostByRank():
                return self.definition.cost.total_cost(ranks)
            case _:
                raise NotImplementedError(
                    f"Don't know how to compute cost with {self.definition.cost}"
                )

    def max_rank_increase(self, available_cp: int = -1) -> int:
        if available_cp < 0:
            available_cp = self.character.cp.value
        available_ranks = self.definition.max_ranks - self.value
        current_cost = self.cp_cost
        if available_ranks < 1:
            return 0
        match self.definition.cost:
            case int():
                # Relatively trivial case
                return math.floor(available_cp / self.definition.cost)
            case defs.CostByRank():
                while available_ranks > 0:
                    cp_delta = (
                        self.cost_for(self.paid_ranks + available_ranks) - current_cost
                    )
                    if cp_delta <= available_cp:
                        return available_ranks
                    available_ranks -= 1
                return 0
            case None:
                return available_ranks
            case _:
                raise NotImplementedError(
                    f"Don't know how to compute cost with {self.definition.cost}"
                )

    def can_increase(self, value: int) -> Decision:
        if value <= 0:
            return _MUST_BE_POSITIVE
        current = self.value
        if current >= self.definition.max_ranks:
            return Decision(success=False)
        # Is the purchase within defined range?
        if (current + value) > self.definition.max_ranks:
            max_increase = self.definition.max_ranks - current
            return Decision(
                success=False,
                reason=f"Max is {self.definition.max_ranks}, so can't increase to {current + value}",
                amount=max_increase,
            )
        # Does the character meet the prerequisites?
        if not (rd := self.character.meets_requirements(self.definition.requires)):
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
        # Is this an option skill without an option specified?
        if self.is_option_skill and not self.option:
            return Decision(success=False, needs_option=True)
        elif (
            self.is_option_skill
            and self.option
            and not self.definition.option.freeform
            and current == 0
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
        if not self.is_option_skill and self.option:
            return Decision(
                success=False, reason=f"Skill {self.id} does not accept options."
            )
        return Decision.SUCCESS

    def increase(self, value: int) -> Decision:
        if not (rd := self.can_increase(value)):
            return rd
        current = self.purchased_ranks
        self.purchased_ranks = current + value
        if current == 0:
            # This is a new skill for this character. Cache this controller.
            self._link_to_character()
        self.reconcile()
        return Decision(success=True, amount=self.value)

    def can_decrease(self, value: int) -> Decision:
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

    def decrease(self, value: int) -> Decision:
        if not (rd := self.can_decrease(value)):
            return rd
        current = self.purchased_ranks
        self.purchased_ranks = current - value
        self.reconcile()
        return Decision.SUCCESS

    def _link_to_character(self):
        self.character._skills[self.full_id] = self


class SumAttribute(base_engine.AttributeController):
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
        total: int = 0
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


class CharacterPointController(base_engine.AttributeController):
    character: TempestCharacter

    @property
    def value(self) -> int:
        base = self.character.awarded_cp + self.character.base_cp
        spent: int = 0
        flaw_cp: int = 0

        for skill in self.character.skills.values():
            spent += skill.cp_cost
        return base + flaw_cp - spent


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
