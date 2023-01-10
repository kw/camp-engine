"""Basic tests for the character controller."""
from __future__ import annotations

import pathlib

import pytest

from camp.engine import loader
from camp.engine.rules.base_engine import Engine
from camp.engine.rules.tempest.controllers.character_controller import TempestCharacter
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


def test_list_taken_features(character: TempestCharacter):
    character.purchase("basic-skill:3")
    character.purchase("basic-perk")
    features = {f.id: f.ranks for f in character.list_features(taken=True)}
    assert features == {
        "basic-skill": 3,
        "basic-perk": 1,
    }


def test_list_unavailable_features(character: TempestCharacter):
    character.purchase("basic-skill")
    character.purchase("basic-perk")
    features = {f.id: f.ranks for f in character.list_features(available=False)}
    # Basic Skill has multiple ranks that can still be purchased, so it's not in the dict.
    assert "basic-skill" not in features
    # Basic Perk doesn't have multiple ranks, so it's now unavailable.
    assert "basic-perk" in features
