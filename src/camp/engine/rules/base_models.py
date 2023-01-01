from __future__ import annotations

import re
import types
import typing
from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import ClassVar
from typing import Iterable
from typing import Literal
from typing import Type
from typing import TypeAlias
from uuid import uuid4

import pydantic

from .. import utils
from ..utils import maybe_iter
from . import base_engine
from .decision import Decision

_REQ_SYNTAX = re.compile(
    r"""(?P<prop>[a-zA-Z0-9_-]+)
    (?:@(?P<tier>-?\d+))?          # Tier, aka "@4"
    (?:\#(?P<option>[a-zA-Z0-9?_-]+))?   # Skill options, aka "#Undead_Lore"
    (?::(?P<value>-?\d+))?       # Minimum value, aka ":5"
    (?:\$(?P<single>-?\d+))?       # Minimum value in single thing, aka "$5"
    (?:<(?P<less_than>-?\d+))?     # Less than value, aka "<5"
    """,
    re.VERBOSE,
)

FlagValue: TypeAlias = bool | int | float | str
FlagValues: TypeAlias = list[FlagValue] | FlagValue


class BaseModel(pydantic.BaseModel):
    def dump(self, as_json=True) -> str | dict:
        return utils.dump(self, as_json)

    class Config:
        extra = pydantic.Extra.forbid


class Attribute(BaseModel):
    id: str
    name: str
    abbrev: str | None = None
    default_value: int = 0
    hidden: bool = False
    scoped: bool = False
    tiered: bool = False
    tier_names: list[str] | None = None
    is_tag: bool = False
    compute: str | None = None
    property_name: str | None = None


class BoolExpr(BaseModel, ABC):
    @abstractmethod
    def evaluate(self, char: base_engine.CharacterController) -> Decision:
        ...

    def identifiers(self) -> set[str]:
        return set()


# The model class or union of classes to be parsed into models.
ModelDefinition: TypeAlias = Type[BaseModel] | types.UnionType
Identifiers: TypeAlias = str | list[str] | None


class AnyOf(BoolExpr):
    any: Requirements

    def evaluate(self, char: base_engine.CharacterController) -> Decision:
        messages: list[str] = []
        for expr in maybe_iter(self.any):
            if isinstance(expr, str):
                raise TypeError(f"Expression '{expr}' expected to be parsed by now.")
            if rd := expr.evaluate(char):
                return rd
            messages.extend(rd.reason or "[unspecified failure reason]")
        return Decision(success=False, reason=f"AnyOf({'; '.join(messages)})")

    def identifiers(self) -> set[str]:
        ids = set()
        for op in maybe_iter(self.any):
            if isinstance(op, str):
                ids.add(op)
            else:
                ids |= op.identifiers()
        return ids


class AllOf(BoolExpr):
    all: Requirements

    def evaluate(self, char: base_engine.CharacterController) -> Decision:
        for expr in maybe_iter(self.all):
            if isinstance(expr, str):
                raise TypeError(f"Expression '{expr}' expected to be parsed by now.")
            if not (rd := expr.evaluate(char)):
                return rd
        return Decision(success=True)

    def identifiers(self) -> set[str]:
        ids = set()
        for op in maybe_iter(self.all):
            if isinstance(op, str):
                ids.add(op)
            else:
                ids |= op.identifiers()
        return ids


class NoneOf(BoolExpr):
    none: Requirements

    def evaluate(self, char: base_engine.CharacterController) -> Decision:
        for expr in maybe_iter(self.none):
            if isinstance(expr, str):
                raise TypeError(f"Expression '{expr}' expected to be parsed by now.")
            if expr.evaluate(char):
                return Decision(success=False, reason=f"Not({expr})")
        return Decision(success=True)

    def identifiers(self) -> set[str]:
        ids: set[str] = set()
        for op in maybe_iter(self.none):
            if isinstance(op, str):
                ids.add(op)
            else:
                ids |= op.identifiers()
        return ids


