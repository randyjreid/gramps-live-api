# gramps-live-api

An agent-assisted way to put genealogical facts into a **Gramps** family tree, with a human
approving every write. Single-user, on the owner's own machine.

**What works today:** a note onto a person — from a terminal, or by asking an agent and then typing
`y` at a console window the agent cannot reach.

⚠️ **Both write into a copy of the tree blessed by hand, and both read a snapshot export. Nothing
has ever been written to a real family tree.**

**Where it is going** is one sentence, the owner's own:

> *"I photograph or transcribe a census record. I want an agent to read it, work out what it says
> about people in my tree, work out what is already recorded and what is not, and make all the
> necessary updates — new people, events, places, the source, the citation, the image attached — as
> ONE thing I review and approve, not twenty."*

The route from here to there, and what is a plan rather than a feature, is
[`docs/roadmap.md`](docs/roadmap.md).

## What works today

Two slices. Each has a page with the exact steps; this is enough to tell whether the click is worth
it. Setup is Windows PowerShell, and every command is run from a checkout.

**Slice 1 — a note onto a person, from the terminal.** [`docs/using.md`](docs/using.md). You write
the note as a JSON file; `preview` shows the one sentence that would be written; `apply` shows it
again and asks; `y` writes it through Gramps' own plugin door inside a `DbTxn`, and a second, fresh
Gramps process goes and reads it back. Then you open the copy in Gramps and find the note — that,
and not the exit code, is the verification.

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
- **Reads are a snapshot, not the database.** `list_people` reads a Gramps XML export you produced
  by hand. It cannot see its own writes until you export again
  ([#77](https://github.com/randyjreid/gramps-live-api/issues/77)), and a `priv="1"` flag set
  *after* the export was taken would be a privacy fail-open — which is why `check` **fails** rather
  than warns on a stale export.
- **One writable operation type** (`add_note`), one target type (person), one operation per
  approval. Everything that looks restrictive is a named refusal with its widening point recorded.
- **No HTTP server and no endpoint of any kind.** The MCP server speaks **stdio** only.
- **The core has `dependencies = []`** and runs on the standard library alone. The official MCP SDK
  is an optional extra — installing it brings 27–30 packages behind it, measured, including an HTTP
  stack this project uses none of. What that costs and why the SDK anyway:
  [`docs/slice2-mcp.md`](docs/slice2-mcp.md).

```sh
python -m pip install -e ".[mcp]"     # only if you want the MCP server
```

## Where it is going

Named by the demo each slice has to perform. **Every one of these is a plan, not a feature**, and
there are no dates because none exist.

- **3 — *"My tree came back from a file."*** A backup taken and restored into Gramps, verified by
  the owner. It depends on nothing and is startable now; slice 4 depends on it.
- **4 — *"My real tree."*** Graduation off the blessed copy. ⚠️ Gated on a ruling, not on work:
  every door onto a tree Gramps holds open is currently closed, so this is a reversal of a standing
  decision rather than a demo.
- **4½ — *"Two notes, one console, one yes."*** The batch spine — two notes, one transaction, one
  approval. This is where *"not twenty"* in the sentence above lives, and building operation types
  before it is the single most expensive mistake available.
- **Then**, as a pool of specified work rather than a schedule: a read surface the agent can
  question, sources and citations, events and dates, people and relationships, analytics, media,
  matching — and finally the census demo itself.

[`docs/roadmap.md`](docs/roadmap.md) carries the full version: what each slice settles, what it
releases, the six rulings the owner still owes and the four measurements nobody has taken. The
eight-phase milestone list this page used to carry is superseded by those slices; retiring the
milestones themselves is one of the rulings owed.

## Running the gates

With `".[dev,mcp]"` installed, from the checkout root:

```sh
ruff check .
ruff format --check .
mypy src
pytest -rs
```

`-rs` names every skipped test and its reason, and that matters here: a skip is this suite's answer
to a platform it cannot observe, and an unseen skip reads exactly like a pass. `CONTRIBUTING.md` has
the fifth gate — the privacy guard — and how to run it over a push.

CI runs those on Python 3.10, 3.11 and 3.12 in two legs over the same tree: a **core** leg that
installs `.[dev]` and refuses to continue if `mcp` is importable or if this distribution declares a
single unconditional requirement, and an **mcp** leg that installs the extra and refuses a run whose
MCP tests did not actually execute. A third job runs the guard.

⚠️ **Green CI is not evidence the write path works.** The runners have no Gramps, no `gi` and no
tree, so the write, the plugin registration and the read-back cannot be observed there at all — those
tests skip, by name, in the log. That is the stated cost of going through Gramps' own door rather
than parsing a file, and it is why every demo above ends with you looking at the tree.

It is also why `src/` imports no `gramps` and no `gi`. The two files that must are a top-level
`gramps_plugin/`, outside the package and never imported by it — Gramps loads them, we do not.
`CONTRIBUTING.md` records that as an exception and why it exists.

## Privacy

This repository is public. The family tree it is built for is not, and no part of it will ever be
committed here. A guard (`src/gramps_live_api/core/pii_guard.py`) fails the build on absolute
filesystem paths that identify a person or a machine, and on genealogy data — refusing outright any
file type it cannot prove safe. Three things about it are deliberate: it scans **what Git contains**
rather than the working tree, because a push publishes every commit it holds; it **fails closed**,
because it cannot possibly know every genealogy format that exists; and in CI it **redacts what it
matched**, because a build log is as public as the repository. It does not scan for credentials —
`CONTRIBUTING.md` records why, and what would reopen the question. Read it before adding a fixture
or a new file type.

Separately, and **by design**: slice 2 puts the names and note text of non-private people into a
model's context. That is bounded by the tree's own `priv="1"` flag — a private person is neither
listed nor accepted as a target — by a required search term, and by a result cap. It is not bounded
by anything else, and text that has reached a model's context has reached it. The residual is stated
plainly in [`docs/slice2-mcp.md`](docs/slice2-mcp.md).

## Licence

GPL-2.0. A Gramps addon imports Gramps and is a derivative work of it, so the licence is not a
choice this project gets to make. See `LICENSE`.
