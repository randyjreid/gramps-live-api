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

### 1. A copy of your tree, blessed by hand

In Gramps: **Family Trees → Export** your tree to Gramps XML, then **Family Trees → Import into a new
family tree** and give it a name that says it is a copy.

Then find that copy's directory. Gramps keeps its trees under `%APPDATA%\gramps\grampsdb\`, one
opaque directory per tree; the copy's directory is the one whose `name.txt` holds the name you just
gave it.

**Create an empty file inside that directory called `.gramps-live-api-copy`.**

That file is the whole permission model. Nothing is written to any tree that does not carry it, there
is no flag that overrides it, and there is no configuration key that reaches the check. The check
resolves symlinks and junctions first, so a shortcut named like the copy cannot point at the live
tree.

> ⚠️ **Inside the tree's directory, not beside it.** Beside it means in `grampsdb\`, which holds
> *every* tree — including the live one.

### 2. The plugin, where Gramps looks for plugins

Gramps runs our code through its own CLI tool door, so it has to be able to find it. From an
**Administrator** command prompt, make a junction from Gramps' user plugin folder to this checkout:

```
mklink /J "%APPDATA%\gramps\gramps60\plugins\gramps-live-api" "<your checkout>\gramps_plugin"
```

Copying the two files works just as well and goes stale; the junction does not.

### 3. Where the copy is

Create `%APPDATA%\gramps-live-api\config.json`:

```json
{
  "copy_path": "<the copy's directory, with every backslash doubled>"
}
```

**This file lives outside the repository, and that is deliberate** — it is the one value this project
must never commit. Nothing expands environment variables inside it, so write the path out in full.
Add `"gramps_runtime"` beside it if you have more than one Gramps installed, or if it is not under
`%ProgramFiles%\GrampsAIO64-<version>\`; with exactly one installed it is found for you, and with two
you are asked to name one rather than have this guess.

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
  ok   runtime: %ProgramFiles%\GrampsAIO64-<version>\grampsd.exe
  ok   plugin: %APPDATA%\gramps\gramps60\plugins\gramps-live-api
  ok   copy: <the copy's directory>
  ok   name.txt: is a Gramps family tree directory
  ok   .gramps-live-api-copy: is blessed for writing by hand
  ok   lock: not locked

ready
```

**Now point it at your real tree** and watch it refuse:

```powershell
python -m gramps_live_api check "<your live tree's directory>"
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

Write the note you want as a file. Call it `op.json`, anywhere outside the checkout:

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

**Where the handle comes from.** Gramps does not show handles anywhere in its interface, and this is
the sharpest rough edge in slice 1. Open the Gramps XML export you made in step 1 in a text editor
and find the line that opens the person you want: it carries both an `id` and a `handle` attribute.
**Take the handle's value and drop its leading underscore** — Gramps strips underscores from handles
when it imports, so the value in your copy is the attribute without it.

Both halves are required, and they are checked against each other: the Gramps ID is what resolves the
person, and if the handle names a different object the write is refused rather than guessing which
one you meant.

```powershell
python -m gramps_live_api preview "<wherever you put it>\op.json"
```

```
add a research note to person I0044: “The note you want to attach.”
```

That sentence is the thing you are approving. `preview` writes nothing and opens nothing.

### 3. `apply` — write it, then go and look

```powershell
python -m gramps_live_api apply "<wherever you put it>\op.json"
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
| `the approved sentence is not this operation's sentence` | the file changed between the preview and the write |
| `printed no GRAMPS-LIVE-API-RESULT line` | the Gramps run did not complete. Its own error output is printed underneath |

That last one is worth knowing about: **the exit code of a Gramps run tells you nothing here.** Its
launcher refuses to start by exiting zero, and it catches and logs any exception a tool raises and
then exits normally. So this reads a single line of result from the run's output and treats its
absence as failure — which is the only reading that is right in both of those cases.
