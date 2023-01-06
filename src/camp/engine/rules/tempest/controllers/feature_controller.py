from __future__ import annotations

from abc import abstractproperty
from functools import cached_property
from typing import Iterable

from camp.engine.rules import base_engine
from camp.engine.rules.base_models import OptionDef
from camp.engine.rules.base_models import PropExpression
from camp.engine.rules.decision import Decision

from .. import defs
from . import character_controller

_MUST_BE_POSITIVE = Decision(success=False, reason="Value must be positive.")
_NO_RESPEND = Decision(success=False, reason="Respend not currently available.")


class FeatureController(base_engine.FeatureController):
    character: character_controller.TempestCharacter
    definition: defs.BaseFeatureDef
    expression: PropExpression
    full_id: str
    _effective_ranks: int | None
    _granted_ranks: int
    _discount: int

    def __init__(self, full_id: str, character: character_controller.TempestCharacter):
        self.expression = PropExpression.parse(full_id)
        self.full_id = full_id
        super().__init__(self.expression.prop, character)
        self.definition = character.ruleset.features[self.id]
        self._effective_ranks = None
        self._granted_ranks = 0
        self._discount = 0

    @cached_property
    def feature_type(self) -> str:
        return self.definition.type

    @property
    def option(self) -> str | None:
        return self.expression.option

    @property
    def option_def(self) -> OptionDef | None:
        return self.definition.option

    @property
    def taken_options(self) -> dict[str, int]:
        options = {}
        for controller in self.character.features[self.feature_type].values():
            if controller.id == self.id and controller.option and controller.value > 0:
                options[controller.option] = controller.value
        return options

    @abstractproperty
    def purchased_ranks(self) -> int:
        ...

    @purchased_ranks.setter
    def purchased_ranks(self, value: int):
        ...

    @property
    def granted_ranks(self) -> int:
        return self._granted_ranks

    @property
    def paid_ranks(self) -> int:
        """Number of ranks purchased that actually need to be paid for with some currency.

        This is generally equal to `purchased_ranks`, but when grants push the total over the
        feature's maximum, these start to be refunded. They remain on the sheet in case the
        grants are revoked in the future due to an undo, a sellback, a class level swap, etc.
        """
        total = self.purchased_ranks + self.granted_ranks
        max_ranks = self.max_ranks
        if total <= max_ranks:
            return self.purchased_ranks
        # The feature is at maximum. Only pay for ranks that haven't been granted.
        # Note that the total grants could also exceed max_ranks. This is more likely
        # to happen with single-rank features like weapon proficiencies that a character
        # might receive from multiple classes.
        if self.granted_ranks < max_ranks:
            return max_ranks - self.granted_ranks
        return 0

    @property
    def value(self) -> int:
        if self.option_def and not self.option:
            # This is an aggregate controller for the feature.
            # Sum any ranks the character has in instances of it.
            total: int = 0
            for feat, controller in self.character.features[self.feature_type].items():
                if feat.startswith(f"{self.id}#"):
                    total += controller.value
            return total
        if self._effective_ranks is None:
            self.reconcile()
        return self._effective_ranks

    @property
    def max_value(self) -> int:
        if self.option_def and not self.option:
            # This is an aggregate controller for the feature.
            # Return the value of the highest instance.
            current: int = 0
            for feat, controller in self.character.features[self.feature_type].items():
                if feat.startswith(f"{self.id}#"):
                    new_value = controller.value
                    if new_value > current:
                        current = new_value
            return current
        return super().max_value

    def _link_to_character(self):
        feats = self.character.features[self.definition.type]
        if self.full_id not in feats:
            feats[self.full_id] = self

    def can_increase(self, value: int) -> Decision:
        if value <= 0:
            return _MUST_BE_POSITIVE
        current = self.value
        if current >= self.definition.ranks:
            return Decision(success=False)
        # Is the purchase within defined range?
        if (current + value) > self.definition.ranks:
            max_increase = self.definition.ranks - current
            return Decision(
                success=False,
                reason=f"Max is {self.definition.ranks}, so can't increase to {current + value}",
                amount=max_increase,
            )
        # Does the character meet the prerequisites?
        if not (rd := self.character.meets_requirements(self.definition.requires)):
            return rd
        # Is this an option skill without an option specified?
        if self.option_def and not self.option:
            return Decision(success=False, needs_option=True)
        elif (
            self.option_def
            and self.option
            and not self.definition.option.freeform
            and self.purchased_ranks == 0
        ):
            # The player is trying to buy a new option. Verify that it's legal.
            options_available = self.character.options_values_for_feature(
                self.id, exclude_taken=True
            )
            if self.option not in options_available:
                return Decision(
                    success=False,
                    reason=f"'{self.option}' not a valid option for {self.id}",
                )
        # Is this a non-option skill and an option was specified anyway?
        if not self.option_def and self.option:
            return Decision(
                success=False, reason=f"Feature {self.id} does not accept options."
            )
        return Decision.SUCCESS

    def can_decrease(self, value: int) -> Decision:
        if not self.character.can_respend:
            return _NO_RESPEND
        if value < 1:
            return _MUST_BE_POSITIVE
        purchases = self.purchased_ranks
        if value > purchases:
            return Decision(
                success=False,
                reason=f"Can't sell back {value} ranks when you've only purchased {purchases} ranks.",
                amount=(value - purchases),
            )
        return Decision.SUCCESS

    def propagate(self, data: base_engine.PropagationData) -> None:
        if not data:
            return
        self._granted_ranks += data.grants
        self._discount += data.discount
        self.reconcile()

    def reconcile(self) -> None:
        """If this controller's value has been updated (or on an initial pass on character load), update grants.

        Grants represent any feature (or feature ranks) gained simply by possessing this feature (or a number of ranks of it).
        All features in this model have a `grants` field in their definition that specify one or more features to grant one or
        more ranks of, and this will be processed whenever any ranks of this feature are possessed.

        Subclasses may have more specific grants. For example, classes may automatically grant certain features at specific levels.

        """
        previous_ranks = self._effective_ranks or 0
        self._effective_ranks = min(
            self.granted_ranks + self.purchased_ranks, self.max_ranks
        )

        self._link_to_character()
        self._perform_propagation(previous_ranks, self._effective_ranks)

    def _perform_propagation(self, from_ranks: int, to_ranks: int) -> None:
        props = self._gather_propagation(from_ranks, to_ranks)
        for id, data in props.items():
            if controller := self.character._controller_for_property(id):
                controller.propagate(data)

    def _gather_propagation(
        self, from_ranks: int, to_ranks: int
    ) -> dict[str, base_engine.PropagationData]:
        if not (from_ranks == 0 or to_ranks == 0) or (from_ranks == to_ranks):
            # At the moment, all grants only happen at the boundary of 0, so skip
            # all this if we're not coming from or going to 0.
            return {}
        grants = dict(self._gather_grants(self.definition.grants, from_ranks, to_ranks))
        discounts = dict(
            self._gather_discounts(self.definition.discounts, from_ranks, to_ranks)
        )
        props: dict[str, base_engine.PropagationData] = {}
        all_keys = set(grants.keys()).union(discounts.keys())
        for id in all_keys:
            props[id] = base_engine.PropagationData()
            if g := grants.get(id):
                props[id].grants = g
            if d := discounts.get(id):
                props[id].discount = d
        return props

    def _gather_grants(
        self, grants: defs.Grantable, from_ranks: int, to_ranks: int
    ) -> Iterable[tuple[str, int]]:
        if not grants:
            return
        elif isinstance(grants, str):
            expr = PropExpression.parse(grants)
            value = expr.value or 1
            if to_ranks <= 0:
                value = -value
            yield expr.full_id, value
        elif isinstance(grants, list):
            for grant in grants:
                yield from self._gather_grants(grant, from_ranks, to_ranks)
        elif isinstance(grants, dict):
            for key, value in grants.items():
                if to_ranks <= 0 and from_ranks > 0:
                    value = -value
                yield key, value
        else:
            raise NotImplementedError(f"Unexpected grant value: {grants}")

    def _gather_discounts(
        self, discounts: defs.Discounts, from_ranks: int, to_ranks: int
    ):
        if not discounts:
            return
        elif isinstance(discounts, dict):
            for key, value in discounts.items():
                if to_ranks <= 0:
                    value = -value
                yield key, value
        else:
            raise NotImplementedError(f"Unexpected discount value: {discounts}")
