from __future__ import annotations

import json
import sys
from collections import defaultdict
from importlib import import_module
from typing import Any
from typing import Iterable
from typing import TypeVar


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


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


class Aggregator:
    _MAX = ":max_{}"
    _cache: defaultdict[str, int]

    def __init__(self):
        self._cache = defaultdict(lambda: 0)

    def aggregate(self, prop: str, value: int, do_max: bool = True):
        self._cache[prop] += value
        if do_max:
            max_prop = self._MAX.format(prop)
            if value > self._cache[max_prop]:
                self._cache[max_prop] = value

    def get(self, prop: str) -> int:
        return self._cache[prop]

    def get_max(self, prop: str) -> int:
        return self._cache[self._MAX.format(prop)]
