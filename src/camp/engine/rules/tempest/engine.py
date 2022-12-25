from __future__ import annotations

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

    @property
    def xp(self) -> int:
        """Experience points"""
        return self.model.metadata.currencies.get("xp", 0)

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

    @property
    def base_cp(self) -> int:
        return self.model.metadata.currencies["cp"] + 2 * self.xp_level

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
    def level(self) -> base_engine.AttributeController:
        return SumAttribute("level", self, "class")

    @property
    def levels_available(self) -> int:
        return self.xp_level - self.level.value

    @property
    def classes(self) -> dict[str, ClassController]:
        """Dict of the character's class controllers.

        The primary class will be first in iteration order.
        """
        classes: dict[str, ClassController] = {}
        primary = self.model.primary_class
        if primary:
            classes[primary] = ClassController(primary, self)

        for id in self.model.classes:
            if id == primary:
                # Already added.
                continue
            classes[id] = ClassController(id, self)
        return classes

    def can_purchase(self, entry: Purchase | str) -> Decision:
        if not isinstance(entry, Purchase):
            entry = Purchase.parse(entry)
        if controller := self._controller_for_feature(entry.expression, create=True):
            return controller.can_increase(entry.ranks)
        return Decision(success=False, reason=f"Not implemented: {entry.expression}")

    def purchase(self, entry: Purchase | str) -> Decision:
        if not isinstance(entry, Purchase):
            entry = Purchase.parse(entry)
        if not isinstance(entry, Purchase):
            entry = Purchase.parse(entry)
        if controller := self._controller_for_feature(entry.expression, create=True):
            return controller.increase(entry.ranks)
        return Decision(success=False, reason=f"Not implemented: {entry.expression}")

    def has_prop(self, expr: str | PropExpression) -> bool:
        """Check whether the character has _any_ property (feature, attribute, etc) with the given name.

        The base implementation only knows how to check for attributes. Checking for features
        must be added by implementations.
        """
        expr = PropExpression.parse(expr)
        if self._controller_for_feature(expr):
            return True
        return super().has_prop(expr)

    def get_prop(self, expr: str | PropExpression) -> int:
        expr = PropExpression.parse(expr)
        if controller := self._controller_for_feature(expr):
            return controller.value
        return super().get_prop(expr)

    @property
    def features(self) -> Mapping[str, Mapping[str, base_engine.FeatureController]]:
        return {"class": self.classes}

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

    def _controller_for_type(
        self, feature_type: str, id: str
    ) -> base_engine.FeatureController:
        match feature_type:
            case "class":
                return ClassController(id, self)
        raise NotImplementedError(
            f"Unknown feature controller {feature_type} for feature {id}"
        )

    def _controller_for_feature(
        self, expr: PropExpression, create: bool = False
    ) -> base_engine.FeatureController | None:
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


class ClassController(base_engine.FeatureController):
    character: TempestCharacter
    definition: defs.ClassDef

    def __init__(self, id: str, character: TempestCharacter):
        super().__init__(id, character)
        self.definition = character.ruleset.features[id]
        if not isinstance(self.definition, defs.ClassDef):
            raise ValueError(
                f"Expected {id} to be a class, but was {type(self.definition)}"
            )

    @property
    def primary(self) -> bool:
        return self.character.model.primary_class == self.id

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
    def value(self) -> int:
        return self.character.model.classes.get(self.id, 0)

    def can_increase(self, value: int = 1) -> Decision:
        character_available = self.character.levels_available
        class_available = self.definition.max_ranks - self.value
        available = min(character_available, class_available)
        return Decision(success=available >= value, amount=available)

    def increase(self, value: int) -> Decision:
        if value <= 0:
            return _MUST_BE_POSITIVE
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
        self.character.clear_caches()
        return Decision(success=True, amount=self.value)

    def can_decrease(self, value: int = 1) -> Decision:
        if not self.character.can_respend:
            return _NO_RESPEND
        current = self.character.model.classes[self.id]
        return Decision(success=current >= value, amount=current)

    def decrease(self, value: int) -> Decision:
        if value <= 0:
            return _MUST_BE_POSITIVE
        if not (rd := self.can_decrease(value)):
            rd.success = False
            return rd
        current = self.value
        new_value = current - value
        if new_value > 0:
            self.character.model.classes[self.id] = new_value
        else:
            del self.character.model.classes[self.id]
        if (
            self.primary
            and max(self.character.model.classes.values(), default=0) < new_value
        ):
            self.character.model.primary_class = None
        self.character.clear_caches()
        # Determine if we can easily reverse a level gain in the model's grants cache.
        # Otherwise, clear the grants cache.
        return Decision(success=True, amount=self.value)


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
