# Rulings

**Decisions the owner made about this project, with what each one cost.** Each
page records a decision and does not argue it again.

⛔ **This index says what each ruling DECIDED. It does not say what the code does
today, and the difference is not pedantry.** A ruling can be in force while the
implementation has moved: **R7's mechanism diverged** — the shipped backup opens
its own connection rather than using Gramps' — and **R8's scope has exceptions**,
because the legacy `approve` console and the export-backed `list_people` predate
it.

⚠️ **An earlier draft carried a "still holds" column and was wrong about it four
times in five review rounds**, always the same way: written from the rulings,
never checked against the source. ⭐ **Whether a ruling is in force and whether the
code still matches it are two questions, and only the first can be answered from
this directory.** For the second, read the module.

They are the answer to *why is it built this way?* — and to *why does it not do
the safer-sounding thing?*, which is more often the interesting question.

| | Decided | It ruled that |
| --- | --- | --- |
| **[R3](R3-injection-under-live-reads.md)** — injection under live reads | 2026-08-21 | Text in the tree may influence what the agent **proposes**, and that is not preventable at the read. **The damage is bounded at the write instead**: nothing reaches the tree without a human approving a rendering of it. Fencing is defence in depth, not the guarantee. |
| **[R4](R4-graduation-to-the-live-tree.md)** — graduation to the live tree | 2026-08-21 | The live tree **may** carry the `.gramps-live-api-copy` sentinel and be written to, **with a backup taken first.** Recorded explicitly as a **downgrade**: from *a bad write cannot happen* to *a bad write can be reversed*. |
| **[R7](R7-backup-with-gramps-open.md)** — backup with Gramps open | 2026-08-21 | The backup uses `sqlite3.Connection.backup()` against the **live connection Gramps already holds**, and **restore is file replacement, not import** — an import regenerates every handle. |
| **[R8](R8-channel-architecture.md)** — channel architecture | 2026-08-19 | The tool is a **Gramps addon inside the Gramps process**: a loopback HTTP listener on a daemon thread, all database and GTK work marshalled to the **GTK main thread**, approval in a **Gramps dialog**, and the MCP server a thin client holding no Gramps code. |
| **[R9](R9-retire-the-note-flow.md)**: retire the note flow | 2026-09-04 | The note flow goes: `propose_note`, `approve`, the export reader, the spawned console, `export_path`, the staleness check, and the CLI `preview` and `apply` surface, which has nothing left to write once `AddNote` goes. **Conditioned on note types reaching `main` first**, because a caller chosen note type is the only capability it has that the document route lacks. Carries four carve outs of things inside the blast radius that must survive. |

## Reading them without the context they were written in

⚠️ **They cite things a newcomer cannot resolve**, because they were written for
one reader who could. The recurring ones:

| You will see | It means |
| --- | --- |
| **`R1`, `R2`, `R5`, `R6`** | earlier rulings **not published here**. They are referenced, not reproduced. |
| **`slice 1`, `slice 2`, `slice 3`, `Slice A`** | development stages, mapped in `docs/roadmap.md`. ⚠️ Slice 1's page is `docs/using.md`, which is **current usage documentation and not a record**; `docs/slice2-mcp.md` and `docs/slice-a-demo.md` **are** records and say so at the top. |
| **a bare `#25`, `#103`, `#104`** | GitHub issues and pull requests in this repository. |
| **`.claude/decisions/…`** | the case that was *put* to the owner before he ruled. ⛔ **Not in this repository** — the ruling is the published half. |
| **`accepted risk 4`** | numbered residuals inside R8 itself. |
| **`the copy`, `the blessed copy`** | a duplicate of the tree used for development. ⚠️ Pre-R4 wording — after R4 the live tree may be blessed too. |

## What a ruling is, and what it is not

⭐ **A ruling records an irreversible decision together with the cost of taking
it.** R4 is the clearest example: it approves a *downgrade* in the safety
guarantee, in those words, rather than presenting the new position as equally
safe.

⛔ **They are not documentation of how the code works.** For that, read
[`../../README.md`](../../README.md) and the source. A ruling tells you why an
option that looks obviously better was rejected — which is usually the thing a
newcomer is about to suggest.
