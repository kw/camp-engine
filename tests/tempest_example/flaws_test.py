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


def test_basic_flaw(character: TempestCharacter):
    assert character.can_purchase("basic-flaw")
    assert character.purchase("basic-flaw")
    assert character.cp.flaw_award_cp == 1
    # can't buy it more than once
    assert not character.can_purchase("basic-flaw")


def test_exceed_flaw_cap(character: TempestCharacter):
    assert character.purchase("basic-flaw")
    # Even though this would put us over flaw cap, we can still buy it
    assert character.can_purchase("big-flaw")
    assert character.purchase("big-flaw")
    # ...but that doesn't put us over flaw cap
    assert character.cp.flaw_award_cp == 5


def test_conflicting_requirements(character: TempestCharacter):
    # If flaws have conflicting requirements, they can't both
    # be purchased.
    assert character.purchase("conflicting-mod-a")
    assert not character.can_purchase("conflicting-mod-b")
    assert not character.purchase("conflicting-mod-b")


def test_option_award_1(character: TempestCharacter):
    rd = character.can_purchase("option-award-flaw")
    assert rd.needs_option

    assert character.can_purchase("option-award-flaw#Something")
    assert character.purchase("option-award-flaw#Something")
    assert character.cp.flaw_award_cp == 1


def test_option_award_2(character: TempestCharacter):
    rd = character.can_purchase("option-award-flaw")
    assert rd.needs_option

    assert character.can_purchase("option-award-flaw#Something_Else")
    assert character.purchase("option-award-flaw#Something_Else")
    assert character.cp.flaw_award_cp == 2


def test_option_flag_1(character: TempestCharacter):
    rd = character.can_purchase("option-flag-flaw")
    assert rd.needs_option

    assert character.can_purchase("option-flag-flaw#Foo")
    assert character.purchase("option-flag-flaw#Foo")
    assert character.cp.flaw_award_cp == 1


def test_option_flag_2(character: TempestCharacter):
    rd = character.can_purchase("option-flag-flaw")
    assert rd.needs_option

    assert character.can_purchase("option-flag-flaw#Xyzzy")
    assert character.purchase("option-flag-flaw#Xyzzy")
    assert character.cp.flaw_award_cp == 2


def test_award_mod(character: TempestCharacter):
    # This flaw is worth 2, unless the character has basic-flaw,
    # in which case it's worth 1.
    assert character.purchase("award-mod-flaw")
    assert character.cp.flaw_award_cp == 2

    assert character.purchase("basic-flaw")
    assert character.cp.flaw_award_cp == 2


def test_overcome_flaw(character: TempestCharacter):
    character.purchase("basic-flaw")
    assert character.get_prop("basic-flaw") == 1
    assert character.cp.flaw_overcome_cp == 0

    character.flaws["basic-flaw"].overcame = True
    assert character.cp.flaw_award_cp == 1
    assert character.cp.flaw_overcome_cp == 3
    assert character.get_prop("basic-flaw") == 0


def test_remove_flaw(character: TempestCharacter):
    character.purchase("basic-flaw")
    assert character.get_prop("basic-flaw") == 1
    assert character.cp.flaw_overcome_cp == 0

    character.flaws["basic-flaw"].removed = True
    assert character.cp.flaw_award_cp == 1
    assert character.cp.flaw_overcome_cp == 0
    assert character.get_prop("basic-flaw") == 0


def test_no_cp_awarded(character: TempestCharacter):
    character.purchase("basic-flaw")
    assert character.get_prop("basic-flaw") == 1
    assert character.cp.flaw_overcome_cp == 0

    character.flaws["basic-flaw"].cp_awarded = False
    assert character.cp.flaw_award_cp == 0
    assert character.cp.flaw_overcome_cp == 0
    assert character.get_prop("basic-flaw") == 1
