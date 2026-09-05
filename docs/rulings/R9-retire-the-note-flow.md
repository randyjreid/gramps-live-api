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

### 1. The note type TABLE is kept. The map and the alias go with their consumers

⚠️ **An earlier revision of this carve out kept too much, and said so for a reason that was not true
of the code once note types merged.** Verified against `main` at the note types build:

- **What the document route actually reads is `core/_note_types.py`.** `host/document.py` imports
  `ACCEPTED_NOTE_TYPES` from that module directly, and imports nothing from `core/schema.py`. The
  writer carries its own inlined copy, bound to the table by test. **That table is the carve out.**
- **`schema.NOTE_TYPES` is an alias to the same object.** Its consumers are the note flow's own
  description and validation, both retiring. It goes with them; the document route does not notice.
- **`apply.NOTE_TYPE_ATTRIBUTES` has no surviving consumer.** Its only runtime lookup is the apply
  route's drift guard in `core/apply.py`, which retires, and the tests that read it are that route's.
  Keeping it would strand note flow code after its sole consumer is removed.

⛔ **So: keep `core/_note_types.py` and the derivation behind it. Do not keep `NOTE_TYPES` or
`NOTE_TYPE_ATTRIBUTES` on the premise that the document route needs them.** It does not. The
retirement build had the earlier wording when it was dispatched; if it kept either, removing them is
a small follow up on the same branch, and keeping too much is the safe direction to be wrong in.

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
| the documentation | ⛔ **measured, not listed. See the section below** |

⚠️ **`core/schema.py` is the note flow's operation model, and an earlier revision of this line said
it "also validates the document graph". That was false.** Graph validation is `host/document.py`,
which imports nothing from `core/schema.py`; the document route calls `document.parse`, never
`schema.validate`. Every surviving reference to `schema` is either the note flow (`validate`,
`AddNote`, `ObjectRef`, `NOTE_TYPES` in the `propose_note` description, and `cli.py`'s retiring
subcommands) or `schema.OBJECT_TYPES` in `server.py`, which sits inside `PROPOSE_NOTE_DESCRIPTION` and retires with it. **After the retirement nothing surviving imports `core/schema.py`.** ⛔ **Do not
retain the operation model on the premise that the document route validates through it.** What the
document route needs from `core/` is the note type table, carve out 1.

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
   module. ⛔ **Nothing in it is carved out**: `NOTE_TYPE_ATTRIBUTES` has no surviving consumer and
   goes with the route that read it, per carve out 1, which keeps only the note type table in
   `core/_note_types.py`. An earlier revision of this question said the opposite and contradicted the
   carve out it cited.
3. What does `check` report once `PLUGIN_FILES` no longer names the apply plugin, and is a doctor that
   reports on one route still the right shape?

## ⛔ The documentation set, MEASURED

**Three consecutive review rounds each added one page to this row.** That is a search being run one
page at a time, so it was run properly instead.

**The instrument, and how it is calibrated.** The symbol half is derived rather than recalled: every
module level name defined in the files this retirement deletes, minus every name also defined in a
file that survives, plus the identifiers R9's own inventory names. ⚠️ **That subtraction matters.**
`RESULT_CAP` is defined in `core/people.py` and again in `host/reads.py`, which survives, so deleting
the export reader does not retire it. Matching is on **word boundaries and single tokens**, never
phrases: a phrase spans a line break in a hard wrapped file, and that exact mistake produced five
false "not found" answers about the README in one evening. The sweep is calibrated in both
directions before its result is believed, against a token known present and a token known absent.

⛔ **The prose half CANNOT be derived, and is the accepted residual.** A page that names a retired
command in prose without using a distinctive identifier is invisible to any token search.
`gramps_live_api preview`, `apply` and `approve` are ordinary English words, so they were excluded
from the derived set and searched for separately by hand. **Anything naming the retired surface
without naming a token remains unfound**, and this list does not claim otherwise.

### ⚠️ The residual, measured: three files the sweep could not see, found by review

The paragraph above says prose naming no distinctive token is invisible to the token search. **A
review round then found three such files, and a word bounded check of all 24 derived tokens against
each returns nothing.** That is the residual behaving exactly as described, not the instrument being
wrong, and the distinction decides what happens next.

| file | what it says, in prose only | why the sweep cannot see it |
| --- | --- | --- |
| `CONTRIBUTING.md` | `gramps_plugin/` *"now holds two registrations: the CLI apply tool, and the loopback host"*, and compares how each crosses the Gramps boundary | "two registrations" and "CLI apply tool" name no identifier |
| `pyproject.toml` | the comment over the empty dependency list counts *"the CLI console"* among the standard library core | "CLI console" names no identifier |
| `.github/workflows/ci.yml` | the header comment lists *"schema, write path, CLI console, pii_guard"* as what the core leg measures | same phrase |

**These are current guidance, not records, and the retirement build updates them.** That makes
**ten** files: six under `docs/` counting the moved plan, the README, and these three outside it.

⛔ **This row is CLOSED, by a rule set before the round rather than after it.** Three consecutive
rounds each added one page, so the whole set was measured, and the rule for the round after that was
decided in advance: a page the search *should* have caught means the instrument is wrong and gets
fixed once; a page the search *could not* catch is an accepted residual and is recorded. These three
are the second kind. **Further prose references to the retired surface are expected, they are the
removal build's to find while it is in every one of these files anyway, and they do not reopen this
ruling.**

