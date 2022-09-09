from camp.engine.models import FeatureEntry
from camp.engine.models import RulesDecision
from camp.engine.rules.geas5.models import Character
from camp.engine.rules.geas5.models import SkillDef

# TODO: There's probably a better way to factor this stuff. Think about it
# after we make some progress.


def can_add_feature(character: Character, entry: FeatureEntry) -> RulesDecision:
    ruleset = character._ruleset
    if entry.id not in ruleset.features:
        return RulesDecision(success=False, reason="Feature not defined")

    feature = ruleset.features[entry.id]
    entries = character.get_feature(entry.id)

    # Skills are the only feature in Geas that can
    # potentially have multiple instances.
    if entries:
        if isinstance(feature, SkillDef):
            if feature.option and not feature.option.multiple:
                return RulesDecision(success=False, reason="Already have this feature")
            elif any(e for e in entries if e.option == entry.option):
                return RulesDecision(
                    success=False, reason="Already have this feature with this option"
                )

    # TODO: Lots of other checks, like:
    # * Enforce build order, maybe (Starting Class -> Breeds -> Other)?
    # * Enforce currencies (CP, XP, BP, etc)
    # * Requirements checking
    # * Etc?

    return RulesDecision(success=True)


def add_feature(character: Character, entry: FeatureEntry) -> RulesDecision:
    ruleset = character._ruleset
    if rd := can_add_feature(character, entry):
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
