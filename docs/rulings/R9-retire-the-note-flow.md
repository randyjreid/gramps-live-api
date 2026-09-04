# R9: retire the note flow

**Ruled 2026-09-04.** This page records a decision. It is not a proposal and it is not argued again
here.

⚠️ **When ruled, nothing described below was removed.** The retirement is a build that has not run.
What this page fixes is *that* it runs, what it may not take with it, and what has to exist first.

---

## The ruling

**The note flow is retired.** `propose_note` and `approve` go, and with them the export reader, the
spawned console, `export_path`, and the export staleness check. **The document route becomes the only
write path an agent can reach.**

⛔ **And the CLI operation surface goes with it.** `gramps_live_api preview` and
`gramps_live_api apply` read an operation file, and `apply` writes into the blessed copy directly
without `propose_note` and without `approve`. **`AddNote` is the only thing it can write**, so the
command has nothing left to do once the note flow goes. It is retired in the same change.

⛔ **Retirement does not run until note types are on `main`.** The one capability the note flow has
that the document route lacks is a caller chosen note type, and removing the flow before that
capability moves would make `research` and `todo` notes unwritable. **Note types are the precondition,
not a follow up.**

Option B, deprecate for one release, was rejected on its own terms: a deprecation window exists to
discover an unknown user, the tool is not shipped, and so it buys information that does not exist to
be bought.

## ⛔ Three things the retirement build may NOT take with it

These sit inside the blast radius and would each be removed by a careful reading of the inventory
below. Each one is load bearing somewhere else.

### 1. `NOTE_TYPES` and `NOTE_TYPE_ATTRIBUTES` are KEPT

`core/schema.py` defines `NOTE_TYPES` and `core/apply.py` defines `NOTE_TYPE_ATTRIBUTES`. They read
as note flow constants and they are inside the `AddNote` removal, but **the note types work on the
document route depends on them**. Removing them removes the capability that made retiring safe, in
the same commit that relies on it existing.

### 2. The `mcp` pin stays. #173 is NOT made moot

The pin's own comment names the tool it measured, and it is a live read:

```
2.0.0  Error executing tool find_source: source X0001 is marked private in this tree
2.1.1  Error executing tool find_source
```

`find_source` is one of the thirteen live reads, all of which survive this ruling. **Retiring the
note flow removes one caller of that refusal and none of the reads that need it.** Anyone reading the
inventory and concluding the pin was protecting `propose_note` has it backwards.

### 3. `core/proposals.py` is NOT deleted wholesale. The document route runs on it

The inventory below lists "the proposal store" against `core/proposals.py`, and reading that as
"delete the file" **stops the surviving route from starting.** Verified in
`src/gramps_live_api_mcp/server.py`: `propose_document` and `approve_document` use
`proposals.store_directory`, `proposals.new_session`, `proposals._ID`, `proposals.ProposalNotFound`
and `proposals.claim_document`, and the tool object builds a `proposals.Store` from
`proposals.store_directory`.

⛔ **So the shared helpers either stay where they are or move BEFORE the note specific store is
removed**, and the document route moves with them in the same change. Which of the module is note
only is a question for the removal build to answer by reading, not by assuming the filename.

⚠️ **This is the sharpest item on the page.** It is the one carve out whose omission would not show up
as a lost capability or a failing edge case: the document route would simply not work, having been
broken by a deletion aimed at something else.

### 4. The round trip integration test is PORTED, not deleted

`tests/integration/test_round_trip.py` is **the only automated coverage against a real Gramps
database**: a throwaway database, a real `DbTxn`, a real write, verified from a second fresh process.
It currently drives the note flow, through `schema.from_dict` and `apply.approval_digest`.

⛔ **It is ported to the document route in the same pull request that removes the note flow.** There
must be no window in which the project has no automated real Gramps coverage, and "delete it, port it
next" is exactly such a window.

## What goes, by file

⚠️ **Named by symbol, because line numbers drift.** The inventory below was read on 2026-09-03 and
`main` has moved since. **Every location is re-verified at removal time**; a line number here is a
hint about where to look, never an instruction about what to cut.

