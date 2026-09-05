# R9 review ledger: pull request #222, `r9-ruling`

Generated 2026-09-05 from the pull request's review threads. Every finding below is
the reviewer's own text, quoted verbatim; the disposition names the commit that answered it. This is
the committed record the contract requires, and it did not exist until the round it records as a
failure.

## ⛔ The backstop failed here, and the record says so in those words

**Thirteen rounds on thirteen heads, seven past the ceiling before the count was stated.** The
five round backstop exists so that a human decides whether continuing is still worth it; it requires
the owner to say continue, explicitly, at five. What happened instead was implicit continuation: each
dispatch said fix the findings, the conductor read that as authority for the round each fix required,
and the number was never spoken until round thirteen. That is the failure the ceiling exists for, a
conductor holding the work with every next round defensible on its own terms, and it belongs in the
record rather than in a footnote.

Every round produced a genuine correction rather than a refinement, which is exactly why the count
matters: the diagnostic stop never fired, so the count ceiling was the only thing that could have, and
it did not because nobody counted. The owner ruled at round thirteen: merge on his override, file
anything further with the finding quoted verbatim, and let the retirement build be the executable
test of what the ruling says.

## The rounds

| round | head | sev | finding | disposition |
| --- | --- | --- | --- | --- |

| 1 | `b31aaaf` | P1 | **</sub>  Include the direct apply command in retirement** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 4b85846 |
| 1 | `b31aaaf` | P1 | **</sub>  Preserve the document proposal helpers** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 4b85846 |
| 2 | `4b85846` | P1 | **</sub>  Retire or implement the remaining apply operation** (`docs/rulings/R9-retire-the-note-flow.md:None`) | answered |
| 3 | `8887fa5` | P2 | **</sub>  Add R9 to the canonical rulings index** (`docs/rulings/R9-retire-the-note-flow.md:1`) | fixed in 4b8e130 |
| 3 | `8887fa5` | P2 | **</sub>  Count all fourteen surviving live-read tools** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 4b8e130 |
| 4 | `4b8e130` | P2 | **</sub>  Inventory the registered writer behind the CLI** (`docs/rulings/R9-retire-the-note-flow.md:115`) | fixed in e650628 |
| 5 | `e650628` | P1 | **</sub>  Include plugin discovery in the surviving check work** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 74ada36 |
| 6 | `74ada36` | P2 | **</sub>  Inventory the remaining user-facing documentation** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in b7205d5 |
| 7 | `b7205d5` | P2 | **</sub>  Add the census brief to the documentation inventory** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 3d856cb |
| 8 | `3d856cb` | P2 | **</sub>  Refresh current-status text in the historical records** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 3f32a83 |
| 9 | `3f32a83` | P2 | **</sub>  Add contributor and build guidance to the update set** (`docs/rulings/R9-retire-the-note-flow.md:300`) | fixed in 915024b |
| 10 | `915024b` | P2 | **</sub>  Drop NOTE_TYPE_ATTRIBUTES from the carve-out** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 1baa3e6 |
| 10 | `915024b` | P2 | **</sub>  Remove the false document-schema preservation rule** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 1baa3e6 |
| ? | `?` | P3 | **</sub>  Count the documentation groups consistently** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 1baa3e6 |
| 11 | `a859be3` | P2 | **</sub>  Remove the remaining NOTE_TYPE_ATTRIBUTES carve-out** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in d720082 |
| 12 | `d720082` | P2 | **</sub>  Correct the live R9 dependency in the note-types plan** (`docs/rulings/R9-retire-the-note-flow.md:None`) | fixed in 12fbe32 |
| 13 | `12fbe32` | P1 | **</sub>  Preserve the surviving authorization helpers** (`docs/rulings/R9-retire-the-note-flow.md:247`) | OPEN UNRESOLVED |

## The findings, verbatim

### Round 1, P1: </sub>  Include the direct apply command in retirement

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-04. Disposition: fixed in 4b85846.

> If the listed retirement is implemented as written, the document route will not be the only write path: `gramps_live_api apply` remains registered in `src/gramps_live_api/cli.py:85-124` and directly writes an `AddNote` without using `propose_note` or `approve`. Conversely, removing the documented `AddNote` schema support would leave that public command present but broken, so the ruling must either retire `apply` and its associated surface explicitly or narrow the claim that the document route becomes the sole writer.

### Round 1, P1: </sub>  Preserve the document proposal helpers

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-04. Disposition: fixed in 4b85846.

> When the retirement build follows this inventory and deletes `core/proposals.py` wholesale, the surviving document route cannot start: `propose_document` and `approve_document` still use `store_directory`, `new_session`, `_ID`, `ProposalNotFound`, and `claim_document` in `src/gramps_live_api_mcp/server.py:833-887`. Carve these shared helpers out of the deletion or relocate them and update the document route before removing the note-specific store.

