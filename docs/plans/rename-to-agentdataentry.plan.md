# Plan: rename the project to `AgentDataEntry`

**Destination path:** `docs/plans/rename-to-agentdataentry.plan.md`. Plan mode confines writes to
the harness plan file, so this document is the plan; copy it to that path at build time.

**Status:** plan only. Nothing was built, no branch was created, no commit was made, the working
tree was not modified, the suite was not run, Gramps was not started, and nothing under
`%APPDATA%` or `.claude.json` was touched. Every command run for this plan was read only.

---

## Context

The owner has chosen `AgentDataEntry` as the name of the Gramps addon. The project currently
spells itself `gramps-live-api` in 572 places across 106 of 147 tracked files. Issue #227 is the
packaging and install slice, which publishes a name; renaming after publication is expensive and
public, so **the rename comes before #227**. That ordering is the reason this is happening now
rather than later, and it is recorded here so it does not have to be remembered.

A rename probe has already been executed on a throwaway worktree and its failure set is the
inventory this plan is measured against. Where this plan departs from what the probe measured, it
says so and says why.

---

## 1. What the collision check found (done, not to be re-run)

| name | PyPI | GitHub repository search |
| --- | --- | --- |
| `gramps-agent-data-entry` | HTTP 404 | `total_count=0` |
| `gramps_agent_data_entry` | HTTP 404 | `total_count=0` |
| `gramps-agent-entry` | HTTP 404 | `total_count=0` |
| `AgentDataEntry` | HTTP 404 | `total_count=0` |

Commands: `curl -s -o <discard> -w "%{http_code}" https://pypi.org/pypi/<name>/json` and
`gh api -X GET search/repositories -f q="<name> in:name" --jq .total_count`.

Positive controls fired in the same command shape: PyPI `gramps-mcp` and `requests` both 200;
GitHub `gramps-mcp` 12 and `gramps-live-api` 1. The full `gramps-project/addons-source` listing was
fetched, **156 entries, not truncated**, with zero matches for `AgentDataEntry` and zero entries
beginning with `Agent`; controls `GraphView`, `MediaVerify` and `NoteCleanup` each returned 1.

⚠️ **One fact that changes what a reservation means:** under PEP 503, PyPI normalizes
`gramps_agent_data_entry` and `gramps-agent-data-entry` to the **same project**. The underscore
spelling is not a separate reservation and cannot be held separately. There is one name to take,
not two.

---

## 2. Goal

Rename every spelling of the project that names **the project**, and change no spelling that names
**something already written to disk**.

That one sentence is the whole design. It is stated as a rule rather than as four separate
judgement calls because the probe's four highest-consequence findings (F5, F6, F9 and the sentinel
arms) are all the same failure in different clothes: a constant whose value exists on a user's disk
was treated as a name to sweep.

---

## 3. The name mapping (decision A)

| surface | today | recommended | why |
| --- | --- | --- | --- |
| Gramps addon name and plugin `id` | `gramps_live_api_host` | `AgentDataEntry` | the owner's choice |
| distribution (`pyproject` `name`) | `gramps-live-api` | `gramps-agent-data-entry` | the addon name in PyPI form; nothing holds it |
| core package | `gramps_live_api` | `gramps_agent_data_entry` | matches the distribution |
| MCP package | `gramps_live_api_mcp` | `gramps_agent_data_entry_mcp` | matches the distribution |
| repository slug | `gramps-live-api` | `gramps-agent-data-entry` | matches the distribution; GitHub redirects the old URL |
| plugin registration filename | `gramps_live_api_host.gpr.py` | `AgentDataEntry.gpr.py` | Gramps addon convention, and it is what the probe executed |
| plugin module (`fname=`) | `gramps_live_api_host.py` | `AgentDataEntry.py` | must match `fname=` in the registration |
| writer module | `gramps_live_api_writer.py` | `AgentDataEntry_writer.py` | flat Gramps plugin namespace; the addon prefix is what makes it unique there, and the host imports it by name |
| addon display `name=` | `gramps-live-api: loopback host` | `Agent Data Entry` | see below |
| MCP `SERVER_NAME` | `gramps-live-api` | `gramps-agent-data-entry` | handshake name, not the client key |
| `cli.HOOK_MARKER` | `gramps_live_api.core.pii_guard` | `gramps_agent_data_entry.core.pii_guard` | follows the package |
| env prefix | `GRAMPS_LIVE_API_*` | `GRAMPS_AGENT_DATA_ENTRY_*` | safe: see the measurement below |
| abbreviation | `glapi` | `gade` | F12; the probe measured the rewrite green |
| **`%APPDATA%` directory** | `gramps-live-api` | **unchanged** | section 4 |
| **tree sentinel, undo, proposals** | `.gramps-live-api-*` | **unchanged** | section 4 |
| **`JOURNAL_FORMAT`** | `gramps-live-api/document/1` | **unchanged** | section 4 |

### The addon display name (probe H3)

