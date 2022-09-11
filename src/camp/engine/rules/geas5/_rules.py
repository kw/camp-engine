from __future__ import annotations

from camp.engine.models import FeatureEntry
from camp.engine.models import RulesDecision

from . import models

# TODO: There's probably a better way to factor this stuff. Think about it
# after we make some progress.


def can_add_feature(
    character: models.Character, entry: FeatureEntry | str
) -> RulesDecision:
    if isinstance(entry, str):
        entry = FeatureEntry(id=entry)

    ruleset = character._ruleset
    if entry.id not in ruleset.features:
        return RulesDecision(success=False, reason="Feature not defined")

    feature = ruleset.features[entry.id]
    entries = character.get_feature(entry.id)

    # Skills are the only feature in Geas that can
    # potentially have multiple instances. Probably.
    if entries:
        if feature.option and not feature.multiple:
            return RulesDecision(success=False, reason="Already have this feature")
        elif any(e for e in entries if e.option == entry.option):
            return RulesDecision(
                success=False, reason="Already have this feature with this option"
            )
        elif not feature.option:
            return RulesDecision(success=False, reason="Already have this feature.")

    if feature.option and not entry.option:
        # The feature requires an option, but one was not provided. This happens
        # during preliminary scans of purchasable features. As long as there are
        # any options available for purchase, report true, but mark it appropriately.
        if feature.option.freeform or character.options_values_for_feature(
            feature.id, exclude_taken=True
        ):
            return RulesDecision(success=True, needs_option=True)
    if not character.option_satisfies_definition(
        feature.id, entry.option, exclude_taken=True
    ):
        return RulesDecision(
            success=False, reason="Option does not satisfy requirements"
        )

    # TODO: Lots of other checks, like:
    # * Enforce build order, maybe (Starting Class -> Breeds -> Other)?
    # * Enforce currencies (CP, XP, BP, etc)
    # * Requirements checking
    # * Etc?

    return RulesDecision(success=True)


def add_feature(
    character: models.Character, entry: FeatureEntry | str
) -> RulesDecision:
    if isinstance(entry, str):
        entry = FeatureEntry(id=entry)

    ruleset = character._ruleset
    rd = can_add_feature(character, entry)
    if rd and rd.needs_option:
        return RulesDecision(
            success=False,
            needs_option=True,
            reason="Option value required for purchase",
        )
    elif rd:
        feature = ruleset.features[entry.id]
        match feature.type:
            case "class":
                character.classes.append(entry)
            case "classfeature":
                character.classfeatures.append(entry)
            case "breed":
                character.breeds.append(entry)
            case "skill":
                character.skills.append(entry)
        character._features = None
    return rd
