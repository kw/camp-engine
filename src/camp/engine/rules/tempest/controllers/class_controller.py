from __future__ import annotations

from camp.engine.rules.decision import Decision

from .. import defs
from . import character_controller
from . import feature_controller

_MUST_BE_POSITIVE = Decision(success=False, reason="Value must be positive.")


class ClassController(feature_controller.FeatureController):
    definition: defs.ClassDef

    def __init__(self, id: str, character: character_controller.TempestCharacter):
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
