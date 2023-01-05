from __future__ import annotations

import pathlib

import pytest

from camp.engine import loader
from camp.engine.rules.base_engine import Engine
from camp.engine.rules.tempest.engine import TempestCharacter
from camp.engine.rules.tempest.engine import TempestEngine

EXAMPLES = pathlib.Path(__file__).parent.parent.parent / "examples"
GEASTEST = EXAMPLES / "geastest"


@pytest.fixture
def engine() -> TempestEngine:
    engine = loader.load_ruleset(GEASTEST).engine
    if not isinstance(engine, TempestEngine):
        raise Exception("Example ruleset does not specify expected engine")
    return engine


@pytest.fixture
def character(engine: Engine) -> TempestCharacter:
    return engine.new_character()


@pytest.mark.skip
def test_creation_only_perks(character: TempestCharacter):
    # TODO: Implement this test when we implement the charater creation flag.
    pass


def test_basic_perk(character: TempestCharacter):
    assert character.can_purchase("basic-perk")
    assert character.purchase("basic-perk")
    assert character.cp.spent_cp == 1


def test_advanced_perk(character: TempestCharacter):
    """Perks with requirements work as expected."""
    assert not character.can_purchase("advanced-perk")
    character.purchase("basic-perk")
    assert character.can_purchase("advanced-perk")
    assert character.purchase("advanced-perk")
    assert character.cp.spent_cp == 3


def test_grants_bonus_lp(character: TempestCharacter):
    """Some perks grant bonus life points."""
    starting_lp = character.lp.value
    assert character.purchase("grants-bonus-lp")
    assert character.lp.value == starting_lp + 3


def test_skill_discount(character: TempestCharacter):
    character.purchase("skill-discount-perk")

    base_cp = character.cp.spent_cp
    assert character.purchase("basic-skill")
    # basic-skill only costs 1, so the discount doesn't help.
    assert character.cp.spent_cp == base_cp + 1

    # But one-requirement costs 2, so this'll be cheaper
    assert character.purchase("one-requirement")
    assert character.cp.spent_cp == base_cp + 2


def test_perk_discount(character: TempestCharacter):
    character.purchase("perk-discount-perk")

    base_cp = character.cp.spent_cp
    assert character.purchase("basic-perk")
    # basic-perk only costs 1, so the discount doesn't help
    assert character.cp.spent_cp == base_cp + 1

    # But advanced-perk costs 2, so this'll be cheaper
    assert character.purchase("advanced-perk")
    assert character.cp.spent_cp == base_cp + 2
