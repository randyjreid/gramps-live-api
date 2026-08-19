# gramps-live-api

An agent-assisted way to put genealogical facts into a **Gramps** family tree, with a human
approving every write. Single-user, on the owner's own machine.

**What works today:** a note onto a person — from a terminal, or by asking an agent and then typing
`y` at a console window the agent cannot reach.

⚠️ **Both write into a copy of the tree blessed by hand, and only the agent path reads a snapshot
export. Nothing has ever been written to a real family tree.**

**Where it is going** is one sentence, the owner's own:

> *"I photograph or transcribe a census record. I want an agent to read it, work out what it says
> about people in my tree, work out what is already recorded and what is not, and make all the
> necessary updates — new people, events, places, the source, the citation, the image attached — as
> ONE thing I review and approve, not twenty."*

The route from here to there, and what is a plan rather than a feature, is
[`docs/roadmap.md`](docs/roadmap.md).

## What works today

Two slices, each with a page carrying the exact steps. Setup and commands are Windows PowerShell,
run from a checkout.

**Slice 1 — a note onto a person, from the terminal.** [`docs/using.md`](docs/using.md). You write
the note as a JSON file; `preview` shows the one sentence that would be written; `apply` shows it
again and asks; `y` writes it through Gramps' own plugin door inside a `DbTxn`, and a second, fresh
Gramps process reads it back. Then you open the copy in Gramps and find the note — that, and not the
exit code, is the verification.

**Slice 2 — the same write, with an agent in front of it.**
[`docs/slice2-mcp.md`](docs/slice2-mcp.md). Three MCP tools — `list_people`, `propose_note`,
`approve` — registered with `claude mcp add`. The operation never travels through the agent:
`propose_note` files it server-side and returns only an id, the sentence you will be shown, and a
digest; `approve` takes only an id and a digest, and opens a **console window the agent cannot type
in**. Your yes in the chat is a courtesy; the `y` in that window is the approval. The agent is never
told the outcome — not written, not declined, not failed.

## The honest status

- **Both demos end in a copy.** Every write goes into a tree carrying a `.gramps-live-api-copy`
  sentinel file you created by hand. There is no flag and no config key that overrides it, so the
  live tree is unwritable by construction.
