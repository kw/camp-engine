from __future__ import annotations

import re
import types
import typing
from abc import ABC
from abc import abstractmethod
from abc import abstractproperty
from functools import cache
from typing import ClassVar
from typing import Iterable
from typing import Type
from typing import TypeAlias
from uuid import uuid4

import pydantic
from packaging import version

from . import utils
from .utils import maybe_iter

_REQ_SYNTAX = re.compile(
    r"""(?P<prop>[a-zA-Z0-9_-]+)
    (?:@(?P<tier>\d+))?          # Tier, aka "@4"
    (?:\#(?P<option>[a-zA-Z0-9?_-]+))?   # Skill options, aka "#Undead_Lore"
    (?::(?P<minimum>\d+))?       # Minimum value, aka ":5"
    (?:\$(?P<single>\d+))?       # Minimum value in single thing, aka "$5"
    (?:<(?P<less_than>\d+))?     # Less than value, aka "<5"
    """,
    re.VERBOSE,
)


class BaseModel(pydantic.BaseModel):
    def dump(self, as_json=True) -> str | dict:
        return utils.dump(self, as_json)

    class Config:
        extra = pydantic.Extra.forbid


class BoolExpr(BaseModel, ABC):
    @abstractmethod
    def evaluate(self, char: BaseCharacter) -> bool:
        ...

    def identifiers(self) -> set[Identifier]:
        return set()


# The model class or union of classes to be parsed into models.
ModelDefinition: TypeAlias = Type[BaseModel] | types.UnionType
Identifier: TypeAlias = str
Identifiers: TypeAlias = Identifier | list[Identifier] | None
FlagValue: TypeAlias = bool | int | float | str
FlagValues: TypeAlias = list[FlagValue] | FlagValue
OptionValue: TypeAlias = str


class AnyOf(BoolExpr):
    any: Requirements

    def evaluate(self, char: BaseCharacter) -> bool:
        # TODO: This could have been a pretty simple generator expression,
        # but mypy isn't as good as pylance at recognizing when types have
        # been constrained. Maybe do something about it, maybe stop using mypy.
        for expr in maybe_iter(self.any):
            if isinstance(expr, str):
                raise TypeError(f"Expression '{expr}' expected to be parsed by now.")
            if expr.evaluate(char):
                return True
        return False

    def identifiers(self) -> set[Identifier]:
        ids = set()
        for op in maybe_iter(self.any):
            if isinstance(op, str):
                ids.add(op)
            else:
                ids |= op.identifiers()
        return ids


class AllOf(BoolExpr):
    all: Requirements

    def evaluate(self, char: BaseCharacter) -> bool:
        for expr in maybe_iter(self.all):
            if isinstance(expr, str):
                raise TypeError(f"Expression '{expr}' expected to be parsed by now.")
            if not expr.evaluate(char):
                return False
        return True

    def identifiers(self) -> set[Identifier]:
        ids = set()
        for op in maybe_iter(self.all):
            if isinstance(op, str):
                ids.add(op)
            else:
                ids |= op.identifiers()
        return ids


