from __future__ import annotations

from functools import cached_property

from camp.engine import utils
from camp.engine.rules.decision import Decision

from .. import defs
from .. import models
from . import character_controller
from . import feature_controller

_NO_RESPEND = Decision(success=False, reason="Respend not currently available.")


class FlawController(feature_controller.FeatureController):
    definition: defs.FlawDef

    def __init__(self, full_id: str, character: character_controller.TempestCharacter):
        super().__init__(full_id, character)
        if not isinstance(self.definition, defs.FlawDef):
            raise ValueError(
                f"Expected {full_id} to be a flaw, but was {type(self.definition)}"
            )

    @property
    def option(self) -> str | None:
        return self.expression.option

    @property
    def overcame(self) -> bool:
        if m := self.model:
            return m.overcame
        return False

    @overcame.setter
    def overcame(self, value: bool):
        if m := self.model:
            m.overcame = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def cp_awarded(self) -> bool:
        if m := self.model:
            return m.cp_awarded
        return False

    @cp_awarded.setter
    def cp_awarded(self, value: bool):
        if m := self.model:
            m.cp_awarded = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def removed(self) -> bool:
        if m := self.model:
            return m.removed
        return False

    @removed.setter
    def removed(self, value: bool):
        if m := self.model:
            m.removed = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def added_by_player(self) -> bool:
        if m := self.model:
            return m.added_by_player
        return False

    @added_by_player.setter
    def added_by_player(self, value: bool):
        if m := self.model:
            m.added_by_player = value
            self.reconcile()
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

    @property
    def can_overcome(self) -> bool:
        if m := self.model:
            return m.can_overcome
        return False

    @can_overcome.setter
    def can_overcome(self, value: bool):
        if m := self.model:
            m.can_overcome = value
        else:
            raise ValueError(f"Can't set update {self.full_id} - flaw not present")

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
    def model(self) -> models.FlawModel | None:
        return self.character.model.flaws.get(self.id)

    @property
    def purchased_ranks(self) -> int:
        # No flaws currently have ranks, so we just check whether there's a model
        # for it and whether that model is "active" (not overcome or removed).
        if m := self.model:
            return int(not (m.overcame or m.removed))
        return 0

    @purchased_ranks.setter
    def purchased_ranks(self, value: int):
        if self.purchased_ranks == 0 and value > 0:
            self.character.model.flaws[self.id] = models.FlawModel()
        elif self.purchased_ranks > 0 and value <= 0:
            del self.character.model.flaws[self.id]

    @property
    def award_cp(self):
        """CP awarded for having the flaw.

        Zero if no CP was awarded for the flaw.
        """
        if m := self.model:
            if not m.cp_awarded:
                return 0
            return self.hypothetical_award_value
        return 0

    @property
    def overcome_cp(self):
        """CP spent in overcoming the flaw.

        Zero if not overcome.
        """
        if m := self.model:
            if m.overcame and not m.removed:
                return (
                    self.hypothetical_award_value + self.character.ruleset.flaw_overcome
                )
        return 0

    @property
    def hypothetical_award_value(self) -> int:
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
        return max(award, 0)

    def can_increase(self, value: int) -> Decision:
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

    def decrease(self, value: int) -> Decision:
        if not (rd := self.can_decrease(value)):
            return rd
        # TODO: Implement Overcome, here or by some other action.
        # For the moment, this is just the character creation action, which
        # drops the model entirely.
        del self.character.model.flaws[self.id]
        self.reconcile()
        return Decision.SUCCESS
