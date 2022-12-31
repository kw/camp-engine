# camp-engine
Engine for building and verifying characters and such, for use in Camp. Work in progress.

## Design

[Camp](https://www.github.com/kw/camp) is intended to be rules system agnostic, and each rules engine
will no doubt have its own quirks, special behaviors, terminology, and preferred format for representing
their game elements. However, a few basic concepts are used in the base engine to help process and
display data, and engines should translate their concepts into these internally if possible. They are:

* Features
* Currencies
* Attributes
* Slots

### Features

A feature is a named concept attached to a character sheet that might have some properties associated,
most commonly a concept of "ranks" or "levels". In many systems these will represent concepts like
Skills, Classes, Advantages, Flaws, Perks, Feats, or the like.

### Currencies

Currencies, in the context of a character sheet, aren't like the gold coins or credits or whatever that
your character might carry. Instead, they're the currencies that you buy features with. Skills might
require Skill Points or Character Points to buy, and Flaws might grant additional points.

Some currencies are local. For example, in Geas Core, each "breed" has a list of Challenges and Advantages that grant or
cost Breed Points, but Breed Points granted by one breed's Challenges can only be spent on that breed's
Advantages. In effect, there's not really a "Breed Points" currency, there's an "Elf Points" currency,
and a "Human Points", and so on, one for each breed.

### Attributes

Attributes are typically numeric values that might be granted or modified by skills, and that you might want
to display on the character sheet, particularly when printed out for play. Attributes might represent things
like number of spells that the character can prepare, amount of coin they receive at the start of each event,
the damage output of a particular skill that changes based on certain other skill purchases, the number of
packets that a channeler can channel, and so on.

### Slots

Slots are a means of granting features outside of using currencies to buy them. For example, your game's
Fighter class might have a special feature at some level that grants your choice of three specific options,
which might be something generic like "+1 damage against beasts", "the Heavy Armor skill", or "any single
weapon proficiency skill". While Slots are a less prominent concept than Features or Currencies, they require
some thought. Depending on the system and the slot in question, you may have to consider things like: what happens
if this slot only grants Feature X, but the character already has it? Does it do nothing, refund the original
cost, or allow selection of some equivalent feature? These are considerations that will either need to be baked
into your particular rules engine or specified in some way for each slot that could trigger it.
