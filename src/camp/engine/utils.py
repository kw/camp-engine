from __future__ import annotations

import sys
from importlib import import_module
from typing import Any


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