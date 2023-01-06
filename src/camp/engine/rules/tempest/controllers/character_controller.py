from __future__ import annotations

from functools import cached_property
from typing import Mapping

from camp.engine import utils
from camp.engine.rules import base_engine
from camp.engine.rules.base_models import PropExpression
from camp.engine.rules.base_models import Purchase
from camp.engine.rules.decision import Decision

from .. import defs
from .. import engine  # noqa: F401
from .. import models
from . import attribute_controllers
from . import class_controller
from . import feature_controller
from . import flaw_controller
from . import perk_controller
from . import skill_controller


class TempestCharacter(base_engine.CharacterController):
    model: models.CharacterModel
    engine: engine.TempestEngine
    ruleset: defs.Ruleset
    _classes: dict[str, class_controller.ClassController] | None = None
    _skills: dict[str, skill_controller.SkillController] | None = None
    _perks: dict[str, perk_controller.PerkController] | None = None
    _flaws: dict[str, flaw_controller.FlawController] | None = None

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
    def lp(self) -> attribute_controllers.LifePointController:
        return attribute_controllers.LifePointController("lp", self)

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
    def cp(self) -> attribute_controllers.CharacterPointController:
        return attribute_controllers.CharacterPointController("cp", self)

    @cached_property
    def level(self) -> attribute_controllers.SumAttribute:
        return attribute_controllers.SumAttribute("level", self, "class")

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
    def classes(self) -> dict[str, class_controller.ClassController]:
        """Dict of the character's class controllers.

        The primary class will be first in iteration order.
        """
        if self._classes:
            return self._classes
        classes: dict[str, class_controller.ClassController] = {}
        primary = self.model.primary_class
        if primary:
            classes[primary] = class_controller.ClassController(primary, self)

        for id in self.model.classes:
            if id == primary:
                # Already added.
                continue
            classes[id] = class_controller.ClassController(id, self)
        self._classes = classes
        return classes

    @property
    def skills(self) -> dict[str, skill_controller.SkillController]:
        if self._skills:
            return self._skills
        skills: dict[str, skill_controller.SkillController] = {}
        for id in self.model.skills:
            skills[id] = skill_controller.SkillController(id, self)
        self._skills = skills
        return skills

    @property
    def perks(self) -> dict[str, perk_controller.PerkController]:
        if self._perks:
            return self._perks
        perks: dict[str, perk_controller.PerkController] = {}
        for id in self.model.perks:
            perks[id] = perk_controller.PerkController(id, self)
        self._perks = perks
        return perks

    @property
    def flaws(self) -> dict[str, flaw_controller.FlawController]:
        if self._flaws:
            return self._flaws
        flaws: dict[str, flaw_controller.FlawController] = {}
        for id in self.model.flaws:
            flaws[id] = flaw_controller.FlawController(id, self)
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
    def features(
        self,
    ) -> Mapping[str, Mapping[str, feature_controller.FeatureController]]:
        return {
            "class": self.classes,
            "skill": self.skills,
            "perk": self.perks,
            "flaw": self.flaws,
        }

    @cached_property
    def martial(self) -> base_engine.AttributeController:
        return attribute_controllers.SumAttribute("martial", self, "class", "martial")

    @cached_property
    def caster(self) -> base_engine.AttributeController:
        return attribute_controllers.SumAttribute("caster", self, "class", "caster")

    @cached_property
    def arcane(self) -> base_engine.AttributeController:
        return attribute_controllers.SumAttribute("arcane", self, "class", "arcane")

    @cached_property
    def divine(self) -> base_engine.AttributeController:
        return attribute_controllers.SumAttribute("divine", self, "class", "divine")

    def _controller_for_type(
        self, feature_type: str, id: str
    ) -> feature_controller.FeatureController:
        match feature_type:
            case "class":
                return class_controller.ClassController(id, self)
            case "skill":
                return skill_controller.SkillController(id, self)
            case "flaw":
                return flaw_controller.FlawController(id, self)
            case "perk":
                return perk_controller.PerkController(id, self)
        raise NotImplementedError(
            f"Unknown feature controller {feature_type} for feature {id}"
        )

    def _controller_for_feature(
        self, expr: PropExpression | str, create: bool = True
    ) -> feature_controller.FeatureController | None:
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
