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

    Attributes:
      added_by_player: True if the player intentionally added it. False if plot added it
         for plot reasons. If plot adds it at the player's request, it's reasonable to set
         it to True. Either way, there's no mechanical effect, it's just for record keeping.
      cp_awarded: True if the PC gets CP for this (but not over the flaw cap). Usually
         only true if the player added it, but plot-granted flaws could also, I guess?
      can_overcome: The player can choose to overcome the flaw at a cost. The flaw CP are lost,
         and the player pays an additional 2 CP for this privilege.
      overcame: True if the player has paid the overcome price. The model must remain to
         represent the CP expenditure.
      removed: True if plot has deactivated this flaw. Similar to overcome, but the player
         doesn't pay anything, and (unless plot toggles cp_awarded) the granted CP remains.
    """

    added_by_player: bool = True
    cp_awarded: bool = True
    can_overcome: bool = True
    overcame: bool = False
    removed: bool = False


class CharacterModel(base_models.CharacterModel):
    primary_class: str | None = None
    starting_class: str | None = None
    classes: dict[str, int] = Field(default_factory=dict)
    skills: dict[str, int] = Field(default_factory=dict)
    flaws: dict[str, FlawModel] = Field(default_factory=dict)
