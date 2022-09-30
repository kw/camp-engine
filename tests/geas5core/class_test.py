import pathlib

import pytest

from camp.engine import loader
from camp.engine.models import FeatureEntry
from camp.engine.rules.geas5.models import Character
from camp.engine.rules.geas5.models import Ruleset

EXAMPLES = pathlib.Path(__file__).parent.parent.parent / "examples"
GEASTEST = EXAMPLES / "geastest"


@pytest.fixture
def ruleset() -> Ruleset:
    return loader.load_ruleset(GEASTEST)


@pytest.fixture
def character(ruleset: Ruleset) -> Character:
    return ruleset.new_character()


def test_fighter(character: Character):
    entry = FeatureEntry(id="fighter", ranks=2)
    assert character.can_add_feature(entry)
    assert character.add_feature(entry)
    assert character.meets_requirements("fighter:2")
    assert character.meets_requirements("martial")
    assert character.meets_requirements("martial:2")
    assert character.meets_requirements("level:2")
    assert not character.meets_requirements("caster")
    assert not character.meets_requirements("caster:2")
    assert not character.meets_requirements("arcane:2")
    assert not character.meets_requirements("divine:2")


def test_wizard(character: Character):
    entry = FeatureEntry(id="wizard", ranks=2)
    assert character.can_add_feature(entry)
    assert character.add_feature(entry)
    assert character.meets_requirements("wizard:2")
    assert not character.meets_requirements("martial")
    assert not character.meets_requirements("martial:2")
    assert character.meets_requirements("level:2")
    assert character.meets_requirements("caster")
    assert character.meets_requirements("caster:2")
    assert character.meets_requirements("arcane:2")
    assert not character.meets_requirements("divine:2")


def test_druid(character: Character):
    entry = FeatureEntry(id="druid", ranks=2)
    assert character.can_add_feature(entry)
    assert character.add_feature(entry)
    assert character.meets_requirements("druid:2")
    assert not character.meets_requirements("martial")
    assert not character.meets_requirements("martial:2")
    assert character.meets_requirements("level:2")
    assert character.meets_requirements("caster")
    assert character.meets_requirements("caster:2")
    assert not character.meets_requirements("arcane:2")
    assert character.meets_requirements("divine:2")


def test_multiclass(character: Character):
    assert character.add_feature(FeatureEntry(id="fighter", ranks=3))
    assert character.add_feature(FeatureEntry(id="wizard", ranks=5))
    assert character.add_feature(FeatureEntry(id="druid", ranks=7))
    assert character.meets_requirements("martial:3")
    assert character.meets_requirements("martial$3")
    assert not character.meets_requirements("martial$4")
    assert character.meets_requirements("martial<4")
    assert not character.meets_requirements("martial<3")

    assert character.meets_requirements("arcane:5")
    assert character.meets_requirements("arcane$5")
    assert not character.meets_requirements("arcane$6")
    assert character.meets_requirements("arcane<7")
    assert not character.meets_requirements("arcane<3")

    assert character.meets_requirements("divine:7")
    assert character.meets_requirements("divine$7")
    assert not character.meets_requirements("divine$8")
    assert character.meets_requirements("divine<8")
    assert not character.meets_requirements("divine<3")

    assert character.meets_requirements("caster:12")
    assert character.meets_requirements("caster<15")
    assert character.meets_requirements("caster$7")
    assert not character.meets_requirements("caster$8")

    assert character.meets_requirements("level:15")
    assert not character.meets_requirements("level$15")
    assert character.meets_requirements("level$7")
    assert character.meets_requirements("level<16")