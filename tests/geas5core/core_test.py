import pathlib
import shutil

import pytest

from camp.engine import loader

EXAMPLES = pathlib.Path(__file__).parent.parent.parent / "examples"
GEASTEST = EXAMPLES / "geastest"


def test_load_ruleset():
    """Very basic loader test.

    1. Does the load return with no bad defs?
    2. Are features loaded?

    Other tests will cover more specific cases.
    """
    ruleset = loader.load_ruleset(GEASTEST)
    assert not ruleset.bad_defs
    assert ruleset.features


@pytest.mark.parametrize("format", ["zip"])
def test_load_archive_ruleset(tmp_path_factory, format):
    """Zipfile loader test."""
    temp_base = tmp_path_factory.mktemp("camp-engine-test") / "geastest"
    archive = shutil.make_archive(temp_base, format, root_dir=GEASTEST)
    ruleset = loader.load_ruleset(archive)
    assert not ruleset.bad_defs
    assert ruleset.features


def test_serialize_ruleset():
    """Test that the ruleset can be serialized and deserialized.

    For this to work, the ruleset must properly indicate its
    feature types on its ruleset subclass.
    """
    ruleset = loader.load_ruleset(GEASTEST)
    ruleset_json = ruleset.dump()
    assert ruleset_json
    reloaded_ruleset = loader.deserialize_ruleset(ruleset_json)
    assert reloaded_ruleset.features
    assert ruleset == reloaded_ruleset
