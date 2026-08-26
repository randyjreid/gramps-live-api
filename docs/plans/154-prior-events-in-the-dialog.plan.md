# Plan — #154: show the owner what the record already holds

**FULL tier.** Touches the approval dialog, which is the surface the whole safety
argument rests on. ⛔ Not built. This page is the deliverable.

## Goal

The dialog shows what **will be written**. It does not show what is **already
there**. So a proposal adding a second event of a kind the person already has
renders exactly like a first one, and catching it requires the owner to know that
person's events from memory — for four or five people at a time.

Give him the other half of the comparison. **Information, not judgement.**

## Shape

For every record under `ATTACHING TO EXISTING`, list what it already holds:

```
ATTACHING TO EXISTING
  <id>  <person>  (b. <year>)
        already has: Birth <year> · Census <year> · Occupation <year>
      + Census, <date> -- <description>
```

## Mechanically checkable acceptance criteria

1. For every attached **person**, the dialog shows a line naming the events that
   person already holds, or says plainly that it holds none.
2. That line is rendered from the **tree**, never from the proposal.
3. A private record contributes nothing to it — the existing privacy gate applies
   unchanged, and a test asserts a private event does not appear.
4. The dialog states nothing about whether the proposal is a duplicate. No
   warning, no highlight, no reordering, no refusal.
5. If the prior-event read **fails or times out**, the dialog still opens and says
   the prior events could not be read. ⛔ It never blocks the approval and never
   silently omits the line, because an absent line reads as *"holds nothing"*.
6. The same graph rendered twice produces the same text.

## Out of scope

- Any judgement about duplication. ⛔ **A census saying one year against a tree
  saying another is two sources disagreeing, not a duplicate** — that is research,
  and the tool must not resolve it.
- Warning on same-type events. Most types legitimately repeat, and a warning that
  fires constantly is one nobody reads.
- Families, places and sources. Persons first; the others only if the same shape
  proves out.
- #156's "this type is new" marker. Same cause, different surface — see below.

## Open questions, with a recommendation

**1. What does it cost, and does R8's per-callback cap allow it?**
One read per attached person, on the GTK main thread, while the owner waits for a
dialog that has not appeared yet.

⭐ Measured what could be measured without a tree: the rendering code is
**0.008 ms at 3 events, 0.021 ms at 10, 0.076 ms at 30** — linear and trivial. So
**our code is not the cost.** What is unmeasured is the Gramps database read and
the main-thread hop, which is where the cost actually lives.

**Recommendation:** measure that first, against a real tree, before designing
around it — a household of five is five reads. ⚠️ If it is material, the reads
belong *before* the dialog is built rather than inside its construction, so the
owner waits once rather than watching a window assemble.

**2. Volume — does this make the dialog too long to read?**
A household attaches four or five people, each gaining a line.

⭐ **Recommendation: show only the event types the proposal actually touches.** If
the graph adds a Census, show the person's existing Census events and nothing
else. That keeps exactly the comparison the owner needs and drops the rest.
⚠️ **A dialog nobody finishes reading is the elision defect in a new form** — the
same failure as text that is delivered and never seen.

**3. What about a person the proposal only cites, rather than adding an event to?**
**Recommendation:** no prior-events line. There is nothing to compare against, and
a line there is volume without signal.

## Falsifier

If the measurement in question 1 shows the reads cost enough to be felt when the
dialog opens, **this design is wrong as written** and the work becomes *how to get
prior events in front of the owner without paying for them at approval time.*
