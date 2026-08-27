# Restoring a tree from a backup

**R4 downgraded this project's strongest guarantee on purpose.** It used to be
*unwritable-by-construction* — nothing could touch a tree that had not been blessed by hand. It is
now **recoverable-after**: a write can happen, and a copy taken immediately before it is what makes
that survivable.

⚠️ **That guarantee is only worth what this page is worth.** R7 records the backup as *"a mechanism,
not a procedure someone can follow under stress"*. This is the procedure. Read it before you need
it, because the moment you need it is the worst moment to read it.

> ⛔ **This applies to the document route only.** The three commands — `preview`, `apply`, `approve`
> — take **no backup**. What they leave is an undo record, which is enough to reverse one note by
> hand and is not a copy of your tree.

---

## Before anything: do not do these

⛔ **Do not delete the damaged tree.** Not until a restore is verified and you have opened it and
looked. A damaged tree still holds everything that was right about it; a failed restore over a
deleted one holds nothing.

⛔ **Do not restore by importing.** Not `importxml`, not *Family Trees → Import*, not any route that
reads a `.gramps` file into an existing tree.

> ⚠️ **Importing into a tree that holds even one person silently regenerates every handle.** Handles
> are what notes, citations, events and family memberships point at. Nothing errors, nothing warns,
> and the tree afterwards looks correct — while every internal reference now names something else.
> **This is the single reason R7 chose a byte-level copy over Gramps' own export**, and it is why
> restoring is a file operation rather than an import.

⛔ **Do not do any of this with Gramps open.** Close it first, properly, through the File menu.

⛔ **Do not delete a `lock` file.** If one is present, Gramps — or something that crashed — still has
that tree. See *If a lock file is in the way* below.

---

## 1. Find the backup

Backups live in:

```
%APPDATA%\gramps-live-api\backups\
```

Each tree has one folder, named by a digest of the tree's directory rather than by its display name
— **so that renaming a tree cannot scatter its backups.** Inside each folder is a file called
`which-tree.txt` naming the tree in words.

```powershell
Get-ChildItem "$env:APPDATA\gramps-live-api\backups" |
  ForEach-Object { "{0}  ->  {1}" -f $_.Name, (Get-Content "$($_.FullName)\which-tree.txt" -First 1) }
```

Inside the right folder, the files are named with a UTC timestamp first, so they sort oldest to
newest:

```powershell
Get-ChildItem "$env:APPDATA\gramps-live-api\backups\<digest>\*.sqlite" | Sort-Object Name
```

**Twenty are kept per tree.**

## 2. Choose the right one, from the record rather than by guessing

⛔ **Do not pick by file timestamp.** A copied file's modification time is not its age.

The tree's own undo directory holds one record per write:

```
<your tree's directory>\.gramps-live-api-undo\
```

⚠️ **Both write routes use this one directory, and they write different records.** The three
commands write a note record; the document route writes the one described here. **Only the document
route's records name a backup at all** — so the listing below filters on the format, and a note
record simply does not appear.

⛔ **Without that filter a note record prints as a completed write with a blank backup path**, which
reads as *"a write whose backup is missing"*. It is not: it is a write that never had one.

```powershell
$DOC = 'gramps-live-api/document/1'
Get-ChildItem "<tree>\.gramps-live-api-undo\*.json" | Sort-Object Name | ForEach-Object {
  $r = Get-Content $_.FullName -Raw | ConvertFrom-Json
  if ($r.record -ne $DOC) { return }   # a note-route record: no backup, not restorable this way
  $state = if ($r.PSObject.Properties.Name -contains 'write_confirmed') { "INTENT ONLY" } else { "completed" }
  "{0}  [{1}]  wrote {2}" -f $r.written_utc, $state, ($r.created | ConvertTo-Json -Compress)
  "    backup {0}" -f $r.backup.path
  "    taken  {0}   people before: {1}" -f $r.backup.taken_utc, $r.backup.totals_before.people
}
```

> ⚠️ **If that prints nothing, the tree has no document-route writes** — and therefore no backups
> this procedure can restore from. See *If there is no backup for the write you want to undo* at the
> end of this page.