`AgentDataEntry.gpr.py` currently registers `name="gramps-agent-data-entry: loopback host"`. That
is a distribution slug being used as a human readable label in the Gramps addon list, beside an
addon whose id is `AgentDataEntry`. It is mechanically correct and wrong in kind.

**Recommendation:** `name="Agent Data Entry"`. It is the only registration in the plugin directory
(measured: `git ls-files | grep gpr` returns one file), so the qualifier that distinguished it from
a sibling registration no longer has a sibling to distinguish it from. The `description=` field
already says what it does, in a sentence, and that is the field Gramps shows for the detail.

### The length cost, named (probe F1 and F2)

`gramps_agent_data_entry` is **8 characters longer** than `gramps_live_api`. The probe measured
that this alone produced:

- **7 `E501` line length errors** (`ruff check .` exit 1), and
- **5 files failing `ruff format --check`**.

`ruff format .` reflowed 6 of the 7. The seventh, `tests/unit/test_cli.py:289`, is a **string
literal** the formatter cannot split; it needs a hand edit into two adjacent literals. So a rename
to a longer name is not fully mechanical, and the budget is **one hand edit per over long string
literal**, measured at one.

**The alternative considered and rejected:** `gramps-agent-entry` is only 3 characters longer and
produces few or none of these. It is rejected because it does not spell the addon the owner chose,
and a distribution whose name reads differently from the addon it installs is a permanent, quiet
tax on every reader. Seven mechanical edits, six of them automatic, is a cheap price for one name.

**This is the gate question on this section:** if the owner would rather have the shorter name,
say so at the gate and the mapping changes in one row.

---

## 4. The on disk names (decision B): freeze all of them

**Recommendation: no name that has been written to disk changes in this rename.** That is five
constants and one directory:

| constant | value, kept | what is on disk today |
| --- | --- | --- |
| `core/apply.py` `SENTINEL_NAME` | `.gramps-live-api-copy` | the blessing on two blessed trees |
| `host/document.py` `SENTINEL` | `.gramps-live-api-copy` | same value, second spelling |
| the writer's inlined `SENTINEL` | `.gramps-live-api-copy` | same value, third spelling |
| `host/document.py` `UNDO_DIRECTORY` | `.gramps-live-api-undo` | **5 undo journals** |
| `core/proposals.py` `PROPOSAL_DIRECTORY` | `.gramps-live-api-proposals` | **2 pending proposals** |
| `host/document.py` `JOURNAL_FORMAT` | `gramps-live-api/document/1` | written into every journal record |
| `config.py` and the plugin's `DIRECTORY_NAME` | `gramps-live-api` | config, token, port, logs, and about 96 MB of tree backups under `%APPDATA%` |

### Why, in the order the evidence lands

1. **The brief's Arm A freezes one of three, and the probe found the other two.** Renaming
   `-undo` and `-proposals` while freezing `-copy` leaves a blessed tree showing
   `.gramps-live-api-copy` beside `.gramps-agent-data-entry-undo`, which is visible to anyone who
   lists the directory and defensible to nobody. Whatever is decided, the three are one decision.

2. **F5 is the sharpest finding in the probe and it is not about orphaning.** The probe's
   controlled experiment, same `config.json` bytes, one variable changed:

   ```
   directory name matches   ->  ConfigError: ['export_path'] is not a setting --
                                known settings are ['copy_path', 'gramps_runtime']
   directory renamed        ->  load() returned: copy_path EMPTY
   ```

   Renaming the state directory converts a loud, named refusal into a silent empty. `config.py`'s
   own docstring says the design exists to stop a file the owner edited from being ignored while he
   believes his edit is in force. Renaming the directory produces exactly that state by a different
   route. **A rename that defeats a stated design property of the thing being renamed is not a
   rename, it is a regression wearing one.**

3. **F6 puts about 96 MB of backups permanently outside `prune`'s retention bound**, and
   `docs/restoring.md`, the document a person reads while undoing a bad write, would point in three
   places at an empty directory. R4 is a **recorded downgrade** from *a bad write cannot happen* to
   *a bad write can be reversed*; the backups are what makes the second half true. And the codebase
   already records this exact failure one level down, at `host/backup.py:111-119`, where a tree
   rename split one tree's retention across folders and `prune`, given one directory, never saw the
   old one again. A project directory rename is that same shape one level up.

4. **The cost of freezing is cosmetic and bounded.** The old name stays visible in the doctor's
   most read line (`ok .gramps-live-api-copy: is blessed for writing by hand`) and in the state
   directory path. Nothing breaks. Nobody has to do anything.

5. **The cost of renaming is real and measured.** Two blessed trees on this machine, one blessing,
   five undo journals and two pending proposals that can no longer be claimed. The probe's
   correction to the brief stands and narrows it: the refusals **do** name the file to create
   (`apply.authorise` and `document.py:114-118` both do), so the sentinel case costs one rename by a
   user who was told the target filename. **But `-undo` and `-proposals` have no such message**, and
   the state directory has the F5 silent empty instead of one. The parts with no message are the
   parts holding the most content.

### What freezing dissolves

