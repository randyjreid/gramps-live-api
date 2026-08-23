# #105 — writing an event onto a family

⚠️ **A PLAN, awaiting the owner's approval. Nothing here is built.** It writes to a tree, so it is
FULL tier.

## The defect this closes, and why it is not just a missing feature

`events[]` in the proposal graph carries only `people`, and `gramps_live_api_writer.write` only ever
calls `add_event_ref` on a **person**. The family loop never attaches an event at all.

⛔ **So the workflow does not terminate:**

1. `list_family_events` reports the couple has no marriage;
2. a marriage is proposed;
3. it is written onto the two **spouses**;
4. `list_family_events` **still reports none** — and step 2 can happen again, forever.

**That is worse than not having the read**, because the read now confidently reports a gap that
acting on cannot close.

⭐ **PR #104 shipped the honest interim**: both tool descriptions state that an event can only be
attached to people, and tell the model to report the gap to the owner rather than write a record
that lands in the wrong place. `test_the_family_event_gap_is_stated_rather_than_implied` pins that.
**Building this removes the need for that wording, and the wording must come out in the same
change** — a limitation notice that outlives its limitation is a new false statement.

---

## ⚠️ The easy half, stated only so it is not mistaken for the work

`Family.add_event_ref` exists and behaves like `Person.add_event_ref`. The write is a few lines in
the family loop, beside the child-ref append that already lives there.

**That is not the slice.**

## ⭐ The hard half: the preview must render it

R3's ruled criterion is **no byte reaches the tree that was not rendered in full to the human.**

⛔ **A marriage attaching to a household the owner never saw named is that criterion failing.** He
must be able to read *which* family gains the event, by the name the **tree** holds — not the name
the model proposed — because recognising the wrong household is the only check there is.

**This is harder than the person case for a specific reason.** A person node carries a `gramps_id`
the owner can be shown a name for. A family event names a family that may itself be new in the same
graph, so the preview has to render *"the marriage joins the household you are also creating on the
line above"* without the household existing yet. **The renderer already solves this for children via
local ids and `named_node`; the same mechanism has to reach events.**

## Acceptance criteria

| # | criterion |
|---|---|
| **A1** | `events[]` accepts `family: <family local id>`, validated by `document.parse` with the same reference rules as `place` and `people`. |
| **A2** | The writer calls `add_event_ref` on the family, and the family is committed. ⛔ Both sides written explicitly, as the child refs already are. |
| **A3** | **The preview names the family the event joins**, read from the tree when it exists there, from the graph when it does not. |
| **A4** | `list_family_events` reports the event afterwards. ⭐ **This is the criterion that proves the loop terminates**, and it is the one the whole slice exists for. |
| **A5** | The role written is the role the preview showed. |
| **A6** | The interim wording added by #104 is **removed**, and its test with it. |

## ⚠️ Open questions the build must answer, not assume

**The role vocabulary is not the person one.** `EventRoleType` has `FAMILY` and `PRIMARY`, and what a
family event ref should carry is a Gramps convention this project has not established. ⛔ **Do not
guess it from the person path** — `_event_role` already learned that lesson: it silently fell back to
`PRIMARY` and the dialog said *Godparent* while the tree recorded something else.

**Does an event belong to a family or to its members, or both?** Gramps' own data model allows a
marriage on the family and separate event refs on each spouse. **The build must pick one and say
why**, because a proposal that writes both produces a record the owner did not read as duplicated.

**Attaching an event to an EXISTING family is a larger claim than attaching a child.** #104 takes the
position that attaching is addition rather than modification. ⚠️ **A marriage is a much bigger
assertion about two people than a child reference is**, and whether it is still *addition* under R4's
reading is a question for the owner, not a detail for the build. **If the answer is that it needs its
own ruling, this slice stops at that question rather than proceeding under an assumption.**

## Out of scope

- ⛔ Editing or removing an event already on a family.
- ⛔ Any other event type gaining a family attachment implicitly — the graph says `family` or it does
  not.
- ⛔ Deduplicating against an existing marriage. **The tool reports; the owner decides.** `#106`'s
  class is the reason to be careful here: a preview that says *"this family already has a marriage,
  so nothing will be added"* is a claim about the write, and claims about the write are exactly what
  keeps going wrong.

## How this interacts with #106

⚠️ **They touch the same surface and #106 should probably land first.** #106 is about the preview and
the write disagreeing; this slice **adds a new thing for them to disagree about**. If the derived-preview
question #106 raises is answered, this becomes much safer to build; if it is not, this adds a fourth
direction for the same class to fail in.

⛔ **That is a sequencing opinion, not a decision.** The owner orders them.
