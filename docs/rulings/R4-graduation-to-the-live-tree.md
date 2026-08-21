# R4 — Graduation to the live tree: blessed, with a backup taken first

**Ruled 2026-08-21.** This page records a decision. It is not a proposal and it is not argued again
here. The case that was put is in `.claude/decisions/R4-graduation-to-the-live-tree.md`.

⚠️ **When ruled, nothing described below was built.** In particular the arming check this ruling
depends on does not exist — see the preconditions.

---

## The ruling

**Option B. The live tree may carry `.gramps-live-api-copy`**, with a backup taken first.

### ⛔ The downgrade, approved in its own words

The screen was explicit that this had to be approved as a downgrade rather than absorbed as a
detail, so it is recorded as it was put:

> **The guarantee changes from unwritable-by-construction to recoverable-after, and that is a change
> of kind, not of degree. The first says a bad write cannot occur and holds without anyone doing
> anything. The second says a bad write can occur and can be reversed, and holds only if a backup
> exists, predates the damage, and the damage is noticed. This is approved as a downgrade.**

## Three things this ruling settles

### 1. The backup stays per-write, not per-session

**This keeps #25's condition intact.** Its roadmap row warns that the coupling holds only while
backup stays **per-write**: at per-session cadence, restore *is* batch undo, and destructive
operations jump the queue on that basis. **B keeps it per-write deliberately**, so the ordering that
put backup before delete survives this ruling rather than being quietly inverted by it.

### 2. ⭐ No config flag is adopted

**Blessing is creating a file, not setting a setting.**

So R8's *"one config flag to relax later"* is **not taken up**, and `docs/using.md`'s sentence —
*"there is no flag that overrides it, and there is no configuration key that reaches the check"* —
**stays true and needs no change.**

⛔ **Stated explicitly because the apparent contradiction cost two review rounds.** There is no
conflict to resolve and no wording to reconcile: the mechanism this ruling adopts is a file on disk,
which is the same mechanism `using.md` already describes. **This ruling retires that thread.**

### 3. It depends on R7 shipping

**The sentinel does not go on the live tree until a backup can actually be taken.**

⚠️ **This is a sequencing condition, not a caveat.** Blessing the live tree before the backup path
works would take the downgrade's cost — a bad write can occur — without delivering the thing that
pays for it.

## Preconditions inherited from the screen

1. **A backup can be taken.** R7 rules the mechanism; it is not yet built.
2. **A restore preserves handles.** ⭐ **R7's file-replacement route satisfies this; the export route
   does not** — importing into a tree holding even one person silently regenerates every handle.
3. ⚠️ **The arming check refuses a tree with no sentinel, under test, in the host — and that check
   does not exist in `src/gramps_live_api/host/` at all today.** Verified against the source: the
   host package contains no sentinel check and no write path. **This is the largest gap between this
   ruling and anything that could act on it.**
4. **The backup's age relative to the write is visible without archaeology.** A recoverable-after
   guarantee that requires forensics to evaluate is not one the owner can rely on in the moment.

## ⭐ One piece of evidence, because it is the only production observation of the guard there is

On **2026-08-19**, the blessing check **refused the live tree from inside a running Gramps process,
unprompted**, with **both limbs firing** — the missing sentinel, and the parent directory failing the
`name.txt` check that establishes a directory is a family tree at all.

**That is the reasoning in `src/gramps_live_api/core/apply.py:55-62` exercised rather than argued.**
The sentinel is specified to live *inside* the tree directory precisely because a sentinel placed
beside one would sit in the shared parent and bless every tree in it — including the live one — and
on that day the parent-directory path was the second limb that refused.

⚠️ **The guard has now been tested against the real thing rather than against a fixture.** It is the
floor this ruling stands on, not an aspiration.

## Accepted risks

- **The strongest guarantee this project had is gone by choice.** Unwritable-by-construction needed
  nobody to be careful. Recoverable-after needs a backup to exist, to predate the damage, and for
  someone to notice.
- **"The damage is noticed" is unbounded and unowned.** Nothing in this ruling detects a bad write.
- **The blessing is a file the owner creates by hand**, so it can be created by mistake, and nothing
  distinguishes a deliberate blessing from an accidental one.

## What this does not settle

- **When the live tree actually gets blessed.** That is a decision for the day R7 ships, not this
  one.
- **Whether backups are pruned, and by what.**
- **Nothing about what may be written** once the tree is blessed — that is R3's territory and the
  operation registry's.
