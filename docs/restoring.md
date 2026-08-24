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

Each is JSON, and each names the backup taken before that write, when it was taken, when the write
landed, and what was created:

```powershell
Get-ChildItem "<tree>\.gramps-live-api-undo\*.json" | Sort-Object Name | ForEach-Object {
  $r = Get-Content $_.FullName -Raw | ConvertFrom-Json
  "{0}  confirmed={1}  wrote {2}" -f $r.written_utc, $r.write_confirmed, ($r.created | ConvertTo-Json -Compress)
  "    backup {0}" -f $r.backup.path
  "    taken  {0}   people before: {1}" -f $r.backup.taken_utc, $r.backup.totals_before.people
}
```

⭐ **Find the write you want to undo, and take `backup.path` from its own record.** That is what the
two timestamps are for: `backup.taken_utc` against `written_utc` tells you the copy predates the
change without your inspecting either database.

> ⚠️ **The backup fields are NESTED under `backup`** — `$r.backup.path`, not `$r.backup_path`. Worth
> saying because a wrong field name in PowerShell is not an error: it evaluates to nothing and the
> line prints blank, which under stress reads as *"there is no backup"*.

⭐ **`backup.totals_before.people` is the count recorded at backup time**, and it is what step 6 tells
you to check the restored tree against. It is stored precisely so that step has something to compare
with.

> ⚠️ **A record whose `write_confirmed` is `false` describes a write that was refused or never
> finished.** Its backup is of a tree nothing changed. That is not the one you want.

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
& "$env:ProgramFiles\GrampsAIO64-6.0.8\gramps.exe" -O "<tree name>"
```

**Check three things, in this order:**

1. **The thing you were undoing is gone.** The undo record names the Gramps IDs the write created —
   search for one. It should not be there.
2. **The rest of the tree is present.** Open the person you know best. Check their events, notes and
   family, not just their name.
3. **The counts are plausible.** *Family Trees → Manage Family Trees* shows how many people the tree
   holds.

> ⛔ **Only when all three look right should you consider the restore finished.** Until then the
> damaged file is still your best copy, and it is still on disk under the name you gave it in step 4.

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
is not a fix. Close Gramps properly and the lock goes with it. If it does not, that is a question to
answer before restoring, not a file to remove.

## If there is no backup for the write you want to undo

The three commands take no backup, and a write refused before its copy succeeded leaves none by
design.

**What you still have** is the undo record in `.gramps-live-api-undo\`, which names every Gramps ID
the write created. Deleting those objects by hand in Gramps reverses the write, though it will not
restore anything the write *changed* about an existing object.

⛔ **Gramps' own Edit → Undo does not survive a restart.** It is a process-local list, discarded when
Gramps closes.
