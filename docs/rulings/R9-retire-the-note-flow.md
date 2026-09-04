# R9 — Retire the note flow

**Ruled 2026-09-04.** This page records a decision. It is not a proposal and it is not argued again
here.

⚠️ **When ruled, nothing described below was removed.** The retirement is a build that has not run.
What this page fixes is *that* it runs, what it may not take with it, and what has to exist first.

---

## The ruling

**The note flow is retired.** `propose_note` and `approve` go, and with them the export reader, the
spawned console, `export_path`, and the export staleness check. The document route becomes the only
write path.

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

### 3. The round trip integration test is PORTED, not deleted

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
| the proposal store, and `AddNote` | `core/proposals.py` whole, and the `AddNote` parts of `core/schema.py` |
| the CLI console `approve` | `src/gramps_live_api/cli.py` |
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

## What this does not settle

- **Whether the loss of the separate process console matters enough to revisit.** The screen put this
  to the owner explicitly and it was not the deciding factor either way. If it later proves to
  matter, it is a new question about the approval surface and not a reopening of this ruling.
- **The order of the retirement build's own steps.** That belongs to its plan gate.
