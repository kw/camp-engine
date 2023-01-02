from __future__ import annotations

from pydantic import Field

from .. import base_models


class FlawModel(base_models.BaseModel):
    """Data needed to model a flaw on a character sheet.

    There are a few journeys to consider:

    1. Player selects flaws at character creation and receives Award CP for them.
       Later, the player chooses to overcome the flaw for Award CP + 2. Alternatively,
       staff may remove the flaw for plot reasons at no cost, while keeping the initial
       award.
    2. Staff impose a flaw on a character for plot reasons. No CP are awarded.
       Staff allow the flaw to be overcome for the normal overcome price if the
       player desires, or removed upon completion of a quest.
    3. The player requests that staff add a particular flaw. Staff add the flaw and
       award the flaw CP, assuming the character hasn't exceeded their bonus CP quota.
    4. The player adds a flaw during character creation, but removes it later during character
       creation. For this, we just delete the flaw model.

    Like skills, flaws can have an option attached, but it can stay in the dictionary key.
    They might also have a description, such as for an Honor Debt (though it should be
    explained at more length in a backstory).

    We should be able to cover this with the following fields.
    """

    description: str | None = None
    added_by_player: bool
    cp_awarded: bool
    can_overcome: bool = True
    overcame: bool = False
    removed: bool = False


class CharacterModel(base_models.CharacterModel):
    primary_class: str | None = None
    starting_class: str | None = None
    classes: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    flaws: dict[str, FlawModel] = Field(default_factory=dict)