⭐ **Find the write you want to undo, and take `backup.path` from its own record.** That is what the
two timestamps are for: `backup.taken_utc` against `written_utc` tells you the copy predates the
change without your inspecting either database.

> ⚠️ **The backup fields are NESTED under `backup`** — `$r.backup.path`, not `$r.backup_path`. Worth
> saying because a wrong field name in PowerShell is not an error: it evaluates to nothing and the
> line prints blank, which under stress reads as *"there is no backup"*.

⭐ **`backup.totals_before.people` is the count recorded at backup time**, and it is what step 6 tells
you to check the restored tree against. It is stored precisely so that step has something to compare
with.

### ⛔ What `INTENT ONLY` means, and what it does not

A record is written **before** the transaction and completed **after** it. The one written first
carries `write_confirmed: false`; the completion has no such field at all, and carries the real
`written_utc` and the created Gramps IDs.

⛔ **`INTENT ONLY` means the completion was never recorded. It does NOT mean nothing was written.**

⚠️ There is a window in which the database has committed and the completion has not been written —
Gramps runs its post-commit callbacks *after* the SQLite COMMIT, and an exception in one of them
exits the write with **the tree already changed**. The plugin keeps the backup in exactly that case,
deliberately, because it may be the only way back.

### ⛔ No test on the record settles it. Do not look for one.

**This page has told you three different ways to decide whether an `INTENT ONLY` write committed, and
all three were wrong.** They are not written out here, because the useful thing is why no fourth
attempt will work either:

- **the IDs in `graph` are the ones being attached to.** They existed *before* the write, so finding
  them in the tree proves nothing;
- **anything the write created receives its Gramps ID inside the write.** Those IDs appear only in a
  completion — which, by definition, this record does not have.

⭐ **The record structurally cannot answer the question.** Not "answers it unreliably" — the
information is not in it.

### What to do instead

⭐ **Do not try to decide first. Try the newest candidate and look.**

Step 4 renames the damaged database rather than deleting it, **so restoring is reversible.** That
mechanism is already in this procedure and it is what makes the question safe to leave open: restore
this record's backup, open the tree, and see. If it is wrong, put the renamed file back and try the
next one.

> ⚠️ **The evidence that does exist, and what it is worth.** `backup.totals_before` holds the counts
> as they stood when the backup was taken. Comparing them with the tree (*Family Trees → Manage
> Family Trees*) tells you whether the tree holds more than the record expected. **That is evidence,
> not proof** — anything else you have done since moves the count too. Use it to choose which
> candidate to try first, never to decide without looking.

⛔ **And the failure direction that matters:** every version of the check this page has carried could
make a **correct** restore look like a failed one. Acting on that sends you to an older backup, which
**discards every change made between the two** — the outcome this whole procedure exists to prevent.
**A reversible attempt beats a confident guess**, and the guess has been wrong three times.

## 3. Close Gramps

Through **File → Quit**, and wait for the window to go.

⛔ **Do not force-kill it.** A killed Gramps can leave the database mid-transaction, which turns one
problem into two. If it will not close, leave it running and come back to it — nothing here is more
urgent than that.

Confirm it is really gone:

```powershell
Get-Process | Where-Object { $_.ProcessName -like "*gramps*" }
```

⚠️ **Match by pattern, not by name.** The process is `grampsw.exe`, and `Get-Process gramps` does not
match it — an empty result from the wrong query looks exactly like an empty result from the right
one.

## 4. Put the damaged database aside — do not delete it

Your tree's directory holds a file called `sqlite.db`. **Rename it. Do not remove it.**

```powershell
$tree = "<your tree's directory>"
Rename-Item "$tree\sqlite.db" "sqlite.db.damaged-$(Get-Date -Format yyyyMMddHHmmss)"
```

⭐ **This is the step that makes the whole procedure reversible.** If the restore turns out to be
wrong — wrong backup, wrong tree, a problem that was never in the database — you can put this file
straight back.

## 5. Copy the backup into place

```powershell
Copy-Item "$env:APPDATA\gramps-live-api\backups\<digest>\<chosen>.sqlite" "$tree\sqlite.db"
```

⛔ **Copy, do not move.** Leave the backup where it is. It is one of twenty and it costs nothing to
keep; a moved backup that turns out to be the wrong one is gone.