Probe **H4** proposed a one time check for the old state directory, reported by `check` rather than
migrated silently, and asked whether to build it. **Freezing dissolves the question rather than
deferring it:** there is no old directory, because there is no new one. No migration is built, no
migration is filed, and no build time question is left open on this point.

If a state directory rename is ever wanted, **#227 is where it belongs**, because that is the slice
that gains an installer, and an installer is the only thing that can perform a migration at a
moment the user is expecting change. File it there; do not do it here.

### Why this departs from both measured arms, and what that costs

⚠️ **This is a hypothesis where it departs from the probe.** The probe measured Arm A (sentinel
frozen, everything else swept) and Arm A plus B (nothing frozen). Both were fully green. This plan
freezes **more** than Arm A, and that state was not executed.

The departure is low risk and the reason is measurable rather than argued. Every test reaches these
values through the named constant, not through a literal. Measured over tracked files:

```
.gramps-live-api-copy          tests:0   src:3   docs:16
.gramps-live-api-undo          tests:1   src:2   docs:9
.gramps-live-api-proposals     tests:0   src:1   docs:1
gramps-live-api/document/1     tests:0   src:1   docs:1
control: gramps_live_api       tests:200
```

The single test literal is `tests/unit/test_host_plugin.py:756`, `tmp_path / ".gramps-live-api-undo"`,
and under the freeze it needs no change and keeps acting as a pin on `UNDO_DIRECTORY`. The control
line is there to show the instrument fires.

Nothing else asserts these strings literally, so freezing them is a **smaller** change than either
measured arm rather than a different one. **The build states this measurement in its report; it is
not carried on this plan's word.**

---

## 5. F4, the sentinel with no gate (decision C): add the pin

**Recommendation: this plan adds the missing pin. It is not filed.**

F4 is the probe's highest severity finding and the only one it rates as such. The sentinel is
spelled independently in three places (`core/apply.py` `SENTINEL_NAME`, `host/document.py`
`SENTINEL`, the writer's inlined `SENTINEL`, the last inlined deliberately because Gramps `exec`s
the plugin rather than importing it). A partial rename is **green on all six CI jobs**, measured
with a negative control:

```
MUTANT: <writer>   ".gramps-agent-data-entry-copy" -> ".gramps-live-api-copy"
1072 passed, 17 skipped        <- core leg: MUTANT SURVIVES
```

The one guard that exists is in `tests/integration/test_round_trip.py`, which skips twice over
(`mcp_or_skip()` on the core leg, `runtime_or_skip()` wherever no Gramps runtime is installed, and
its own skip text says this is expected on CI), and it is not among the three modules the
"Refuse a run whose MCP tests did not run" step protects.

**Freezing the sentinel makes the pin more necessary, not less.** After this change, three
constants hold a name that no longer matches the project. That is precisely the shape a future
tidying pass fixes in one place and not the other two, and the failure it ships is `document.py`
and `apply.py` answering *this tree is blessed* while the writer inside Gramps answers *it is not*,
from constants whose entire purpose is to be the same answer. **Freezing without the pin is the
setup for F4, not an escape from it.**

### What to build

One test in `tests/unit/`, on the **core leg** so it runs on all six CI jobs, with no Gramps and no
MCP extra:

- read the three sources, extract each `SENTINEL` / `SENTINEL_NAME` assignment as an
  `ast.Constant`, and assert the three values are equal.
- **Reuse the existing pattern.** `tests/fixtures/host_sources.py:registered_filename` already
  reads a constant out of a plugin file with `ast` rather than by text match, for the stated reason
  that a name mentioned in prose above a call must not be mistaken for the one being declared. Use
  the same approach, in the same file, next to it.
- **The precedent to follow for shape** is `tests/unit/test_cli.py:323`
  `test_the_source_check_matches_what_the_host_actually_does`, which reads the plugin's source and
  fails when two spellings of one rule stop agreeing. Its docstring calls that this project's most
  recorded defect class. This is another instance of it.
- The contrast case is already pinned and needs nothing:
  `test_the_last_resort_log_agrees_with_the_real_one` catches the `DIRECTORY_NAME` mutant on three
  platform layouts.

**Acceptance for this item:** reverting any one of the three sentinel spellings makes the **core**
leg red. The builder demonstrates it with a negative control and restores in a `finally`.

---

## 6. F11, the dated records (decision D): do not touch them

**Policy, stated once and applied as a rule rather than per file:**

> **`docs/plans/`, `docs/reviews/` and `docs/rulings/` are not modified by this change.** They are
> dated records of work done under the old name. A statement about the past that names the old name
> is true, and rewriting it makes it false.
>
> **One dated paragraph is added to `README.md`**, recording that the project was called
> `gramps-live-api` until the rename, and that every document in those three directories describes
> work done under that name and is left as written.

### Why one note rather than eighteen banners

The standing rule is that a document recording something that happened takes a dated banner while
one describing how the thing works now takes its sentences corrected, and the rows decide which.
The rows here decide **all eighteen are records**: 9 plans, 3 review ledgers, 6 rulings including
the rulings index.