class PropExpression(BoolExpr):
    """Things that might get parsed out of a property expression.

    Mostly used for requirement parsing and evaluation, but can be used
    elsewhere.

    Attributes:
        prop: The property being tested. Often a feature ID. Required.
        option: Text value listed after a #. Ex: lore#Undead
            This is handled specially if the value is '?', which means
            "You need the same option in the indicated skill as you are
            taking for this skill".
        value: "At least this many ranks/levels/whatever". Ex: caster:5 is
            "at least 5 levels in casting classes"
        single: "At least this many ranks in the highest thing of this type"
            Ex: caster$5 is "at least 5 ranks in a single casting class".
        less_than: "No more than this many ranks". Ex: lore<2 means no more
            than one total ranks of Lore skills.
        tier: For tiered properties like spell slots. Ex: spell@4 indicates
            at least one tier-4 spell slot, while spell@4:3 indicates at least
            three tier-4 spell slots.
    """

    prop: str
    tier: int | None = None
    option: str | None = None
    value: int | None = None
    single: int | None = None
    less_than: int | None = None

    @property
    def full_id(self) -> str:
        return full_id(self.prop, self.option)

    def evaluate(self, char: base_engine.CharacterController) -> Decision:
        id = self.unparse(prop=self.prop, tier=self.tier, option=self.option)
        if not char.has_prop(id):
            return Decision(success=False, reason=f"{self!r} [{id} not present]")
        ranks = char.get_prop(id)
        if self.value is not None:
            if ranks < self.value:
                return Decision(
                    success=False, reason=f"{self!r} [{ranks} < {self.value}]"
                )
        elif self.less_than is not None:
            if ranks >= self.less_than:
                return Decision(
                    success=False, reason=f"{self!r} [{ranks} ≥ {self.less_than}]"
                )
        elif self.single is not None:
            max_ranks = char.get_prop(f"{id}$0")
            if max_ranks < self.single:
                return Decision(
                    success=False, reason=f"{self!r} [{max_ranks} < {self.single}]"
                )
        else:
            if ranks < 1:
                return Decision(success=False, reason=f"{self!r} [ranks={ranks}]")
        return Decision(success=True)

    def identifiers(self) -> set[str]:
        return set([self.prop])

    @classmethod
    def parse(cls, req: str | PropExpression) -> PropExpression:
        if isinstance(req, PropExpression):
            # Convenient pass-thru for methods that can take the str or parsed version.
            return req
        if match := _REQ_SYNTAX.fullmatch(req):
            groups = match.groupdict()
            prop = groups["prop"]
            tier = int(t) if (t := groups.get("tier")) else None
            option = o.replace("_", " ") if (o := groups.get("option")) else None
            value = int(m) if (m := groups.get("value")) else None
            single = int(s) if (s := groups.get("single")) else None
            less_than = int(lt) if (lt := groups.get("less_than")) else None
            return cls(
                prop=prop,
                tier=tier,
                option=option,
                value=value,
                single=single,
                less_than=less_than,
            )
        raise ValueError(f"Requirement parse failure for {req}")

    @classmethod
    def unparse(
        cls,
        prop: str,
        tier: int | None = None,
        option: str | None = None,
        value: int | None = None,
        single: int | None = None,
        less_than: int | None = None,
    ):
        req = prop
        if tier:
            req += f"@{tier}"
        if option:
            req += f"#{option.replace(' ', '_')}"
        if value:
            req += f":{value}"
        if single:
            req += f"${single}"
        if less_than:
            req += f"<{less_than}"
        return req

    def __repr__(self) -> str:
        return self.unparse(
            prop=self.prop,
            tier=self.tier,
            option=self.option,
            value=self.value,
            single=self.single,
            less_than=self.less_than,
        )


