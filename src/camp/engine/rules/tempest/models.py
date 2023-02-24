from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import base_models


class FeatureModel(base_models.BaseModel):
    """Data needed to model a generic feature on a character sheet.

    Attributes:
        type: Set to the type of power (as per the feature definition's type). If a model
            subclass specifies a specific type literal (see FlawModel), that subclass model
            will be loaded instead.
        ranks: Number of ranks purchased. Occasionally, a power with 0 ranks will need to be
            recorded. Typically this happens if the character has a power that grants ranks
            in another power, _and_ something else about it needs to be recorded (like a Notes field
            or a choice).
        notes: Notes about this feature added by the player.
        choices: If this power has choices, what has been chosen?
        plot_added: Marks this power as added by plot. In some cases, sheet mechanics may vary slightly
            depending on whether plot forcibly added it.
        plot_notes: Notes about this feature added by plot. Not shown to players.
        plot_free: If true and this power comes with a cost or award (in CP or BP) then it does
            not apply here. Generally used when plot wants to grant a flaw, perk, role, etc
            as a reward or punishment.
        plot_suppressed: The power is marked off on the character sheet and no longer functions.
            This usually only happens with Patron (and perks obtained from it) and Religions.
            Powers may appear suppressed for other reasons (for example, if one of their prerequisites
            becomes suppressed or otherwise removed).
    """

    type: str
    ranks: int = 0
    notes: str | None = None
    choices: dict[str, list[str]] | None = None
    plot_added: bool = False
    plot_notes: str | None = None
    plot_free: bool = False
    plot_suppressed: bool = False

    def should_keep(self) -> bool:
        """Should return True if the model has been populated with something worth saving."""
        return bool(
            self.ranks
            or self.notes
            or self.choices
            or self.plot_added
            or self.plot_notes
            or self.plot_free
        )


class FlawModel(FeatureModel):
    """
    Flaws need extra state for their overcome status and extra flags for plot override behavior.

    Attributes:
        overcome: Records whether the flaw has been overcome. The price is usually the
            original award price +2, but see overcome_award_override.
        plot_disable_overcome: Plot may prevent a flaw from being overcome. Usually this happens
            when the flaw is added as a penalty by plot that must be resolved through gameplay.
        overcome_award_override: Used when plot wants to change the cost of overriding a flaw.
            If the flaw was added by plot
    """

    type: Literal["flaw"] = "flaw"
    overcome: bool = False
    plot_disable_overcome: bool = False
    overcome_award_override: int | None = None

    def should_keep(self) -> bool:
        return (
            super().should_keep()
            or self.overcome
            or self.plot_disable_overcome
            or self.overcome_award_override is not None
        )


class ClassModel(FeatureModel):
    type: Literal["class"] = "class"
    primary: bool = False
    starting: bool = False

    def should_keep(self) -> bool:
        return super().should_keep() or self.primary or self.starting


# Subclass models must be added here ahead of FeatureModel to deserialize properly.
FeatureModelTypes = ClassModel | FlawModel | FeatureModel


class CharacterModel(base_models.CharacterModel):
    features: dict[str, FeatureModelTypes] = Field(default_factory=dict)