- **The agent's reads are a snapshot, not the database.** `list_people` reads a Gramps XML export
  you produced by hand. It cannot see its own writes until you export again
  ([#77](https://github.com/randyjreid/gramps-live-api/issues/77)), and a `priv="1"` flag set
  *after* the export was taken would be a privacy fail-open — which is why `check` **fails** rather
  than warns on a stale export.
- **One writable operation type** (`add_note`), one target type (person), one operation per
  approval. Everything that looks restrictive is a named refusal with its widening point recorded.
- **No HTTP server and no endpoint of any kind.** The MCP server speaks **stdio** only. ⚠️ **That is
  a statement about what ships, and the direction below changes it:** the ruled architecture puts a
  loopback HTTP listener inside Gramps. None of it is written.
- **The core has `dependencies = []`** and runs on the standard library alone. The official MCP SDK
  sits behind an optional `mcp` extra, and installing it brings 27–30 packages with it, measured —
  what that costs, and why the SDK anyway, is in [`docs/slice2-mcp.md`](docs/slice2-mcp.md).

## Where it is going

Named by the demo each slice has to perform. **Every one of these is a plan, not a feature**, and
there are no dates because none exist.

⚠️ **The architecture changed on 2026-08-19 and nothing shipped changed with it.** Two rulings, both
the owner's: **Gramps stays open** (R2), and **the tool becomes a Gramps addon running inside the
Gramps process** (R8) — a plugin loaded at startup that hosts a loopback HTTP listener on a
background thread and does every database and GTK touch on Gramps' own main thread, with **approval
taken in a Gramps dialog**. The MCP server becomes a thin client holding no Gramps code. **There is
no export, no copy-to-write, no spawned Gramps process left in that design.**

⛔ **None of it exists.** Not a line of the addon is written, and the two slices above still work the
way this page describes. The ruling is
[`docs/rulings/R8-channel-architecture.md`](docs/rulings/R8-channel-architecture.md).

- **4 — *"My real tree."*** Graduation off the blessed copy: add a person in Gramps, ask the agent
  about them, get a note back into the tree you actually work in. ⚠️ Still gated on rulings, not on
  work — a backup that can be taken while Gramps holds the tree open, and the trust model for a tool
  that reads live tree prose.
- **4½ — *"Two notes, one dialog, one yes."*** The batch spine — two notes, one transaction, one
  approval. This is where *"not twenty"* in the sentence above lives, and building operation types
  before it is the single most expensive mistake available.
- **Then**, as a pool of specified work rather than a schedule: a read surface the agent can
  question, sources and citations, events and dates, people and relationships, analytics, media,
  matching — and finally the census demo itself.

⚠️ **There used to be a slice 3 here — *"my tree came back from a file"* — and R8 deleted its plan,
because that plan spawned a second Gramps process against a closed tree.** **The requirement
survives**: nothing writes to the real tree before the owner has watched a backup of it come back.
What produces one against a tree Gramps is holding open is an open ruling.

[`docs/roadmap.md`](docs/roadmap.md) carries the full version: what each slice settles, what it
releases, the rulings the owner still owes and the measurements nobody has taken. The eight-phase
milestone list this page used to carry is superseded by those slices; retiring the milestones
themselves is one of the rulings owed.

## Running the gates

With `".[dev,mcp]"` installed, from the checkout root:

```sh
ruff check .
ruff format --check .
mypy src
pytest -rs
```

`-rs` names every skipped test and its reason, which matters here: an unseen skip reads exactly like
a pass. `CONTRIBUTING.md` has the fifth gate — the privacy guard — and how to run it over a push.

CI runs those on Python 3.10, 3.11 and 3.12 in two legs over the same tree: a **core** leg that
refuses to continue if `mcp` is importable or if this distribution declares a single unconditional
requirement, and an **mcp** leg that installs the extra and refuses a run whose MCP tests did not
actually execute. A third job runs the guard.

⚠️ **Green CI is not evidence the write path works.** The runners have no Gramps, no `gi` and no
tree, so the write, the plugin registration and the read-back cannot be observed there at all — those
tests skip, by name, in the log. It is why every demo above ends with you looking at the tree, and it
is why `src/` imports no `gramps` and no `gi`: the two files that must are a top-level
`gramps_plugin/`, outside the package and never imported by it. Gramps loads them; we do not.

## Privacy

This repository is public. The family tree it is built for is not, and no part of it will ever be
committed here. A guard (`src/gramps_live_api/core/pii_guard.py`) fails the build on absolute
filesystem paths that identify a person or a machine, and on genealogy data — refusing outright any
file type it cannot prove safe. Three things about it are deliberate: it scans **what Git contains**
rather than the working tree, because a push publishes every commit it holds; it **fails closed**,
because it cannot know every genealogy format that exists; and in CI it **redacts what it matched**,
because a build log is as public as the repository. It does not scan for credentials.
`CONTRIBUTING.md` has the reasoning — read it before adding a fixture or a new file type.

Separately, and **by design**: slice 2 puts the names and note text of non-private people into a
model's context. That is bounded by the tree's own `priv="1"` flag — a private person is neither
listed nor accepted as a target — by a required search term, and by a result cap. It is bounded by
nothing else, and text that has reached a model's context has reached it. The residual is stated
plainly in [`docs/slice2-mcp.md`](docs/slice2-mcp.md).

## Licence

GPL-2.0. A Gramps addon imports Gramps and is a derivative work of it, so the licence is not a
choice this project gets to make. See `LICENSE`.
