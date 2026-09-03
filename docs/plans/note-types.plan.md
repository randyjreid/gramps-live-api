# Plan — a note's type on the document route

**FULL tier.** It changes the graph schema and the writer, which is the
publication-of-personal-data surface. ⛔ **Not built. This page is the
deliverable, and it needs the owner's approval before anything is written.**

## Why this exists

**R9 asks whether to retire the note flow.** The one real capability that flow
has and the document route does not is **a caller-chosen note type**.

⛔ **Retiring without this makes two note types unwritable.** So R9 and this page
are ruled together, or R9's answer is *"retire — but first plan the thing that
makes retiring safe"*, which is another round.

## What is true today, verified by reading and running

| | |
| --- | --- |
| the note flow's types | `schema.NOTE_TYPES = frozenset({"research", "todo"})` |
| how it spells them for Gramps | `apply.NOTE_TYPE_ATTRIBUTES = {"research": "RESEARCH", "todo": "TODO"}` — attribute **names**, never the integers, ⭐ **already asserted total over `NOTE_TYPES` by test** |
| how the shim applies it | `gramps_plugin/gramps_live_api_apply.py:158` — `note.set_type(NoteType(getattr(NoteType, note_type)))` |
| what the document route accepts | `NODE_KEYS["notes"] = {"text", "attach_to"}`, plus `gramps_id` for every group (`_only_known_keys:453`) |
| what the document route writes | ⛔ `gramps_plugin/gramps_live_api_writer.py:527` — `note.set_type(NoteType(NoteType.TRANSCRIPT))`, **hardcoded, every note** |
| what the preview shows | `+ Note:` and the text. ⛔ **No type at all** (`document.py:1313–1318`) |

⭐ **Three types, no overlap.** `research` and `todo` cannot be written through
the document route; `TRANSCRIPT` cannot be written through the note flow.

## Goal

**A note proposed through the document route may carry a type, validated against
the same closed set the note flow uses, shown in the preview, and written by the
writer — and every graph that exists today keeps working unchanged.**

## Mechanically checkable acceptance criteria

1. **`notes` accepts an optional `type`.** `NODE_KEYS["notes"]` gains `"type"`.
   A graph that omits it still parses.

2. ⛔ **Validated against `schema.NOTE_TYPES` ITSELF, never a copy.** The test
   imports the frozenset and drives the parametrisation from it, so a member
   added there without the parser following fails. ⚠️ **A literal list in the
   test would be a second tally**, which is the counter bug this repository has
   already paid for.

3. **Omitted means `TRANSCRIPT`.** ⭐ Asserted by a test that takes a graph with
   no `type` and shows the written type is unchanged from today's behaviour, so
   **every graph that exists now is unaffected**. This is the backward-compatible
   half and it is the one most easily broken by a default landing in the wrong
   place.

4. **The preview shows the type.** ⛔ A type written but not rendered is a byte
   reaching the tree that was not shown in the approval — which is the one
   property the whole document route exists to hold. The rendered line names the
   type for a typed note and is unchanged for an untyped one.

5. **The writer sets it**, through `getattr` on the attribute name, never a
   pinned integer — the discipline `_event_type` and the apply shim already use.

6. **A refused type names the set.** `type: "gossip"` is refused by name and the
   message lists what is accepted, in the shape `_only_known_keys` already uses.
   ⚠️ **Refused, not silently coerced** — see the open question below for why
   this is the whole argument.

7. ⭐ **No duplicate that nothing checks.** If the writer carries its own copy of
   the spelling map, a test asserts it equals `apply.NOTE_TYPE_ATTRIBUTES`.
   **There is precedent**: `tests/unit/test_attachable_bound.py` and
   `test_write_summary.py` already import the writer **by path** with
   `importlib.util.module_from_spec`, without Gramps.

8. ⛔ **The tool description advertises `type`, and it must.**
   `test_the_ADVERTISED_shape_is_exactly_what_the_parser_accepts` compares
   `PROPOSE_DOCUMENT_DESCRIPTION` against `NODE_KEYS` **in both directions** —
   adding the key without advertising it fails that test, and it fails it for a
   reason worth stating: *"a key the parser accepts but the description omits is
   a capability nobody uses."*

