from __future__ import annotations

from .. import defs
from . import _costs_cp_controller
from . import character_controller


class SkillController(_costs_cp_controller.CostsCharacterPointsController):
    definition: defs.SkillDef

    def __init__(self, full_id: str, character: character_controller.TempestCharacter):
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