Eighteen banners is eighteen new claims. **One note is one claim.** Every new sentence is a new
claim, and a claim written while fixing a claim is where the worst findings come from. Applying the
directory as the unit rather than the file also removes the classification step entirely, which is
the step that would have to be reviewed.

**It also makes both of the probe's measured falsifications impossible rather than repaired:**

- `docs/rulings/R8-channel-architecture.md:203` records a raw log under the old state directory
  name, a file the probe verified exists under that name. Untouched, so still true. (It is also
  covered twice over, since the state directory name is frozen.)
- `docs/rulings/README.md:26`, the single line the probe rewrote in that file, names
  `.gramps-live-api-copy`, which is frozen. That file needs **zero** edits.

### The one exception outside those directories

`src/gramps_live_api/cli.py:37` is a comment inside a live source file making a statement about the
past: that `_PLUGIN_GLOB` used to name `gramps_live_api_apply.gpr.py`, the registration the R9
retirement deleted. The sweep rewrote it and thereby asserted the prior existence of a file that
never existed under any name. **This line is excluded from the sweep.**

It is the only one. Derived rather than assumed, over `src`, `scripts`, `gramps_plugin` and `tests`:

```
git grep -I -n -E -- '(used to|formerly|was called|no longer|renamed|until|previously)' \
  -- src scripts gramps_plugin tests | grep -i 'live.api\|live_api'
```

returns one line carrying the project name in a historical statement. **The builder re-runs this
command and reports its output**, because a plan asserting a count of one is exactly the kind of
number that goes stale.

### The trade, recorded in both directions

A reader who opens `docs/rulings/R8-channel-architecture.md` directly will not see the README note
and will meet the old name with no explanation on the page. That is the cost, it is accepted, and
it is cheaper than eighteen hand written banners each of which is a new reviewable claim.

---

## 7. F10, the ordering (decision E)

`scripts/pr_ready.py:57` hardcodes `REPOSITORY = "<owner>/gramps-live-api"` plus two GraphQL
literals, the README CI badge carries the slug, and about 20 issue and pull request links in `docs/`
carry it. Rewritten links 404 **before** the GitHub rename and work after. The two renames are
coupled and no gate or test can observe the coupling.

**The sequence, and it is not negotiable within the branch:**

1. Build the whole change locally on a branch. Run every local gate. Run every local review round
   to disposition (Codex, then the official `/code-review` pass, then one scoped Codex delta).
   **Nothing is pushed yet.**
2. Post the comment on #220 (section 9).
3. **Rename the GitHub repository** to `gramps-agent-data-entry`.
4. `git remote set-url origin https://github.com/<owner>/gramps-agent-data-entry.git`, run **once**
   in the primary checkout (section 8 explains why once), and once in the counsel clone.
5. Push the branch and open the pull request.
6. Bot rounds, full CI matrix green, then the owner merges.

**Why the GitHub rename goes at step 3 and not after the merge.** Putting it after the merge means
that between merge and rename the merged code's slug names a repository that does not exist, and
about 20 user facing documentation links 404. Putting it at step 3 means `pr_ready.py` is only ever
invoked from the branch, where it already carries the new slug, and only after GitHub already
answers to that slug. **That ordering makes the question of whether GitHub's GraphQL API follows
rename redirects moot, which is better than answering it**, since the answer is not something this
plan can pin.

**The window this leaves, stated:** between steps 3 and 6, the nine other worktree branches carry
the old slug in `pr_ready.py` and it will fail against a repository that no longer answers to that
name. Those branches are paused for the duration. That is the whole cost and it falls on the
conductor, loudly, not on a user, silently.

---

## 8. Surfaces outside the repository (F): reported, not changed

This plan changes none of these. Each is reported so the owner can act, and the two that need
action after the merge are named as such.

**The GitHub redirect.** GitHub redirects the old repository URL after a rename, for the web and
for git over HTTPS. The redirect survives as long as nothing takes the old name. The collision
check in section 1 measured that nothing holds `gramps-agent-data-entry` anywhere; the risk here is
the reverse, that something later takes `gramps-live-api` and shadows the redirect. Nothing is
scheduled to. **Stated rather than assumed:** the old name is not re-registered by anyone, including
by the owner, after the rename.

**Local checkouts and worktrees, with a correction.** `git worktree list` reports the primary
checkout plus ten `glapi-*` worktrees, one of which is the throwaway rename probe. **They are
worktrees, not clones: they share one repository and one remote configuration.** Measured:
`git remote -v` in the primary checkout reports one `origin`, and a worktree's `.git` is a file
reading `gitdir: %USERPROFILE%/projects/gramps-live-api/.git/worktrees/<name>`.

So the remote update is **one command in one place**, not ten. What *is* ten-fold is the `gitdir:`
pointer: renaming the primary checkout **directory** breaks every worktree's pointer and every
`.git/worktrees/*/gitdir` back-pointer at once.

**Recommendation: do not rename the local checkout directory.** It is not required by anything,
it costs ten breakages, and it is the half of probe F7 that would otherwise break the MCP
registration's `command` field. If it is ever wanted, do it when no worktrees exist.

