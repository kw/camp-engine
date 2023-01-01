from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from abc import abstractproperty
from functools import cached_property
from functools import total_ordering
from typing import Any
from typing import Type

import pydantic
from packaging import version

from ..utils import maybe_iter
from . import base_models
from .decision import Decision


class CharacterController(ABC):
    model: base_models.CharacterModel
    engine: Engine

    @property
    def ruleset(self):
        return self.engine.ruleset

    def __init__(self, engine: Engine, model: base_models.CharacterModel):
        self.model = model
        self.engine = engine

    def clear_caches(self):
        """Clear any cached data that might need to be recomputed upon mutating the character model.

        Subclasses should override this.
        """

    def has_prop(self, expr: str | base_models.PropExpression) -> bool:
        """Check whether the character has _any_ property (feature, attribute, etc) with the given name.

        The base implementation only knows how to check for attributes. Checking for features
        must be added by implementations.
        """
        expr = base_models.PropExpression.parse(expr)
        return expr.prop in self.engine.attribute_map

    def get_prop(self, expr: str | base_models.PropExpression) -> int:
        """Retrieve the value of an arbitrary property (feature, attribute, etc).

        The base implementation only knows how to retrieve attributes. If the attribute
        is configured with `compute`, the named property is retrieved. Otherwise, checks
        the character controller for a property named either `property_name` or whatever
        the attribute's ID is and returns that. If none of the above work, just returns
        the attribute's configured `default_value`.

        Implementations can use this base implementation for attribute retrieval, but must
        add support for features.
        """
        expr = base_models.PropExpression.parse(expr)
        attr: base_models.Attribute
        if attr := self.engine.attribute_map.get(expr.prop):
            # There are a few different ways an attribute might be stored or computed.
            if hasattr(self, attr.property_name or attr.id):
                attr_value: AttributeController | int = getattr(
                    self, attr.property_name or attr.id
                )
                if isinstance(attr_value, AttributeController):
                    if expr.single is not None:
                        return attr_value.max_value
                    return attr_value.value
                return attr_value
            else:
                return attr.default_value
        return 0

    def get_options(self, expr: str) -> dict[str, int]:
        """Retrieves the options (and their values) for a particular property or feature."""
        return {}

    @abstractmethod
    def can_purchase(self, entry: base_models.Purchase | str) -> Decision:
        ...

    @abstractmethod
    def purchase(self, entry: base_models.Purchase | str) -> Decision:
        ...

    def meets_requirements(self, requirements: base_models.Requirements) -> Decision:
        messages: list[str] = []
        for req in maybe_iter(requirements):
            if isinstance(req, str):
                # It's unlikely that an unparsed string gets here, but if so,
                # go ahead and parse it.
                req = base_models.PropExpression.parse(req)
            if not (rd := req.evaluate(self)):
                messages.append(rd.reason)
        if messages:
            messages = ["Not all requirements are met."] + messages
        return Decision(
            success=not (messages), reason="\n".join(messages) if messages else None
        )

    def options_values_for_feature(
        self, feature_id: str, exclude_taken: bool = False
    ) -> set[str]:
        """Retrieve the options valid for a feature for this character.

        Args:
            feature_id: Identifier of the feature to check.
            exclude_taken: If this character has already taken
                this feature, removes any that have already been taken.
        """
        feature_def = self.engine.feature_defs[feature_id]
        option_def = feature_def.option
        if not (option_def.values or option_def.inherit):
            return set()
        options_excluded: set[str] = set()
        if exclude_taken and (taken_options := self.get_options(feature_id)):
            if not feature_def.multiple:
                # The feature can only have a single option and it already
                # has one, so no other options are legal.
                return set()
            options_excluded = set(taken_options.keys())

        if option_def.inherit:
            expr = base_models.PropExpression.parse(option_def.inherit)
            legal_values = set(self.get_options(expr.prop))
            # If expr has a value specified, the only legal options are the
            # ones that meet this requirement.
            if expr.value:
                for option in legal_values.copy():
                    req = expr.copy(update={"option": option})
                    if not req.evaluate(self):
                        legal_values.remove(option)
        else:
            legal_values = set(option_def.values)
            if option_def.flag:
                # If a values flag is specified, check the character metadata to
                # see if additional legal values are provided. This will probably
                # be a list of strings, but handle other things as well. If a
                # value in the list is prefixed with "-" it is removed from the
                # legal value set.
                extra_values = self.model.metadata.flags.get(option_def.flag, [])
                if not isinstance(extra_values, list):
                    extra_values = [extra_values]
                for value in (str(v) for v in extra_values):
                    if value.startswith("-"):
                        legal_values.remove(value[1:])
                    else:
                        legal_values.add(value)

        legal_values ^= options_excluded

        # An option definition can specify requirements for each option. If a
        # requirement is specified and not met, remove it from the set.
        if option_def.requires:
            unmet = set()
            for option in legal_values:
                if option in option_def.requires:
                    req = option_def.requires[option]
                    if not self.meets_requirements(req):
                        unmet.add(option)
            legal_values ^= unmet

        return legal_values

    def option_satisfies_definition(
        self,
        feature_id: str,
        option_value: str,
        exclude_taken: bool = False,
    ) -> bool:
        feature_def = self.engine.feature_defs[feature_id]
        option_def = feature_def.option
        if not option_def and not option_value:
            # No option needed, no option provided. Good.
            return True
        if not option_def and option_value:
            # There's no option definition, if an option was provided
            # then it's wrong.
            return False
        if option_def.freeform:
            # The values are just suggestions. We may want to
            # filter for profanity or something, but otherwise
            # anything goes.
            return True
        # Otherwise, the option must be in a specific set of values.
        return option_value in self.options_values_for_feature(
            feature_id, exclude_taken=exclude_taken
        )