class NoneOf(BoolExpr):
    none: Requirements

    def evaluate(self, char: BaseCharacter) -> bool:
        for expr in maybe_iter(self.none):
            if isinstance(expr, str):
                raise TypeError(f"Expression '{expr}' expected to be parsed by now.")
            if expr.evaluate(char):
                return False
        return True

    def identifiers(self) -> set[Identifier]:
        ids = set()
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
        minimum: "At least this many ranks/levels/whatever". Ex: caster:5 is
            "at least 5 levels in casting classes"
        single: "At least this many ranks in the highest thing of this type"
            Ex: caster$5 is "at least 5 ranks in a single casting class".
        less_than: "No more than this many ranks". Ex: lore<2 means no more
            than one total ranks of Lore skills.
        tier: For tiered properties like spell slots. Ex: spell@4 indicates
            at least one tier-4 spell slot, while spell@4:3 indicates at least
            three tier-4 spell slots.
    """

    prop: Identifier
    tier: int | None = None
    option: str | None = None
    minimum: int | None = None
    single: int | None = None
    less_than: int | None = None

    def evaluate(self, char: BaseCharacter) -> bool:
        id = self.prop
        if self.tier is not None:
            id = f"{id}@{self.tier}"
        if self.option is not None:
            id = f"{id}#{self.option.replace(' ', '_')}"
        if not char.has_prop(id):
            return False
        ranks = char.get_prop(id)
        if self.minimum is not None:
            if ranks < self.minimum:
                return False
        elif self.less_than is not None:
            if ranks >= self.less_than:
                return False
        elif self.single is not None:
            max_ranks = char.get_prop_max(id)
            if max_ranks < self.single:
                return False
        else:
            if ranks < 1:
                return False
        return True

    def identifiers(self) -> set[Identifier]:
        return set([self.prop])

    @classmethod
    def parse(cls, req: str) -> PropExpression:
        if match := _REQ_SYNTAX.fullmatch(req):
            groups = match.groupdict()
            prop = groups["prop"]
            tier = int(t) if (t := groups.get("tier")) else None
            option = o.replace("_", " ") if (o := groups.get("option")) else None
            minimum = int(m) if (m := groups.get("minimum")) else None
            single = int(s) if (s := groups.get("single")) else None
            less_than = int(lt) if (lt := groups.get("less_than")) else None
            return cls(
                prop=prop,
                tier=tier,
                option=option,
                minimum=minimum,
                single=single,
                less_than=less_than,
            )
        raise ValueError(f"Requirement parse failure for {req}")

    def __repr__(self) -> str:
        req = self.prop
        if self.tier:
            req += f"@{self.tier}"
        if self.option:
            req += f"#{self.option.replace(' ', '_')}"
        if self.minimum:
            req += f":{self.minimum}"
        if self.single:
            req += f"${self.single}"
        if self.less_than:
            req += f"<{self.less_than}"
        return req


# The requirements language involves a lot of recursive definitions,
# so define it here. Pydantic models using forward references need
# to be poked to know the reference is ready, so update them as well.
Requirement: TypeAlias = AnyOf | AllOf | NoneOf | PropExpression | str
Requirements: TypeAlias = list[Requirement] | Requirement | None
AnyOf.update_forward_refs()
AllOf.update_forward_refs()
NoneOf.update_forward_refs()
PropExpression.update_forward_refs()


class BaseFeatureDef(BaseModel):
    id: Identifier
    name: str
    type: str
    requires: Requirements = None
    def_path: str | None = None
    tags: set[str] = pydantic.Field(default_factory=set)
    description: str | None = None
    ranks: bool | int = False
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
    features: dict[Identifier, BaseFeatureDef] = pydantic.Field(default_factory=dict)
    bad_defs: list[BadDefinition] = pydantic.Field(default_factory=list)

    name_overrides: dict[str, str] = pydantic.Field(default_factory=dict)
    _display_names: dict[str, str] = pydantic.PrivateAttr(default_factory=dict)
    attributes: ClassVar[Iterable[BaseAttributeDef]] = []
    builtin_identifiers: ClassVar[set[Identifier]] = set()

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

    @abstractproperty
    def sheet_type(self) -> Type[BaseCharacter]:
        ...

    @classmethod
    @cache
    def attribute_map(cls) -> dict[str, BaseAttributeDef]:
        return {a.id: a for a in cls.attributes}

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

    @abstractmethod
    def feature_model_types(self) -> ModelDefinition:
        ...

    def new_character(self, **data) -> BaseCharacter:
        character = self.sheet_type(
            ruleset_id=self.id, ruleset_version=self.version, **data
        )
        character._ruleset = self
        return character

    def load_character(self, data: dict) -> BaseCharacter:
        """Load the given character data with this ruleset.

        Returns:
            A character sheet of appropriate subclass.

        Raises:
            ValueError: if the character is not compatible with this ruleset.
                By default, characters are only comaptible with the ruleset they
                were originally written with.
        """
        updated_data = self.update_data(data)
        char = pydantic.parse_obj_as(self.sheet_type, updated_data)
        char._ruleset = self
        return char

    def update_data(self, data: dict) -> dict:
        """If the data is from a different but compatible rules version, update it.

        The default behavior is to reject any character data made with a different ruleset ID,
        and assume newer versions are backward (but not forward).

        Raises:
            ValueError: if the character is not compatible with this ruleset.
                By default, characters are only comaptible with the ruleset they
                were originally written with.
        """
        if data["ruleset_id"] != self.id:
            raise ValueError(
                f'Can not load character id={data["id"]}, ruleset={data["ruleset_id"]} with ruleset {self.id}'
            )
        if version.parse(self.version) < version.parse(data["ruleset_version"]):
            raise ValueError(
                f'Can not load character id={data["id"]}, ruleset={data["ruleset_id"]} v{data["ruleset_version"]}'
                f" with ruleset {self.id} v{self.version}"
            )
        return data

    def identifier_defined(self, identifier: Identifier) -> bool:
        """Check if the identifier is meaningful in the ruleset.

        By default, the space of identifiers is the set of feature IDs,
        the set of feature types, and anything else defined in the
        ruleset's name_overrides. Attributes will usually be listed there,
        so this should cover most cases. However, if you have other
        identifiers or attributes without display names, you may need
        to override this.
        """
        return (
            identifier in self.features
            or identifier in self.attribute_map()
            or identifier in self.builtin_identifiers
        )

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
    """

    id: str = pydantic.Field(default=uuid4)
    player_id: str | None = None
    character_name: str | None = None
    player_name: str | None = None
    events_played: float = 0.0
    currencies: dict[str, int] = pydantic.Field(default_factory=dict)
    flags: dict[str, FlagValues] = pydantic.Field(default_factory=dict)


