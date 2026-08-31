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

## ⛔ A read that finds nothing has not proved nothing is there

**Every lookup in this brief can come back empty for reasons that have nothing to
do with the tree being empty.** Three of them, all real:

- **Privacy.** `find_people` excludes private people and does not count them, and
  `list_events` skips a private event *or a private reference to a public one*.
  So a private person reads as **not in the tree**, and a public person's private
  Naturalization reads as **not recorded**.
- **The cap.** `list_events` returns at most 25 and reports `capped: true` with
  `withheld > 0`. It offers no paging and no type filter, so beyond 25 events an
  absent type may simply be past the end.
- **Staleness.** `list_people` reads an export; `find_people` reads the tree.
  That is why this brief says use the live one.

⭐ **So the rule is one rule, and it applies to every "does this already exist?"
question here:** an empty or capped result means *nothing was returned*, never
*nothing exists*. **Say which you have** — and when the answer decides whether
you create a record, ask the owner to confirm in Gramps first.

⚠️ **Check `capped` and `withheld` on every `list_events` result** before
concluding a type is absent. If either says there is more, say so and stop.

## Before proposing a source or citation

Call **`find_source`** for this document's source, and if it exists,
**`find_citation`** on it with the page. If a citation already names the page you
are about to enter, this document is probably already in the tree — **say so; do
not propose it again.**

⛔ **Citations are always created new; nothing matches them.** They cannot carry a
`gramps_id`, so there is no attaching to one. Re-transcribing the same page adds a
**second** citation rather than warning you, and nothing downstream will notice.

## ⛔ When you attach to an existing event, say what could not be written

An event you attach to **keeps its own fields.** Its date, place and description
come from the tree, and anything you send for them is **dropped** — shown to the
owner as dropped, but dropped.

⚠️ So when the document says something about that event which the tree does not
already hold — **a birthplace where the tree's event has no place**, a more
precise date, a different place — the citation attaches and **that detail cannot
be written at all.**

**Attach anyway; do not create a second event.** But **tell the owner explicitly
what the document carries that the existing event cannot receive**, so he can add
it by hand in Gramps. ⛔ Silently attaching and moving on loses the fact.

The same for a disagreement: if the document's birthplace differs from the tree's,
**say so.** That is two sources disagreeing and it is his to resolve.

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
| name, sex | the person node: given, surname, gender — ⛔ **`male` or `female`, spelled out** |
| birth year, birthplace | the person's **existing** Birth event — see below |
| age | the same Birth event, or a new one dated `abt <year>` |
| immigration year | an **Immigration** event |
| naturalisation year | a **Naturalization** event |
| occupation | that person's **Census description**. ⛔ Not a separate Occupation event |
| where living | a **Residence** event with a place |
| relationship to head, marital status | that person's own Census description |

### ⛔ `gender` takes `male` or `female`, spelled out

A census column says `M` or `F`, and copying that straight across **loses the
sex silently.** The parser accepts any string, the writer recognises only
`male` and `female`, and **anything else is stored as unknown** — while the
preview shows you the value you sent. So `M` renders as `M` in the dialog and
lands as unknown in the tree.

⚠️ **That is a preview/write disagreement, and the dialog will not warn you.**
Normalise before proposing: `M` → `male`, `F` → `female`. Anything you cannot
map confidently, leave out and say so — an absent gender is honest, and an
unknown one you believed you had set is not.

⛔ **This applies to people the census INTRODUCES. For a person already in the
tree, `gender` is dropped.** An attached person keeps their own `given`,
`surname` and `gender`; the writer ignores every one of them deliberately.

⚠️ So if a matched person's sex is missing from the tree, or the census disagrees
with it, **sending `gender` changes nothing and nothing warns you.**

⛔ **And you cannot check which it is.** No read returns a person's gender —
`find_people` gives the name and a birth year, and nothing else — so *"the tree
disagrees"* is not a comparison you are able to make. Do not claim it either way.

⭐ **Report the census value and say it could not be compared**, so the owner can
look. That is weaker than the birthplace rule, where the tree's value *is*
visible, and the difference is worth keeping straight: there you report a
conflict, here you report that a conflict cannot be seen.

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

⭐ **A new Birth event is for a person who has none** — whether the census
introduced them, or they were already in the tree with no Birth event recorded.

⚠️ **That second case is real and an earlier version of this page had no answer
for it.** `find_people` finds them, `list_events` returns no Birth, and the rule
above said only *attach the citation* — which left the census's birth year,
birthplace and citation with nowhere to go. **Create the Birth event**, with
`people` pointing at that person's local node; the writer installs it as the
person's birth reference when the slot is empty.

⛔ **But an empty `list_events` does not prove there is no Birth event.** The
privacy gate drops private records before you see them — a **public person with a
private Birth event** reads as having none. The approval dialog omits it too, so
the owner cannot catch the duplicate there either.

⭐ So after an empty lookup on an **existing** person: **say that you found none
and ask him to confirm in Gramps before you propose a Birth.** For a person the
census introduces there is nothing to hide, and no confirmation is needed.

⚠️ **And "the census introduces them" is itself a read that can be wrong.** A
private person is excluded from `find_people` and not counted, so **no match does
not prove they are new** — see the rule at the top. A name that ought to be in
this tree and is not returned is worth saying aloud before you create a person.

⛔ **The same caution covers every type, not just Birth.** A private
Naturalization, Residence or Occupation reads as absent exactly the same way.

⭐ So the test is **does this person have a Birth event**, not *did the census
introduce them*.

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

## ⭐ A family event: `events[].family`

**Family-level events are creatable, and this is the key that does it.** A
marriage or a divorce belongs on the family, and an event node carries `family`
the same way it carries `people`.

⛔ **`family` names a LOCAL id, never a `gramps_id` directly.** Every reference
names a node in the graph, so the family gets a node of its own carrying the
`gramps_id`, and the event points at that node's local id:

    "families": [
      {"id": "f1", "gramps_id": "<from find_families>"}
    ],
    "events": [
      {"id": "e1", "type": "Marriage", "date": "...", "family": "f1"}
    ]

⚠️ **Both ids in that example are required and both were missing from the first
version of this page.** Putting the `gramps_id` straight into `family` is
refused — *"event 'e1''s family refers to '…', which is not in this graph"* —
and an event with no `id` is refused before that: *"every entry in 'events'
needs an 'id'"*. The example above is the one that parses.

The writer attaches it with Gramps' own family role, and commits the family. So
`family` and `people` are the two ways an event finds its subject: **`people`
for a person's own events — birth, death, census, residence — and `family` for
a couple's.**

⚠️ **This was believed impossible once, from a roadmap line describing a hole
that has since been closed.** A capability nobody knows about is a capability
nobody uses, so it is written here rather than left to be rediscovered.
