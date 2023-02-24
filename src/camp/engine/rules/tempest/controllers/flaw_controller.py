from __future__ import annotations

from functools import cached_property

from camp.engine import utils
from camp.engine.rules.decision import Decision

from .. import defs
from .. import models
from . import character_controller
from . import feature_controller

_NO_RESPEND = Decision(success=False, reason="Respend not currently available.")
_NO_OVERCOME = Decision(
    success=False, reason="Plot is preventing this flaw from being overcome."
)
_ALREADY_OVERCOME = Decision(success=False)


class FlawController(feature_controller.FeatureController):
    definition: defs.FlawDef
    model_type = models.FlawModel
    model: models.FlawModel

    def __init__(self, full_id: str, character: character_controller.TempestCharacter):
        super().__init__(full_id, character)
        if not isinstance(self.definition, defs.FlawDef):
            raise ValueError(
                f"Expected {full_id} to be a flaw, but was {type(self.definition)}"
            )

    @property
    def value(self) -> int:
        if self.model.overcome:
            return 0
        return super().value

    @cached_property
    def award_options(self) -> dict[str, int] | None:
        if not isinstance(self.definition.award, dict):
            return None
        award_dict: dict[str, int] = {}
        flags_to_eval: dict[str, int] = {}
        for option, value in self.definition.award.items():
            if not option.startswith("$"):
                award_dict[option] = value
            else:
                flags_to_eval[option[1:]] = value
        for flag, value in flags_to_eval.items():
            for f in utils.maybe_iter(self.character.flags.get(flag, [])):
                if not isinstance(f, str):
                    f = str(f)
                # Negative flag. Remove from awards *if* it has the matching value.
                if f.startswith("-"):
                    f = f[1:]
                    if f in award_dict and award_dict[f] == value:
                        del award_dict[f]
                else:
                    award_dict[f] = value
        return award_dict

    @property
    def award_cp(self):
        """CP awarded for having the flaw.

        Zero if no CP was awarded for the flaw.
        """
        if self.model.plot_free:
            return 0
        return self._award_value

    @property
    def overcome(self) -> bool:
        return self.model.overcome

    @overcome.setter
    def overcome(self, value: bool) -> None:
        self.model.overcome = value

    @property
    def overcome_disabled(self):
        return self.model.plot_disable_overcome

    @overcome_disabled.setter
    def overcome_disabled(self, value: bool):
        self.model.plot_disable_overcome = value

    @property
    def overcome_cp(self):
        """CP spent in overcoming the flaw.

        Zero if not overcome.
        """
        if self.model.overcome:
            return self._overcome_value
        return 0

    @property
    def _overcome_value(self) -> int:
        if self.model.overcome_award_override is not None:
            award = self.model.overcome_award_override
        else:
            award = self._award_value
        return award + self.character.ruleset.flaw_overcome

    @property
    def _award_value(self) -> int:
        """Amount of CP that would be awarded, assuming this flaw was taken at character creation."""
        award: int = 0
        if isinstance(self.definition.award, int):
            award = self.definition.award
        else:
            award = self.award_options.get(self.option, 0)
        # The award value can be modified if other features are present.
        if self.definition.award_mods:
            for flaw, mod in self.definition.award_mods.items():
                if self.character.get_prop(flaw) > 0:
                    award += mod
        return max(award * self.paid_ranks, 0)

    def can_increase(self, value: int = 1) -> Decision:
        # Players can't take flaws after character creation, except by asking plot.
        if not self.character.can_respend:
            return _NO_RESPEND
        return super().can_increase(value)

    def increase(self, value: int) -> Decision:
        if not (rd := self.can_increase(value)):
            return rd
        self.purchased_ranks = value
        self.reconcile()
        return Decision.SUCCESS

    def can_decrease(self, value: int = 1) -> Decision:
        rd = super().can_decrease(value)
        if self.model.overcome:
            # If a flaw has been overcome, it can't be further removed.
            return _ALREADY_OVERCOME
        elif not rd:
            # If the superclass says it can't be removed, it probably can't be.
            return rd
        elif self.character.can_respend:
            # If the character is in respend mode, anything can be removed.
            return rd
        elif self.model.plot_disable_overcome:
            # Plot can block overcome, generally for things they add.
            return _NO_OVERCOME
        # If nothing else is blocking overcome it's just a matter of checking if you have the CP for it.
        current_cp = self.character.cp
        cp_delta = self._overcome_value
        if cp_delta < current_cp:
            return Decision(
                success=False,
                reason=f"Need {cp_delta} CP to overcome, but only have {current_cp}",
            )
        return Decision.SUCCESS

    def decrease(self, value: int) -> Decision:
        if not (rd := self.can_decrease(value)):
            return rd
        if self.character.can_respend:
            return super().decrease(value)
        else:
            # We don't remove the model, just mark it overcome.
            self.model.overcome = True
        self.reconcile()
        return Decision.SUCCESS
