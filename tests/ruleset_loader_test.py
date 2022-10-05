import pathlib
import shutil

import pytest

from camp.engine import loader
from camp.engine import utils

BASEDIR = pathlib.Path(__file__).parent.parent
PATH_PARAMS = [
    pytest.param(BASEDIR / "examples" / "geastest", id="geastest"),
    pytest.param(BASEDIR / "repos" / "geas5core", id="geas5core"),
]

FAIL_TEMPLATE = """
Could not parse {path}

Parse failed with {exception_type}:
{exception_message}

Parsed data:
{data}
"""


@pytest.mark.parametrize("path", PATH_PARAMS)
def test_load_ruleset(path):
    """Very basic loader test.

    1. Does the load return with no bad defs?
    2. Are features loaded?

    Other tests will cover more specific cases.
    """
    ruleset = loader.load_ruleset(path)
    if ruleset.bad_defs:
        bd = ruleset.bad_defs[0]
        bd.data["description"] = "<...>"
        pytest.fail(
            FAIL_TEMPLATE.format(
                path=bd.path,
                exception_type=bd.exception_type,
                exception_message=bd.exception_message,
                data=utils.dump(bd.data, sort_keys=True, indent=4),
            ),
            pytrace=False,
        )
    assert ruleset.features


@pytest.mark.parametrize("path", PATH_PARAMS)
@pytest.mark.parametrize("format", ["zip"])
def test_load_archive_ruleset(path, format, tmp_path_factory):
    """Zipfile loader test."""
    temp_base = tmp_path_factory.mktemp("camp-engine-test") / "GEAS5CORE"
    archive = shutil.make_archive(temp_base, format, root_dir=path)
    ruleset = loader.load_ruleset(archive)
    assert not ruleset.bad_defs
    assert ruleset.features


@pytest.mark.parametrize("path", PATH_PARAMS)
def test_serialize_ruleset(path):
    """Test that the ruleset can be serialized and deserialized.

    For this to work, the ruleset must properly indicate its
    feature types on its ruleset subclass.
    """
    ruleset = loader.load_ruleset(path)
    ruleset_json = ruleset.dump()
    assert ruleset_json
    reloaded_ruleset = loader.deserialize_ruleset(ruleset_json)
    assert reloaded_ruleset.features
    assert ruleset == reloaded_ruleset