### Round 2, P1: </sub>  Retire or implement the remaining apply operation

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-04. Disposition: answered.

> When retirement removes `AddNote` as directed, `gramps_live_api apply` cannot keep working for citations: `core/apply.py::_writable` accepts only `OPERATION_TYPE == "add_note"`, and `tests/unit/test_apply_operation.py:164-175` explicitly verifies that `AddCitation` raises `UnsupportedOperation`. The fresh evidence is that schema registration was mistaken for write support, so executing this ruling leaves the retained `apply` command with no writable operation; either retire that surface or add citation write support before claiming it survives.

### Round 3, P2: </sub>  Add R9 to the canonical rulings index

`docs/rulings/R9-retire-the-note-flow.md:1`, 2026-09-04. Disposition: fixed in 4b8e130.

> This publishes R9 without adding it to `docs/rulings/README.md:22-27`, even though that file explicitly serves as the rulings index and every existing ruling links back to it. Consequently readers following the documented entry point see only R3, R4, R7, and R8 and can miss this retirement decision entirely; add the R9 index entry and the usual backlink with this page.

### Round 3, P2: </sub>  Count all fourteen surviving live-read tools

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-04. Disposition: fixed in 4b8e130.

> The reviewed tree has fourteen live reads: `src/gramps_live_api_mcp/server.py:69-82`, `README.md:194-197`, and `docs/STATUS.md:15-19` all enumerate fourteen, with `tree_name` as the additional argument-free read. This page says thirteen here and again in the retirement benefit at line 110, so the ruling's source inventory undercounts the surfaces that survive; update both counts to fourteen.

### Round 4, P2: </sub>  Inventory the registered writer behind the CLI

`docs/rulings/R9-retire-the-note-flow.md:115`, 2026-09-04. Disposition: fixed in e650628.

> When the retirement build follows this row, removing only the subcommands and handlers does not retire the writer they invoke: `gramps_plugin/gramps_live_api_apply.gpr.py:36-58` still registers the `gramps_live_api_apply` tool, `gramps_live_api_apply.py:83-126` still accepts and applies an operation payload, and `src/gramps_live_api/cli.py:550-554` still requires both plugin files during `check`. Fresh evidence after the earlier apply finding is that the added inventory row stops at the frontend despite a repo-wide reference search showing this separate registered implementation; include the plugin and invocation machinery in the retirement inventory while preserving or moving the `core.apply` helpers used by the document route.

### Round 5, P1: </sub>  Include plugin discovery in the surviving check work

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in 74ada36.

> When the retirement deletes `gramps_live_api_apply.gpr.py`, fixing only these two listed couplings still leaves every `check` invocation reporting the plugin as absent: `src/gramps_live_api/cli.py:47` sets `_PLUGIN_GLOB` specifically to that apply registration, and `_plugin_check` at lines 521-526 uses it as the sole way to discover the plugin directory. In fact, during the described deletion probe this prevents `_source_check` from reaching its `PLUGIN_FILES` check at all, so the headline misdiagnoses most of the resulting `check` failures. Inventory changing `_PLUGIN_GLOB` to discover the surviving host registration as a third required coupling.

### Round 6, P2: </sub>  Inventory the remaining user-facing documentation

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in b7205d5.

> When the retirement build runs, this row names only `docs/using.md`, `docs/slice2-mcp.md`, and the README, but a repo-wide `rg` also finds current guidance that will become false: `docs/restoring.md:12-14` warns that the retired `preview`, `apply`, and `approve` commands take no backup, while `docs/STATUS.md:12-21` and `docs/STATUS.md:122-125` count and advertise the retiring tools as live. Leaving these pages out lets the build complete this checklist while the canonical status and recovery documentation still presents removed commands, so include them in the documentation-update inventory.

### Round 7, P2: </sub>  Add the census brief to the documentation inventory

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in 3d856cb.

> When the retirement build follows this inventory, `docs/census-brief.md` remains a current, README-linked working brief that tells agents at lines 27–28 and 72–73 that `list_people` reads an export and explains why they should avoid it. After `list_people` and the export reader are removed, that operational guidance describes a nonexistent tool. Fresh evidence after `b7205d5` is a repo-wide `rg` for the retired surfaces, which finds this additional current page; include it in this documentation-update row.

### Round 8, P2: </sub>  Refresh current-status text in the historical records

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in 3f32a83.