⚠️ **Copy it into the tree's own directory, next to `name.txt`.** Nothing else in that directory
should be touched — not `name.txt`, not the sentinel, not `.gramps-live-api-undo\`.

## 6. Open it and look

Start Gramps and open the tree **by name**:

```powershell
& "$env:ProgramFiles\GrampsAIO64-<version>\gramps.exe" -O "<tree name>"
```

⚠️ **`<version>` is yours to fill in, and this page will not guess it.** A pinned version here
pointed at an executable that does not exist on any other installation — and the setup supports
both version discovery and a custom `gramps_runtime`, so pinning one was wrong twice over.
`check` prints the runtime it found; the GUI executable sits beside it in the same directory.

### What the record gives you to look at

⛔ **This section describes what each field holds. It does not tell you what the tree should
contain** — four earlier versions tried to, and each was wrong in a different way. What follows are
the mechanisms; the judgement is yours, and step 4 makes it reversible.

**`backup.totals_before`** — the counts as they stood when the backup was taken. *Family Trees →
Manage Family Trees* shows the tree's current person count.

**`created`** — the Gramps IDs the write made. ⚠️ A `completed` record has this field; an
`INTENT ONLY` one does not, and **a completed record can carry an empty `created`** when the write
only attached to records that already existed.

**`approved_preview`** — the exact text you were shown, in two sections
([`document.py:679`](../src/gramps_live_api/host/document.py) and
[`:757`](../src/gramps_live_api/host/document.py)):

- Records under **ATTACHING TO EXISTING** show the name Gramps holds.
- Records under **CREATING NEW** show what the agent proposed — there is no tree record to read.

⭐ **That is the whole of what the two headings mean.** Everything a reader might want to conclude
from them — what should be present, what should be absent, whether the write landed — depends on
which record you restored from and what else you have done since, and the record does not carry that.

### So: open the tree and look

1. **The person you know best is intact** — events, notes and family, not just the name.
2. **The count** against `backup.totals_before`, if you have it.
3. **What `approved_preview` describes**, read with the two headings above in mind.

> ⛔ **Until all three look right, the damaged file is still your best copy** — and it is still on
> disk under the name you gave it in step 4.
>
> ⭐ **If it looks wrong, put that file back and try the next candidate.** Step 4 exists so this is
> reversible. **A reversible attempt beats a confident reading of a record that cannot answer the
> question** — which is what the four earlier versions of this section each tried to be.

## 7. Afterwards

Keep `sqlite.db.damaged-*` until you have used the restored tree for a while and are confident.
When you are, delete it yourself — nothing in this project will.

---

## If a lock file is in the way

A file called `lock` in the tree's directory means Gramps thinks that tree is open.

⛔ **Never delete it, and never use `--force-unlock`.**

⚠️ **The lock proves less than it looks like it proves.** It holds one line of `user@host`, with no
process id and no timestamp, and Gramps writes it on open **without checking whether one is already
there**. So it cannot tell you whether Gramps is genuinely running — which is exactly why deleting it
is not a fix. Close Gramps properly and the lock goes with it.

⭐ **And when Gramps crashed, so there is no process to close?** That is the case this section used
to leave with nothing to do. **Open the tree in Gramps and let Gramps decide about the lock** — it
owns that file, it is the only thing that can tell a stale one from a live one, and clearing it is
its call to offer, not ours to take. That is what `check` already tells you when it finds a lock;
this page used to stop one step short of it.

⛔ **What does not change: we never delete it, and never `--force-unlock`.** Not because a stale
lock is dangerous, but because *this file cannot tell you it is stale* — no process id, no
timestamp — so anything we did with it would be a guess about somebody else's tree.

## If there is no backup for the write you want to undo

The three commands take no backup, and a write refused before its copy succeeded leaves none by
design.

**What you still have** is the undo record in `.gramps-live-api-undo\`, which names every Gramps ID
the write created. Deleting those objects by hand in Gramps reverses the write, though it will not
restore anything the write *changed* about an existing object.

⛔ **Gramps' own Edit → Undo does not survive a restart.** It is a process-local list, discarded when
Gramps closes.