**The counsel clone** at `%USERPROFILE%\projects\counsel\gramps-live-api` is a real clone with its
own `origin` pointing at the old URL (measured). It needs its own `git remote set-url`. Its
directory name and its `evidence/` paths carry the old name, and 127 files under `counsel` name the
project. **Out of scope; reported.**

**The MCP client registration** in `%USERPROFILE%\.claude.json`, probe F7:

- `args: ["-m", "gramps_live_api_mcp"]` is **unconditionally broken** by the package rename. The
  server stops starting with `No module named gramps_live_api_mcp`. **This server is live in the
  session doing this work.** It must be edited to `gramps_agent_data_entry_mcp` after the merge, by
  the owner or an interactive session, and the client restarted.
- `command`, the checkout path, is **unaffected** given the recommendation above not to rename the
  checkout directory.
- The client key `gramps` is name independent and needs no change.

**The workflow contract** names `gramps-live-api`. ⛔ It lives in another repository owned by
another session. **Reported; changed by nothing here.**

**The installed junction**, probe F8. `%APPDATA%\gramps\gramps60\plugins\gramps-live-api` is a
junction into the checkout's `gramps_plugin/`. Because it is a junction and not a copy, the plugin
files follow the rename automatically and the junction keeps working under its old name. The defect
is in the **rewritten instructions**: `docs/using.md` lines 86 and 128 set
`$link = "$plugins\gramps-live-api"` inside an `if (Test-Path $link) { ... } else { New-Item ... }`,
so a user following the rewritten page creates a **second** junction and the first is never removed
or mentioned. Two directories then register the same `.gpr.py`.

**In scope, minimally:** `docs/using.md` is already being rewritten by the sweep, so it also gains a
line instructing the reader to remove a junction named `gramps-live-api` if one exists, before
creating the new one. That is one added sentence in a file already changing.

**Filed, not fixed:** probe H2, that `cli._plugin_check` returns `found[0]` and reports one path
while never mentioning the others, so the install doctor cannot surface a duplicate. It is
pre-existing and independent of this rename; the rename only makes a second directory likely. One
issue, the finding quoted verbatim from the probe report.

**The installed pre-push hook**, probe section 7. `cli.HOOK_MARKER` changes with the package, and
`_push_gate_check` compares the installed hook body line by line against `scripts/hooks/pre-push`.
A developer with the pre-rename hook installed gets a **loud message that names its own remedy**
(`is a STALE copy ... Re-copy it: cp scripts/hooks/pre-push <installed>`). No build work. Reported
so nobody diagnoses it twice.

**Environment variables are safe to rename here, measured.** `GRAMPS_LIVE_API_COPY`,
`_RUNTIME`, `_SRC`, `_GATE_BASE`, `_PYTHON`, `_OP` are not set persistently on this machine:
`[Environment]::GetEnvironmentVariables('User')` and `('Machine')` both return no key matching
`*GRAMPS*`. So the rename cannot silently drop an override that exists, because none exists.

---

## 9. #220, the external contributor (decision G)

**Recommendation: rename now, and post a short comment as a courtesy.**

### The correction that decides it

The brief states that a repository rename breaks the contributor's local remote with no warning.
**Measured, it largely does not.** `gh pr view 220` reports `"isCrossRepository": true` and a head
repository owned by the contributor: #220 comes from **their fork**. Their fork is not renamed and
keeps its own name, so their `origin` is untouched. If they also keep an `upstream` remote at the
old URL, GitHub's rename redirect keeps git over HTTPS working against it.

The stated harm is therefore mostly absent, and the case for waiting rests on it.

### The real cost, which is different and smaller than the brief assumed

125 of 147 tracked files change, so **any** open branch needs a rebase. #220 touches five files
(`docs/census-brief.md`, `gramps_plugin/gramps_live_api_writer.py`,
`src/gramps_live_api/host/document.py`, `src/gramps_live_api_mcp/server.py`,
`tests/unit/test_document_preview.py`), of which three are renamed by this change. That rebase is
the cost, and it is imposed on an external contributor.

It is bounded, and the commit structure in section 11 is chosen partly to bound it: **the first
commit is `git mv` only, 33 files, zero insertions and zero deletions**, which is the shape git's
rename detection handles best.

**Renaming after #220 closes** would make an external contributor's availability the gate on the
rename, and the rename is the gate on #227. That is a worse trade than one rebase on a five file
pull request.

Also note **PR #247 is open and is the owner's**. It should merge or close before this branch is
built, for the same conflict reason and with none of the external cost.

### The comment to post, drafted

⛔ **This plan does not post it, does not touch #220's branch, and runs nothing from it.**

