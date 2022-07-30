from __future__ import annotations

import json
import types
import typing
from abc import ABC
from abc import abstractmethod
from uuid import uuid4

import pydantic

# The model class or union of classes to be parsed into models.
ModelDefinition = typing.Type[pydantic.BaseModel] | types.UnionType
FeatureId: typing.TypeAlias = str
FeatureIds: typing.TypeAlias = FeatureId | list[FeatureId] | None


class BaseFeatureDef(pydantic.BaseModel):
    id: FeatureId
    name: str
    type: str
    def_path: str | None = None

    class Config:
        allow_mutation = False

    @property
    def subfeatures(self) -> typing.Iterator[BaseFeatureDef]:
        """Provide any subfeatures present in this feature definition.

        Subfeatures might include things like a class feature that provides
        one of five possible benefits depending on your preferred combat style.
        Since these options are not used outside of the class, you may wish to
        define your feature language to include them inline in the class definition.
        """
        return []


class BadDefinition(pydantic.BaseModel):
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


class BaseRuleset(pydantic.BaseModel, ABC):
    id: str
    name: str
    version: str
    ruleset_model_def: str
    features: dict[FeatureId, BaseFeatureDef] = pydantic.Field(default_factory=dict)
    type_names: dict[str, str] = pydantic.Field(default_factory=dict)
    bad_defs: list[BadDefinition] = pydantic.Field(default_factory=list)

    @abstractmethod
    def feature_model_types(self) -> ModelDefinition:
        ...

    def new_character(self, id=None) -> CharacterSheet:
        if id is None:
            id = uuid4()
        return CharacterSheet(id=id, ruleset_id=self.id)

    def dump(self) -> str:
        return json.dumps(self.dict(by_alias=True))

    class Config:
        allow_mutation = False


class CharacterSheet(pydantic.BaseModel):
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
        features: The full set of a character's purchased features.
    """

    id: str
    ruleset_id: str
    name: str | None = None
    features: list[FeatureEntry] = pydantic.Field(default_factory=list)


class FeatureEntry(pydantic.BaseModel):
    """Represents an instance of a feature for a character.

    Attributes:
        id: The ID of the feature definition. Note that some in some systems,
            certain features may have multiple instances on a character sheet.
            For example, in the d20 SRD, Weapon Focus can be taken multiple
            times, once per type of weapon.
        ranks: If the feature has ranks or levels, the number of them currently
            held by the character.
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
        description: Got a skill in your larp called "Craftsman" or "Lore"
            or something where you fill in an arbitrary description of what
            sort of craft or lore you can do and it has no mechanical effect?
            Store it in this field, and the feature will be rendered as
            "Craftsman (Programmer)" or "Lore (Larp History)" or whatever.
            If your feature requires storing a paragraph because it lets you
            rewrite the incantations for your spells or something, put that
            in the `data` field.
    """

    id: FeatureId
    ranks: int | None = None
    slot: str | None = None
    currency: str | None = None
    cost: int | None = None
    description: str | None = None
