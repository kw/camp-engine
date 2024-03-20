from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from camp.engine.rules import base_engine
from camp.engine.rules.base_models import ChoiceMutation
from camp.engine.rules.base_models import Issue
from camp.engine.rules.base_models import PropExpression
from camp.engine.rules.base_models import RankMutation
from camp.engine.rules.decision import Decision

from .. import defs
from .. import engine  # noqa: F401
from .. import models
from . import attribute_controllers
from . import breed_controller
from . import cantrip_controller
from . import class_controller
from . import culture_controller
from . import devotion_controller
from . import feature_controller
from . import flaw_controller
from . import power_controller
from . import religion_controller
from . import spell_controller
from . import spellbook_controller
from . import subfeature_controller
from . import undefined_controller
from . import utility_controller

_DISPLAY_PRIORITIES = {
    "class": 0,
    "breed": 1,
    "subbreed": 1.1,
    "breedchallenge": 1.2,
    "breedadvantage": 1.3,
    "culture": 2,
    "religion": 3,
    "flaw": 4,
    "perk": 5,
    "skill": 6,
    "cantrip": 7,
    "utility": 8,
    "spell": 9,
    "power": 10,
}


class TempestCharacter(base_engine.CharacterController):
    model: models.CharacterModel
    engine: engine.TempestEngine
    ruleset: defs.Ruleset
    _features: dict[str, feature_controller.FeatureController] | None = None
    _costuming: models.CostumingData | None = None

    @property
    def xp(self) -> int:
        """Experience points"""
        return self.model.metadata.awards.get("xp", 0)

    @property
    def xp_level(self) -> int:
        """Experience level.

        This is slightly different than character level - XP level is
        the character level that you're entitled to have, but actual
        character level is the sum of class levels you've selected. The
        "Level Up!" (or equivalent) button will appear when character level
        is less than XP Level, but will cause a validation error if character
        level exceeds XP level.
        """
        return self.ruleset.xp_table.evaluate(self.xp)

    @xp_level.setter
    def xp_level(self, value):
        """Set the XP level to a specific level.

        This is a convenience method primarily for testing purposes. If an XP
        level is manually set, the copy of the metadata attached to the sheet will be
        overwritten with the needed XP. Characters in a real app will likely have
        their source of metadata truth stored elsewhere and applied on load, so
        persisting this change will not do what you want for such characters.
        """
        self.model.metadata.awards["xp"] = self.ruleset.xp_table.reverse_lookup(value)
        self.mutated = True

    @property
    def base_cp(self) -> int:
        """CP granted by formula from the ruleset.

        By default, this is 1 + 2 * Level.
        """
        return self.ruleset.cp_baseline + (self.ruleset.cp_per_level * self.level.value)

    @property
    def freeplay_cp(self) -> int:
        """CP assigned in freeplay mode."""
        return self.model.metadata.awards.get("cp", 0)

    @freeplay_cp.setter
    def freeplay_cp(self, value: int) -> None:
        self.model.metadata.awards["cp"] = value
        self.mutated = True

    @property
    def event_cp(self) -> int:
        return self.model.metadata.awards.get("event_cp", 0)

    @property
    def bonus_cp(self) -> int:
        return self.model.metadata.awards.get("bonus_cp", 0)

    @property
    def backstory_cp(self) -> int:
        return self.model.metadata.awards.get("backstory_cp", 0)

    @property
    def base_lp(self) -> int:
        return self.ruleset.lp.evaluate(self.level.value)

    @cached_property
    def lp(self) -> attribute_controllers.LifePointController:
        return attribute_controllers.LifePointController("lp", self)

    @property
    def spikes(self) -> int:
        return self.ruleset.spikes.evaluate(self.level.value)

    @property
    def can_respend(self) -> bool:
        """Can the character be freely edited?

        This should be true before the character's first full weekend game, and potentially
        before the second. There may be some other situations where it turns on, such as
        a ritual that allows respend, though many of these may be more specific (e.g. a
        ritual that allows breed options to be edited, or an SP action that allows a single
        class level to be respent). We'll handle those on a case-by-case basis elsewhere.
        """
        # TODO: Actually base this on something
        return True

    @cached_property
    def cp(self) -> attribute_controllers.CharacterPointController:
        return attribute_controllers.CharacterPointController("cp", self)

    @cached_property
    def bp_primary(self) -> attribute_controllers.BreedPointController:
        return attribute_controllers.BreedPointController(True, self)

    @cached_property
    def bp_secondary(self) -> attribute_controllers.BreedPointController:
        return attribute_controllers.BreedPointController(False, self)

    @cached_property
    def level(self) -> attribute_controllers.SumAttribute:
        return attribute_controllers.SumAttribute("level", self, "class")

    @property
    def levels_available(self) -> int:
        return self.xp_level - self.level.value

    @property
    def primary_class(self) -> class_controller.ClassController | None:
        for controller in self.classes:
            if controller.is_archetype:
                return controller
        return None

    @property
    def basic_classes(self) -> int:
        return sum(1 for c in self.classes if c.class_type == "basic")

    @property
    def starting_class(self) -> class_controller.ClassController | None:
        for controller in self.classes:
            if controller.is_starting:
                return controller
        return None

    def display_priority(self, feature_type: str) -> int:
        return _DISPLAY_PRIORITIES.get(feature_type, 99)

    @property
    def features(self) -> dict[str, feature_controller.FeatureController]:
        if self._features:
            return self._features
        self._features = {id: self._new_controller(id) for id in self.model.features}
        self._features["__plot__"] = feature_controller.PlotController("__plot__", self)
        return self._features

    @property
    def culture(self) -> culture_controller.CultureController | None:
        for feature in self.features.values():
            if feature.feature_type == "culture" and feature.value > 0:
                return feature
        return None

    @property
    def breeds(self) -> int:
        return len(self.all_breeds)

    @property
    def all_breeds(self) -> list[breed_controller.BreedController]:
        breeds: list[breed_controller.BreedController] = []
        for feature in self.features.values():
            if feature.feature_type == "breed" and feature.value > 0:
                breeds.append(feature)
        breeds.sort(key=lambda b: b.is_primary, reverse=True)
        return breeds

    @property
    def primary_breed(self) -> breed_controller.BreedController | None:
        for breed in self.all_breeds:
            if breed.is_primary:
                return breed
        return None

    @property
    def secondary_breed(self) -> breed_controller.BreedController | None:
        for breed in self.all_breeds:
            if not breed.is_primary:
                return breed
        return None

    @property
    def subbreed(self) -> breed_controller.SubbreedController | None:
        if pb := self.primary_breed:
            return pb.subbreed
        return None

    @property
    def religion(self) -> religion_controller.ReligionController | None:
        for feature in self.features.values():
            if feature.feature_type == "religion" and feature.value > 0:
                return feature
        return None

    @property
    def classes(self) -> list[class_controller.ClassController]:
        """List of the character's class controllers."""
        classes = [
            feat
            for feat in list(self.features.values())
            if feat.feature_type == "class" and feat.value > 0
        ]
        classes.sort(key=lambda c: c.value, reverse=True)
        return classes

    @property
    def archetype_legal_classes(self) -> list[class_controller.ClassController]:
        """List of classes that are legal to be the character's archetype."""
        classes = self.classes
        max_level = max([c.value for c in classes], default=0)
        return [c for c in classes if c.value == max_level]

    @property
    def is_multiclass(self) -> bool:
        return len(self.classes) > 1

    @property
    def skills(self) -> list[feature_controller.FeatureController]:
        skills = [
            feat
            for (feat) in self.features.values()
            if feat.feature_type == "skill" and feat.value > 0
        ]
        skills.sort(key=lambda s: s.display_name())
        return skills

    def feature_def(self, feature_id: str) -> defs.FeatureDefinitions | None:
        expr = PropExpression.parse(feature_id)
        return self.ruleset.features.get(expr.prop)

    def _feature_type(self, feature_id: str) -> str | None:
        if feature_def := self.feature_def(feature_id):
            return feature_def.type
        return None

    @property
    def flaws(self) -> dict[str, flaw_controller.FlawController]:
        return {
            id: feat
            for (id, feat) in self.features.items()
            if isinstance(feat, flaw_controller.FlawController)
        }

    @property
    def cantrips(self) -> dict[str, cantrip_controller.CantripController]:
        return [
            feat
            for feat in self.features.values()
            if isinstance(feat, cantrip_controller.CantripController)
        ]

    @property
    def spells(self) -> list[spell_controller.SpellController]:
        return [
            feat
            for feat in self.features.values()
            if isinstance(feat, spell_controller.SpellController)
        ]

    def spell(self, expr: PropExpression | None = None) -> int:
        """The number of spell slots total or at a paritcular tier."""
        slot = int(expr.slot) if (expr and expr.slot is not None) else None
        count = 0
        for sphere in ["arcane", "divine"]:
            if slot is not None:
                count += self.get(f"{sphere}.spell_slots@{slot}")
            else:
                count += self.get(f"{sphere}.spell_slots")
        return count

    @property
    def martial_powers(self) -> list[power_controller.PowerController]:
        return [feat for feat in self.features.values() if feat.feature_type == "power"]

    def power(self, expr: PropExpression | None = None) -> int:
        """The number of martial powers known total or at a given tier."""
        if expr is None or expr.slot is None:
            return sum(p.value for p in self.martial_powers)
        slot = int(expr.slot)
        return sum(p.value for p in self.martial_powers if p.tier == slot)

    @property
    def utilities(self) -> list[utility_controller.UtilityController]:
        return [
            feat for feat in self.features.values() if feat.feature_type == "utility"
        ]

    def can_purchase(self, entry: RankMutation | str) -> Decision:
        if not isinstance(entry, RankMutation):
            entry = RankMutation.parse(entry)
        if controller := self.feature_controller(entry.expression):
            if entry.ranks > 0:
                return controller.can_increase(entry.ranks)
            elif entry.ranks < 0:
                return controller.can_decrease(-entry.ranks)
        return Decision(
            success=False, reason=f"Purchase not implemented: {entry.expression}"
        )

    def purchase(self, entry: RankMutation) -> Decision:
        if controller := self.feature_controller(entry.expression):
            if entry.ranks > 0:
                rd = controller.increase(entry.ranks)
            elif entry.ranks < 0:
                rd = controller.decrease(-entry.ranks)
            return rd
        return Decision(
            success=False, reason=f"Purchase not implemented: {entry.expression}"
        )

    def choose(self, entry: ChoiceMutation) -> Decision:
        if controller := self.feature_controller(entry.id):
            if entry.remove:
                return controller.unchoose(entry.choice, entry.value)
            return controller.choose(entry.choice, entry.value)
        return Decision(success=False, reason=f"Unknown feature {entry.id}")

    def has_prop(self, expr: str | PropExpression) -> bool:
        """Check whether the character has _any_ property (feature, attribute, etc) with the given name.

        The base implementation only knows how to check for attributes. Checking for features
        must be added by implementations.
        """
        expr = PropExpression.parse(expr)
        if super().has_prop(expr):
            return True
        if controller := self.controller(expr):
            return controller.value > 0
        return False

    def get_choice_def(self, id: str | PropExpression) -> defs.ChoiceDef | None:
        expr = PropExpression.parse(id)
        if feat := self.ruleset.features.get(expr.prop):
            return feat.choices.get(expr.choice)
        return None

    def has_choice(self, id: str) -> bool:
        expr = PropExpression.parse(id)
        if not expr.choice:
            raise ValueError(f"ID {id} does not name a choice.")
        # To have a choice, the character must both have the named feature (including option, if present)
        # and the feature must actually define a choice with that ID.
        return self.has_prop(expr.full_id) and self.get_choice_def(id)

    def get_options(self, id: str) -> dict[str, int]:
        if controller := self.feature_controller(PropExpression.parse(id)):
            return controller.taken_options
        return super().get_options(id)

    @cached_property
    def martial(self) -> spellbook_controller.SphereAttribute:
        return spellbook_controller.SphereAttribute("martial", self)

    @cached_property
    def caster(self) -> base_engine.AttributeController:
        return attribute_controllers.SumAttribute("caster", self, "class", "caster")

    @cached_property
    def arcane(self) -> spellbook_controller.SphereAttribute:
        return spellbook_controller.SphereAttribute("arcane", self)

    @cached_property
    def divine(self) -> spellbook_controller.SphereAttribute:
        return spellbook_controller.SphereAttribute("divine", self)

    @cached_property
    def spellbooks(self) -> list[spellbook_controller.SpellbookController]:
        return [self.arcane.spellbook, self.divine.spellbook]

    @cached_property
    def powerbook(self) -> spellbook_controller.PowerbookController:
        return self.martial.powerbook

    @cached_property
    def devotion(self) -> base_engine.AttributeController:
        controller = attribute_controllers.SumAttribute("devotion", self, "devotion")
        basic_devotion = attribute_controllers.SumAttribute(
            "basic", self, "devotion", "is_basic"
        )
        adv_devotion = attribute_controllers.SumAttribute(
            "advanced", self, "devotion", "is_advanced"
        )
        controller.basic = basic_devotion
        controller.advanced = adv_devotion
        return controller

    def sphere_data(self) -> list[SphereData]:
        spheres = []
        for sphere in sorted(self.available_spheres):
            name = self.display_name(sphere)
            slots = tuple(
                self.get(f"{sphere}.spell_slots@{tier}") for tier in range(1, 5)
            )
            prepared = self.get(f"{sphere}.spells_prepared")
            spheres.append(
                SphereData(
                    name=name,
                    id=sphere,
                    slots=slots,
                    prepared=prepared,
                )
            )
        return spheres

    def tag_name(self, tag: str) -> str | None:
        if tag in self.ruleset.tags:
            return self.ruleset.tags[tag]
        if tag.islower():
            return self.display_name(tag)
        return tag

    def display_name(self, expr: str, use_abbrev: bool = False) -> str:
        return super().display_name(expr, use_abbrev)

    def _new_controller(self, id: str) -> feature_controller.FeatureController:
        match self._feature_type(id):
            case None:
                # Handle the circumstance of a feature that was previously purchased but
                # stops existing in the ruleset. This will appear on the character sheet
                # in a semi-dead state until removed.
                controller = undefined_controller.UndefinedFeatureController(id, self)
                if not controller.purchased_ranks:
                    raise ValueError("No such feature")
                return controller
            case "class":
                return class_controller.ClassController(id, self)
            case "flaw":
                return flaw_controller.FlawController(id, self)
            case "subfeature":
                return subfeature_controller.SubfeatureController(id, self)
            case "skill":
                return feature_controller.SkillController(id, self)
            case "perk":
                return feature_controller.PerkController(id, self)
            case "cantrip":
                return cantrip_controller.CantripController(id, self)
            case "spell":
                return spell_controller.SpellController(id, self)
            case "power":
                return power_controller.PowerController(id, self)
            case "utility":
                return utility_controller.UtilityController(id, self)
            case "culture":
                return culture_controller.CultureController(id, self)
            case "religion":
                return religion_controller.ReligionController(id, self)
            case "devotion":
                return devotion_controller.DevotionController(id, self)
            case "breed":
                return breed_controller.BreedController(id, self)
            case "subbreed":
                return breed_controller.SubbreedController(id, self)
            case "breedadvantage":
                return breed_controller.BreedAdvantageController(id, self)
            case "breedchallenge":
                return breed_controller.BreedChallengeController(id, self)
            case _:
                return feature_controller.FeatureController(id, self)

    def feature_controller(
        self, expr: PropExpression | str
    ) -> feature_controller.FeatureController:
        expr = PropExpression.parse(expr)
        # If this is already on the sheet, fetch its controller
        if controller := self.features.get(expr.full_id):
            return controller
        # Otherwise, create a controller and for it.
        return self._new_controller(expr.full_id)

    @property
    def available_spheres(self) -> set[str]:
        """Spheres of magic that the character has access to."""
        # This will do for the moment, but if plot starts adding more
        # player-accessible spheres that are supposed to work with skills
        # and classes and such, we'll want to make this more generic.
        spheres = set()
        if self.get("basic-arcane"):
            spheres.add("arcane")
        if self.get("basic-faith"):
            spheres.add("divine")
        return spheres

    def get_costuming(self) -> models.CostumingData:
        if self._costuming is not None:
            return self._costuming
        all_costuming = models.CostumingData()
        for feature in self.list_features(
            taken=True, available=False, filter_subfeatures=False
        ):
            feature: feature_controller.FeatureController
            if costuming := feature.get_costuming():
                all_costuming = all_costuming.add(costuming)
        self._costuming = all_costuming
        return self._costuming

    def issues(self) -> list[Issue]:
        issues = super().issues()
        for spellbook in (self.arcane.spellbook, self.divine.spellbook):
            if not spellbook:
                continue
            if excess := spellbook.excess_spells:
                issues.append(
                    Issue(
                        issue_code=f"excess-spells-{spellbook.sphere}",
                        reason=f"Too many {self.display_name(spellbook.sphere)} spells known ({excess})",
                    )
                )
        cp_controller = self.cp
        cp_awarded = cp_controller.total_cp
        cp_spent = cp_controller.spent_cp
        if cp_spent > cp_awarded:
            issues.append(
                Issue(
                    issue_code="insufficient-cp",
                    reason=f"Too much CP spent {cp_spent}/{cp_awarded}",
                )
            )

        return issues

    def clear_caches(self):
        super().clear_caches()
        self._features = {}
        self._costuming = None
        for feature in list(self.features.values()):
            feature.reconcile()


@dataclass
class SphereData:
    name: str
    id: str
    slots: tuple[int]
    prepared: int
