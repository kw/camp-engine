from __future__ import annotations

import json
import re
import types
import typing
from abc import ABC
from abc import abstractmethod
from abc import abstractproperty
from typing import Iterable
from typing import Type
from typing import TypeAlias
from uuid import uuid4

import pydantic
from packaging import version

from . import utils

NON_WORD = re.compile(r"[^\w-]+")

# The model class or union of classes to be parsed into models.
ModelDefinition: TypeAlias = Type[pydantic.BaseModel] | types.UnionType
Identifier: TypeAlias = str
Identifiers: TypeAlias = Identifier | list[Identifier] | None
Requirements: TypeAlias = str | list[str] | None
FlagValue: TypeAlias = bool | int | float | str
FlagValues: TypeAlias = list[FlagValue] | FlagValue
OptionValue: TypeAlias = str


class BaseModel(pydantic.BaseModel):
    class Config:
        extra = pydantic.Extra.forbid


class BaseFeatureDef(BaseModel):
    id: Identifier
    name: str
    type: str
    requires: Requirements = None
    def_path: str | None = None
    tags: set[str] = pydantic.Field(default_factory=set)
    description: str | None = None
    option: OptionDef | None = None
    multiple: bool = False

    @classmethod
    def default_name(cls) -> str:
        try:
            return cls._type_key().title()
        except Exception:
            return str(cls)

    @classmethod
    def type_key(cls) -> str:
        return cls.__fields__["type"].type_.args[0]

    @property
    def subfeatures(self) -> Iterable[BaseFeatureDef]:
        """Provide any subfeatures present in this feature definition.

        Subfeatures might include things like a class feature that provides
        one of five possible benefits depending on your preferred combat style.
        Since these options are not used outside of the class, you may wish to
        define your feature language to include them inline in the class definition.
        """
        return []

    def post_validate(self, ruleset: BaseRuleset) -> None:
        ruleset.validate_identifiers(self.requires)


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


class AttributeDef(BaseModel):
    id: str
    name: str
    base: int | None = None
    min: int | None = None
    max: int | None = None
    scoped: bool = False
    currency: bool = False


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

    def dump(self) -> str:
        return json.dumps(
            self.dict(by_alias=True, exclude_unset=True, exclude_none=True),
            cls=utils._JSONEncoder,
        )

    def identifier_defined(self, identifier: Identifier) -> bool:
        """Check if the identifier is meaningful in the ruleset.

        By default, the space of identifiers is the set of feature IDs,
        the set of feature types, and anything else defined in the
        ruleset's name_overrides. Attributes will usually be listed there,
        so this should cover most cases. However, if you have other
        identifiers or attributes without display names, you may need
        to override this.
        """
        return identifier in self.features or identifier in self._display_names

    def validate_identifiers(self, identifiers: Identifiers) -> None:
        id_list: list[str]
        match identifiers:
            case str(identifiers):
                id_list = [identifiers]
            case list(identifiers):
                id_list = identifiers
            case None:
                id_list = []
            case _:
                raise TypeError(f"Unsupport identifiers: {identifiers}")
        # Identifiers provided may have extra syntax in the context
        # of requirements or grants. For example, "craftsman#Artist",
        # "alchemy>3", "!magic-insensitive"
        for req in id_list:
            # TODO: We'll need a more general parser later.
            id, *tail = NON_WORD.split(req)
            # If there's a prefix operator, the first result will be empty, skip it.
            if tail and not id:
                id, *tail = tail
            if not id:
                raise ValueError(f'Invalid identifier "{req}"')
            if not self.identifier_defined(id):
                raise ValueError(f'Required identifier "{id}" not found in ruleset.')


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
    metadata: CharacterMetadata = pydantic.Field(default_factory=CharacterMetadata)
    _ruleset: BaseRuleset | None = pydantic.PrivateAttr(default=None)
    _cache: dict = pydantic.PrivateAttr(default_factory=dict)

    @abstractmethod
    def features(self) -> Iterable[FeatureEntry]:
        ...

    @abstractmethod
    def get_feature(self, id) -> list[FeatureEntry] | None:
        ...

    def can_add_feature(self, entry: FeatureEntry | str) -> RulesDecision:
        return RulesDecision(success=False, reason="Not implemented")

    def add_feature(self, entry: FeatureEntry | str) -> RulesDecision:
        return RulesDecision(success=False, reason="Not implemented")

    def attributes(self) -> list[AttributeEntry]:
        return []

    def open_slots(self) -> list[SlotEntry]:
        return []

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
        if exclude_taken and (feature_entries := self.get_feature(feature_id)):
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


class AttributeEntry(BaseModel):
    id: Identifier
    value: int
    max_value: int | None = None
    scope: str | None = None


class SlotEntry(BaseModel):
    id: Identifier
    feature_type: str
    requires: Requirements = None
    immediate: bool = False


class FeatureSource(BaseModel):
    """
    Attributes:
        ranks: How many ranks were acquired from this source. If the
            feature doesn't have ranks, this is blank.
        slot: If the feature occupies a slot, the slot ID.
        currency: If the feature was purchased, which currency was used?
            Some features may be purchased with alternative currencies, such
            as Roles in Geas 5 that can be purchased with either CP or SP.
        cost: If the feature was purchased with a currency and the system
            needs to remember the cost, it will be stored here. Some systems
            have variable costs for skills depending on, say, the
            character's chosen class, and changing class retroactively changes
            the cost of already purchased skills, leading to a deficit or
            surplus of currency; these systems do not need to remember the cost.
            Meanwhile, other systems may only apply cost changes going forward,
            so the cost of previously purchased items needs to be stored. And
            in some cases, a system may generally do one thing but throw you
            a curve ball, like that one option in Geas 5 Core that has a
            different cost depending on what level you are when you initially
            purchase it.
    """

    ranks: int | None = None
    slot: str | None = None
    currency: str | None = None
    cost: int | None = None


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


class FeatureEntry(BaseModel):
    """Represents an instance of a feature for a character.

    Attributes:
        id: The ID of the feature definition. Note that some in some systems,
            certain features may have multiple instances on a character sheet.
            For example, in the d20 SRD, Weapon Focus can be taken multiple
            times, once per type of weapon.
        ranks: If the feature has ranks or levels, the number of them currently
            held by the character.

        option: Got a skill in your larp called "Craftsman" or "Lore"
            or something where you fill in an arbitrary description of what
            sort of craft or lore you can do and it has no mechanical effect?
            Store it in this field, and the feature will be rendered as
            "Craftsman (Programmer)" or "Lore (Larp History)" or whatever.
            In the future this field may accept non-string values if more
            complex options are needed.
    """

    id: Identifier
    ranks: int | None = None
    sources: list[FeatureSource] = pydantic.Field(default_factory=list)
    option: str | None = None


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
