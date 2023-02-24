from __future__ import annotations

from camp.engine.rules.decision import Decision

from .. import defs
from .. import models
from . import character_controller
from . import feature_controller

_MUST_BE_POSITIVE = Decision(success=False, reason="Value must be positive.")


class ClassController(feature_controller.FeatureController):
    definition: defs.ClassDef
    model_type = models.ClassModel
    model: models.ClassModel

    def __init__(self, id: str, character: character_controller.TempestCharacter):
        super().__init__(id, character)
        if not isinstance(self.definition, defs.ClassDef):
            raise ValueError(
                f"Expected {id} to be a class, but was {type(self.definition)}"
            )

    @property
    def is_primary(self) -> bool:
        return self.model.primary

    @is_primary.setter
    def is_primary(self, value: bool) -> None:
        self.model.primary = value
        if value:
            # There can be only one primary class
            for id, controller in self.character.classes.items():
                if id != self.full_id:
                    controller.is_primary = False

    @property
    def is_starting(self) -> bool:
        return self.model.starting

    @is_starting.setter
    def is_starting(self, value: bool) -> None:
        self.model.starting = value
        if value:
            # There can be only one starting class
            for id, controller in self.character.classes.items():
                if id != self.full_id:
                    controller.is_starting = False

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

    def can_increase(self, value: int = 1) -> Decision:
        if not (rd := super().can_increase(value)):
            return rd
        character_available = self.character.levels_available
        available = min(character_available, self.purchaseable_ranks)
        return Decision(success=available >= value, amount=available)

    def increase(self, value: int) -> Decision:
        if self.character.level == 0 and value < 2:
            # This is the character's first class. Ensure at least 2 ranks are purchased.
            value = 2
        if not (rd := super().increase(value)):
            return rd
        if (
            not self.is_primary
            and max((c.value for c in self.character.classes.values()), default=0)
            < self.purchased_ranks
        ):
            self.is_primary = True
        if self.character.starting_class is None:
            self.is_starting = True
        self.reconcile()
        return rd

    def can_decrease(self, value: int = 1) -> Decision:
        if not (rd := super().can_decrease(value)):
            return rd
        current = self.purchased_ranks
        # If this is the starting class, it can't be reduced below level 2
        # unless it's the only class on the sheet.
        if self.is_starting and current != self.character.level.value:
            if current - value < 2:
                return Decision(
                    success=False,
                    amount=(current - 2),
                    reason="Can't reduce starting class levels below 2 while multiclassed.",
                )
        return Decision(success=current >= value, amount=current)

    def decrease(self, value: int) -> Decision:
        current = self.purchased_ranks
        if self.is_starting and current - value < 2:
            # The starting class can't be reduced to level 1, only removed entirely.
            value = current
        if not (rd := super().decrease(value)):
            return rd
        if self.model.ranks <= 0:
            self.model.starting = False
            self.model.primary = False
        if (
            self.is_primary
            and max((c.value for c in self.character.classes.values()), default=0)
            > self.purchased_ranks
        ):
            # TODO: Auto-set to the new highest
            pass
        self.reconcile()
        return Decision(success=True, amount=self.value)
