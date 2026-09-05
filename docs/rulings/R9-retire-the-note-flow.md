# R9: retire the note flow

**Ruled 2026-09-04.** This page records a decision. It is not a proposal and it is not argued again
here.

> Index: [`README.md`](README.md).

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

## ⛔ Four things the retirement build may NOT take with it

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

`find_source` is one of the fourteen live reads, all of which survive this ruling. **Retiring the
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
places read the export and both are note flow tools; the fourteen live reads and the document route
all go through the accessor against the tree Gramps has open. The only Windows only branch goes. One
write route instead of two. Roughly 1,500 lines of first party code and their tests go. A new user no
longer configures `export_path` or works out why one tool reads a snapshot.

**Costs, accepted:**

- ⛔ **The separate process console approval goes**, leaving the in Gramps dialog as the only approval
  surface. The agent cannot type in either one, but they are different trust arguments, and the
  weaker of the two is what remains.
- Typed notes survive only because note types move first. **That is the precondition, and it is the
  reason this ruling has one.**

## ⛔ The removal checklist, MEASURED. And it is a LOWER BOUND

⛔ **This list was produced by deleting and running the gate, not by reading and
reasoning.** The inventory above had been wrong five times, and the fifth was found by a reviewer
rather than by the analysis that produced it. So the checklist below was measured: branch from the
note types head, delete the surface this ruling names, run the full gate, and record every failure.
That set is the checklist.

⛔ **IT IS A LOWER BOUND, AND THAT IS A PROPERTY OF THE LIST RATHER THAN A CAVEAT ON IT.** Only part
of the named surface could be removed by deleting; the rest is surgery, and a probe that performed it
would have been authoring rather than measuring. **A reader who treats what follows as the complete
set will be wrong**, and will be wrong in the same way the five earlier inventories were, one level
down and harder to catch because these numbers look measured.

### What was probed

Deleted, as whole files or whole settings, from the note types head: `src/gramps_live_api/core/people.py`,
`gramps_plugin/gramps_live_api_apply.py`, `gramps_plugin/gramps_live_api_apply.gpr.py`, and
`export_path` with `ENV_EXPORT` out of `src/gramps_live_api/config.py`.

### ⛔ What was NOT probed, and why

| not probed | why |
| --- | --- |
| `AddNote` in `core/schema.py` | a registered dataclass with a registry entry; removing it is surgery, not deletion |
| the note only parts of `core/proposals.py` | carve out 3 forbids deleting the file, and separating the note parts is a judgement the removal build makes by reading |
| the MCP tool registrations for `propose_note`, `approve`, `list_people` | decorated functions inside a builder, removed by editing rather than by deleting a file |
| the CLI `preview`, `apply` and console `approve` subcommands | subparser registrations and handlers, same shape |

⚠️ **Each of those is expected to produce failures this probe could not reach.** When the removal
build finds them, that is the lower bound behaving as described, not the plan being wrong.

### The measured failure set

**mypy, 7 errors in 2 files.** It fails before pytest runs, so pytest was run separately.

| where | what it names |
| --- | --- |
| `cli.py` | `export_path` twice and `ENV_EXPORT` once, in the staleness check |
| `server.py` | the `core.people` import, `export_path`, `ENV_EXPORT`, and one return type that follows from them |

**pytest, 56 failed and 4 collection errors, against 1782 passed.**

| entry | count | reading |
| --- | --- | --- |
| `tests/unit/test_cli_approve.py` | 32 | the console approve, which this ruling names |
| ⭐ **`tests/unit/test_cli.py`** | **18** | ⛔ **the headline. See below** |
| `tests/unit/test_config.py` | 4 | the `export_path` settings, named |
| `tests/integration/test_round_trip.py` | 2 | the port carve out 4 requires |
| `tests/unit/test_mcp_seam.py` | collection | coupled to the deleted surface |
| `tests/unit/test_mcp_server.py` | collection | coupled to the deleted surface |
| `tests/unit/test_people.py` | collection | coupled to `core/people.py` |
| `tests/unit/test_tool_descriptions_fit.py` | collection | coupled to the deleted surface |

⚠️ **The four collection errors are entries, not gaps in the measurement.** A module that cannot
import because the surface is gone is coupled to that surface, and the coupling is what a checklist
records. What their failing to collect masks is the failure **count** inside them, never the fact of
the coupling.

### ⭐ The headline entry: `check` survives and is coupled to what goes

**`tests/unit/test_cli.py` produced 18 failures and this ruling names none of them.** They are almost
all `check` tests: `test_check_reports_a_blessed_copy_as_writable`,
`test_PLUGIN_FILES_is_what_the_plugin_directory_actually_holds`,
`test_the_candidate_the_HOST_would_bind_is_the_one_checked`, and the source check family.

`check` is the doctor command. **It survives the retirement**, and it breaks because it is coupled to
the retired surface in **three** ways this page did not record. They are listed in the order they
bite, which is not the order they look important:

1. ⛔ **`_PLUGIN_GLOB` is the whole of plugin discovery, and it is keyed on the apply registration.**
   `src/gramps_live_api/cli.py` sets it to `gramps*/plugins/**/gramps_live_api_apply.gpr.py`, and
   `_plugin_check` is the only thing that locates the plugin directory. Delete that registration and
   `check` reports the plugin absent on every invocation, **whatever else is present**. The file
   already says as much beside `PLUGIN_FILES`: *"`_PLUGIN_GLOB` finds one of these, the apply
   registration, and finding it..."*. The retirement must repoint discovery at the surviving host
   registration.
2. `PLUGIN_FILES` names `gramps_live_api_apply.gpr.py` and `gramps_live_api_apply.py`, so it demands
   files the retirement deletes.
3. The staleness branch reads `export_path`, which the retirement removes.

⚠️ **The first one gates the second, and an earlier revision of this section got that wrong.** It
attributed the 18 failures to items 2 and 3. `_source_check` takes the plugin `Check` and reads its
`detail` for the directory, so once discovery fails there is no directory to compare `PLUGIN_FILES`
against and the comparison is never meaningfully reached. **Most of those failures are item 1.**

⛔ **That correction is worth more than the entry it fixes.** The failure set was measured, and then
its cause was attributed by reading rather than by checking, which is the same defect this section
exists to warn against, one level in. A measured effect with an unverified cause is not a measured
finding.

⛔ **None of the three is in the inventory above.** That is the sixth inventory miss, and the first
found by measurement rather than by a review round, which is what the probe was for.

### Build time questions, for the removal build to answer

⚠️ **Not answered here, deliberately.** Once the remaining items are hypotheses about code nobody has
written, the build is the cheaper and more accurate reviewer, and answering them from this page would
be producing a seventh unmeasured inventory.

1. What does the unprobed surface break that the probe could not reach? Expect entries beyond this
   list, from `AddNote`, the note parts of `core/proposals.py`, the tool registrations and the CLI
   subcommands.
2. What is left of `core/apply.py` once `AddNote` and its writer are gone? This page never named that
   module, and carve out 1 keeps `NOTE_TYPE_ATTRIBUTES` inside it.
3. What does `check` report once `PLUGIN_FILES` no longer names the apply plugin, and is a doctor that
   reports on one route still the right shape?

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
