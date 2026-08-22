# Handover — graph nodes may name something that already exists

**Branch `document-write-route`, one new commit, not pushed.**

⚠️ **There are TWO dialogs stacked on screen.** The top one is the real test.
See *"What is on screen"* before anything else.

---

## The change

**People, places and the source may now carry `gramps_id`.** Present → resolve to
the existing record. Absent → create, exactly as before.

```json
"people": [{"id": "p1", "gramps_id": "I0123"}]
```

⛔ **Not events** — their handles are invisible in the Gramps UI, so a field
nobody can fill is a field that only ever holds a mistake. Not citations,
families or notes: a document asserting a relationship asserts a **new** claim
about it, even between people who already exist. A `gramps_id` on any of those is
**refused**, not ignored — a silently ignored field is one somebody comes to rely
on.

⛔ **Nothing already in the tree is ever modified.** An existing object is only
attached to. `given`/`surname`/`gender` on an attached node are **dropped and
reported in the dialog** rather than written over what Gramps holds. That is what
keeps this out of ruling territory: R3 wants everything written rendered in full,
and an addition is fully renderable. **A diff is not, and is not this.**

## What is verified, and how

| | |
| --- | --- |
| **Refusal names every missing id, no dialog, nothing written** | ✅ live, `403` |
| **Resolution against the real tree** | ✅ live |
| **The dialog renders the name from the TREE** | ✅ live — see below |
| **`gramps_id` refused on events / families** | ✅ unit |
| **Preview renders the two sections as specified** | ✅ unit |
| **The attach WRITE lands on the existing person** | ⚠️ **not verified — your click** |
| suite | 1504 passed, 6 skipped; ruff and mypy clean. **No test broken this time.** |

The refusal, live:

```
HTTP 403
these Gramps IDs are not in the open tree: I9999 (person), P9999 (place),
S9999 (source). Nothing was written and no dialog was shown. Look them up
with list_people, or leave gramps_id out to create a new record.
```

## ⭐ The safety mechanism proved itself, by catching me

I picked a four-digit test id I assumed was obviously fake. **It is a real
person in your copy** (the id is in my message, not in this file --
it is tracked and this repository is public) — the tree has 2,933 people and I had assumed the ids stopped near the
ones added this week. The route resolved it and opened a dialog **showing that
person's real name, read from the tree.**

⭐ **That is exactly the mechanism working.** I meant nobody; the dialog showed
somebody; a human reading it would cancel at once. If the preview had echoed back
the name *I* supplied — "Also Missing" — there would have been nothing to notice.

⛔ **Nothing was written to that person.** That graph carried no events and no
citations, so even "Write it" writes nothing. Its dialog is the **bottom** of the
two on screen.

⚠️ **I have not put that person's name in any tracked file**, and the test graphs
that named their id are in my scratchpad, not the repo.

## What is on screen, and what to do

**Two stacked modal dialogs.** Deal with the top one first — GTK will not let you
reach the lower one until it is answered.

### Top dialog — the real test. It should read close to:

```
ATTACHING TO EXISTING

  I0024  Standlake, Peregrine
      (the document also gave given, surname -- NOT applied; nothing
       already in your tree is changed)
      + Baptism, 1868-05-03, St Bartholomew under Marle
      + Citation -> S0010  Whitmarsh Hollow census, 1861 p.folio 44
  S0010  Whitmarsh Hollow census, 1861

CREATING NEW

  Place   St Bartholomew under Marle
```

⭐ **Check the two names against the screen rather than trusting this file.**
`I0024` is *Peregrine Standlake* — the invented person **you** wrote in last
night by clicking. `S0010` is the invented *Whitmarsh Hollow census, 1861* from
the write probe. **I deliberately targeted invented records rather than real
ones**, so nothing of yours is exposed in a tracked file. *If you wanted this
proved against a real person instead, the code path is identical —
`get_person_from_gramps_id` — and you can repeat it with any id.*

**Click "Write it".** Then check the counts below.

### Counts immediately before your click

```
person 2933   event 10929   place 2255
source 13     citation 15   note 64    family 1586
```

**After clicking "Write it" on the top dialog, this is the whole test:**

| | expected |
| --- | --- |
| **person** | ⭐ **2933 — UNCHANGED.** This is the point. No duplicate. |
| **source** | **13 — UNCHANGED.** `S0010` was reused, not copied. |
| event | 10930 (+1, the baptism) |
| place | 2256 (+1, St Bartholomew under Marle) |
| citation | 16 (+1) |

And on **I0024** itself: event refs `0 → 1`, citations `1 → 2`.

### Bottom dialog

Trivial and harmless. **Cancel** it.

## ⚠️ A mess I made and cleaned up

**The write probe was still installed in `%APPDATA%\gramps\gramps60\plugins\`
and re-ran on every Gramps start**, writing its four-person invented household
each time. It ran twice before I noticed. **I have removed it.**

So the copy now holds **two** Quillfeather families:

- **I0016** Ambrose · **I0017** Serafina · **I0020** Tobias · **I0021** Marigold
- **I0029** Ambrose · **I0032** Serafina · **I0033** Tobias · **I0034** Marigold

plus the duplicated events, places and source that came with the second run. All
invented; delete freely. ⛔ **I deleted nothing** — deletion is a destructive
operation and #25 defers those until a backup is proven.

**The lesson, which is the same one as last time in a new costume:** a probe that
fires on `database-changed` is not self-terminating just because it guards
against running twice *in one process*. Its guard was per-process; Gramps
restarts were the loop.

## Restart your MCP connection

`propose_document`'s description is rewritten and now spells out the local-id
convention, the `gramps_id` field, and — in capitals — *look the person up with
`list_people` first and pass their Gramps ID*. It also says that `list_people`
reads a possibly-stale export, and that **Gramps IDs are stable once assigned**,
so an id from a stale export still points at the right person; the only risk is
that somebody added very recently is not in it yet.

**Claude cannot do any of this unless the tool tells it to, and your client is
holding the old description.**

## The single next thing I would do

**Nothing, until you have run it on a real document of yours.** Every remaining
idea I have — media, matching by name, a second document in one batch — is a
guess about what you will hit. **One real parish register through this end to end
will name the next thing better than I can.**
