from __future__ import annotations

import dataclasses
from collections import defaultdict
from math import floor
from typing import Callable
from typing import Literal


@dataclasses.dataclass
class Property:
    """Defines a trackable property value and evaluates it.

    Attributes:
        id: The identifier for this particular property.
        type: Whether this property tracks a feature, attribute, or tag value.
            Mostly useful for display purposes.
        base: What's the starting value for the property? Usually, but not always, 0.
        min_value: If the property value should not fall below a particular value, what value?
            If None, this is not performed. Default is 0.
        max_value: If the property value should not rise above a particular value, what value?
            If None, this is not performed. Default is None.
        min_max_each: If False, evaluation of min/max values are only performed after adding all
            modifiers together.
            If True, min/max are also evaluated after each modifier value is applied. For example, if true,
            a property with min=0 gets modifiers -1, -1, -1, -1, +5, then the output will be +5 rather than
            +1. Note that if all those modifiers had the same source/type, they might be coalesced before
            evaluation into a single +1.
        coalesce: If True, compatible modifiers (those with the same source and type) will be combined into
            a single modifier instead of storing them individually. This may affect how certain evaluation-stage
            computations are performed. Coalesce should be true if a single logical modifier might be broken into
            multiple pieces, such as multiple purchases of levels of a class or skill.
        is_tag: This property is a tag property. While it may directly have modifiers, it will also use modifiers
            applied to any property that has this tag. Mutually exclusive with `tags`.
            Ex: All classes have the "level" tag, so the virtual "level" attribute gets its value by adding them
                all together.
            Ex: All classes use their "sphere" field value as a tag, so a Wizard will have points in the virtual
                "arcane" property. Non-martial classes might also have a "caster" tag property.
        tags: When a "tag property" is evaluated, modifiers from any property that has that tag will be included
            in the evaluation. Mutually exclusive with `is_tag`.
        rounding: While modifiers might be float-valued, properties are generally expected to be
            int-valued at the end. This callable defines how rounding is handled. Defaults to `floor`.
        modifiers: List of all modifiers currently attached to the property.
            Do not set this manually. Instead, use `add_mod`, which will perform the `coalesce` operation and
            clear the cached computation as appropriate.
    """

    id: str
    type: Literal["feature", "attribute"]
    base: float = 0.0
    min_value: int | None = 0
    max_value: int | None = None
    min_max_each: bool = False
    coalesce: bool = True
    is_tag: bool = False
    tags: set[str] | None = None
    rounding: Callable[[float], int] = floor
    modifiers: list[Modifier] | None = None
    _aggregator: Aggregator | None = None
    _float_cache: float | None = None
    _rounded_cache: int | None = None
    _max_cache: int | None = None
    _applied_modifiers: list[Modifier] | None = None

    def __post_init__(self):
        if self.is_tag and self.tags:
            raise ValueError(
                f"Property definition {self.id} invalid, is_tag and tags are mutually exclusive."
            )

    def add_mod(
        self,
        modifier: Modifier | None = None,
        *,
        source: str | None = None,
        value: float = 0,
    ) -> None:
        """Add the provided modifier to the list.

        If `coalesce` is enabled, attempts to coalesce the modifier
        with a compatible modifier if feasible.

        If `modifier` is not provided, the keyword-only arguments are
        passed to the Modifier constructor as a convenience.
        They are not used otherwise.
        """
        if modifier is None:
            modifier = Modifier(
                source=source,
                value=value,
            )
        self.clear_caches()
        if self.modifiers is None:
            self.modifiers = [modifier]
            return
        elif self.coalesce:
            # Attempt to combine similar modifiers.
            for m in self.modifiers:
                if m.coalesce(modifier):
                    return
        self.modifiers.append(modifier)

    def clear_caches(self):
        self._float_cache = None
        self._rounded_cache = None
        self._max_cache = None
        self._applied_modifiers = None

    def evaluate(self) -> int:
        """Evaluates the property with the given modifiers."""
        if self._float_cache is None:
            self.evaluate_float()
        return self._rounded_cache

    def evaluate_max(self) -> int:
        if self._max_cache is None:
            self.evaluate_float()
        return self._max_cache

    def evaluate_float(self) -> float:
        """Evaluates the property with the given modifiers, without rounding."""
        if self._float_cache is not None:
            return self._float_cache
        value = self.base or 0

        # These track which modifier source provided the biggest values. Since
        # modifiers from the same source might not always coalesce into a single
        # modifier, track them and figure out the max at the end.
        source_values: dict[str, float] = defaultdict(lambda: self.base or 0)

        # Tag properties copy modifiers from any other property that has that tag.
        if self.is_tag and self._aggregator:
            modifiers = list(self.modifiers) if self.modifiers else []
            for prop in self._aggregator._props.values():
                if prop.tags and prop.modifiers and self.id in prop.tags:
                    modifiers.extend(prop.modifiers)
        else:
            modifiers = self.modifiers or []

        for m in modifiers:
            if m.value:
                value += m.value
                source_values[m.source] += m.value
            if self.min_max_each:
                value = self._force_range(value)

        value = self._force_range(value)

        self._float_cache = value
        self._rounded_cache = self.rounding(value)
        if source_values:
            self._max_cache = self.rounding(max(source_values.values()))
        else:
            self._max_cache = self.rounding(self.base or 0)
        self._applied_modifiers = modifiers
        return value

    def _force_range(self, value: float) -> float:
        if self.min_value is not None and value < self.min_value:
            value = self.min_value
        if self.max_value is not None and value > self.max_value:
            value = self.max_value
        return value


@dataclasses.dataclass
class Modifier:
    source: str
    value: float

    def coalesce(self, other: Modifier) -> bool:
        """Try to combine modifiers of the same source and type.

        The main source of this is features that have multiple purchase events. For example,
        class levels are typically purchased one at a time, spread across the character's history.

        Arguments:
            other: Another Modifier. If the source or type differ, coalesce fails.

        Returns:
            True if coalesced successfully (and `other` can be discarded), False otherwise.
            If True, this modifier has been updated in-place.
        """
        if self.source != other.source:
            return False

        self.value += other.value

        return True


class Aggregator:
    _props: dict[str, Property]

    def __init__(self):
        self._props = dict()

    def has_property(self, prop: str) -> bool:
        return prop in self._props

    def define_property(self, prop: Property) -> None:
        if self.has_property(prop.id):
            raise ValueError(f"Property {prop.id} already defined")
        prop._aggregator = self
        self._props[prop.id] = prop

    def apply_mod(self, prop: str, value: int, source: str | None = None):
        if source is None:
            source = prop
        self._props[prop].add_mod(source=source, value=value)

    def get_prop(self, prop: str) -> int:
        return self._props[prop].evaluate()

    def get_prop_max(self, prop: str) -> int:
        return self._props[prop].evaluate_max()