# The requirements language involves a lot of recursive definitions,
# so define it here. Pydantic models using forward references need
# to be poked to know the reference is ready, so update them as well.
Requirement: TypeAlias = AnyOf | AllOf | NoneOf | PropExpression | str
Requirements: TypeAlias = list[Requirement] | Requirement | None
AnyOf.update_forward_refs()
AllOf.update_forward_refs()
NoneOf.update_forward_refs()
PropExpression.update_forward_refs()


class OptionDef(BaseModel):
    """

    Attributes:
        short: If true, the option text will be rendered along with
            the title, such as "Lore [Undead]". Otherwise, where
            (and if) the option is rendered depends on custom view code.
        freeform: If true, allows free entry of text for this option.
        values: If provided, a drop-down list of options will
            be presented with these values. If `freeform` is
            also specified, the list will have an "Other..." option
            that allows freeform entry.
        requires: If provided, a mapping of option values to requirements.
            Requirements are specified in the same way as for features. The
            listed requirements must be met to choose the indicated option.
            If an option does not appear in this mapping (for example, if it
            comes from the `flag` set) then no requirements are assumed.
        flag: If provided, names a flag that might appear in the
            character's metadata, which should be a list of strings.
            Values in this list are added to the provided values list
            unless they are prefixed with "-", in which case they signal
            the value should be removed. This allows staff to potentially
            add or remove values in the default ruleset for the playerbase
            or a specific character without needing to edit the ruleset.
        inherit: If provided, specifies the ID of another feature that has
            options. The options available to this feature are limited to
            options taken in the chosen feature.
            Should not be specified with `freeform`, `values`, `flag`, etc.
    """

    short: bool = True
    freeform: bool = False
    values: set[str] | None = None
    requires: dict[str, Requirements] | None = None
    flag: str | None = None
    inherit: str | None = None


class BaseFeatureDef(BaseModel):
    id: str
    name: str
    type: str
    requires: Requirements = None
    def_path: str | None = None
    tags: set[str] = pydantic.Field(default_factory=set)
    description: str | None = None
    ranks: int | Literal["unlimited"] = 1
    option: OptionDef | None = None
    multiple: bool = False

    @classmethod
    def default_name(cls) -> str:
        try:
            return cls.type_key().title()
        except Exception:
            return str(cls)

    @classmethod
    def type_key(cls) -> str:
        return cls.__fields__["type"].type_.__args__[0]

    def post_validate(self, ruleset: BaseRuleset) -> None:
        self.requires = parse_req(self.requires)
        if self.requires:
            ruleset.validate_identifiers(list(self.requires.identifiers()))


class BadDefinition(BaseModel):
    """Represents a feature definition that could not be parsed.

    Attributes:
        path: The path of the definition file.
        data: Data as parsed from the json/yaml/toml file with defaults applied.
        raw_data: Same data, but without the defaults.
        exception: Exception from the model parser.
    """

    path: str
    data: typing.Any
    raw_data: typing.Any
    exception_type: str
    exception_message: str