> I am about to rename this repository from `gramps-live-api` to `gramps-agent-data-entry`. GitHub
> forwards the old address, so this pull request and its link keep working, and your fork keeps its
> current name, so the `origin` remote you push to needs no change.
>
> Two things do change, and I am sorry for the disruption:
>
> 1. The code moves. `src/gramps_live_api/` becomes `src/gramps_agent_data_entry/`,
>    `src/gramps_live_api_mcp/` becomes `src/gramps_agent_data_entry_mcp/`, and
>    `gramps_plugin/gramps_live_api_writer.py` gets a new filename. Three of the five files in this
>    pull request are among them, so it will need a rebase once the rename lands. The first commit
>    of the rename is file moves only, with no content changes, which is the case git handles best.
>    If you would rather not do the rebase, say so and I will do it for you.
>
> 2. If you have a second remote pointing at this repository, often called `upstream`, you can point
>    it at the new address with:
>
>    ```
>    git remote set-url upstream https://github.com/<owner>/gramps-agent-data-entry.git
>    ```
>
> Nothing else about your work here is affected, and the review continues as normal.

---

## 10. Acceptance criteria, mechanically checkable

**Gates, both legs, on the branch head.** Baseline to beat is the probe's, taken on `main`:

| gate | must read |
| --- | --- |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `140 files already formatted` |
| `mypy src/gramps_agent_data_entry` (core leg) | `Success: no issues found in 27 source files` |
| `pytest -rs` (core leg) | at least `1072 passed`, plus the new pin test, `17 skipped` |
| `mypy src` (mcp leg) | `Success: no issues found in 30 source files` |
| `pytest -rs` (mcp leg) | at least `1125 passed`, plus the new pin test, `10 skipped` |
| MCP-tests-ran refusal | `49 MCP test cases ran across 3 modules; none skipped, none errored` |
| dependency-free refusal | `'mcp' absent, 4 requirement(s), all behind extras` |
| `python -m gramps_agent_data_entry.core.pii_guard --range HEAD .` | `0 finding(s)` |
| `scripts/gate.py` and `scripts/hooks/pre-push` | pass |

**The census arithmetic, with positive controls.** Baseline measured on `main`:

```
git grep -I -o -i -E -- 'gramps[-_. ]?live[-_. ]?api' | Measure-Object -Line     -> 572
  of which, in docs/plans + docs/reviews + docs/rulings                          -> 100
  of which, everywhere else                                                      -> 472
```

After the change, the criterion is **not** that the wide net returns zero. It cannot and must not,
because two classes of occurrence are correct by design. The criterion is that the residual is
**fully accounted for**, and the builder reports the arithmetic:

```
rewritten + residual == 572
```

with every residual line falling into exactly one of four classes:

1. anything in `docs/plans/`, `docs/reviews/` or `docs/rulings/` (section 6);
2. a frozen on disk constant or documentation describing one (section 4);
3. the state directory name, its two constants, and documentation naming that path;
4. the single historical comment at `cli.py:37` (section 6).

**Predicted residual outside the three dated directories, measured component by component on
`main`:** `.gramps-live-api-copy` 14, `.gramps-live-api-undo` 11, `.gramps-live-api-proposals` 2,
`gramps-live-api/document/1` 2, state directory path mentions 13, `DIRECTORY_NAME` constants 2, the
historical comment 1. That is **45**, so the whole predicted residual is about **145**.

⚠️ **145 is a prediction, not an assertion.** The component greps use different patterns and one or
two lines may match more than one of them, and the new README note adds occurrences of its own. **The
builder measures the actual residual, reports it, and reconciles it against 572.** A number this plan
computed is exactly the kind that drifts.

**Every negative is calibrated against a positive control in the same command shape**, as the probe
did. A count of zero from an instrument that was never shown to fire is not evidence.

**The F4 pin.** Reverting any one of the three sentinel spellings turns the **core** leg red.
Demonstrated with a negative control, restored in a `finally`.

**The manual Gramps check, which no gate covers.** Before merge, on this machine: remove the old
junction, create the new one per the rewritten `docs/using.md`, start Gramps once, and confirm

- `check` reports `plugin: ok` and `source: ok`;
- the host starts and the loopback route answers;
- one document proposal round trips against the blessed copy;
- the tree's `.gramps-live-api-copy`, `.gramps-live-api-undo` and `.gramps-live-api-proposals` are
  the same directories as before, with the five journals and two proposals still present and
  claimable.

This is the only item the probe explicitly could not test, and section 12 explains why it is the
one thing here that could still break.

**CI.** All six jobs (ubuntu-latest, 3.10, 3.11, 3.12, both legs) green **on the head the decision
screen describes**, before the screen is posted.

---

## 11. What is one commit and what is separate

One branch, one pull request, **six commits**. Not one commit: mixing file moves with content edits
defeats git's rename detection, which is what makes both the review and #220's rebase tractable.

| # | commit | shape |
| --- | --- | --- |
| 1 | `git mv` only | 33 files, **0 insertions, 0 deletions** |
| 2 | the content sweep | packages, distribution, slug, env prefix, plugin id, `fname`, display name, `SERVER_NAME`, `HOOK_MARKER`, `_PLUGIN_GLOB`, `PLUGIN_FILES`, `HOST_IMPORT`, `REPOSITORY`. **Excludes** every frozen name, all of `docs/plans|reviews|rulings`, and `cli.py:37` |
| 3 | `ruff format .` plus the one hand edit | the 5 files of F2 and the string literal of F1 |
| 4 | `glapi` to `gade` | 2 files, 6 occurrences (F12) |
| 5 | the F4 sentinel pin, plus docstrings on the frozen constants saying they are frozen and why | new test, comment only edits to the constants |
| 6 | the README dated note, and the `docs/using.md` old junction line | 2 files |

