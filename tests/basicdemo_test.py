import pathlib
import shutil

import pytest

from camp.engine import loader

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"
BASICDEMO = EXAMPLES / "basicdemo"
BROKEN = EXAMPLES / "broken"


def test_load_ruleset():
    """Very basic loader test.

    1. Does the load return with no bad defs?
    2. Are features loaded?

    Other tests will cover more specific cases.
    """
    ruleset = loader.load_ruleset(BASICDEMO)
    assert not ruleset.bad_defs
    assert ruleset.features


def test_load_broken_ruleset():
    """Test that broken things are detected.

    A separate directory called "broken" contains
    feature definitions that are all broken in some way,
    so loading it should produce bad_defs but not features.
    """
    ruleset = loader.load_ruleset(BROKEN)
    assert ruleset.bad_defs
    assert not ruleset.features


@pytest.mark.parametrize("format", ["zip"])
def test_load_archive_ruleset(tmp_path_factory, format):
    """Zipfile loader test."""
    temp_base = tmp_path_factory.mktemp("camp-engine-test") / "basicdemo"
    archive = shutil.make_archive(temp_base, format, root_dir=BASICDEMO)
    ruleset = loader.load_ruleset(archive)
    assert not ruleset.bad_defs
    assert ruleset.features


def test_serialize_ruleset():
    """Test that the ruleset can be serialized and deserialized.

    For this to work, the ruleset must properly indicate its
    feature types on its ruleset subclass.
    """
    ruleset = loader.load_ruleset(BASICDEMO)
    ruleset_json = ruleset.dump()
    assert ruleset_json
    reloaded_ruleset = loader.deserialize_ruleset(ruleset_json)
    assert reloaded_ruleset.features
    assert ruleset == reloaded_ruleset
