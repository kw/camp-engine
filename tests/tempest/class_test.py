from __future__ import annotations

import pathlib

import pytest

from camp.engine import loader
from camp.engine.rules.base_engine import CharacterController
from camp.engine.rules.base_engine import Engine
from camp.engine.rules.base_models import Purchase

EXAMPLES = pathlib.Path(__file__).parent.parent.parent / "examples"
GEASTEST = EXAMPLES / "geastest"


@pytest.fixture
def engine() -> Engine:
    return loader.load_ruleset(GEASTEST).engine


@pytest.fixture
def character(engine: Engine) -> CharacterController:
    return engine.new_character()


def test_fighter(character: CharacterController):
    entry = Purchase(id="fighter", ranks=2)
    assert character.can_purchase(entry)
    assert character.purchase(entry)
    assert character.meets_requirements("fighter:2")
    assert character.meets_requirements("martial")
    assert character.meets_requirements("martial:2")
    assert character.meets_requirements("level:2")
    assert not character.meets_requirements("caster")
    assert not character.meets_requirements("caster:2")
    assert not character.meets_requirements("arcane:2")
    assert not character.meets_requirements("divine:2")


def test_wizard(character: CharacterController):
    entry = Purchase(id="wizard", ranks=2)
    assert character.can_purchase(entry)
    assert character.purchase(entry)
    assert character.meets_requirements("wizard:2")
    assert not character.meets_requirements("martial")
    assert not character.meets_requirements("martial:2")
    assert character.meets_requirements("level:2")
    assert character.meets_requirements("caster")
    assert character.meets_requirements("caster:2")
    assert character.meets_requirements("arcane:2")
    assert not character.meets_requirements("divine:2")


def test_druid(character: CharacterController):
    entry = Purchase(id="druid", ranks=2)
    assert character.can_purchase(entry)
    assert character.purchase(entry)
    assert character.meets_requirements("druid:2")
    assert not character.meets_requirements("martial")
    assert not character.meets_requirements("martial:2")
    assert character.meets_requirements("level:2")
    assert character.meets_requirements("caster")
    assert character.meets_requirements("caster:2")
    assert not character.meets_requirements("arcane:2")
    assert character.meets_requirements("divine:2")


def test_multiclass(character: CharacterController):
    character.model.metadata.currencies["xp"] = 153  # XP required to be level 15
    assert character.purchase(Purchase(id="fighter", ranks=3))
    assert character.purchase(Purchase(id="wizard", ranks=5))
    assert character.purchase(Purchase(id="druid", ranks=7))
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


@pytest.mark.xfail(reason="Not yet implemented")
def test_spell_slots(character: CharacterController):
    character.purchase(Purchase(id="wizard", ranks=7))
    assert character.meets_requirements("spells:7")
    assert character.meets_requirements("spells@1:6")
    assert character.meets_requirements("spells@2:1")
    assert not character.meets_requirements("spells@3")
    assert character.meets_requirements("spells@1#arcane:6")
    assert not character.meets_requirements("spells@1#divine:6")
