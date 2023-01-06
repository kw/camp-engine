from __future__ import annotations

from .. import defs
from . import _costs_cp_controller
from . import character_controller


class PerkController(_costs_cp_controller.CostsCharacterPointsController):
    definition: defs.PerkDef

    def __init__(self, full_id: str, character: character_controller.TempestCharacter):
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
