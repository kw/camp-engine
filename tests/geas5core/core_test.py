import pathlib

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
