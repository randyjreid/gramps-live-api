# gramps-live-api

A loopback HTTP API over a **live, already-open Gramps family tree**, plus a thin MCP client so an
assistant can read and eventually propose changes to that tree.

The distinction that matters: this is not a tool that opens a tree file and parses it. It is an
addon that runs *inside* a Gramps process you already have open, and serves the tree as Gramps
itself currently sees it.

## Why in-process

A Gramps tree is a live database with a single owning process. Talking to it from outside means
either parsing an export -- which is a stale copy the moment it is written -- or opening the same
database a second time, which risks lock contention and, on a write, corruption.

So the API runs inside Gramps and borrows **Gramps' own database handle**:

- **One writer.** Every change goes through the handle Gramps is already using, inside Gramps'
  own transaction and undo machinery. There is never a second process writing the same tree.
- **No staleness.** A read reflects the tree as of now, including edits made in the UI a second
  ago and not yet saved anywhere.
- **Gramps' own rules.** Validation, referential integrity and undo are Gramps', not a
  reimplementation that drifts from it.

The API binds to loopback only. Nothing about this design is intended to be reachable from another
machine.

## Status

**Phase 0 of 8 -- scaffold.** There is no product functionality yet. What exists is the test
skeleton, the CI gates, and the guard that keeps personal data out of this public repository.

Nothing in this repository imports `gramps` or `gi` yet, and there is no HTTP server.

## Roadmap

Provisional; the phases after the current one will be specified as they are reached.

| Phase | What it adds |
| --- | --- |
| 0 | Scaffold: test-first layout, CI gates, the PII guard |
| 1 | A read-only bridge to the live database |
| 2 | The loopback HTTP server and read endpoints |
| 3 | The gramplet: the addon that runs the server inside Gramps |
| 4 | The backup mechanism, before any write is possible |
| 5 | An operation schema: a typed vocabulary for proposed changes |
| 6 | Apply logic: validated writes through Gramps' own handle |
| 7 | The MCP client |

## Privacy

This repository is public. The family tree it is built for is not, and no part of it will ever be
committed here. A guard (`src/gramps_live_api/core/pii_guard.py`) fails the build on absolute
filesystem paths that identify a person or a machine, and on genealogy data — under any filename for
the formats it has a property for, and by refusing any file type it cannot prove safe for the rest.
That distinction is deliberate and `CONTRIBUTING.md` records what it does and does not reach.

It does **not** scan for credentials. That was a third property, it failed four times, and this
repository's risk is personal data rather than secrets — see `CONTRIBUTING.md` for the reasoning and
for what would reopen the question.

Three things about it are deliberate:

- **It scans what Git contains, not the working tree.** A push publishes every commit in it, so
  content added in one commit and deleted in the next is still reachable, and still a finding.
- **It fails closed.** Content passes only if it can be positively classified as safe. A file type
  nobody has vouched for is a build failure, not a silent pass -- because the guard cannot possibly
  know every genealogy format that exists.
- **It does not republish what it finds.** In CI the matched value is redacted; a build log is as
  public as the repository. At a terminal it is shown, because you already have the file.

See `CONTRIBUTING.md` before adding fixtures or a new file type.

## Licence

GPL-2.0. A Gramps addon imports Gramps and is a derivative work of it, so the licence is not a
choice this project gets to make. See `LICENSE`.