class BaseRuleset(BaseModel, ABC):
    id: str
    name: str
    version: str = "0.0a"
    ruleset: str | None = None
    ruleset_model_def: str | None = None
    engine_class: str
    features: dict[str, BaseFeatureDef] = pydantic.Field(default_factory=dict)
    bad_defs: list[BadDefinition] = pydantic.Field(default_factory=list)

    name_overrides: dict[str, str] = pydantic.Field(default_factory=dict)
    _display_names: dict[str, str] = pydantic.PrivateAttr(default_factory=dict)
    attributes: ClassVar[Iterable[Attribute]] = []

    def __init__(self, **data):
        super().__init__(**data)
        # Compute the display names for each type. If not specified, the
        # feature type has a built-in default, usualy based on the
        # 'type' field. So if your model has:
        #    Literal['skill'] = 'skill'
        # as the type field, the default name will be 'Skill'.
        f: BaseFeatureDef
        for f in self.feature_model_types().__args__:
            key = f.type_key
            self._display_names[key] = self.name_overrides.get(key, f.default_name())
        # The name override list can also include names for attributes and such,
        # so copy the rest of it over.
        for key, name in self.name_overrides.items():
            if key not in self._display_names:
                self._display_names[key] = name

    @property
    def attribute_map(self) -> dict[str, Attribute]:
        return {a.id: a for a in self.attributes}

    @property
    def display_names(self) -> dict[str, str]:
        """Mapping of IDs to display names for feature types, attributes, etc.

        To override the default name, include the new mapping in the "name_overrides"
        table of the ruleset file.

        For example, this would allow a Geas 5 game to change "Breed" to "Lineage"
        in the UI without having to change how the breed system is implemented, by
        adding this to "ruleset.toml":

        [name_overrides]
        breed = 'Lineage'
        """
        return self._display_names

    @property
    def engine(self) -> base_engine.Engine:
        engine_class = utils.import_name(self.engine_class)
        if not issubclass(engine_class, base_engine.Engine):
            raise ValueError(
                f"Ruleset declares {self.engine_class} as its engine, but it isn't an engine."
            )
        return engine_class(self)

    @abstractmethod
    def feature_model_types(self) -> ModelDefinition:
        ...

    def identifier_defined(self, identifier: str) -> bool:
        """Check if the identifier is meaningful in the ruleset.

        By default, the space of identifiers is the set of feature IDs,
        the set of feature types, and anything else defined in the
        ruleset's name_overrides. Attributes will usually be listed there,
        so this should cover most cases. However, if you have other
        identifiers or attributes without display names, you may need
        to override this.
        """
        return identifier in self.features or identifier in self.attribute_map

    def validate_identifiers(self, identifiers: Identifiers) -> None:
        id_list: list[str]
        match identifiers:
            case str():
                id_list = [identifiers]
            case None:
                id_list = []
            case _:
                id_list = list(identifiers)
        # Identifiers provided may have extra syntax in the context
        # of requirements or grants. For example, "craftsman#Artist",
        # "alchemy:3", "!magic-insensitive"
        for req in id_list:
            if not (parsed_req := parse_req(req)):
                continue
            for id in parsed_req.identifiers():
                if not self.identifier_defined(id):
                    raise ValueError(
                        f'Required identifier "{id}" not found in ruleset.'
                    )


class FeatureMatcher(BaseModel):
    """Matcher for checking if a particular feature can be used in some context.

    Generally this is used in slot definitions that want to say something like
    "Pick any character option" or "Choose any martial skill" or the like.

    Attributes:
        id: One or more feature IDs. If present, features must be in this set of IDs.
            When a single ID is used, the matcher is likely trying to match against an
            option of the feature.
        type: The type of the feature, suck as 'skill', 'class', 'classfeature', etc.
        option:
    """

    id: Identifiers = None
    type: str | None = None
    tags: set[str] | None = None
    option: str | list[str] | None = None
    attrs: dict[str, Any] = pydantic.Field(default_factory=dict)

    class Config:
        extra = pydantic.Extra.allow

    @pydantic.root_validator(pre=True)
    def _build_attrs(cls, values: dict[str, Any]) -> dict[str, Any]:
        defined_fields = {field.alias for field in cls.__fields__.values()}

        attrs: dict[str, Any] = values.get("attrs", {})
        for field, value in values.items():
            if field not in defined_fields:
                attrs[field] = value
        values["attrs"] = attrs
        return values

    def matches(
        self, feature: BaseFeatureDef, character: base_engine.CharacterController
    ) -> bool:
        """Does this feature match the matcher?

        Args:
            feature: The feature to check.
            character: The character to use for context. See the doc string for the "option"
                attribute for why.
        """
        if self.id is not None:
            if isinstance(self.id, str):
                if feature.id != self.id:
                    return False
            elif feature.id not in self.id:
                return False
        if self.type is not None:
            if feature.type != self.type:
                return False
        if self.tags is not None:
            if not self.tags.issubset(feature.tags):
                return False
        if self.option is not None:
            # Are any of the specified options valid for this feature on this character?
            options = self.option if not isinstance(self.option, str) else [self.option]
            if not any(
                character.option_satisfies_definition(feature.id, opt)
                for opt in options
            ):
                return False
        # Arbitrary attribute matcher.
        for attr, value in self.attrs.items():
            if not hasattr(feature, attr):
                return False
            if getattr(feature, attr) != value:
                return False
        # If none of the filters was negative, this is a match
        return True


