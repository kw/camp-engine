from __future__ import annotations

from camp.engine.rules.base_models import Discount
from camp.engine.rules.decision import Decision

from . import choice_controller


class SphereGrantChoice(choice_controller.GrantChoice):
    """Choose a feature to grant from a magic sphere.

    This is a special case of a bonus feature chooser where the choices are linked
    to a sphere/class... _maybe_. For example, the Additional Cantrip skill lets you
    take a bonus cantrip. Simple enough, right? Wrong. If you have a casting class,
    the cantrip _must_ come from that class. If you don't have a casting class, then
    your cantrip choice can come from any casting class, but your choice of sphere
    depends on whether you have Basic Arcane and/or Basic Faith (which you must have
    at least one of to take the skill).
    """

    def _check_req(self, choice: str) -> Decision:
        if not (rd := super()._check_req(choice)):
            return rd
        controller = self._feature.character.feature_controller(choice)
        if sphere := getattr(controller, "sphere", None):
            return super()._check_req(sphere)
        return Decision.OK

    def _matches(self, choice: str, already_chosen: bool = False) -> bool:
        """In addition to the normal feature match, does the rest of the filtering described above."""
        # Rule 0: The choice must match the normal feature match.
        if not super()._matches(choice, already_chosen=already_chosen):
            return False

        # The following rules only apply at the time when the choice is made. Having a spellcasting
        # class can invalidate some choices, but only if you have the class at the time the choice
        # is made.
        if already_chosen:
            return True

        character = self._feature.character
        feat = character.feature_controller(choice)

        # Rule 1: The character shouldn't already have the choice.
        if character.get(choice):
            return False

        # Rule 2: The choice must come from a casting class the character has, if they have any.
        # If a sphere is specified in controller_data, only classes of that sphere are considered.
        if (data := self.definition.controller_data) and (sphere := data.get("sphere")):
            casting_classes = {
                claz.full_id
                for claz in character.classes
                if claz.caster and claz.sphere == sphere
            }
        else:
            casting_classes = {
                claz.full_id for claz in character.classes if claz.caster
            }
        if casting_classes:
            # In the off chance that a cantrip/spell/whatever is listed with a cost, it should be excluded.
            # These have unique purchase rules and shouldn't be available as a choice for anything that uses
            # this controller.
            if feat.cost:
                return False
            # Otherwise, the choice must be from one of these classes.
            return feat.parent and feat.parent.full_id in casting_classes

        # Rule 3: If the character does _not_ have a casting class, the spell in question must still
        # come from a class.
        # TODO: The rules team might want to restrict this to just basic classes.
        # As is, the skills that use this controller say nothing about the type of class the spell
        # can come from.
        if not (parent := feat.parent) or not parent.feature_type == "class":
            return False

        # Rule 4: If the character does _not_ have a casting class, the choice must come from a sphere
        # they have access to via the Basic Arcane or Basic Faith skills. One of these skills is always
        # a requirement to take a skill that uses this controller, though sometimes it's implicit.
        if sphere := getattr(feat, "sphere", None):
            if sphere == "arcane" and not character.meets_requirements("basic-arcane"):
                return False
            if sphere == "divine" and not character.meets_requirements("basic-faith"):
                return False

        return True


class SphereBonusChoice(choice_controller.ChoiceController):
    """Presents a list of spheres of magic that the character can get a bonus for.

    Most choice controllers list features, but this one lists spheres.
    At time of writing, only Arcane and Divine are supported, but if other spheres
    become available we'll need to update this to figure out what spheres are available
    in a more generic way.
    """

    def available_choices(self) -> dict[str, str]:
        """Available choices depend, by default, on sphere availability.

        The character controller's `available_spheres` property returns a set of
        spheres possessed by the character.

        Some choices may require something more, such as attaining a certain spell
        slot level in the sphere. In that case, the choice definition will contain
        controller data titled `sphere_requires` that contains a requirement fragment
        to be applied to the sphere. Only available spheres will be checked.
        """
        choices = {}
        if not self.choices_remaining > 0:
            return choices
        for sphere in sorted(self._feature.character.available_spheres):
            if self._check_req(sphere):
                choices[sphere] = self.describe_choice(sphere)
        return choices

    def update_propagation(
        self, grants: dict[str, int], discounts: dict[str, list[Discount]]
    ) -> None:
        super().update_propagation(grants, discounts)

        for choice, ranks in self.choice_ranks().items():
            if not self._check_req(choice):
                continue
            bonus = self.definition.controller_data.get("bonus", None)
            if bonus:
                choice = f"{choice}.{bonus}"
            if choice not in grants:
                grants[choice] = 0
            grants[choice] += ranks
