"""Shared fixtures for Tempest engine tests."""
import pytest

from camp.engine import loader
from camp.engine.rules.base_engine import Engine
from camp.engine.rules.tempest.controllers.character_controller import TempestCharacter
from camp.engine.rules.tempest.engine import TempestEngine


@pytest.fixture
def engine() -> TempestEngine:
    engine = loader.load_ruleset("$camp.tempest.test").engine
    if not isinstance(engine, TempestEngine):
        raise Exception("Example ruleset does not specify expected engine")
    return engine


@pytest.fixture
def character(engine: Engine) -> TempestCharacter:
    return engine.new_character()