class CharacterMetadata(BaseModel):
    """Overarching character data.

    While a character might have multiple sheets for various occassions,
    this data comes from outside of the sheet and generally represents
    external factors. For example, a character sheet can usually be
    freely rewritten up until the point where the character is used
    at an event, at which point changes are much more constrained.

    CharacterMetadata is not necessarily expected to be persisted.
    It can be constructed at any time from a player's attendenace
    records, service point expenditures, etc. The metadata provided
    might vary, for example, for a level-down sheet at a level
    capped event.

    Attributes:
        id: The character ID this applies to.
        player_id: The player ID this applies to.
        character_name: The actual name of the character. A single character
            might have various sheets with their own sheet names, but the
            actual character name will be in the metadata.
        player_name: The actual name of the player. Mostly here for offline
            use in the future, where a character data blob might need to be
            printed without datatabase access.
        awards: Awarded currency values. Since the award schedule isn't necessarily
            deterministic, this is left as an out-of-engine concern. For example,
            Tempest awards bonus CP for turning in a backstory, and +1 CP for each
            full weekend event attended, but double value if attending the game
            while below the campaign maximum CP, but the maximum doesn't apply to
            CP earned in other chapters, or does it? Game engine doesn't care,
            just tell it how many CP you got.
        flags: Extra flags for the engine to interpret. These may be "feature flags"
            for experimentation, extra options for skills that have set options (allowing
            things like "I want Craftsman (Orthodontist) but it's not in the list" without
            having to modify the actual ruleset), flagging the character as being able to
            see certain secret purchase options, and so on.
    """

    id: str = pydantic.Field(default=uuid4)
    player_id: str | None = None
    character_name: str | None = None
    player_name: str | None = None
    awards: dict[str, int] = pydantic.Field(default_factory=dict)
    flags: dict[str, FlagValues] = pydantic.Field(default_factory=dict)


class CharacterModel(BaseModel, ABC):
    """Represents the serializable data of a character sheet.

    Individual rulesets can override this to add fields for
    currency or attribute tracking if desired.

    While this base model may be sufficient for many games, others might
    need to store additional data. The character and feature models may be
    overridden in the ruleset definition.

    Attributes:
        id: The character ID, probably matching a database record.
            Note that a particular character might have more than one
            character sheet for various reasons, so the ID might be compound.
        ruleset_id: The ID of the ruleset. A particular character could
            potentially have sheets of different rulesets if their game is
            testing new rules. If the game has minion characters, their sheets
            might also use a different ruleset than normal PCs.
        name: The character sheet name, as specified by the player. While the
            main character sheet likely has this unset, if the character has
            any subsheets (a transformation, a minion, a medforge, etc) these
            may have different names for organizational purposes.
        metadata: Information about the character originating from outside of
            the rules engine. This includes basic fluff like the character's
            actual name, the name of the player, number of events played,
            base currency values, special flags, etc.
    """

    id: str = pydantic.Field(default_factory=uuid4)
    ruleset_id: str
    ruleset_version: str
    metadata: CharacterMetadata = pydantic.Field(default_factory=CharacterMetadata)
    name: str | None = None
    purchases: list[Purchase] = pydantic.Field(default_factory=list)