| | where |
| --- | --- |
| `propose_note`, `approve` | `src/gramps_live_api_mcp/server.py`: the two tools, their descriptions, and their `TOOL_NAMES` entries |
| `list_people` | same file, the `people.search(people.read_export(...))` tool |
| the console spawn | same file, the `popen(..., creationflags=CREATE_NEW_CONSOLE)` call and `CREATE_NEW_CONSOLE` itself |
| the Windows only branch | same file, `require_console` and its `if platform != "win32"` |
| `TargetNotInExport` | same file, its definition and its raise site |
| `export_path` | `src/gramps_live_api/config.py`: the `_KEYS` entry, the `Settings` field, the `load` wiring, and `ENV_EXPORT` |
| the export staleness check | `src/gramps_live_api/cli.py`, inside `check` |
| the export reader | `src/gramps_live_api/core/people.py`, the whole file |
| `AddNote`, and the note only parts of the proposal store | the `AddNote` parts of `core/schema.py`, and the note specific parts of `core/proposals.py`. ⛔ **Not that file whole. See carve out 3** |
| the CLI console `approve` | `src/gramps_live_api/cli.py` |
| the CLI operation surface | `src/gramps_live_api/cli.py`: the `preview` and `apply` subcommands and their handlers. ⛔ **`AddNote` is the only writable operation, so `apply` has nothing left to write** |
| the doc passages explaining why one tool differs | `docs/using.md`, `docs/slice2-mcp.md`, and the README tool groups |

⚠️ **`core/schema.py` does not all go.** It also validates the document graph. Only the `AddNote`
operation is note flow only, and `NOTE_TYPES` stays by carve out 1.

## What this buys, and what it costs

**Buys:** the only stale data path in the product goes, rather than being mitigated. Exactly two
places read the export and both are note flow tools; the thirteen live reads and the document route
all go through the accessor against the tree Gramps has open. The only Windows only branch goes. One
write route instead of two. Roughly 1,500 lines of first party code and their tests go. A new user no
longer configures `export_path` or works out why one tool reads a snapshot.

**Costs, accepted:**

- ⛔ **The separate process console approval goes**, leaving the in Gramps dialog as the only approval
  surface. The agent cannot type in either one, but they are different trust arguments, and the
  weaker of the two is what remains.
- Typed notes survive only because note types move first. **That is the precondition, and it is the
  reason this ruling has one.**

## ⚠️ `AddCitation` is schema only, and this ruling does not decide it

**Two revisions of this page got the CLI wrong, in opposite directions, and the second was mine
correcting the first.** The record is left standing because the mistake is instructive:

> The page first said the document route becomes the only write path, which was false because `apply`
> writes. It was then corrected to say `apply` **survives**, working for citations. **That was also
> false, and worse, because it was asserted confidently against a check that had not been run.**

⛔ **`AddCitation` is registered in the schema and has never been writable.** `core/apply.py`'s
`_writable` refuses anything that is not an `AddNote`, and
`tests/unit/test_apply_operation.py::test_an_operation_this_slice_does_not_write_is_refused` asserts
exactly that. Outside `schema.py` the type appears only in test fixtures and preview tests: no MCP
tool, no writer, no caller. **Schema registration was mistaken for write support.**

⭐ **So `apply` retires with the note flow**, as the ruling above now says, and what remains open is
narrower and is genuinely a separate question:

**Does `AddCitation` still earn its place in the schema?** It can be validated and previewed and never
written. That is either dead surface to remove or an unfinished capability to complete, and deciding
it is not what this page screened. ⚠️ **It is listed here so the removal build does not answer it by
accident** while deleting the command that was the only thing that ever fed it.

## What this does not settle

- **Whether the loss of the separate process console matters enough to revisit.** The screen put this
  to the owner explicitly and it was not the deciding factor either way. If it later proves to
  matter, it is a new question about the approval surface and not a reopening of this ruling.
- **The order of the retirement build's own steps.** That belongs to its plan gate.