### Current guidance, which the retirement makes FALSE and must update

| page | why |
| --- | --- |
| `README.md` | names `propose_note` and `list_people` in the tool groups |
| `docs/STATUS.md` | counts the tools with `propose_note`, `approve` and `list_people` in the table, and says outright *"They are not retired; they are simply not the route the project is built around"* |
| `docs/using.md` | documents the three commands and `export_path` as current setup |
| `docs/slice2-mcp.md` | names `TOOL_NAMES`, `TargetNotInExport`, `export_path`, `list_people`, `propose_note` |
| `docs/census-brief.md` | tells agents `list_people` reads an export and why to prefer `find_people`, in the brief that drives the demo |
| `docs/restoring.md` | ⭐ **found only by the hand search.** Its opening callout warns that `preview`, `apply` and `approve` take no backup, about commands that will not exist, on the page somebody reads while recovering a tree |

### ⛔ Records: re-tested against "does it claim something about now or later?"

**Genre is the wrong discriminator, and the first version of this section used it.** A ruling dated
2026-08-21 makes a claim about that date and its body is untouchable. But a document that asserts
what the project **intends** is making a claim about the present, whatever heading it sits under. So
each of the eight was re-read against the question rather than its type.

| page | verdict | why |
| --- | --- | --- |
| `docs/roadmap.md` | **record, untouched** | its own banner says HISTORICAL, not the current plan; its slice 4 text says the export reader goes, which R9 fulfils rather than contradicts |
| `docs/reviews/slice2-ledger.md` | **record, untouched** | dispositions of findings on a dated head |
| the plans under `docs/plans/` except two | **record, untouched** | their `preview` is `document.preview`, not the CLI command; no claim about the retired surface |
| ⛔ **`docs/plans/note-types.plan.md`** | **body untouched, takes a forward pointer** | its R9 dependency section is a forward instruction about *this* retirement, and it is false: it says `schema.NOTE_TYPES` must survive because the document route depends on it, while the build showed the route reads the table directly. ⚠️ **The first re-test called this plan a record by checking the wrong token.** Two authoritative pages gave the build opposite instructions until this pointer |
| ⛔ **`docs/plans/shippable.plan.md`** | **moves to GUIDANCE** | its packaging steps carry `export_path` twice, marked *"[if kept]"*. That is a forward claim about a milestone still ahead, and R9 resolves it: not kept. **The seventh page the retirement build updates** |
| `docs/rulings/R3` | **body untouched, STATUS banner takes a forward pointer** | its egress bounds are grounded in `core/people.py` and the console; both are retired, the bounds survive in `host/reads.py` |
| `docs/rulings/R4` | **body untouched, STATUS banner takes a forward pointer** | its caveat names the unbacked write paths; R9 retires exactly those, so after the build every write path takes the backup |
| `docs/rulings/R8` | **body untouched, STATUS banner takes a forward pointer** | its two named exceptions are the two surfaces R9 removes |
| `docs/rulings/README.md` | **one sentence takes a forward pointer** | it says R8's scope has exceptions; after R9 it has none |

⭐ **A forward pointer is the third option between editing and silence.** It is dated, it says what
supersedes what, and it is phrased to be true now, while the build has not merged, and true after.
It falsifies nothing, the same act as closing an issue with the reason recorded, and it stops the
next reader acting on a banner that no longer holds. **"Correct as written" and "still in force" are
different properties, and only the first is protected by not editing.**

⛔ **The bodies stay as ruled.** The pointers are added by this ruling's own pull request, not by
the retirement build, so a reader of any of those pages is told before the build runs.

## ⭐ Two questions this page left open, now ruled

**Ruled 2026-09-05, by the owner.**

### `check` survives, repointed

⛔ **The doctor stays.** Packaging toward a one command install is a stated goal, and an install
doctor is worth more once there are users who did not build the thing. The question was never whether
it makes sense against one route; it is **which registration it discovers**, and the answer is the
surviving host registration. `_PLUGIN_GLOB` is repointed there, which the checklist above already
names as the coupling that gates the other two.

### `AddCitation` goes

⛔ **Removed with the rest.** It is schema for a capability that **is** implemented: the document
route's writer creates citations. It simply is not implemented through that operation, and nothing
reaches it. There is no writer, `_writable` refuses it, and the document route's real path is
untouched by deleting it.

⭐ **Dead schema describing a LIVE capability by the wrong mechanism is worse than absence**, because
the next reader finds it and believes it is the route. If the document route ever wants a named
citation operation, it will define one that matches how it actually works.

## ⚠️ How `AddCitation` came to be undecided, and the two wrong CLI claims

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

⭐ **So `apply` retires with the note flow**, as the ruling above says.

⚠️ **The question this left open, whether `AddCitation` still earns its place, was ruled on
2026-09-05 and it goes.** The reasoning is in the rulings section above. This account is kept for the
mistake it records, not because the question is still open.

## What this does not settle

- **Whether the loss of the separate process console matters enough to revisit.** The screen put this
  to the owner explicitly and it was not the deciding factor either way. If it later proves to
  matter, it is a new question about the approval surface and not a reopening of this ruling.
- **The order of the retirement build's own steps.** That belongs to its plan gate.