class BaseCharacter(BaseModel, ABC):
    """Represents a character sheet.

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
    name: str | None = None
    features: dict[str, list[Purchase]] = pydantic.Field(default_factory=dict)

    metadata: CharacterMetadata = pydantic.Field(default_factory=CharacterMetadata)
    _ruleset: BaseRuleset | None = pydantic.PrivateAttr(default=None)

    def can_purchase(self, entry: Purchase | str) -> RulesDecision:
        return RulesDecision(success=False, reason="Not implemented")

    def purchase(self, entry: Purchase | str) -> RulesDecision:
        if isinstance(entry, str):
            entry = Purchase(id=entry)

        feature = self._ruleset.features[entry.id]
        entry.type = feature.type

        rd = self.can_purchase(entry)
        if rd and rd.needs_option:
            return RulesDecision(
                success=False,
                needs_option=True,
                reason="Option value required for purchase",
            )
        elif rd:
            entries = self.features.setdefault(entry.id, [])
            entries.append(entry)
        return rd

    def attributes(self) -> list[AttributeEntry]:
        return []

    def open_slots(self) -> list[Slot]:
        return []

    @property
    def purchases(self) -> Iterable[Purchase]:
        for entries in self.features.values():
            yield from entries

    def meets_requirements(self, requirements: Requirements) -> RulesDecision:
        meets_all = True
        messages: list[str] = []
        for req in utils.maybe_iter(requirements):
            if isinstance(req, str):
                # It's unlikely that an unparsed string gets here, but if so,
                # go ahead and parse it.
                req = PropExpression.parse(req)
            if not req.evaluate(self):
                # TODO: Extract failure messages
                meets_all = False
        if not meets_all:
            messages = ["Not all requirements are met"] + messages
        return RulesDecision(
            success=meets_all, reason="\n".join(messages) if messages else None
        )

    def get_prop(self, id) -> int:
        return 0

    def get_prop_max(self, id) -> int:
        return 0

    def has_prop(self, id) -> bool:
        return False

    def options_values_for_feature(
        self, feature_id: Identifier, exclude_taken: bool = False
    ) -> set[OptionValue]:
        """Retrieve the options valid for a feature for this character.

        Args:
            feature_id: Identifier of the feature to check.
            exclude_taken: If this character has already taken
                this feature, removes any
        """
        feature_def = self._ruleset.features[feature_id]
        option_def = feature_def.option
        if not option_def.values:
            return set()
        options_excluded: set[str] = set()
        if exclude_taken and (feature_entries := self.features.get(feature_id)):
            if not feature_def.multiple:
                # The feature can only have a single option and it already
                # has one, so no other options are legal.
                return set()
            options_excluded = {e.option for e in feature_entries if e.option}

        legal_values = set(option_def.values)
        if option_def.values_flag:
            # If a values flag is specified, check the character metadata to
            # see if additional legal values are provided. This will probably
            # be a list of strings, but handle other things as well. If a
            # value in the list is prefixed with "-" it is removed from the
            # legal value set.
            extra_values = self.metadata.flags.get(option_def.values_flag, [])
            if not isinstance(extra_values, list):
                extra_values = [extra_values]
            for value in (str(v) for v in extra_values):
                if value.startswith("-"):
                    legal_values.remove(value[1:])
                else:
                    legal_values.add(value)

        legal_values ^= options_excluded
        return legal_values

    def option_satisfies_definition(
        self,
        feature_id: Identifier,
        option_value: OptionValue,
        exclude_taken: bool = False,
    ) -> bool:
        feature_def = self._ruleset.features[feature_id]
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


class BaseAttributeDef(BaseModel):
    """Attributes that might appear on a character sheet.

    Attributes:
        id: The identifier of the attribute.
        name: The user-visible name of the attribute, if applicable.
        abbrev: The abbreviation of the attribute, if applicable.
        min_value: The lowest value for the attribute. If penalties
            reduce it below this value, it will display as this minimum.
        max_value: The highest value for the attribute. If bonuses
            push it above this value, it will display as this maximum.
        default_value: If the value may need to be displayed prior to the
            character having anything contributing to the value, what should
            be displayed or used?
        scoped: If this attribute will be scoped to a particular class, role, breed, etc
            instead of being a "global" attribute, mark this True.
        tiered: If this attribute represents multiple tiers of sub-attributes
            (spell levels, etc) mark this True.
        tier_names: If a tiered attribute's tiers have specific names, name them here.
        hidden: If True, will not be displayed by default.
    """

    id: Identifier
    name: str | None = None
    abbrev: str | None = None
    min_value: int | None = 0
    max_value: int | None = None
    default_value: int | None = None
    scoped: bool = False
    tiered: bool = False
    tier_names: list[str] | None = None
    hidden: bool = False
    is_tag: bool = False


class AttributeEntry(BaseModel):
    id: Identifier
    value: int
    scope: str | None = None


class Discount(BaseModel):
    id: Identifier = None
    cp: pydantic.PositiveInt | None = None
    per_rank: bool = True
    min: pydantic.NonNegativeInt = 1


class Slot(BaseModel):
    slot: Identifier
    choices: list[Identifiers] | None = None
    feature_type: Identifier | None = None
    discount: Discount | None = None
    limit: pydantic.PositiveInt = 1


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
        values_flag: If provided, names a flag that might appear in the
            character's metadata, which should be a list of strings.
            Values in this list are added to the provided values list
            unless they are prefixed with "-", in which case they signal
            the value should be removed. This allows staff to potentially
            add or remove values in the default ruleset for the playerbase
            or a specific character without needing to edit the ruleset.
    """

    short: bool = True
    freeform: bool = False
    values: set[str] | None = None
    values_flag: str | None = None


