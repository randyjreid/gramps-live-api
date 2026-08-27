# Census transcription — working rules

Read this before proposing anything. It repeats rules the tool's own description
may not have delivered to you.

## Look it up before you create

    *** IF AN EVENT ALREADY EXISTS, LOOK IT UP FIRST AND PASS ITS GRAMPS ID.
    *** IF A PERSON IS ALREADY IN THE TREE, LOOK THEM UP FIRST.
    *** FOR A FAMILY, CALL find_families FIRST AND PASS ITS GRAMPS ID.
    *** A MARRIAGE BELONGS ON THE FAMILY, NOT ON THE TWO SPOUSES.

Use **find_people**, not list_people. `list_people` reads an XML export that can
predate someone added to the tree recently; `find_people` asks the open tree.
Same for **find_place**, **find_source**, **find_families**.

Which lookup depends on who owns the event, and getting it wrong looks exactly
like the event not existing:

- a person's own events — birth, death, census, residence, occupation — are on
  the PERSON: `list_events` with their Gramps ID
- a couple's events — marriage, divorce — are on the FAMILY, on neither spouse:
  `find_families`, then `list_family_events`

## One Census event per person

`role` and `description` are properties of the EVENT, applied to every
participant. One shared Census event naming four people gives all four the same
description — so the children inherit the head's occupation.

So: **one Census event per person**, each naming only that person, each carrying
its own description.

## One local id per record

A census names the same person twice — head of household, then again in a
relationship column. That is ONE person with ONE local id. Two local ids
carrying the same `gramps_id` are refused and the whole proposal is rejected.

Listing one local id twice inside `children` or `attach_to` is fine.

## Before proposing an event, look at what the person already has

`list_events` on that person and say what they already hold of that type. The
approval dialog shows what would be WRITTEN, not what is already there — so a
second Naturalization renders exactly like a first one. Until the dialog shows
prior events, this check is manual and it is yours.

If the census disagrees with the tree — a naturalisation year two years apart —
that is two sources disagreeing, not a duplicate. Say so; do not resolve it.

## Which census columns go where

Verified against the parser and the renderer:

| column | how |
| --- | --- |
| name, sex | the person node: given, surname, gender |
| birth year, birthplace | the person's **existing** Birth event — see below |
| age | the same Birth event, or a new one dated `abt <year>` |
| immigration year | an **Immigration** event |
| naturalisation year | a **Naturalization** event |
| occupation | that person's **Census description**. ⛔ Not a separate Occupation event |
| where living | a **Residence** event with a place |
| relationship to head, marital status | that person's own Census description |

### ⛔ Almost everyone already has a Birth event. Do not create a second one.

A census gives a birth year and a birthplace, and the obvious move is to propose
a Birth event carrying them. **For almost every person in this tree that is
wrong** — they already have one, and a second Birth event is not a correction,
it is a duplicate the dialog renders exactly like a first.

So: `list_events` on that person, find the Birth event, and **attach the citation
to the one that is there.** The census is a *source for* the birth you already
record, not a new birth.

⚠️ **If the census year disagrees with the recorded one, that is two sources
disagreeing.** Say so and stop; it is research, not a fix. Do not create a second
Birth event to hold the other year.

⭐ **A new Birth event is for a person the census introduces** — someone not in
the tree until this transcription put them there.

### ⛔ Occupation goes in that person's Census description

Not a separate Occupation event. The census records an occupation *as of that
enumeration*, which is exactly what the Census event's own description is for,
and it keeps the fact tied to the record it came from.

An Occupation event says *this person held this occupation*, unanchored from the
census that told you. That is a different and stronger claim, and it is not the
one a census column supports.

Approximate dates: Gramps recognises `about`, `abt`, `abt.`, `circa`, `c.`,
`around`, and the qualifiers `est`, `est.`, `calc`. Write `abt 1877`.
**Do not write `1877?`** — `?` is not in Gramps' vocabulary and the date will be
kept as text rather than as a date.

Attribute-shaped columns — literacy, home owned or rented, race — have no field.
An unrecognised event type becomes a CUSTOM event type carrying your word, so
`type: "Literacy"` does write, but it invents a new event type in the tree.
**Ask before doing that**; otherwise put the fact in a note.

## The shape is exact

Any key the tool does not know is refused by name, and so is any top-level key
that is not a node group. Nothing is dropped quietly. Note in particular:
`events[].people`, never `people[].events`. A note has no `id`.

A node with a `gramps_id` is attached to, never modified — its other fields are
dropped and shown to the owner as dropped — except a family's `children`, which
join the existing family.
