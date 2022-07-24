import json
import pathlib
import textwrap
import types
import typing
from copy import deepcopy
from importlib import import_module

import pydantic
import yaml

from . import base

try:
    # TOML parser is part of the standard library starting at 3.11
    import tomllib
except ImportError:
    import tomli as tomllib


# Generic type for a particular model class.
M = typing.TypeVar("M", bound=pydantic.BaseModel)
# The model class or union of classes to be parsed into models.
ModelDefinition = typing.Type[pydantic.BaseModel] | types.UnionType
# Generic type representing a generator that returns models of type M or BadDefinitions.
ModelGenerator = typing.Generator[M | base.BadDefinition, None, None]


def load_ruleset(path: str | pathlib.Path):
    if isinstance(path, str):
        path = pathlib.Path(path)
    ruleset: base.Ruleset = None
    # First, look for the ruleset.
    for subpath in (p for p in path.iterdir() if p.is_file()):
        if subpath.match("ruleset.*"):
            print("Found ruleset definition: ", subpath)
            ruleset = parse_ruleset(subpath)
            break
    if not ruleset:
        raise ValueError(f"Path {path} does not contain a ruleset definition.")
    feature_defs = import_model(ruleset.feature_model_def)
    for subpath in (p for p in path.iterdir() if p.is_dir()):
        for model in _parse_directory(subpath, feature_defs):
            if isinstance(model, base.BadDefinition):
                ruleset.bad_defs.append(model)
            elif model.id in ruleset.features:
                ruleset.bad_defs.append(
                    base.BadDefinition(
                        path=model.def_path,
                        data=model,
                        raw_data=None,
                        exception=RuntimeError(f"Non-unique ID {model.id}"),
                    )
                )
            else:
                ruleset.features[model.id] = model
    return ruleset


def _parse_directory(path: pathlib.Path, model: M, defaults=None) -> ModelGenerator:
    defaults = defaults.copy() if defaults else {}
    # Load defaults. There's proably not more than one.
    for subpath in path.glob("__defaults__.*"):
        for raw_defaults in parse_raw(subpath):
            defaults.update(raw_defaults)
    # Now parse files based on the defaults.
    for subpath in (p for p in path.iterdir() if p.is_file()):
        if subpath.stem.startswith("__"):
            # Ignore any "special" files at this point.
            continue
        yield from parse(subpath, model, defaults)
    # Now parse subdirectories, passing our current defaults up.
    for subpath in (p for p in path.iterdir() if p.is_dir()):
        yield from _parse_directory(subpath, model, defaults)


def import_model(model_path: str) -> ModelGenerator:
    try:
        module_name, attrib_name = model_path.rsplit(".", 1)
    except ValueError as exc:
        raise ImportError(f"{model_path} does not appear to be a dotted path") from exc
    module = import_module(module_name)
    model = getattr(module, attrib_name)
    if _verify_model_class(model):
        return model
    else:
        raise ValueError(
            textwrap.dedent(
                f"""Feature definition must be a pydantic model or union
                of pydantic models, but got `{model}` instead."""
            )
        )


def _verify_model_class(model: typing.Type) -> bool:
    if isinstance(model, types.UnionType):
        return all(_verify_model_class(c) for c in model.__args__)
    elif issubclass(model, pydantic.BaseModel):
        return True
    return False


def parse_ruleset(path: pathlib.Path) -> base.Ruleset:
    return list(parse(path, base.Ruleset))[0]


def parse(path: pathlib.Path, model: M, defaults=None) -> ModelGenerator:
    count = 0
    for raw_data in parse_raw(path):
        if "id" not in raw_data:
            raw_data["id"] = path.stem + (f"[{count}]" if count else "")
        if raw_data["id"] == "__defaults__":
            # A YAML stream might have embedded defaults.
            # Add them to our existing defaults and skip the entry.
            # Note that these only apply to this file.
            del raw_data["id"]
            defaults = dict_merge(defaults, raw_data)
            continue
        count += 1
        try:
            data = dict_merge(defaults, raw_data)
            data["def_path"] = str(path)
            yield pydantic.parse_obj_as(model, data)
        except ValueError as exc:
            yield base.BadDefinition(path, data, raw_data, exc)


def dict_merge(a: dict | None, b: dict | None) -> dict:
    """Similar to copying 'a' and updating it with 'b'.

    This will be applied recursively to any sub-dicts in common.

    TODO: Or at least, it will do that when I care enough. For
    now it just slaps them together and does a deepcopy.
    """
    return deepcopy((a or {}) | (b or {}))


def parse_raw(path: pathlib.Path) -> typing.Generator[dict, None, None]:
    match path.suffix:
        case ".toml":
            parser = parse_toml
        case ".json":
            parser = parse_json
        case ".yaml" | ".yml":
            parser = parse_yaml
        case _:
            return
    yield from parser(path)


def parse_toml(path: pathlib.Path) -> dict:
    with path.open("rb") as toml_file:
        yield tomllib.load(toml_file)


def parse_json(path: pathlib.Path) -> dict:
    with path.open("rb") as json_file:
        yield json.load(json_file)


def parse_yaml(path: pathlib.Path) -> dict:
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
