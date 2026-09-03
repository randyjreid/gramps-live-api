# Using it: a proposed note becomes a note on a person

**There are two write routes now, and this page covers both.**

**The note route**, which most of this page is about, is three commands you type. It takes a **note
you propose for a person**, shows you the one sentence it would write, waits for you to say yes,
writes it into **a copy of your tree that you have blessed by hand**, and then reads it back in a
fresh process to prove it is there. Nothing in it runs without you typing it.

**[The document route](#the-other-route-a-document-approved-inside-gramps)** works the other way
round: Gramps stays open, the approval is a dialog inside it, and a whole graph is written as one
transaction. **It takes a byte-level copy of the tree before every write.**

> ⚠️ **This page used to say the tool "does exactly one thing" and that the second plugin "writes to
> no tree."** Both were true when they were written and neither is now. They are corrected here
> rather than quietly deleted, because a setup page that once told you something false is worth
> knowing about.

⛔ **Neither route has an unattended path.** Every write on both of them waits for you.

> ⚠️ **Green CI is not evidence this works.** The runners have no Gramps, no `gi` and no tree, so
> the write, the plugin registration and the read-back cannot be observed there at all — the round
> trip test **skips**, by name, in the CI log. That is the stated cost of doing this through Gramps'
> own door rather than by parsing a file. **The verification is you, opening the copy in Gramps and
> finding the note.**

---

## Once: three pieces of setup

> **Every command in this document is PowerShell**, and every one of them is run **from the root of
> this checkout** — that is what `$PWD` refers to below. Nothing here needs `cmd.exe`, and nothing
> here needs a placeholder filled in by hand.

### 1. A copy of your tree, blessed by hand

In Gramps: **Family Trees → Export** your tree to Gramps XML, then **Family Trees → Import into a new
family tree** and give it a name that says it is a copy.

Then find that copy's directory. Gramps keeps its trees under `$env:APPDATA\gramps\grampsdb\`, one
opaque directory per tree, with the tree's name in a `name.txt` inside it. This lists them by name:

```powershell
Get-ChildItem "$env:APPDATA\gramps\grampsdb" -Directory | ForEach-Object {
  [pscustomobject]@{ Name = (Get-Content "$($_.FullName)\name.txt" -Raw).Trim(); Path = $_.FullName }
}
```

Hold the copy's path in a variable — the next two steps both use it, and it is the one value in this
setup that is worth not retyping. **The table's `Path` column is already the full path**, so paste it
as it stands and do not put the directory in front of it again:

```powershell
$copy = "<the Path for your copy from the table above>"
```

**Then create an empty file inside that directory called `.gramps-live-api-copy`:**

```powershell
New-Item -ItemType File "$copy\.gramps-live-api-copy"
```

That file is the whole permission model. Nothing is written to any tree that does not carry it, there
is no flag that overrides it, and there is no configuration key that reaches the check. The check
resolves symlinks and junctions first, so a shortcut named like the copy cannot point at the live
tree.

> ⚠️ **Inside the tree's directory, not beside it.** Beside it means in `grampsdb\`, which holds
> *every* tree — including the live one.

### 2. The plugin, where Gramps looks for plugins

Gramps runs our code through its own CLI tool door, so it has to be able to find it. Make a junction
from Gramps' user plugin folder to this checkout — **from the checkout root**, so that `$PWD` is it:

```powershell
$plugins = (Get-ChildItem "$env:APPDATA\gramps" -Directory -Filter "gramps*" |
            Where-Object { Test-Path "$($_.FullName)\plugins" } |
            Sort-Object Name -Descending | Select-Object -First 1).FullName + "\plugins"
$link    = "$plugins\gramps-live-api"
New-Item -ItemType Directory -Force $plugins | Out-Null
if (Test-Path $link) {
  "already there: $((Get-Item $link).Target)"
} else {
  New-Item -ItemType Junction -Path $link -Target "$PWD\gramps_plugin" | Out-Null
  "created"
}
```

⭐ **The version folder is found, not typed.** This used to hardcode `gramps60`,
which is wrong the moment your Gramps is not 6.0 and gives no hint that it is —
you would create a junction in a folder Gramps never reads. It now picks the
newest `gramps*` folder that actually contains a `plugins` directory, which is
the same shape `check` already uses to find the plugin (`_PLUGIN_GLOB`), and
which skips `grampsdb` — the sibling folder holding your trees, not plugins.

⚠️ **Run it twice and it says so, rather than failing.** The first version of this
step used a bare `New-Item`, which errors with *"an item with the specified name
already exists"* on the second run — and that reads exactly like the setup is
broken when it is in fact already done. It prints what the junction points at, so
a link left over from an earlier checkout is visible rather than assumed.

A **junction** does not require Administrator — only a symbolic link does. If that surprises you, it
surprised us too; it is measured, not assumed.

Copying the files works just as well and goes stale; the junction does not.

> ⚠️ **That folder holds a second plugin**, R8's loopback host, which Gramps starts at launch. It
> binds `127.0.0.1` and needs a bearer token; `docs/slice-a-demo.md` says what it does and how to
> see it. **A copy rather than a junction breaks it**, because it finds its own source by resolving
> the link — one more reason to make the junction.
>
> ⛔ **That plugin is no longer read-only, and it no longer writes to no tree.** It now carries a
> second write route — *the document route* — which puts a dialog in front of you inside Gramps and
> writes through Gramps' own connection with the tree open. **[The other route](#the-other-route-a-document-approved-inside-gramps)
> below says what it does, how it differs from the three commands, and what it backs up first.**

### 3. Where the copy is

The config file lives at `$env:APPDATA\gramps-live-api\config.json` and holds one key. Write it with
`ConvertTo-Json` rather than by hand — JSON requires every backslash in a Windows path to be doubled,
and that is a trap worth handing to the machine:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\gramps-live-api" | Out-Null
@{ copy_path = $copy } | ConvertTo-Json | Set-Content "$env:APPDATA\gramps-live-api\config.json" -Encoding utf8
```

That uses the `$copy` variable from step 1. Read it back to see what it wrote:

```powershell
Get-Content "$env:APPDATA\gramps-live-api\config.json"
```

One object, one key — `copy_path`, holding your copy's directory with each backslash doubled, which
is what makes writing it by hand worth avoiding.

**This file lives outside the repository, and that is deliberate** — it is the one value this project
must never commit. Nothing expands environment variables inside it, so the path is written out in
full. Add `"gramps_runtime"` beside it if you have more than one Gramps installed, or if it is not
under `$env:ProgramFiles\GrampsAIO64-<version>\`; with exactly one installed it is found for you, and
with two you are asked to name one rather than have this guess.

`GRAMPS_LIVE_API_COPY` and `GRAMPS_LIVE_API_RUNTIME` override both, for a one-off run.

---

## The three commands

Run them from the checkout, in this order.

### First, make a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe --version
```

⚠️ **If the first line prints a Microsoft Store message instead of doing
anything, that is the Store alias, not Python.** On a stock Windows box `python`
is a stub that opens the Store, and it answers questions with a sentence rather
than an error — so it looks like output. **The failure announces itself here:
no `.venv` appears and the second line cannot run.**

**The remedy:** install Python 3.10 or newer from python.org, or turn the alias
off under *Settings → Apps → Advanced app settings → App execution aliases*. If
you have the `py` launcher, `py -3 -m venv .venv` works too and is never the stub.

⭐ **Every command below uses `.\.venv\Scripts\python.exe`**, so once that
second line prints a version, which interpreter you get stops being a question.

```powershell
$env:PYTHONPATH = "src"
```

### 1. `check` — is everything in place?

```powershell
.\.venv\Scripts\python.exe -m gramps_live_api check
```

You should see the runtime, the plugin, the source it resolves to, your copy, and each of
the two files the check looks at:

```
  ok   runtime: ...\GrampsAIO64-<version>\grampsd.exe
  ok   plugin: ...\gramps\gramps60\plugins\gramps-live-api
  ok   source: ...\gramps-live-api\src
  ok   copy: ...\grampsdb\1a2b3c4d
  ok   name.txt: is a Gramps family tree directory
  ok   .gramps-live-api-copy: is blessed for writing by hand
  ok   lock: not locked
  ok   export: not configured, and nothing in slice 1 needs one -- list_people and
       propose_note are what cannot run. Set export_path in ... to use them

ready
```

> **The `export` line is slice 2's, and an unconfigured export does not fail this report.** Nothing on
> this page reads an export: `preview`, `apply` and `check` do not. It is `list_people` and
> `propose_note` — the MCP tools in `docs/slice2-mcp.md` — that need one, so the line names them
> rather than refusing. Once you *have* configured an export, a **stale** one does fail, and that is a
> privacy check rather than a nag; see that document.

**Now point it at your real tree** and watch it refuse — its directory is the *other* row in step 1's
table, the one whose `name.txt` holds your live tree's name:

```powershell
.\.venv\Scripts\python.exe -m gramps_live_api check "<the Path for your LIVE tree>"
```

The same report, with one line changed and a non-zero exit:

```
  ok   name.txt: is a Gramps family tree directory
  NO   .gramps-live-api-copy: is NOT blessed for writing by hand
  ok   lock: not locked

not ready: .gramps-live-api-copy
```

`check` opens no database. It looks at directories and reports, which is why it is safe to point at
anything.

> ⚠️ **This copy of the check is advisory.** It is here so a wrong path meets a sentence at your
> terminal instead of a refusal from inside a Gramps subprocess. The one that decides runs *inside*
> Gramps, against the database Gramps has already opened — so a wrong path cannot produce a write
> even if this check were skipped entirely.

### 2. `preview` — what exactly would be written?

Write the note you want as a file. Call it `op.json` and put it **beside the tool's own config**,
which is already outside the checkout and is where the demo actually put it:

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\gramps-live-api" | Out-Null
```

⚠️ **One location, chosen deliberately.** This file holds family data. Anywhere
outside the checkout keeps it out of a public repository, but the home root puts it
alongside everything else you own, and the documentation and the practice had
drifted apart — the page said one place and the demo used another. `$env:APPDATA\gramps-live-api`
is where `config.json` already lives, and it wins.

⭐ **`op.json` is also in `.gitignore`**, so a copy left in the checkout by accident
cannot be committed. That is a backstop, not the instruction: the file belongs
outside the checkout.

```json
{
  "type": "add_note",
  "target": {
    "object_type": "person",
    "handle": "<the person's handle>",
    "gramps_id": "<the person's Gramps ID, for example I0044>"
  },
  "note_type": "research",
  "text": "The note you want to attach."
}
```

`note_type` is `research` or `todo`. `object_type` is `person` — this slice attaches a note to a
person and refuses the other eight object types by name.

**Where the handle comes from.** Gramps does not show handles anywhere in its interface, and this was
the sharpest rough edge in slice 1.

> ⭐ **Slice 2 does this for you.** `list_people` reads the export — decompressing it, which the
> paragraph below never mentioned — and returns the name, birth year, Gramps ID and handle, already
> stripped. See `docs/slice2-mcp.md`. **The instructions below are what you do without it**, and
> they are kept because they still describe what the two identifiers *are*.

Open the Gramps XML export you made in step 1 in a text editor
and find the line that opens the person you want: it carries both an `id` and a `handle` attribute.
**Take the handle's value and drop its leading underscore** — Gramps strips underscores from handles
when it imports, so the value in your copy is the attribute without it.

⚠️ A `.gramps` export is **gzip-compressed XML**, so "open it in a text editor" does not work until
you decompress it — and a real tree is megabytes holding thousands of people. That, and the fact that
this document's own author would not do it, is issue #64 and the whole reason slice 2 exists.

Both halves are required **in an operation file**, and they are checked against each other: the
Gramps ID is what resolves the person, and if the handle names a different object the write is
refused rather than guessing which one you meant.

⭐ **The MCP tool no longer needs the handle.** `propose_note` takes a Gramps ID and resolves the
handle from the same lookup that reads the person's privacy flag (#64). Passing one is still allowed,
and a supplied handle is used as given so the cross-check above still happens. This paragraph is
about the operation file you write by hand.

```powershell
.\.venv\Scripts\python.exe -m gramps_live_api preview "$env:APPDATA\gramps-live-api\op.json"
```

```
add a research note to person I0044: “The note you want to attach.”
```

That sentence is the thing you are approving. `preview` writes nothing and opens nothing.

> ⚠️ **`preview` and `apply` are not linked, and you should not act as though they are.** `preview`
> leaves nothing behind — no token, no state — so `apply` has no knowledge that you ran it. `apply`
> re-reads `op.json` for itself, shows you what it found, and asks. **Edit the file between the two
> commands and `apply` will happily write the edited version**, because the version it shows you and
> the version it writes both come from its own read.
>
> So the sentence you approve is always `apply`'s own, and reading it at the prompt is what protects
> you — not having previewed earlier. `preview` is for looking before you commit to anything; it is
> not a lock. Binding an approval across the two steps is [#71](https://github.com/randyjreid/gramps-live-api/issues/71).

### 3. `apply` — write it, then go and look

```powershell
.\.venv\Scripts\python.exe -m gramps_live_api apply "$env:APPDATA\gramps-live-api\op.json"
```

```
add a research note to person I0044: “The note you want to attach.”
write this into <the copy's directory>? [y/N] y
note N0021 written
  note handle   104072952a584e83a027e511388d
  person handle <the person's handle>
read back from a fresh process: 'The note you want to attach.'
```

The whole thing takes about **three and a half seconds** — two Gramps cold starts, one to write and
one to go back and look.

Answer anything but `y` and nothing at all happens.

> **A long note prints twice, and the second one is the one that matters.** The first line is the
> one-sentence summary, and it shortens the note's text so it fits. Whenever it has shortened
> anything you also get an `in full:` line carrying the whole text, because you cannot approve what
> you were not shown:
>
> ```
> add a research note to person I0044: “Marriage recorded in the parish register, second vo…”
>   in full: add a research note to person I0044: “Marriage recorded in the parish register, second volume, page 141. Confirmed against the original.”
> write this into <the copy's directory>? [y/N]
> ```
>
> What is written is bound to the **whole operation**, not to the summary — so a note differing only
> after the summary's cut-off is a different operation and is refused, not silently accepted.
> Whitespace is the one thing the display does not preserve: runs of spaces and newlines are shown
> collapsed, and stored exactly as you wrote them.

`apply` exits **0 only when the note was written *and* found again by a second, fresh Gramps process**
that went looking for it. Every other outcome exits non-zero: a declined prompt, a run that produced
no result, a read-back that disagrees.

**Then open the copy in Gramps and look at the person.** The note is on them. That is the
verification, and it is the reason this slice exists.

---

## What it leaves behind

Every apply writes two files into `.gramps-live-api-undo\`, inside the copy:

- one **before** the transaction opens, holding the operation, **the exact sentence you approved**,
  and the versions in play. It is flushed to disk before anything is written, and if it cannot be
  written the whole thing aborts having touched nothing.
- one **after** the commit, holding the note's handle and Gramps ID — which cannot exist before the
  write, and are what an undo by hand needs.

If the write succeeds and its record does not, the write **stands** and the handles are printed
anyway, loudly, with a non-zero exit. You can reconstruct a record; you cannot reconstruct a handle
nobody told you.

> ⚠️ **These two files are all the three commands leave behind. They take NO backup.** They make one
> write reversible by hand, from a record; they do not give you a copy of the tree as it was.
>
> ⛔ **The document route is different and does take one** — see below. The asymmetry is real and is
> stated rather than smoothed over: the three commands write one note into a copy you blessed, and
> the document route writes a whole graph. **If you want a copy of the tree before a note goes in,
> make it yourself.**

## The other route: a document, approved inside Gramps

Everything above is the **note route** — three commands you type, each of which starts Gramps, does
one thing, and exits. There is a second route, and it works the other way round: **Gramps stays
open, and the approval happens inside it.**

Use it when what you want to write is not one note but a **document** — a small graph of people,
places, an event, a source and a citation, written as one transaction.

> ⚠️ **The setup is the same setup.** The blessed copy, the junction and `config.json` are what both
> routes read.
>
> ⛔ **This route needs one thing the other does not: the host must be able to import the project
> from inside Gramps.** It gets there by resolving its own plugin directory and stepping up one
> level — which works because that directory is a **junction into the checkout**. Copy the files
> instead and it lands in Gramps' plugin folder, where there is no `src`, and every document route
> fails on import. `check` reports that as its own `source` line, so a passing check does now mean
> this route has what it needs; if it says `NO`, re-make the junction or set `GRAMPS_LIVE_API_SRC`.

### What you do

1. **Leave Gramps open**, on the blessed copy. ⛔ Open it with `-O <tree name>` — reopening on the
   tree manager leaves the plugin bound to no tree.
2. The agent calls **`propose_document`**, which stores the graph and hands back an id. Nothing is
   written and nothing is shown yet.
3. The agent calls **`approve_document`** with that id. **A dialog appears in Gramps.**
4. **You read it and say yes or no.** That dialog is the approval — there is no second confirmation
   and no console step.

> ⚠️ **The answer the agent gets is "accepted", not "written" — and not even "shown".** The host
> **schedules** the dialog and replies immediately (`service._document` calls `schedule(show)` and
> returns), because holding an HTTP connection open while a person reads would time out
> mid-decision. **What happens next is between you and the dialog**, and the agent learns nothing
> about it.
>
> ⛔ **So a reply does not prove a dialog appeared.** Two cases where it does not:
>
> * **another document is already awaiting approval** — the queued dialog is refused, with the
>   reason in `host.log`;
> * **Gramps closes first** — the queued callback never runs at all.
>
> ⚠️ **This page previously said the host "replies the moment the dialog is up".** That was false: it
> replies the moment the dialog is *queued*. If an agent tells you a document was shown and you saw
> nothing, **that is a state the system can genuinely be in** — check `host.log`, and propose it
> again.

### What the dialog is for

**The dialog has two sections, and the difference between them is the whole point.**

⭐ **Under *ATTACHING TO EXISTING*, every name is read from the tree** — never from what the agent
sent. If the model picked the wrong Gramps ID you see the wrong person's name and cancel, and **that
is the only check there is.** An agent echoing back a name it chose itself would defeat it entirely,
which is why the preview resolves each id against the open database instead.

⛔ **Under *CREATING NEW*, the names are the agent's own words.** Nothing exists in the tree to read
them from yet, so there is nothing to check them against — they are a proposal, and approving them is
you deciding they are right.

> ⚠️ **This page previously said "every name is read from the tree", without that split.** It was
> wrong in the direction that matters: it invited you to read a model-proposed name as if the tree
> had confirmed it. **A new person is created exactly as spelled, and nothing is matched by name** —
> if they are already in your tree, you get a second copy.

⛔ **Read the names, not the shape.** The shape is nearly always right; the identity is the thing
worth your attention — and under *CREATING NEW*, the spelling is too.

### What it does before it writes

**A byte-level copy of the tree is taken first, every time, before the dialog opens.**

- It is taken through a second read-only connection to the tree's own database file — not through
  Gramps' connection, and not by exporting.
- It lands in `%APPDATA%\gramps-live-api\backups\<digest>\`, where `<digest>` identifies the tree by
  its directory. A file named `which-tree.txt` inside says which tree that is, in words.
- **Twenty are kept per tree.** Older ones are removed after a successful write.
- On the owner's tree it takes about **a tenth of a second**, so the dialog does not feel delayed.

⛔ **If the copy cannot be taken, nothing is written and no dialog appears.** Not an export instead,
not a write without one, and not a dialog that opens and then apologises — a decision you cannot
have honoured should not cost you the attention of making it.

⚠️ **A cancelled dialog discards its copy**, and so does any other exit before the write. A backup
kept for a write that never happened would push a real one out of the twenty.

### What it leaves behind

One record in `.gramps-live-api-undo\` inside the tree, written **before** the transaction and
completed after it. It holds the backup's path, the time the backup was taken, the time the write
landed, the sentence you approved, and the Gramps IDs created.

⭐ **The two timestamps are the point.** They let you tell, without any archaeology, whether the
backup on disk predates the change you are looking at.

When it succeeds, the dialog tells you what was written, where the undo record is, and which backup
preceded it.

### When the document route refuses

| What you see | What it means |
| --- | --- |
| nothing at all, and a line in `host.log` | another document is already awaiting approval. Finish or cancel that dialog first — a second one is refused, not queued |
| `Nothing was written — no backup` | the copy could not be taken. Nothing was touched |
| `has not been blessed for writing` | the open tree has no sentinel. It names the tree so you can tell which one |
| `is not a Gramps family tree directory` | the path is not a tree at all — a different problem from the one above, and said differently on purpose |
| `the open tree changed after the backup was taken` | the tree was closed or swapped while the dialog was up. The backup is of the old one, so the write is refused |

`host.log` lives at `%APPDATA%\gramps-live-api\host.log` and is the only place a failure inside
Gramps is visible — Gramps' plugin loader swallows exceptions and the all-in-one build has no
console.

> ⛔ **If something did go wrong, [`docs/restoring.md`](restoring.md) is the procedure.** Read it
> before you touch anything, and in particular before you delete anything.

## When the three commands refuse

| What you see | What it means |
| --- | --- |
| `is NOT blessed for writing by hand` | the sentinel file is not in that tree's directory |
| `the open database is not the copy this token authorises` | the tree Gramps opened is not the one that was blessed |
| `locked` | Gramps has that tree open. Close it — we never break Gramps' lock, and only one process ever writes a tree |
| `the reference's handle names a different object` | the handle and the Gramps ID name two different people |
| `the approved operation is not this operation` | the operation that reached the write is not the one you approved |
| `printed no GRAMPS-LIVE-API-RESULT line` | the Gramps run did not complete. Its own error output is printed underneath |

That last one is worth knowing about: **the exit code of a Gramps run tells you nothing here.** Its
launcher refuses to start by exiting zero, and it catches and logs any exception a tool raises and
then exits normally. So this reads a single line of result from the run's output and treats its
absence as failure — which is the only reading that is right in both of those cases.

> ⚠️ **Why `locked` stops us, when the lock itself forbids nothing.** Gramps' lock is **advisory**: a
> text file holding one line of `user@host`, with no PID and no `flock`, and Gramps writes it on open
> **without ever checking whether one is already there**. A second process can open the same tree and
> SQLite will let it. So the lock is not what keeps one writer — it is only the signal that another
> process is holding the tree.
>
> **What actually makes a second writer unsafe is underneath it.** Gramps reads every Gramps ID
> counter into the memory of the process that opened the tree and writes them back **only when that
> process closes**. Two processes are therefore last-writer-wins on those counters: the second one to
> close overwrites what the first recorded, and the next ID Gramps issues **collides** — silent
> duplicate Gramps IDs, with no SQLite error to notice, because row locking says nothing about a value
> cached in another process's heap.
>
> **The policy does not change: we never touch a lock file, and we never write a tree Gramps has
> open.** Only the reason does.
