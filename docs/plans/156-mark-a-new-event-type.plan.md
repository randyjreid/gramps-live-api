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
   defect class, and the writer's `hasattr(EventType, key)` is the one that
   decides what actually gets written.
4. Custom types **already present in the tree** are not marked new. A type the
   owner has used before is his vocabulary, not an invention.
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

**1. Where does "does the tree already use this type" come from?**
Criterion 4 needs the set of custom types already in the tree. That is a database
read, and it puts this back into #154's cost question.

⭐ **Recommendation: ship criteria 1–3 and 5 without it.** Marking every
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

If the writer's notion of a standard type cannot be reached from the renderer
without importing Gramps into `document.py`, criterion 3 is unsatisfiable as
written — `document.py` importing no `gramps` and no `gi` is load-bearing and is
what lets the renderer run under CI. **The design would then need the writer to
tell the renderer, rather than the renderer asking.**
