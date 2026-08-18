# Using it: a proposed note becomes a note on a person

This is slice 1. It does exactly one thing: it takes a **note you propose for a person**, shows you
the one sentence it would write, waits for you to say yes, writes it into **a copy of your tree that
you have blessed by hand**, and then reads it back in a fresh process to prove it is there.

It ships no server, no endpoint and no unattended path. Nothing runs without you typing it.

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
New-Item -ItemType Directory -Force "$env:APPDATA\gramps\gramps60\plugins" | Out-Null
New-Item -ItemType Junction -Path "$env:APPDATA\gramps\gramps60\plugins\gramps-live-api" -Target "$PWD\gramps_plugin"
```

A **junction** does not require Administrator — only a symbolic link does. If that surprises you, it
surprised us too; it is measured, not assumed.

Copying the two files works just as well and goes stale; the junction does not.

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

```powershell
$env:PYTHONPATH = "src"
```

### 1. `check` — is everything in place?

```powershell
python -m gramps_live_api check
```

You should see the runtime, the plugin, your copy, and each of the two files the check looks at:

```
  ok   runtime: ...\GrampsAIO64-<version>\grampsd.exe
  ok   plugin: ...\gramps\gramps60\plugins\gramps-live-api
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
python -m gramps_live_api check "<the Path for your LIVE tree>"
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

Write the note you want as a file. Call it `op.json` and put it anywhere outside the checkout —
`$env:USERPROFILE\op.json` will do, and is what the two commands below assume:

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

Both halves are required, and they are checked against each other: the Gramps ID is what resolves the
person, and if the handle names a different object the write is refused rather than guessing which
one you meant.

```powershell
python -m gramps_live_api preview "$env:USERPROFILE\op.json"
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
python -m gramps_live_api apply "$env:USERPROFILE\op.json"
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

> ⚠️ This is not the Phase 2 backup mechanism and does not replace it. It makes one write reversible
> by hand. A full backup is still required before any write **endpoint** ships.

## When it refuses

| What you see | What it means |
| --- | --- |
| `is NOT blessed for writing by hand` | the sentinel file is not in that tree's directory |
| `the open database is not the copy this token authorises` | the tree Gramps opened is not the one that was blessed |
| `locked` | Gramps has that tree open. Close it — we never break Gramps' lock, and that is the one-writer rail |
| `the reference's handle names a different object` | the handle and the Gramps ID name two different people |
| `the approved operation is not this operation` | the operation that reached the write is not the one you approved |
| `printed no GRAMPS-LIVE-API-RESULT line` | the Gramps run did not complete. Its own error output is printed underneath |

That last one is worth knowing about: **the exit code of a Gramps run tells you nothing here.** Its
launcher refuses to start by exiting zero, and it catches and logs any exception a tool raises and
then exits normally. So this reads a single line of result from the run's output and treats its
absence as failure — which is the only reading that is right in both of those cases.
