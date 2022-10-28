import pathlib

import pytest

from camp.engine import loader
from camp.engine.models import Purchase
from camp.engine.models import RulesDecision
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


def test_add_basic_skill(character: Character):
    assert character.can_purchase("basic-skill")
    assert character.purchase("basic-skill")


def test_add_basic_feature_twice(character: Character):
    character.purchase("basic-skill")
    assert not character.can_purchase("basic-skill")
    assert not character.purchase("basic-skill")


def test_one_requirement_missing(character: Character):
    assert not character.can_purchase("one-requirement")
    assert not character.purchase("one-requirement")


def test_two_requirements_missing(character: Character):
    assert not character.can_purchase("two-requirements")
    assert not character.purchase("two-requirements")


def test_two_requirements_met(character: Character):
    assert character.purchase("basic-skill")
    assert character.purchase("one-requirement")
    assert not character.can_purchase("two-requirements")
    assert character.purchase("granted-skill")
    assert character.purchase("two-requirements")


def test_one_requirement_met(character: Character):
    character.purchase("basic-skill")
    assert character.can_purchase("one-requirement")
    assert character.purchase("one-requirement")


def test_erroneous_option_provided(character: Character):
    """Skill can't be added with an option if it does not define options."""
    entry = Purchase(id="basic-skill", option="Foo")
    assert not character.can_purchase(entry)
    assert not character.purchase(entry)


def test_option_values_required_freeform_prohibited(character: Character):
    """If a skill option requires values, the option must be in that list."""
    entry = Purchase(id="specific-options", option="Fifty Two")
    assert not character.can_purchase(entry)
    assert not character.purchase(entry)


def test_option_values_provided(character: Character):
    """If a skill option requires values, an option from that list works."""
    entry = Purchase(id="specific-options", option="Two")
    assert character.can_purchase(entry)
    assert character.purchase(entry)


def test_option_single_allowed(character: Character):
    """If a skill allows an option but does not allow multiple selection...

    Only accept a single skill entry for it.
    """
    entry = Purchase(id="single-option", option="Rock")
    assert character.can_purchase(entry)
    assert character.purchase(entry)
    assert not character.can_purchase("single-option")
    assert not character.can_purchase(Purchase(id="single-option", option="Paper"))


def test_option_values_flag(character: Character):
    """If a skill with a value option specifies a values flag, additional legal values
    can be passed in via that metadata flag.
    """
    character.metadata.flags["More Specific Options"] = ["Four", "Five", "Six"]
    entry = Purchase(id="specific-options", option="Five")
    assert character.can_purchase(entry)
    assert character.purchase(entry)


def test_multiple_option_skill_without_option(character: Character):
    """If a multiple-purchase skill (no freeform) requires an option,

    1) can_add_feature returns true if it isn't given an option, but
        it returns false if all options are exhausted
    2) Even if it returns true, add_feature fails if the option is left out.

    The return value of can_add_feature will indicate that an option is needed.
    """
    fid = "specific-options"
    success_but_needs_option = RulesDecision(success=True, needs_option=True)
    assert character.can_purchase(fid) == success_but_needs_option
    assert not character.purchase(fid)
    character.purchase(Purchase(id=fid, option="One"))
    character.purchase(Purchase(id=fid, option="Two"))
    assert character.can_purchase(fid) == success_but_needs_option
    assert character.purchase(Purchase(id=fid, option="Three"))
    assert not character.can_purchase(fid)
    options = {e.option for e in character.features.get(fid, [])}
    assert options == {"One", "Two", "Three"}