@total_ordering
class PropertyController(ABC):
    id: str
    character: CharacterController

    def __init__(self, prop_id: str, character: CharacterController):
        self.id = prop_id
        self.character = character

    @abstractproperty
    def value(self) -> int:
        ...

    @property
    def max_value(self) -> int:
        return self.value

    def __eq__(self, other: Any) -> bool:
        if self is other:
            return True
        match other:
            case PropertyController():
                return self.value == other.value
            case _:
                return self.value == other

    def __lt__(self, other: Any) -> bool:
        match other:
            case PropertyController():
                return self.value < other.value
            case _:
                return self.value < other


class FeatureController(PropertyController):
    @cached_property
    def expr(self) -> base_models.PropExpression:
        return base_models.PropExpression.parse(self.id)

    @cached_property
    def definition(self) -> base_models.BaseFeatureDef:
        return self.character.engine.feature_defs[self.expr.prop]

    @property
    def max_ranks(self) -> int:
        if self.definition.ranks == "unlimited":
            # Arbitrarily chosen large int.
            return 101
        return self.definition.ranks

    def can_increase(self, value: int) -> Decision:
        return Decision.UNSUPPORTED

    def can_decrease(self, value: int) -> Decision:
        return Decision.UNSUPPORTED

    def increase(self, value: int) -> Decision:
        return Decision.UNSUPPORTED

    def decrease(self, value: int) -> Decision:
        return Decision.UNSUPPORTED

    @property
    def taken_options(self) -> dict[str, int]:
        return {}

    def __str__(self) -> str:
        if self.expr.option:
            return f"{self.definition.name} ({self.expr.option}): {self.value}"
        return f"{self.definition.name}: {self.value}"


class AttributeController(PropertyController):
    @cached_property
    def definition(self) -> base_models.Attribute:
        return self.character.engine.attribute_map[self.id]

    def __str__(self) -> str:
        return f"{self.definition.name}: {self.value}"


class Engine(ABC):
    def __init__(self, ruleset: base_models.BaseRuleset):
        self._ruleset = ruleset

    @property
    def ruleset(self) -> base_models.BaseRuleset:
        return self._ruleset

    @cached_property
    def attribute_map(self) -> dict[str, base_models.Attribute]:
        return self.ruleset.attribute_map

    @cached_property
    def feature_defs(self) -> dict[str, base_models.BaseFeatureDef]:
        """Convenience property that provides all feature definitions."""
        return self.ruleset.features

    @abstractproperty
    def sheet_type(self) -> Type[base_models.CharacterModel]:
        ...

    @abstractproperty
    def character_controller(self) -> Type[CharacterController]:
        return CharacterController

    def new_character(self, **data) -> CharacterController:
        return self.character_controller(
            self,
            self.sheet_type(
                ruleset_id=self.ruleset.id, ruleset_version=self.ruleset.version, **data
            ),
        )

    def load_character(self, data: dict) -> CharacterController:
        """Load the given character data with this ruleset.

        Returns:
            A character sheet of appropriate subclass.

        Raises:
            ValueError: if the character is not compatible with this ruleset.
                By default, characters are only comaptible with the ruleset they
                were originally written with.
        """
        updated_data = self.update_data(data)
        model = pydantic.parse_obj_as(self.sheet_type, updated_data)
        return self.character_controller(self, model)

    def update_data(self, data: dict) -> dict:
        """If the data is from a different but compatible rules version, update it.

        The default behavior is to reject any character data made with a different ruleset ID,
        and assume newer versions are backward (but not forward).

        Raises:
            ValueError: if the character is not compatible with this ruleset.
                By default, characters are only comaptible with the ruleset they
                were originally written with.
        """
        if data["ruleset_id"] != self.ruleset.id:
            raise ValueError(
                f'Can not load character id={data["id"]}, ruleset={data["ruleset_id"]} with ruleset {self.ruleset.id}'
            )
        if version.parse(self.ruleset.version) < version.parse(data["ruleset_version"]):
            raise ValueError(
                f'Can not load character id={data["id"]}, ruleset={data["ruleset_id"]} v{data["ruleset_version"]}'
                f" with ruleset {self.ruleset.id} v{self.ruleset.version}"
            )
        return data
