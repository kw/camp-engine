from __future__ import annotations

import math

from camp.engine.rules.decision import Decision

from .. import defs
from . import feature_controller


class CostsCharacterPointsController(feature_controller.FeatureController):
    @property
    def cost_def(self) -> defs.CostDef:
        if not hasattr(self.definition, "cost"):
            raise NotImplementedError(f"{self} does not have a cost definition.")
        return self.definition.cost

    @property
    def cp_cost(self) -> int:
        return self.cost_for(self.paid_ranks)

    def cost_for(self, ranks: int) -> int:
        cd = self.cost_def
        if isinstance(cd, int):
            cd = max(cd - self._discount, 1)
            return cd * ranks
        elif isinstance(cd, defs.CostByRank):
            return cd.total_cost(ranks, discount=self._discount)
        else:
            raise NotImplementedError(f"Don't know how to compute cost with {cd}")

    def max_rank_increase(self, available_cp: int = -1) -> int:
        if available_cp < 0:
            available_cp = self.character.cp.value
        available_ranks = self.max_ranks - self.value
        current_cost = self.cp_cost
        if available_ranks < 1:
            return 0
        match cd := self.cost_def:
            case int():
                # Relatively trivial case
                return min(available_ranks, math.floor(available_cp / cd))
            case defs.CostByRank():
                while available_ranks > 0:
                    cp_delta = (
                        self.cost_for(self.paid_ranks + available_ranks) - current_cost
                    )
                    if cp_delta <= available_cp:
                        return available_ranks
                    available_ranks -= 1
                return 0
            case _:
                raise NotImplementedError(f"Don't know how to compute cost with {cd}")

    def can_increase(self, value: int) -> Decision:
        if not (rd := super().can_increase(value)):
            return rd
        # Can the character afford the purchase?
        current_cp = self.character.cp
        cp_delta = self.cost_for(self.paid_ranks + value) - self.cp_cost
        if current_cp < cp_delta:
            return Decision(
                success=False,
                reason=f"Need {cp_delta} CP to purchase, but only have {current_cp}",
                amount=self.max_rank_increase(current_cp.value),
            )
        return Decision.SUCCESS

    def increase(self, value: int) -> Decision:
        if not (rd := self.can_increase(value)):
            return rd
        current = self.purchased_ranks
        self.purchased_ranks = current + value
        if current == 0:
            # This is a new feature for this character. Cache this controller.
            self._link_to_character()
        self.reconcile()
        return Decision(success=True, amount=self.value)

    def decrease(self, value: int) -> Decision:
        if not (rd := self.can_decrease(value)):
            return rd
        current = self.purchased_ranks
        self.purchased_ranks = current - value
        self.reconcile()
        return Decision.SUCCESS
