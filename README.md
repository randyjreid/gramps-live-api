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

**Phase 1 of 8 -- `core/schema`**, in progress: the operation model and its validation, on pure
unit tests. There is no product functionality yet. What exists is the test skeleton, the CI gates,
and the guard that keeps personal data out of this public repository.

Nothing in this repository imports `gramps` or `gi` yet, and there is no HTTP server.

## Roadmap

Provisional beyond the current phase; the ones after it are specified as they are reached.

**When this table and the [milestones](https://github.com/randyjreid/gramps-live-api/milestones)
disagree, the milestones are the authority.** This table was stale in all eight rows once already,
and the point of saying where the answer lives is that the next drift is resolved by looking rather
than re-argued.

| Phase | Milestone | What it adds |
| --- | --- | --- |
| 0 | Scaffold | Repo, GPL-2.0, `.gitignore` in the first commit, `pyproject`, ruff/mypy, CI green on an empty suite |
| 1 | core/schema | Operation model and validation. Pure unit tests. Gramps' `Date` model used directly, conditional on an import check passing on 3.10/3.11/3.12 |
| 2 | Backup mechanism | How a pre-batch backup is produced from inside a running Gramps. No write endpoint ships before this |
| 3 | core/apply | `DbTxn` writes. Integration tests assert reference backlink integrity after every operation |
| 4 | core/query | Read helpers over a seeded synthetic tree |
| 5 | bridge/server | Loopback HTTP with token auth and the four endpoints. Tests against a stub core |
| 6 | gramplet | GTK shell and `GLib.idle_add` marshalling. Manual verification checklist; not CI-testable |
| 7 | mcp | stdio MCP client, `claude mcp add`, full end-to-end verification against the live tree |

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