Commit 5's docstrings are load bearing, not decoration. A narrowing can be misread as licence to
revert what preceded it: a frozen constant with no recorded reason reads to the next reader as an
occurrence the sweep missed. **Each frozen constant says, in one line, that its value names
something already on disk and is deliberately not swept.**

---

## 12. The one question, applied to this plan

**Would following this plan produce something you could show breaking?** Ten candidates were tried.
Nine are dismissible with a named reason. One is not, and it is stated as the plan's live risk.

Dismissed, with the reason:

- *Frozen sentinel drifts across its three spellings.* Commit 5's pin makes it red on the core leg.
- *A fresh user meets `%APPDATA%\gramps-live-api\` under a project called Agent Data Entry.*
  Confusing; `check` names the exact path; nothing breaks.
- *`_PLUGIN_GLOB` no longer finds the existing junction.* It does: the junction points at the same
  directory, which now holds `AgentDataEntry.gpr.py`. The doctor reports `plugin: ok` under the old
  junction name.
- *A user following the rewritten `docs/using.md` gets two junctions.* Commit 6's added line.
- *A test asserts a frozen literal and the sweep breaks it.* Measured: one such literal exists,
  `test_host_plugin.py:756`, and the freeze means the sweep never reaches it.
- *A saved environment override is silently dropped.* Measured: no `GRAMPS_*` variable is set
  persistently on this machine.
- *`pr_ready.py` runs against a repository that does not exist.* Section 7's ordering makes it
  unreachable within the branch, and names the branches that are paused.
- *#220's contributor loses their remote.* Measured: their `origin` is their own fork, which is not
  renamed.
- *A dated record is falsified.* Section 6's rule means no dated record is edited at all.

⚠️ **The one that survives: Gramps' own acceptance of the new plugin filenames and id.** The probe
could not start Gramps, and lists as unverified that Gramps accepts `id="AgentDataEntry"`, that it
accepts a `.gpr.py` whose filename is PascalCase, that `fname="AgentDataEntry.py"` resolves, and
that `import AgentDataEntry_writer` works under Gramps' `exec`-not-import loading. The named input
is: start Gramps with the new junction in place. The named wrong output is: the addon does not
register, or registers and does not load, and the loopback host never starts, which is silent from
inside the repository because every gate is green.

**This is not a reason to specify deeper. It is a build time question with a mandatory manual
answer**, and it is written into section 10 as an acceptance criterion rather than left to the
build's judgement. Probe H1, what Gramps does with one id registered under two junctions, is
answered by the same launch.

---

## 13. Platform coverage

The probe ran **one interpreter, CPython 3.12.13, on Windows**. CI runs ubuntu-latest on 3.10, 3.11
and 3.12, and this project has been bitten by Linux-only failures after clean local runs.

What this plan does about it:

- F1 and F2 are line length and F3 is a path; all three are platform independent, and the probe
  says so.
- The F4 skip analysis for Linux is a **reading** of `config.discover_runtime` (which returns
  `None` off Windows unconditionally) and of `ci.yml` (which installs no Gramps), **not a
  measurement**. The new pin test in commit 5 is written to be dependency free and runtime free
  precisely so that it is a measurement on all six jobs rather than a reading.
- **No decision screen is posted, and no merge is proposed, until the full six job matrix is green
  on the head the screen describes.** The local Windows run is a precondition, never the verdict.
- The manual Gramps check in section 10 is Windows only by necessity. It is recorded as such: it
  proves the addon loads on this machine, and proves nothing about Linux, where Gramps is not
  installed by CI and the round trip skips by design.

---

## 14. Out of scope, explicitly

- Renaming the local checkout directory (section 8 recommends against it).
- Renaming or migrating the `%APPDATA%` state directory (section 4; belongs to #227 if ever).
- Renaming the three tree local on disk names or `JOURNAL_FORMAT` (section 4).
- Editing `%USERPROFILE%\.claude.json` (section 8; the owner or an interactive session does it
  after the merge).
- The counsel clone, its directory name, its remote and its `evidence/` paths.
- The workflow contract file, which lives in another repository.
- Submitting the addon to `gramps-project/addons-source`.
- Reserving or publishing the distribution on PyPI; that is #227.
- Fixing probe H2 (`_plugin_check` returning `found[0]`); filed as an issue instead.
- Probe H5 (`JOURNAL_FORMAT` still `/1` while the identifier changed); dissolved by the freeze,
  since the identifier does not change.

---

## 15. Issues to file (not fixed here)

One issue per finding, each quoting the probe verbatim; none folded into another.

1. **H2**, `cli._plugin_check` returns `found[0]` and reports it as the installation, never
   mentioning other matches. Pre-existing fail-open, made likelier by a second install directory.
2. **The state directory migration**, deferred to #227 with the reason recorded: an installer is
   the only thing that can migrate at a moment the user expects change. Includes F5's controlled
   measurement and F6's backup arithmetic.
3. **The cosmetic residual of the freeze:** the old project name remains user visible in the
   doctor's most read line and in the `%APPDATA%` path, permanently, by decision.
4. **`gramps_plugin/__pycache__/` accumulates and is never swept** (probe F8's tail), currently
   holding four stale `.pyc` files including two from the R9 retirement. Residue, not a defect.

---

## 16. Open gate questions for the owner

1. **The distribution and package name.** `gramps-agent-data-entry` is recommended and costs 7 line
   length edits, one of them by hand. `gramps-agent-entry` is 5 characters shorter and costs fewer
   or none, at the price of a distribution that does not read like the addon.
2. **The freeze.** Section 4 recommends freezing all on disk names, which leaves the old project
   name permanently visible in the doctor's output. Arm B was measured fully green inside the gates
   and costs one rename per blessed tree plus the loss of five undo journals and two claimable
   proposals. This is the one place where the recommendation buys correctness with cosmetics, and
   it is the owner's to reverse.
3. **The addon display name**, recommended as `Agent Data Entry`.
4. **#220.** Rename now with the drafted comment is recommended. Waiting is the alternative and
   makes an external contributor's availability the gate on #227.
5. **Depth.** Whether the second review seat runs on this change, per the standing loop.

---

## 17. The owner's gate decisions, 2026-09-06

**Recorded by the conductor. This section is a record of rulings, not new design.**
Where it contradicts an earlier section, this section governs and says so.

### ⭐ The finding the build reads first

> **The test suite does not measure this change at all.**

Measured by the probe, not asserted: the suite's pass rate is **identical before and after** the
rename, core `1072 passed, 17 skipped` and mcp `1125 passed, 10 skipped`. Twelve findings, **three
caught by a gate, and all three of those are mechanical** (two line-length, one path). **Every
finding with a user-visible consequence is invisible to CI.**

⚠️ **What this means for the build: a green gate is not evidence that this change is correct.** It
is evidence that the change did not break something the suite already covered. The acceptance
criteria in section 10 exist because the gates do not, and the manual Gramps check is not a
formality appended to them, it is the only check that observes the one risk section 12 could not
dismiss.

### The five answers

1. **Distribution and repository slug: `gramps-agent-data-entry`.** Exact match with the addon
   name. The shorter alternative in section 3 is declined; the 7 line-length edits, 6 of them
   automatic, are accepted.
2. **The freeze: YES**, all on-disk names, as section 4 recommends. F5 alone carries it.
3. **The F4 pin is added, not filed**, as section 5 recommends.
4. **Addon display name: `Agent Data Entry`.**
5. **#220: rename now.** ⚠️ **With one change to section 7's sequence, see below.**

### ⚠️ The freeze caveat becomes an acceptance criterion

Section 4 records that this plan freezes **more** than either arm the probe executed, so **that
state was never run**. It is a hypothesis, and the plan's defence is a measurement over tracked
files that only one test asserts a frozen string as a literal.

**The build MEASURES it rather than inheriting it.** Added to section 10:

- Re-run the component counts in section 4 on the branch head and report them, with a positive
  control in the same command shape.
- Report the actual full-gate result for the frozen state, both legs, as a measurement of a
  configuration no probe arm executed.
- Confirm `tests/unit/test_host_plugin.py:756` still reaches `UNDO_DIRECTORY` through the constant
  and still acts as a pin on it.

### ⚠️ Section 7's sequence changes: the #220 comment moves

Section 7 places the #220 comment at step 2, **before** the GitHub rename. **That is superseded.**
The comment is posted **when the rename lands, not before**, and its wording goes to the owner for
approval before it is posted. The corrected sequence:

1. Build on the branch. Every local gate. Every local review round to disposition. Nothing pushed.
2. Rename the GitHub repository.
3. `git remote set-url origin ...`, once in the primary checkout and once in the counsel clone.
4. **Post the #220 comment**, wording approved by the owner beforehand.
5. Push the branch, open the pull request.
6. Bot rounds, full six-job matrix green, then the owner merges.

Everything section 7 argues about why the GitHub rename precedes the push is unchanged; only the
comment moves, from before the rename to after it.

### Depth: FULL

**Codex plan round, Codex code rounds to closure, and an Opus `/code-review` pass.**

The owner's reason, recorded because it is the argument for the cost: **the probe proved every gate
is blind to this change, so review is the only thing that can catch a bad rename.**

### The local checkout directory is not renamed

Confirmed, as section 8 recommends. Nine worktrees share one repository, so the remote update is one
command, but renaming the directory breaks ten `gitdir:` pointers at once. Nothing requires it, and
leaving it removes half of probe F7.

### Section 15's first issue is filed

**F4 is issue #248**, filed with the negative control verbatim, so the defect does not depend on
this plan landing. The remaining three issues in section 15 are still to file.