9. ⛔ **And it must fit the delivery budget, which is nearly full.** Measured
   today: `PROPOSE_DOCUMENT_DESCRIPTION` is **2032 of 2048 characters — 16 spare.**
   A description over budget is delivered **cut, mid-sentence**, and the model is
   never told what fell past the cut.

   | what is added to `notes: "text","attach_to"(ids)` | total | |
   | --- | --- | --- |
   | `,"type"` | 2040 | ⭐ fits, 8 spare |
   | `,"type"?` | 2041 | fits, 7 spare |
   | `,"type"(research\|todo)` | 2055 | ⛔ **over by 7** |

   ⭐ **So the vocabulary cannot go in the description.** Advertise the key; let
   **criterion 6's refusal** carry the values, which is where a caller meets them
   anyway and which costs no budget at all.

   ⚠️ **This is a real constraint on the design, not a formatting note.** If a
   later change needs more than eight characters in that description, something
   already in it has to come out, and what to remove is a judgement about what a
   caller most needs — not a trim.

## Out of scope

- Retiring the note flow. ⛔ That is R9 and it is the owner's.
- Any change to how notes attach, or to `attach_to`.
- Editing a note that already exists — the route attaches and creates, never
  modifies, and this does not change that.
- Note types on anything but notes.

## ⭐ Open question 1: whose vocabulary — `NOTE_TYPES`, or Gramps' `NoteType`?

**The event-type question already made this choice, one way, and I recommend
NOT repeating it.**

`_event_type` (`writer.py:130`) does `getattr(EventType, KEY)` against **Gramps'
own class**, and anything unrecognised becomes a **CUSTOM type carrying the
document's own word**. It defers to Gramps' vocabulary and never refuses.

⛔ **That choice has a recorded cost, in the owner's own words:** *"An
unrecognised type silently creates a new custom type in the tree and nothing
tells me it's new."* It is the reason the shipped MCP prompt now carries an
ask-first rule about event types.

⭐ **Recommendation: the closed set — `schema.NOTE_TYPES`, refusing by name.**

| | closed set (recommended) | Gramps' `NoteType` via `getattr` |
| --- | --- | --- |
| an unknown type | ⭐ **refused, naming what is accepted** | ⛔ silently becomes a custom type nobody was told about |
| reuse | ⭐ `NOTE_TYPES` and `NOTE_TYPE_ATTRIBUTES` exist and are tested | a new resolver |
| if R9 retires the note flow | ⚠️ **both constants must survive the retirement** — see below | nothing to keep |
| cost | ⛔ a Gramps note type the user legitimately wants is unavailable | none |

**Why the closed set wins here and lost for events:** an event type comes off a
document — a census says *Occupation*, a certificate says *Baptism* — and the
vocabulary is open in practice. **A note's type is a filing decision with two
useful answers**, and being told *"must be one of: research, todo"* is a better
outcome than a tree quietly growing a type called `gossip`.

⚠️ **The dependency this creates, stated plainly.** If R9 retires the note flow,
`schema.NOTE_TYPES` and `apply.NOTE_TYPE_ATTRIBUTES` **must not be deleted with
it**. R9's removal list names `core/proposals.py` and the `AddNote` parts of
`core/schema.py`; these two constants are inside that blast radius and would have
to be explicitly kept or moved. **That is a line in R9's execution, not a
surprise to discover afterwards.**

## Open question 2: where does the spelling map live for the writer?

The writer **deliberately does not import the package** — *"the plugin must not
depend on the package resolving on Gramps' `sys.path`"* (`writer.py:33`).

⭐ **Recommendation: the writer inlines the two-entry map, and a test asserts it
equals `apply.NOTE_TYPE_ATTRIBUTES`.** The inlining is the existing, reasoned
pattern; the assertion is what stops it from being a duplicate nothing checks.

⛔ **Rejected: resolving the type in the package before storing the proposal.**
It would mean the stored graph is not the graph the agent sent, and the binding
property — *the thing written is the thing that was approved* — rests on those
being identical.

## Falsifier

⛔ **If criterion 3 cannot be made to hold — if a default cannot be added without
changing what an existing untyped graph writes — the design is wrong** and the
type must be required rather than optional, which is a breaking change to the
graph and needs its own ruling.

⚠️ **And a smaller one worth naming.** If the preview cannot show the type
without changing the rendering of untyped notes, criterion 4 collides with
criterion 3, and the collision is the thing to bring back rather than to resolve
by picking one.

## Estimated shape

Small. `NODE_KEYS` gains a key; one validation branch; one preview line; one
writer line; and the tests above. ⚠️ **The plan is FULL tier for what it touches,
not for its size.**
