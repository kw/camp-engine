from __future__ import annotations

import re

from camp.engine.models import AllOf
from camp.engine.models import AnyOf
from camp.engine.models import BoolExpr
from camp.engine.models import FeatureEntry
from camp.engine.models import NoneOf
from camp.engine.models import Requirements
from camp.engine.models import RulesDecision
from camp.engine.utils import maybe_iter

from . import models

# TODO: There's probably a better way to factor this stuff. Think about it
# after we make some progress.

_REQ_SYNTAX = re.compile(
    r"""(?P<prop>[a-zA-Z0-9_-]+)
    (?:@(?P<tier>\d+))?          # Tier, aka "@4"
    (?:\#(?P<option>[a-zA-Z0-9?_-]+))?   # Skill options, aka "#Undead_Lore"
    (?::(?P<minimum>\d+))?       # Minimum value, aka ":5"
    (?:\$(?P<single>\d+))?       # Minimum value in single thing, aka "$5"
    (?:<(?P<less_than>\d+))?     # Less than value, aka "<5"
    """,
    re.VERBOSE,
)


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
    # * Etc?

    if not (rd := character.meets_requirements(feature.requires)):
        return rd

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


class PropReq(BoolExpr):
    """Things that might get parsed out of a requirement string.

    Attributes:
        prop: The property being tested. Often a feature ID. Required.
        option: Text value listed after a #. Ex: lore#Undead
            This is handled specially if the value is '?', which means
            "You need the same option in the indicated skill as you are
            taking for this skill".
        minimum: "At least this many ranks/levels/whatever". Ex: caster:5 is
            "at least 5 levels in casting classes"
        single: "At least this many ranks in the highest thing of this type"
            Ex: caster$5 is "at least 5 ranks in a single casting class".
        less_than: "No more than this many ranks". Ex: lore<2 means no more
            than one total ranks of Lore skills.
        tier: For tiered properties like spell slots. Ex: spell@4 indicates
            at least one tier-4 spell slot, while spell@4:3 indicates at least
            three tier-4 spell slots.
    """

    prop: str
    tier: int | None = None
    option: str | None = None
    minimum: int | None = None
    single: int | None = None
    less_than: int | None = None

    def evaluate(self, *args) -> bool:
        return False

    @classmethod
    def parse(cls, req: str) -> PropReq:
        if match := _REQ_SYNTAX.fullmatch(req):
            groups = match.groupdict()
            prop = groups["prop"]
            tier = int(t) if (t := groups.get("tier")) else None
            option = o.replace("_", " ") if (o := groups.get("option")) else None
            minimum = int(m) if (m := groups.get("minimum")) else None
            single = int(s) if (s := groups.get("single")) else None
            less_than = int(lt) if (lt := groups.get("less_than")) else None
            return cls(
                prop=prop,
                tier=tier,
                option=option,
                minimum=minimum,
                single=single,
                less_than=less_than,
            )
        raise ValueError(f"Requirement parse failure for {req}")

    def __repr__(self) -> str:
        req = self.prop
        if self.tier:
            req += f"@{self.tier}"
        if self.option:
            req += f"#{self.option.replace(' ', '_')}"
        if self.minimum:
            req += f":{self.minimum}"
        if self.single:
            req += f"${self.single}"
        if self.less_than:
            req += f"<{self.less_than}"
        return req


def parse_req(req: Requirements) -> BoolExpr | PropReq:
    if not req:
        return NoneOf(none=[])
    if isinstance(req, list):
        return AllOf(all=[parse_req(r) for r in req])
    if isinstance(req, AllOf):
        return AllOf(all=[parse_req(r) for r in maybe_iter(req.all)])
    if isinstance(req, AnyOf):
        return AnyOf(any=[parse_req(r) for r in maybe_iter(req.any)])
    if isinstance(req, NoneOf):
        return NoneOf(none=[parse_req(r) for r in maybe_iter(req.none)])
    if isinstance(req, str):
        if req.startswith("!"):
            return NoneOf(none=[PropReq.parse(req[1:])])
        else:
            return PropReq.parse(req)
    raise ValueError(f"Requirement parse failure for {req}")
