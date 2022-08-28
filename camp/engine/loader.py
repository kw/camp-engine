import json
import pathlib
import textwrap
import types
import typing
import zipfile
from copy import deepcopy

import pydantic
import yaml

from . import models
from . import utils

try:
    # TOML parser is part of the standard library starting at 3.11
    import tomllib  # type: ignore[reportMissingImports]
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


# Generic type for a particular model class.
M = typing.TypeVar("M", bound=pydantic.BaseModel)
# Generic type representing a generator that returns models of type M or BadDefinitions.
ModelGenerator = typing.Generator[M, None, None]

PathLike = pathlib.Path | zipfile.Path


def load_ruleset(
    path: str | PathLike, with_bad_defs: bool = True
) -> models.BaseRuleset:
    """Load the specified ruleset from disk by path.

    The ruleset path must be a directory containg file named
    "ruleset" with a json, toml, or yaml/yml extension.

    Args:
        path: Path to a directory that contains a ruleset file.
            Alternatively, a path to a zipfile that contains a ruleset
            file and additional ruleset data.
        with_bad_defs: If true (the default), will not raise an exception
            if a feature definition file has a bad definition. Instead,
            the returned ruleset will have its `bad_defs` property populated
            with BadDefinition models.
    """
    if isinstance(path, str):
        if path.endswith(".zip"):
            path = zipfile.Path(zipfile.ZipFile(path))
        else:
            path = pathlib.Path(path)
    # First, look for the ruleset.
    ruleset_path = _find_file(path, stem="ruleset", depth=1)
    if not ruleset_path:
        raise ValueError(f"No ruleset file found within {path}")
    ruleset = _parse_ruleset(ruleset_path)
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
    for subpath in _iter_dirs(path):
        for model in _parse_directory(
            subpath, feature_defs, with_bad_defs=with_bad_defs
        ):
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
    ruleset = ruleset.copy(
        update={
            "features": ruleset.features | feature_dict,
            "bad_defs": bad_defs,
        }
    )
    broken_features: set[str] = set()
    for id, feature in ruleset.features.items():
        try:
            feature.post_validate(ruleset)
        except Exception as exc:
            ruleset.bad_defs.append(
                models.BadDefinition(
                    path=feature.def_path,
                    data=feature.json(),
                    raw_data=None,
                    exception_type=repr(type(exc)),
                    exception_message=str(exc),
                )
            )
            broken_features.add(id)
    for id in broken_features:
        del ruleset.features[id]
    return ruleset


def deserialize_ruleset(json_data: str) -> models.BaseRuleset:
    ruleset_dict = json.loads(json_data)
    return _parse_ruleset_dict(ruleset_dict)


def _parse_ruleset(path: PathLike) -> models.BaseRuleset:
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


def _parse_directory(
    path: PathLike, model: M, with_bad_defs: bool = True, defaults=None
) -> ModelGenerator:
    defaults = defaults.copy() if defaults else {}
    # Load defaults. There's proably not more than one, but if so, okay I guess?
    for subpath in _iter_files(path, stem="__defaults__"):
        for raw_defaults in _parse_raw(subpath):
            defaults.update(raw_defaults)
    # Now parse files based on the defaults.
    for subpath in _iter_files(path):
        stem = _stem(subpath)
        if stem.startswith("_") or stem.startswith("."):
            # Ignore any other "special" files.
            # We may define some with meanings in the future.
            continue
        yield from _parse(
            subpath, model, with_bad_defs=with_bad_defs, defaults=defaults
        )
    # Now parse subdirectories, passing our current defaults up.
    for subpath in _iter_dirs(path):
        yield from _parse_directory(
            subpath, model, with_bad_defs=with_bad_defs, defaults=defaults
        )


def _iter_dirs(path: PathLike) -> typing.Generator[PathLike, None, None]:
    for subpath in (p for p in path.iterdir() if p.is_dir()):
        yield subpath


def _iter_files(
    path: PathLike, stem=None, suffix=None
) -> typing.Generator[PathLike, None, None]:
    for subpath in (p for p in path.iterdir() if p.is_file()):
        if stem and _stem(subpath) != stem:
            continue
        if suffix and not _suffix(subpath) != suffix:
            continue
        yield subpath


def _find_file(path: PathLike, stem=None, suffix=None, depth=0) -> PathLike | None:
    for subpath in _iter_files(path, stem=stem, suffix=suffix):
        return subpath

    if depth >= 1:
        for subpath in _iter_dirs(path):
            recur_path = _find_file(subpath, stem=stem, suffix=suffix, depth=depth - 1)
            if recur_path:
                return recur_path
    return None


def _stem(path: PathLike) -> str:
    if isinstance(path, zipfile.Path):
        return path.filename.stem  # type: ignore[attr-defined]
    return path.stem


def _suffix(path: PathLike) -> str:
    if isinstance(path, zipfile.Path):
        return path.filename.suffix  # type: ignore[attr-defined]
    return path.suffix


def _verify_feature_model_class(model: models.ModelDefinition) -> bool:
    if isinstance(model, types.UnionType):
        return all(_verify_feature_model_class(c) for c in model.__args__)
    elif issubclass(model, pydantic.BaseModel):
        return True
    return False


def _parse(
    path: PathLike, model: M, with_bad_defs: bool = True, defaults=None
) -> ModelGenerator:
    count = 0
    for raw_data in _parse_raw(path):
        if "id" not in raw_data:
            raw_data["id"] = _stem(path) + (f"[{count}]" if count else "")
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
        except pydantic.ValidationError as exc:
            if with_bad_defs:
                yield models.BadDefinition(
                    path=str(path),
                    data=data,
                    raw_data=raw_data,
                    exception_type=repr(type(exc)),
                    exception_message=str(exc),
                )
            else:
                raise


def _dict_merge(a: dict | None, b: dict | None) -> dict:
    """Similar to copying 'a' and updating it with 'b'.

    This will be applied recursively to any sub-dicts in common.

    TODO: Or at least, it will do that when I care enough. For
    now it just slaps them together and does a deepcopy.
    """
    return deepcopy((a or {}) | (b or {}))


def _parse_raw(path: PathLike) -> typing.Generator[dict, None, None]:
    match _suffix(path):
        case ".toml":
            parser = _parse_toml
        case ".json":
            parser = _parse_json
        case ".yaml" | ".yml":
            parser = _parse_yaml
        case _:
            return
    yield from parser(path)


def _parse_toml(path: PathLike) -> typing.Generator[dict, None, None]:
    with path.open("rb") as toml_file:
        yield tomllib.load(toml_file)


def _parse_json(path: PathLike) -> typing.Generator[dict, None, None]:
    with path.open("rb") as json_file:
        yield json.load(json_file)


def _parse_yaml(path: PathLike) -> typing.Generator[dict, None, None]:
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
