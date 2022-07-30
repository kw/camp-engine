import json
import logging
import pathlib
import textwrap
import types
import typing
from copy import deepcopy

import pydantic
import yaml

from . import models
from . import utils

try:
    # TOML parser is part of the standard library starting at 3.11
    import tomllib  # type: ignore
except ImportError:
    import tomli as tomllib


# Generic type for a particular model class.
M = typing.TypeVar("M", bound=pydantic.BaseModel)
# Generic type representing a generator that returns models of type M or BadDefinitions.
ModelGenerator = typing.Generator[M, None, None]


def load_ruleset(path: str | pathlib.Path) -> models.BaseRuleset:
    """Load the specified ruleset from disk by path.

    The ruleset path must be a directory containg file named
    "ruleset" with a json, toml, or yaml/yml extension.

    """
    if isinstance(path, str):
        path = pathlib.Path(path)
    ruleset: models.BaseRuleset = None
    # First, look for the ruleset.
    for subpath in (p for p in path.iterdir() if p.is_file()):
        if subpath.match("ruleset.*"):
            logging.info("Found ruleset definition: %s", subpath)
            ruleset = _parse_ruleset(subpath)
            break
    if not ruleset:
        raise ValueError(f"Path {path} does not contain a ruleset definition.")
    feature_defs = ruleset.feature_model_types()
    if not _verify_feature_model_class(feature_defs):
        raise ValueError(
            textwrap.dedent(
                f"""Feature definition must be a pydantic model or union
                of pydantic models, but got `{feature_defs}` instead."""
            )
        )
    feature_dict: dict[str, models.BaseFeatureDef] = {}
    bad_defs: list[models.BadDefinition] = []
    for subpath in (p for p in path.iterdir() if p.is_dir()):
        for model in _parse_directory(subpath, feature_defs):
            if isinstance(model, models.BadDefinition):
                bad_defs.append(model)
            elif model.id in ruleset.features:
                bad_defs.append(
                    models.BadDefinition(
                        path=model.def_path,
                        data=model,
                        raw_data=None,
                        exception_type="NonUniqueId",
                        exception_message=f"Non-unique ID {model.id}",
                    )
                )
            else:
                feature_dict[model.id] = model
    return ruleset.copy(
        update={
            "features": ruleset.features | feature_dict,
            "bad_defs": bad_defs,
        }
    )


def deserialize_ruleset(json_data: str) -> models.BaseRuleset:
    ruleset_dict = json.loads(json_data)
    return _parse_ruleset_dict(ruleset_dict)


def _parse_ruleset(path: pathlib.Path) -> models.BaseRuleset:
    """Parse a ruleset from its ruleset.(toml|json|ya?ml) file.

    The actual type of the ruleset depends on its contents, but
    will always be a subclass of BaseRuleset.
    """
    ruleset_dict = list(_parse_raw(path))[0]
    return _parse_ruleset_dict(ruleset_dict)


def _parse_ruleset_dict(ruleset_dict: dict):
    if "ruleset_model_def" not in ruleset_dict:
        raise ValueError(
            "Invalid ruleset definition, does not specifiy ruleset_model_def"
        )
    ruleset_def: str = ruleset_dict["ruleset_model_def"]
    ruleset_model = utils.import_name(ruleset_def)
    if not issubclass(ruleset_model, models.BaseRuleset):
        raise ValueError(f"{ruleset_def} does not implement BaseRuleset")
    return pydantic.parse_obj_as(ruleset_model, ruleset_dict)


def _parse_directory(path: pathlib.Path, model: M, defaults=None) -> ModelGenerator:
    defaults = defaults.copy() if defaults else {}
    # Load defaults. There's proably not more than one, but if so, okay I guess?
    for subpath in path.glob("__defaults__.*"):
        for raw_defaults in _parse_raw(subpath):
            defaults.update(raw_defaults)
    # Now parse files based on the defaults.
    for subpath in (p for p in path.iterdir() if p.is_file()):
        if subpath.stem.startswith("_") or subpath.stem.startswith("."):
            # Ignore any other "special" files.
            # We may define some with meanings in the future.
            continue
        yield from _parse(subpath, model, defaults)
    # Now parse subdirectories, passing our current defaults up.
    for subpath in (p for p in path.iterdir() if p.is_dir()):
        yield from _parse_directory(subpath, model, defaults)


def _verify_feature_model_class(model: typing.Type) -> bool:
    if isinstance(model, types.UnionType):
        return all(_verify_feature_model_class(c) for c in model.__args__)
    elif issubclass(model, pydantic.BaseModel):
        return True
    return False


def _parse(path: pathlib.Path, model: M, defaults=None) -> ModelGenerator:
    count = 0
    for raw_data in _parse_raw(path):
        if "id" not in raw_data:
            raw_data["id"] = path.stem + (f"[{count}]" if count else "")
        if raw_data["id"] == "__defaults__":
            # A YAML stream might have embedded defaults.
            # Add them to our existing defaults and skip the entry.
            # Note that these only apply to this file.
            del raw_data["id"]
            defaults = _dict_merge(defaults, raw_data)
            continue
        count += 1
        try:
            data = _dict_merge(defaults, raw_data)
            data["def_path"] = str(path)
            yield pydantic.parse_obj_as(model, data)
        except ValueError as exc:
            yield models.BadDefinition(path, data, raw_data, exc)


def _dict_merge(a: dict | None, b: dict | None) -> dict:
    """Similar to copying 'a' and updating it with 'b'.

    This will be applied recursively to any sub-dicts in common.

    TODO: Or at least, it will do that when I care enough. For
    now it just slaps them together and does a deepcopy.
    """
    return deepcopy((a or {}) | (b or {}))


def _parse_raw(path: pathlib.Path) -> typing.Generator[dict, None, None]:
    match path.suffix:
        case ".toml":
            parser = _parse_toml
        case ".json":
            parser = _parse_json
        case ".yaml" | ".yml":
            parser = _parse_yaml
        case _:
            return
    yield from parser(path)


def _parse_toml(path: pathlib.Path) -> dict:
    with path.open("rb") as toml_file:
        yield tomllib.load(toml_file)


def _parse_json(path: pathlib.Path) -> dict:
    with path.open("rb") as json_file:
        yield json.load(json_file)


def _parse_yaml(path: pathlib.Path) -> dict:
    with path.open("rb") as yaml_file:
        yield from yaml.safe_load_all(yaml_file)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        ruleset = load_ruleset(sys.argv[1])
        if ruleset.bad_defs:
            print("Bad defs:")
            print(ruleset.bad_defs)
        else:
            print(f"Ruleset {ruleset.name} parsed successfully.")
            print("Features:")
            current_type = None
            for (id, feature) in sorted(
                ruleset.features.items(), key=lambda item: item[1].type
            ):
                if current_type != feature.type:
                    current_type = feature.type
                    friendly_type = ruleset.type_names.get(current_type, current_type)
                    print(f"Type: {friendly_type}")
                print(f"- {id}: {feature.name}")
