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


def test_add_basic_skill(character: CharacterController):
    assert character.can_purchase("basic-skill")
    assert character.purchase("basic-skill")
    assert character.meets_requirements("basic-skill")


def test_remove_skill(character: CharacterController):
    character.purchase("basic-skill")
    assert character.can_purchase("basic-skill:-1")
    assert character.purchase("basic-skill:-1")
    assert not character.meets_requirements("basic-skill")


def test_add_basic_feature_twice(character: CharacterController):
    character.purchase("basic-skill")
    assert not character.can_purchase("basic-skill")
    assert not character.purchase("basic-skill")


def test_one_requirement_missing(character: CharacterController):
    assert not character.can_purchase("one-requirement")
    assert not character.purchase("one-requirement")


def test_two_requirements_missing(character: CharacterController):
    assert not character.can_purchase("two-requirements")
    assert not character.purchase("two-requirements")


def test_two_requirements_met(character: CharacterController):
    assert character.purchase("basic-skill")
    assert character.purchase("one-requirement")
    assert not character.can_purchase("two-requirements")
    assert character.purchase("granted-skill")
    assert character.purchase("two-requirements")


def test_one_requirement_met(character: CharacterController):
    character.purchase("basic-skill")
    assert character.can_purchase("one-requirement")
    assert character.purchase("one-requirement")


@pytest.mark.xfail
def test_remove_requirement(character: CharacterController):
    """You can't sell back a skill if another skill depends on it."""
    character.purchase("basic-skill")
    character.purchase("one-requirement")
    assert not character.can_purchase("basic-skill:-1")
    assert not character.purchase("basic-skill:-1")


def test_erroneous_option_provided(character: CharacterController):
    """Skill can't be added with an option if it does not define options."""
    entry = Purchase(id="basic-skill", option="Foo")
    assert not character.can_purchase(entry)
    assert not character.purchase(entry)


def test_option_values_required_freeform_prohibited(character: CharacterController):
    """If a skill option requires values, the option must be in that list."""
    entry = Purchase(id="specific-options", option="Fifty Two")
    assert not character.can_purchase(entry)
    assert not character.purchase(entry)


def test_option_values_required_freeform_allowed(character: CharacterController):
    """If a skill option requires values, the option must be in that list."""
    entry = Purchase(id="free-text", option="Fifty Two")
    assert character.can_purchase(entry)
    assert character.purchase(entry)


def test_option_values_provided(character: CharacterController):
    """If a skill option requires values, an option from that list works."""
    entry = Purchase(id="specific-options", option="Two")
    assert character.can_purchase(entry)
    assert character.purchase(entry)


def test_option_single_allowed(character: CharacterController):
    """If a skill allows an option but does not allow multiple selection...

    Only accept a single skill entry for it.
    """
    entry = Purchase(id="single-option", option="Rock")
    assert character.can_purchase(entry)
    assert character.purchase(entry)
    assert not character.can_purchase("single-option")
    assert not character.can_purchase("single-option#Paper")


def test_option_values_flag(character: CharacterController):
    """If a skill with a value option specifies a values flag, additional legal values
    can be passed in via that metadata flag.
    """
    character.model.metadata.flags["More Specific Options"] = ["Four", "Five", "Six"]
    entry = Purchase(id="specific-options", option="Five")
    assert character.can_purchase(entry)
    assert character.purchase(entry)


def test_multiple_option_skill_without_option(character: CharacterController):
    """If a multiple-purchase skill (no freeform) requires an option,

    1) can_add_feature returns true if it isn't given an option, but
        it returns false if all options are exhausted
    2) Even if it returns true, add_feature fails if the option is left out.

    The return value of can_add_feature will indicate that an option is needed.
    """
    fid = "specific-options"
    rd = character.can_purchase(fid)
    assert not rd.success and rd.needs_option
    assert not character.purchase(fid)
    character.purchase(Purchase(id=fid, option="One"))
    character.purchase(Purchase(id=fid, option="Two"))
    rd = character.can_purchase(fid)
    assert not rd.success and rd.needs_option
    assert not character.purchase(fid)
    assert character.purchase(Purchase(id=fid, option="Three"))
    assert not character.can_purchase(fid)
    options = character.get_options(fid)
    assert options == {"One": 1, "Two": 1, "Three": 1}
