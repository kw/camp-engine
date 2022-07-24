from __future__ import annotations

import typing
from dataclasses import dataclass

import pydantic

FeatureId: typing.TypeAlias = str
FeatureIds: typing.TypeAlias = FeatureId | list[FeatureId] | None


class BaseFeature(pydantic.BaseModel):
    id: FeatureId
    name: str
    def_path: str
    type: str

    class Config:
        allow_mutation = False

    @property
    def subfeatures(self) -> typing.Iterator[BaseFeature]:
        """Provide any subfeatures present in this feature definition.

        Subfeatures might include things like a class feature that provides
        one of five possible benefits depending on your preferred combat style.
        Since these options are not used outside of the class, you may wish to
        define your feature language to include them inline in the class definition.
        """
        return []


@dataclass
class BadDefinition:
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
    exception: Exception


class Ruleset(pydantic.BaseModel):
    id: str
    name: str
    version: str
    feature_model_def: str
    features: dict[FeatureId, BaseFeature] = pydantic.Field(default_factory=dict)
    type_names: dict[str, str] = pydantic.Field(default_factory=dict)
    _bad_defs: list[BadDefinition] = pydantic.PrivateAttr(default_factory=list)

    @property
    def bad_defs(self) -> list[BadDefinition]:
        return self._bad_defs

    @bad_defs.setter
    def bad_defs(self, value: list[BadDefinition]) -> None:
        self._bad_defs = value

    class Config:
        allow_mutation = False
