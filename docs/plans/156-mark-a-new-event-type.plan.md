# Plan — #156: an invented event type should not look like a standard one

**FULL tier.** Touches the approval dialog. ⛔ Not built. This page is the
deliverable.

## Goal

`_event_type` falls back to `EventType((EventType.CUSTOM, <the word you sent>))`.
So **any unrecognised `type` writes**, creating a new custom event type in the
tree carrying whatever the model chose.

Nothing refuses it, and **nothing in the dialog says the type is new.** The
preview renders `+ Literacy, <year> -- <text>` — indistinguishable from a standard
type the owner already uses.

⚠️ A model transcribing a document has wide latitude over that word. Given a
census with a dozen columns and no constraint, it invents a type per column, and
next month invents variants of them. **The tree accumulates a vocabulary nobody
chose, one approval at a time, each individually reasonable-looking.**

## Mechanically checkable acceptance criteria

1. An event whose `type` is not one Gramps already knows is rendered in the dialog
   **marked as new** — e.g. `+ Literacy (NEW EVENT TYPE), <date>`.
2. An event whose type Gramps does know is rendered **exactly as it is today**. A
   test asserts the standard-type rendering is unchanged, or the marker becomes
   noise and stops being read.
3. "Already knows" means **the same test the writer uses** — one expression, not
   two. ⛔ Two ways of deciding what is standard is this project's most-recorded
   defect class.
   ⚠️ **That test is three conditions, not one.** `gramps_live_api_writer.py:139`
   requires a **non-empty** normalised key, `hasattr(EventType, key)`, **and** that
   the attribute value `isinstance(..., int)`. An earlier draft named `hasattr`
   alone — which would render a type as standard while the writer stored it as
   custom, recreating the very disagreement this criterion exists to prevent. The
   predicate must be **extracted or communicated whole**, not restated.
4. ⚠️ **Deferred, explicitly, and the marker's meaning changes with it.** Ideally
   a custom type **already present in the tree** would not be marked new — a type
   the owner has used before is his vocabulary, not an invention. That needs a
   database read, which drags this into #154's cost question.
   ⛔ **So it is out of scope for a first implementation, and the marker therefore
   means *"not a standard Gramps type"*, not *"never seen before"*.** An earlier
   draft listed this as an acceptance criterion and then recommended shipping
   without it — which would have mislabelled the owner's established vocabulary
   while claiming to state a fact.
5. The check runs without a database where it can, so the renderer stays testable
   under CI.

## Out of scope

- **Refusing custom types.** They are a real Gramps feature and the owner may want
  them. This marks; it does not decide.
- Changing `_event_type` itself. The write behaviour is correct; the **dialog** is
  what is blind.
- Note types, place types, attribute types. Events first.
- Pinning an allowed list in the tool description. ⛔ That is guidance, not a
  bound, and the description is delivered truncated (#151) so the model may never
  see it. It is tonight's mitigation, not the fix.

## The relationship to #154 — read them together

| | shows what will be written | does not show |
|---|---|---|
| **#154** | the event being added | that the person already has one like it |
| **#156** | the type being used | that the type does not exist yet |

⭐ **One cause, two surfaces:** the dialog renders the proposal and never the
context the owner needs to judge it. Whoever builds either should look at the
other — **the remedy is the same kind of thing, and building it twice separately
is how two half-solutions get made.**

**Recommendation: build #156 first.** It is smaller, it needs no per-record
database read, and it settles the rendering convention — how the dialog marks
something the owner should look twice at — that #154 then reuses.

## Open questions, with a recommendation

**1. Should the deferred criterion 4 ever be built?**
It needs the set of custom types already in the tree — a database read, which puts
it back into #154's cost question.

⭐ **Recommendation: leave it deferred.** Marking every
non-standard type as new is a small over-warning on types the owner has adopted,
and it needs no read at all. Add criterion 4 only if that over-warning proves
irritating in use — ⚠️ **a use-derived trigger, not a guess.**

**2. What exactly should the marker say?**
**Recommendation:** `(NEW EVENT TYPE)` inline, not a separate warning block. It
sits where the owner is already reading, and it states a fact rather than an
opinion — consistent with #154's *information, not judgement*.

**3. Does this belong in the caller preview too, so the model self-corrects?**
**Recommendation: yes, and cheaply** — the agent learning "that type does not
exist" before the owner ever sees the dialog is strictly better than the owner
catching it. But the dialog is the safety surface and must not depend on the agent
having noticed.

## Falsifier
⭐ **The owner is running a census before deciding on this plan, and that run
outranks any further refinement here.** This plan is wrong if the run produces no
non-standard types at all — if the columns he actually wants map onto types Gramps
already knows, the marker guards against a risk that did not materialise, and the
right answer is the pinned vocabulary in the brief rather than code. **A falsifier
that is a demo about to happen is worth more than a page refined further in the
abstract.**


If the writer's notion of a standard type cannot be reached from the renderer
without importing Gramps into `document.py`, criterion 3 is unsatisfiable as
written — `document.py` importing no `gramps` and no `gi` is load-bearing and is
what lets the renderer run under CI. **The design would then need the writer to
tell the renderer, rather than the renderer asking.**
