import pathlib

import pytest

from camp.engine import loader
from camp.engine.models import FeatureEntry
from camp.engine.rules.geas5 import rules
from camp.engine.rules.geas5.models import Character
from camp.engine.rules.geas5.models import Ruleset

EXAMPLES = pathlib.Path(__file__).parent.parent.parent / "examples"
GEASTEST = EXAMPLES / "geastest"


@pytest.fixture
def ruleset() -> Ruleset:
    return loader.load_ruleset(GEASTEST)


@pytest.fixture
def new_character(ruleset: Ruleset) -> Character:
    return ruleset.new_character()


def test_add_basic_skill(new_character: Character):
    entry = FeatureEntry(id="basic-skill")
    assert rules.can_add_feature(new_character, entry)
    assert rules.add_feature(new_character, entry)


def test_add_basic_feature_twice(new_character: Character):
    entry = FeatureEntry(id="basic-skill")
    rules.add_feature(new_character, entry)
    assert not rules.can_add_feature(new_character, entry.copy())
    assert not rules.add_feature(new_character, entry.copy())


@pytest.mark.xfail
def test_one_requirement_missing(new_character: Character):
    entry = FeatureEntry(id="one-requirement")
    assert not rules.can_add_feature(new_character, entry)
    assert not rules.add_feature(new_character, entry)


def test_one_requirement_met(new_character: Character):
    rules.add_feature(new_character, FeatureEntry(id="basic-skill"))
    entry = FeatureEntry(id="one-requirement")
    assert rules.can_add_feature(new_character, entry)
    assert rules.add_feature(new_character, entry)