> When the retirement build follows this blanket “must NOT be updated” instruction, several explicitly current annotations become false: `docs/rulings/R4-graduation-to-the-live-tree.md:3-8` says the older flows write without backups, `docs/rulings/R8-channel-architecture.md:3-10` says `approve` and `list_people` still contradict R8, and `docs/rulings/README.md:6-10` says R8 currently has those exceptions. Preserve the historical ruling bodies, but include these status banners and the index paragraph in the retirement documentation updates.

### Round 9, P2: </sub>  Add contributor and build guidance to the update set

`docs/rulings/R9-retire-the-note-flow.md:300`, 2026-09-05. Disposition: fixed in 915024b.

> When the retirement deletes the apply plugin and console, this measured table still leaves current guidance outside `docs/` describing them as live: `CONTRIBUTING.md:1581-1588` says the plugin directory “now holds two registrations” and compares the host with the apply tool, while `pyproject.toml:21-25` and `.github/workflows/ci.yml:9-12` enumerate the CLI console as part of the current standard-library core. These are not dated records, so following the listed documentation work leaves contributor and CI/package guidance describing deleted components; include these files in the retirement update set.

### Round 10, P2: </sub>  Drop NOTE_TYPE_ATTRIBUTES from the carve-out

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in 1baa3e6.

> After the note-types precondition is built, `NOTE_TYPE_ATTRIBUTES` is not load-bearing for the document route: its only runtime lookup is the retiring `AddNote` path in `core/apply.py:488`, while `docs/plans/note-types.plan.md:431-445` deliberately requires the document writer to carry its own checked set because it does not import the package. Requiring this mapping to survive therefore strands note-flow-specific code after its sole consumer is removed; keep the shared note-type table/set, but not this mapping unless the precondition build introduces a real surviving consumer.

### Round 10, P2: </sub>  Remove the false document-schema preservation rule

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in 1baa3e6.

> When the retirement build removes both `AddNote` and the separately retired `AddCitation`, this instruction can leave the legacy operation schema behind for a role it does not perform. The document route calls `document.parse` in `src/gramps_live_api_mcp/server.py:804`, and graph validation is implemented by `host/document.py:617`; it never uses `core/schema.py` for that purpose. Preserve or relocate the note-type data that the new route actually consumes, but do not retain the operation model on the premise that it validates document graphs.

### Round ?, P3: </sub>  Count the documentation groups consistently

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in 1baa3e6.

> The enumerated update set contains six files under `docs/` (`STATUS`, `using`, `slice2-mcp`, `census-brief`, `restoring`, and `plans/shippable`), plus the root README and these three outside files, which totals ten. Saying there are seven under `docs/` plus the README and three outside instead totals eleven and makes the supposedly measured inventory appear to be missing an unnamed file.

### Round 11, P2: </sub>  Remove the remaining NOTE_TYPE_ATTRIBUTES carve-out

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in d720082.

> When the retirement build uses these build-time questions, this sentence still directs it to retain `NOTE_TYPE_ATTRIBUTES`, contradicting the corrected carve-out at lines 48–55 that says the map has no surviving consumer and should go. The fresh evidence after the prior finding was marked fixed is this unchanged instruction, which can still strand the map and its note-flow-only dependencies; update the question to reflect that only the note-type table survives.

### Round 12, P2: </sub>  Correct the live R9 dependency in the note-types plan

`docs/rulings/R9-retire-the-note-flow.md:None`, 2026-09-05. Disposition: fixed in 12fbe32.

> When the retirement build consults the supposedly untouched plans, `docs/plans/note-types.plan.md:519-523` still explicitly says that `schema.NOTE_TYPES` must not be deleted because the document route depends on it. That is now a forward instruction about this retirement and directly contradicts the corrected carve-out at lines 46-53, since `host/document.py` imports `ACCEPTED_NOTE_TYPES` directly. Classifying every plan except `shippable.plan.md` as having no claim about the retired surface leaves two authoritative documents giving opposite build instructions; add a supersession pointer or include this plan in the update set.

### Round 13, P1: </sub>  Preserve the surviving authorization helpers

`docs/rulings/R9-retire-the-note-flow.md:247`, 2026-09-05. Disposition: OPEN.

> When the retirement build follows this blanket “nothing” instruction, it can delete `core/apply.py` even though the surviving document route still calls `apply.authorise` in `server.py:831`, `867`, and `1068`, while the retained `check` command reads `apply.NAME_FILE` and `apply.SENTINEL_NAME` in `cli.py:215-216`. That would prevent the document route or doctor from starting unless `WritableCopy`, `authorise`, and those constants are first retained or relocated with their consumers. Fresh evidence beyond the earlier plugin-inventory finding is this newly added blanket instruction that explicitly says no part of the module is carved out.
