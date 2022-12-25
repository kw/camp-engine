from __future__ import annotations

import json
import sys
from importlib import import_module
from typing import Any
from typing import Iterable
from typing import TypeVar

import pydantic


def import_name(name: str) -> Any:
    """Imports the specified thing.

    Args:
        name: A dotted name string of the form 'package.subpackage.attribute'.
              The specified package or subpackage will be imported by Python's
              import machinery if not already loaded, and the named attribute
              will be returned if present.

    Raises:
        ImportError: If the package is not importable.
        AttributeError: If the attribute is not retrievable.
    """
    try:
        module_name, attrib_name = name.rsplit(".", 1)
    except ValueError as exc:
        raise ImportError(f"{name} does not appear to be a dotted path") from exc
    if module_name in sys.modules:
        module = sys.modules[module_name]
    else:
        module = import_module(module_name)
    return getattr(module, attrib_name)


_T = TypeVar("_T")


def maybe_iter(value: str | _T | list[str | _T] | None) -> Iterable[str | _T]:
    if not value:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        yield from value
    else:
        yield value


def table_lookup(table: dict[int, _T], key: int) -> _T:
    best: _T | None = None
    for k in sorted(table.keys()):
        if best is None or k <= key:
            best = table[k]
        elif k > key:
            break
    if best is None:
        raise ValueError("Did not find any values in table")
    return best


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


def dump(data: pydantic.BaseModel | dict, as_json=True, *args, **kwargs) -> str | dict:
    if not isinstance(data, dict):
        data = data.dict(by_alias=True, exclude_unset=True, exclude_none=True)
    if as_json:
        return json.dumps(data, cls=JSONEncoder, *args, **kwargs)
    else:
        return data