class Purchase(BaseModel):
    """Represents a specific purchase event for a character feature.


    Attributes:
        id: The ID of the feature definition. Note that some in some systems,
            certain features may have multiple instances on a character sheet.
            For example, in the d20 SRD, Weapon Focus can be taken multiple
            times, once per type of weapon.
        type: The feature type this represents. Mostly for convenience.
        ranks: Number of ranks to purchase. If the feature does not have ranks,
            use the default of "1".

        option: Got a skill in your larp called "Craftsman" or "Lore"
            or something where you fill in an arbitrary description of what
            sort of craft or lore you can do and it has no mechanical effect?
            Store it in this field, and the feature will be rendered as
            "Craftsman (Programmer)" or "Lore (Larp History)" or whatever.
            In the future this field may accept non-string values if more
            complex options are needed.
    """

    id: Identifier
    type: str | None = None
    ranks: pydantic.NonNegativeInt = 1
    option: str | None = None

    @property
    def option_id(self) -> str | None:
        if self.option:
            return f"{self.id}#{self.option.replace(' ', '_')}"
        else:
            return None


class RulesDecision(BaseModel):
    """
    Attributes:
        success: True if the mutation succeeds or query succeeds.
        needs_option: When returned from a query, will be True
            if the only thing missing from the feature is an option.
        reason: If success=False, explains why.

    Note that this object's truthiness is tied to its success attribute.
    """

    success: bool = False
    needs_option: bool = False
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.success


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