class Feature(BaseModel):
    """Represents a feature on a character sheet.

    Attributes:
        id: The base ID of the feature.
        option: The option value, if any.
        full_id: The option-qualified ID
        purchases: The number of ranks of this feature that the player
            has intentionally purchased.
        grants: The number of ranks the character has received for free.
            If grants cause the character to exceed the feature's max ranks,
            the number of purchases_paid goes down.
        max_ranks: Cached value of max_ranks from the feature definition, for
            quickly determining if a feature can't get more purchases.
        purchases_paid: The number of purchases the character actually needs
            to pay for.
    """

    id: str
    option: str | None = None
    purchases: int = 0
    grants: int = 0
    ranks: int = 0
    max_ranks: int = 1

    @property
    def full_id(self) -> str:
        return full_id(self.id, self.option)

    @property
    def purchases_paid(self) -> int:
        if self.purchases + self.grants > self.ranks:
            return min(self.purchases, self.max_ranks - self.grants)
        else:
            return self.purchases

    def apply(
        self, max_ranks: int, purchase_delta: int = 0, grants_delta: int = 0
    ) -> None:
        """
        Recomputes ranks and purchases_paid based on
        previous updates to purchases and grants.

        Args:
            purchase_delta: Number of ranks purchased (or sold, if negative).
            max_ranks: The maximum number of ranks purchasable
                for this feature.
        """
        # Update value of max ranks, in case the ruleset data has changed.
        self.max_ranks = max_ranks
        # Update purchase records. While the engine should handle this for us,
        # double check that the recorded purchases are within bounds.
        self.purchases += purchase_delta
        if self.purchases < 0:
            self.purchases = 0
        if self.purchases > max_ranks:
            self.purchases = max_ranks
        # Update grant records. Grants could exceed the max ranks if the character
        # happens to have multiple grants that push it over, particularly for single
        # rank skills (e.g. getting multiple grants for Basic Faith due to multiclassing),
        # and we need to keep track of that in case one gets sold back.
        self.grants += grants_delta
        total = self.purchases + self.grants
        self.ranks = max(total, max_ranks)


class Purchase(BaseModel):
    """Represents a specific purchase event for a character feature.

    Note that "purchase" may be a misnomer if your game offers a way to
    decrease values on the sheet in addition to the usual improvement.

    The ruleset should know how to update the character model when a
    purchase is added or removed.

    Attributes:
        id: The ID of the feature definition. Note that some in some systems,
            certain features may have multiple instances on a character sheet.
            For example, in the d20 SRD, Weapon Focus can be taken multiple
            times, once per type of weapon.
        option: Option value, if any
        ranks: Number of ranks to purchase. If the feature does not have ranks,
            use the default of "1".
    """

    id: str
    option: str | None = None
    ranks: int = 1

    @property
    def full_id(self) -> str:
        return full_id(self.id, self.option)

    @property
    def expression(self) -> PropExpression:
        return PropExpression(prop=self.id, option=self.option, value=self.ranks)

    @classmethod
    def parse(self, expr: str) -> Purchase:
        prop = PropExpression.parse(expr)
        return Purchase(
            id=prop.prop,
            option=prop.option,
            ranks=prop.value if prop.value is not None else 1,
        )


def full_id(id: str, option: str | None) -> str:
    if option:
        return f"{id}#{option.replace(' ', '_')}"
    else:
        return id


def parse_req(req: Requirements) -> BoolExpr | None:
    if not req:
        return None
    if isinstance(req, list):
        return AllOf(all=[parse_req(r) for r in req])
    if isinstance(req, AllOf):
        return AllOf(all=[parse_req(r) for r in maybe_iter(req.all)])
    if isinstance(req, AnyOf):
        return AnyOf(any=[parse_req(r) for r in maybe_iter(req.any)])
    if isinstance(req, NoneOf):
        return NoneOf(none=[parse_req(r) for r in maybe_iter(req.none)])
    if isinstance(req, str):
        if req.startswith("!"):
            return NoneOf(none=[PropExpression.parse(req[1:])])
        else:
            return PropExpression.parse(req)
    raise ValueError(f"Requirement parse failure for {req}")
