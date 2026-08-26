# gramps-live-api

**An MCP server that lets an agent propose structured changes to a live desktop application's
database, with a human approving every write.**

The application is [Gramps](https://gramps-project.org/), a genealogy program. The agent reads a
document, works out what it says, and proposes the whole of it as one graph; the owner reads a
preview inside Gramps and approves or cancels. Single-user, on the owner's own machine.

**Where it is going** is one sentence, the owner's own:

> *"I photograph or transcribe a census record. I want an agent to read it, work out what it says
> about people in my tree, work out what is already recorded and what is not, and make all the
> necessary updates — new people, events, places, the source, the citation, the image attached — as
> ONE thing I review and approve, not twenty."*

What is built and what is still a plan is set out below. ⚠️ The older
[`docs/roadmap.md`](docs/roadmap.md) has fallen behind this page and is history rather than a current
plan.

## The shape, in thirty seconds

**Two processes.**

1. **An MCP server**, speaking **stdio only**. It holds no Gramps code and never touches a database.
2. **A Gramps addon** — a plugin Gramps loads at startup, which runs a **loopback HTTP listener**
   (`127.0.0.1`, ephemeral port, bearer token) on a background thread *inside the Gramps process*.

The MCP server is a thin client of that listener. Every database read and every GTK touch is
marshalled onto Gramps' own main thread, because that is the only thread Gramps permits them on.

The listener is deliberately hostile to anything that is not that client: a request carrying an
`Origin` header is refused before anything else, a missing or wrong bearer token is refused before
the route is even looked at, and a main thread that does not answer in time returns a refusal rather
than holding the socket open.

**The approval model is the point.** An agent can propose. It cannot write, and it cannot learn
whether the owner said yes:

- The **document** flow renders a preview from the stored proposal and shows it in a **modal GTK
  dialog inside Gramps**. The dialog's text is built from the record on disk and from the tree, never
  from anything an agent sends at approval time.
- The older **note** flow opens a **console window the agent cannot type in**. A yes in the chat is a
  courtesy; the keystroke in that window is the approval.

In both, the call that opens the approval returns immediately and knows nothing. **The approval
response does not reveal the decision** — not written, not declined, not failed.

⚠️ **That is a property of the response, not a guarantee of secrecy.** The live-read tools are still
there, so an agent can look afterwards — asking for a distinctively named person, or for what changed
since a moment ago — and infer that a write happened. What it cannot do is *be told*, and it cannot
learn anything from a refusal it could not have learned by reading.

## What the agent can do

Eighteen tools, in three groups. The server publishes the list itself, and a test asserts the exposed
surface is exactly what the server says it is.

**Live reads of the open tree** — people, places, sources, citations, events, family events,
associations, notes, orphans, tree totals, and a changed-since query. These answer from the database
Gramps currently has open.

⚠️ **One exception, and it matters:** `list_people` — kept because the older note flow needs it —
still reads a **Gramps XML export produced by hand**. It cannot see writes made since that export was
taken, and a privacy flag set after it would not be reflected. `find_people` is the live equivalent
and is the one to use.

**The document pair** — `propose_document` files a whole graph server-side and returns an id and a
preview; `approve_document` puts that preview in front of the owner. A graph may create people,
places, events, families, sources, citations and notes, and may attach citations and notes to records
that already exist. **One graph is one approval and one transaction.**

⚠️ **A node carrying a Gramps ID keeps its own descriptive fields — that is the whole guarantee, and
it is narrower than "not modified".** Such a record *is* committed to: an event reference can be
added to a person, children to a family, a citation or note to any of them. What is ignored is what
the payload says the record *is* — its name, type, date, place. Anything dropped that way is shown
in the preview as dropped.

**The older note flow** — `propose_note` and `approve`, the terminal-era path that still works.
⛔ **Windows only:** its approval opens a console window, and on any other platform `approve` refuses
outright. The document route has no such restriction.

## The honest status

- **The sentinel is the whole permission model.** A tree is writable only if it carries a
  `.gramps-live-api-copy` file placed there by hand. There is no flag and no config key that
  overrides it.
- ⚠️ **That blessing has been used on the tree holding real data**, and writes have gone into it.
  Earlier work wrote only into a blessed copy. This page said *"nothing has ever been written to a
  real family tree"* for longer than it was true.
- ⚠️ **The safety property was deliberately downgraded** to make that possible. It was *unwritable by
  construction* — the live tree could not be a target at all. It is now **recoverable after**, and
  only on one route: before a **document** write, a backup is taken, verified with SQLite's own
  integrity check, and recorded in a journal naming the backup and both timestamps. **That is a
  weaker guarantee.** It was ruled deliberately, and the preconditions it was granted under are met.
- ⛔ **The backup covers the document route and nothing else.** The older note flow
  (`propose_note`/`approve`) and the `preview`/`apply` commands write without taking one, so a write
  through those paths has **no recovery point** — [`docs/restoring.md`](docs/restoring.md) says so in
  its opening lines, and this page would otherwise have implied a protection they do not have.
- **The approval dialog shows what would be written, not what is already there.** A proposal adding a
  second event of a kind the person already has looks exactly like a first one. Noticing that is
  currently the owner's job.
- **The core has `dependencies = []`** and runs on the standard library alone. The official MCP SDK
  sits behind an optional `mcp` extra, and installing it brings 27–30 packages with it, measured —
  what that costs, and why the SDK anyway, is in [`docs/slice2-mcp.md`](docs/slice2-mcp.md).

### What is tested, and what has never run against a real tree

Coverage is heavy on the parts that can run without Gramps: the graph parser and its refusals, the
preview renderer, the privacy gate, the backup machinery, the guard. Those have real tests, most with
negative controls that are checked to fail when the behaviour is removed.

⚠️ **What is thin is the seam.** No test invokes `propose_document`, `approve_document`, or any of the
live-read tools *at the MCP layer* — their logic is exercised one layer down, against fakes, in the
accessor and document modules. The wiring from an MCP call, through the HTTP listener, onto Gramps'
main thread and back is proved by a person running it, not by the suite.

⭐ **One exception, and it is the strongest evidence here.** An integration test creates a throwaway
Gramps database, performs the **older note flow's** write through a real `DbTxn` in a real Gramps
process, and verifies it from a second fresh process. It runs only when pointed at an installed
Gramps runtime, so it is skipped in CI — but it is automated, and it is real.

⛔ **What that test does not cover, and nothing else does either:** the **document** route's write,
the plugin registration, the approval dialog, and every live read. Those are exercised by a person,
watching — never automatically, and never against the owner's own data.

## Where it is going

**Every one of these is a plan, not a feature**, and there are no dates because none exist.

- **The census demo itself** — the sentence at the top of this page, end to end. ⚠️ *"Not twenty"* is
  the part already standing: the document route takes a whole graph, shows one preview, and writes it
  in one transaction. What is untested is whether a real census document survives that route
  end to end.
- **A dialog that shows what the tree already holds**, so a duplicate stops looking like an addition.
- **Then**, as a pool of specified work rather than a schedule: a richer read surface, media, and
  record matching.

Two rulings shaped what exists now, both the owner's: **Gramps stays open**, and **the tool runs as a
Gramps addon inside the Gramps process**. Unlike when this page was last written, that addon is
written. The ruling is
[`docs/rulings/R8-channel-architecture.md`](docs/rulings/R8-channel-architecture.md).

⚠️ **One requirement no page can retire:** nothing should be written to a tree the owner cannot get
back. The backup path exists and verifies itself; watching a restore actually come back is the
owner's to do, and [`docs/restoring.md`](docs/restoring.md) is the procedure.

⛔ **[`docs/roadmap.md`](docs/roadmap.md) has not kept up with this page and should be read as
history, not as the current plan.** It still describes three MCP tools, writes that only ever target
a copy, and the addon as unwritten — all of which this page contradicts, and the source contradicts
with it. It is left in place because the rulings and open questions it records are still the real
ones.

## Running the gates

With `".[dev,mcp]"` installed, from the checkout root:

```sh
ruff check .
ruff format --check .
mypy src
pytest -rs
```

`-rs` names every skipped test and its reason, which matters here: an unseen skip reads exactly like a
pass. `CONTRIBUTING.md` has the fifth gate — the privacy guard — and how to run it over a push.

CI runs those on Python 3.10, 3.11 and 3.12 in two legs over the same tree: a **core** leg that
refuses to continue if `mcp` is importable or if this distribution declares a single unconditional
requirement, and an **mcp** leg that installs the extra and refuses a run whose MCP tests did not
actually execute. A third job runs the guard.

⚠️ **Green CI is not evidence the write path works.** The runners have no Gramps, no `gi` and no tree,
so the write, the plugin registration and the read-back cannot be observed there at all — those tests
skip, by name, in the log. It is why every demo ends with the owner looking at the tree, and it is why
`src/` imports no `gramps` and no `gi`: the files that must are a top-level `gramps_plugin/`, outside
the package and never imported by it. Gramps loads them; we do not.

## Privacy

This repository is public. The family tree it is built for is not, and no part of it will ever be
committed here. A guard (`src/gramps_live_api/core/pii_guard.py`) fails the build on absolute
filesystem paths that identify a person or a machine, and on genealogy data — refusing outright any
file type it cannot prove safe. Three things about it are deliberate: it scans **what Git contains**
rather than the working tree, because a push publishes every commit it holds; it **fails closed**,
because it cannot know every genealogy format that exists; and in CI it **redacts what it matched**,
because a build log is as public as the repository. It does not scan for credentials.
`CONTRIBUTING.md` has the reasoning — read it before adding a fixture or a new file type.

Separately, and **by design**: the read tools put tree content into a model's context, and **not only
about people**. Source titles and authors, citation pages, event descriptions, note text and the text
of orphaned records all come back as themselves — anything a read tool can return, it returns. That is
bounded by the tree's own `priv="1"` flag, by a required search term, and by a result cap. It is bounded by nothing else, and text that has reached a model's context has reached
it.

⚠️ **The privacy flag hides contents, not existence, and the difference is deliberate.** A **live**
listing never includes a private record. But a record asked for **by name** is refused with a
distinct refusal rather than reported absent — so a caller that already has an identifier can learn
that the record exists, while learning nothing in it. That was chosen so the owner is told *this is
private* instead of *this is not here*, and the cost is exactly that disclosure.

⛔ **`list_people` is exempt until its export is refreshed, and it fails open.** A person marked
private *after* that export was taken is still listed by it and still accepted as a target. That is
why the `check` command **fails** rather than warns on a stale export — the staleness comparison is
a privacy check, not housekeeping.

## Licence

GPL-2.0. A Gramps addon imports Gramps and is a derivative work of it, so the licence is not a choice
this project gets to make. See `LICENSE`.
