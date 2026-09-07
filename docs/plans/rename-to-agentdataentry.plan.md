# Plan: rename the project to `AgentDataEntry`

**Destination path:** `docs/plans/rename-to-agentdataentry.plan.md`. Plan mode confines writes to
the harness plan file, so this document is the plan; copy it to that path at build time.

**Status:** plan only. Nothing was built, no branch was created, no commit was made, the working
tree was not modified, the suite was not run, Gramps was not started, and nothing under
`%APPDATA%` or `.claude.json` was touched. Every command run for this plan was read only.

**Revision 3, 2026-09-07.** Round 2 of the Codex plan gate raised three findings, two blocking, and
one thing larger than all three: **section 6 rested on a property with no fixed point.** Section 6
is rebuilt around a bounded criterion; sections 9, 10, 11, 12 and 18 follow it. Everything else is
unchanged. What changed and why is in section 18, round 2 beside round 1.

---

## Context

The owner has chosen `AgentDataEntry` as the name of the Gramps addon. The project currently
spells itself `gramps-live-api` in 572 places across 106 of 147 tracked files on `main`. Issue #227
is the packaging and install slice, which publishes a name; renaming after publication is expensive
and public, so **the rename comes before #227**. That ordering is the reason this is happening now
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

Section 17 records the owner's answer: the longer name is taken and the seven edits are accepted.

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

The departure is low risk and the reason is measurable rather than argued. **Measured on the
current branch head, with `docs/plans`, `docs/reviews` and `docs/rulings` excluded** (they are not
swept, and this plan document alone sits inside `docs/plans` carrying 80 occurrences of its own,
which is exactly how a docs-wide count goes wrong):

```
                                tests  src  gramps_plugin  scripts  docs  elsewhere
.gramps-live-api-copy               0    2              1        0     9          2
.gramps-live-api-undo               1    2              0        0     8          0
.gramps-live-api-proposals          0    1              0        0     1          0
gramps-live-api/document/1          0    1              0        0     1          0
"gramps-live-api" as a quoted
  string literal                    3    3              1        2     -          -
control: gramps_live_api          200    -              -        -     -          -
```

⚠️ **The exclusion must be spelled `:(exclude)<path>`.** Measured on this box, `:!<path>` was
accepted and **silently excluded nothing**. Any command in this plan that excludes a path is
checked against the same command with the exclusion removed, and the two must differ.

**Two tests, not one, pin a frozen name by writing it as a literal**, and the freeze leaves both
passing untouched:

- `tests/unit/test_host_plugin.py:756`, `tmp_path / ".gramps-live-api-undo"`, a pin on
  `UNDO_DIRECTORY`.
- `tests/unit/test_config.py:209-220`, which creates a literal `gramps-live-api` directory and then
  loads it through `config.load(...)`, which finds it through `config.DIRECTORY_NAME`. That is a pin
  on the state directory name.

The remaining quoted literals are **not** pins on a frozen name and the sweep rewrites them
normally: `tests/integration/test_round_trip.py:320` and `tests/unit/test_cli.py:75` build a fake
**plugin junction** directory under `tmp_path`, which is a different name serving a different
purpose, and `src/gramps_live_api/host/httpd.py:217` (`server_version`) and
`src/gramps_live_api_mcp/server.py:89` (`SERVER_NAME`) are project names, not on disk names.

Nothing else asserts the frozen strings literally, so freezing them is a **smaller** change than
either measured arm rather than a different one. **The build re-runs this table and states it in its
report; it is not carried on this plan's word.**

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

## 6. F11, the records and the historical statements (decision D)

### ⭐ Read this first: the property that was not closing, and what replaced it

Rounds 0, 1 and 2 all rested this section on one property:

> *No statement about the past is falsified by the sweep.*

**That is a universally quantified negative over an unbounded input space.** Two instruments have
been built against it and the review gate has broken both, each time with a genuine instance:

| plan revision | instrument | what the next round found it missed |
| --- | --- | --- |
| 0 and 1 | keyword `grep` piped into a second `grep` | it matched file **paths**, returning 101 lines while the plan claimed 1; it missed `gramps_plugin/gramps_live_api_host.py:827` and `tests/unit/test_host_arming_check.py:3-5` |
| 2 | token scoped: `COMMENT` and `STRING` tokens carrying a past-tense marker | it missed `tests/unit/test_gate_diagnostics.py:91-97`, whose only markers are the plain words `was` and `replaced` |

⛔ **The repair is not a third instrument with two more markers.** The next round finds the third
miss. A reviewer asked to construct a bypass of an unbounded property will construct one every
round, indefinitely, and every one will be genuine.

**And round 2's example shows the marker approach cannot work in principle, not merely in practice.**
`tests/unit/test_gate_diagnostics.py:91-109` needs **four different dispositions inside one
function**, three of them inside one docstring token:

| where | text | disposition |
| --- | --- | --- |
| the docstring's opening sentence | `$env:NAME` is PowerShell-only, and the hint **was** PowerShell-only | present-tense behaviour, swept |
| the same docstring, next sentence | run in bash it expands to `:GRAMPS_LIVE_API_GATE_BASE..HEAD` | present tense about the current hint, swept |
| the same docstring, the quoted git error | `"path 'GRAMPS_LIVE_API_GATE_BASE..HEAD' does not exist"` | a captured observation, arguably frozen |
| lines 104, 107 and 109 | assertion strings that pin the **literal text of `scripts/gate.py`** | swept, or the suite goes red |

No file-level, document-level or marker-level classifier separates those. **The distinction is
semantic and it is per occurrence.**

### ⭐ What replaces it: bound by the sweep's REACH, not by the meaning of the text

The property quantifies over *statements*, which is unbounded. **The sweep does not reach
statements. It reaches occurrences of the old name, and those are countable.** That is the whole
move, and it is what gives this a fixed point: the set of inputs the sweep can possibly falsify is
exactly the set of occurrences it can possibly rewrite.

**Measured on the current branch head, one command, no second `grep`:** the repository holds **652**
occurrences of the old name. They partition, with no occurrence in two classes and none in none:

| class | count today | entry granularity in the build's report |
| --- | --- | --- |
| **P1** prose in the four code trees: every `COMMENT` or `STRING` token in a `.py` file under `src`, `scripts`, `gramps_plugin`, `tests` | **210** in 44 files | **one entry per occurrence** |
| **P2** `scripts/hooks/pre-push`, the only non-Python file in those four trees | **6** | **one entry per occurrence** |
| **P3** markdown outside the three dated directories | **105** in 11 files | **one entry per occurrence** |
| **C1** code tokens in `.py` files: imports, dotted module paths, identifiers | **141** | grouped entries |
| **C2** machine-read files: `.github/workflows/ci.yml` 6, `.gitignore` 2, `pyproject.toml` 1, `uv.lock` 1 | **10** | grouped entries |
| **D** `docs/plans`, `docs/reviews`, `docs/rulings` | **180** | covered by rule 1's set check below, not swept at all |

`210 + 6 + 105 + 141 + 10 + 180 = 652`. **The arithmetic is the completeness proof.**

**The criterion.** Commit 2's report accounts for **every** occurrence on the build's start commit
`B`, exactly once, as `swept` or `frozen`, with a reason. Classes P1, P2 and P3 get one entry per
occurrence, which is **321 individual dispositions across 56 files**. Classes C1 and C2 may be
grouped, because a code token asserts nothing about time and a wrong disposition there changes a
value the interpreter reads, which the gates and the suite observe loudly. Class D is not swept.

**The exit condition, and it is arithmetic rather than a reviewer's silence.**

> The report's entry counts sum to `census(B)`; every P entry names a path and a line; every entry
> carries `swept` or `frozen` and a reason. A reviewer's finding then reads *"entry 137 is wrong"*.

**That has a fixed point.** *"No reviewer can construct a falsification"* does not, and three rounds
have now demonstrated it.

### The cost, stated, and the cheaper boundary that was measured and rejected

**321 hand dispositions is the largest single cost in this plan.** It is recommended anyway:

- A fourth round on this property costs a full plan gate cycle, which is more than 321 report lines.
- Depth is FULL (section 17), so a reviewer reads commit 2's prose diff regardless. The report is
  what makes that reading an audit of a finite list instead of an open-ended re-derivation.
- Most entries are repeats. `tests/unit/test_cli.py` alone holds 55 of the 210.

⛔ **The cheaper boundary was tried and it fails, measured, not reasoned.** Narrowing P1 to comments
and docstrings gives **68** occurrences instead of 210, and it **excludes one of the three confirmed
historical cases**: `src/gramps_live_api/cli.py:37` sits in an **attribute docstring**, a bare string
after the `_PLUGIN_GLOB` assignment, which `ast.get_docstring` does not return and which the narrow
boundary therefore never sees. **A boundary that drops a known defect is not a saving.** The
boundary is `COMMENT` or `STRING`, with no sub-classification.

### The residual, recorded in both directions

⚠️ **The criterion proves every occurrence was judged and recorded. It does not prove every
judgement is right.** That is bounded by review rather than by the criterion, and it is a real
residual, not a rhetorical one. What it buys is that the reviewer's task is now finite: audit 321
recorded judgements, rather than search an unbounded space for a 4th, 5th and 6th bypass.

Two smaller residuals, both measured:

- The instrument sees only files it can tokenize. **The run reports the number of `.py` files it
  tokenized and that number must equal `git ls-files '*.py'` over the four trees**, measured at 106
  today. A silent parse failure would otherwise drop a file with no signal.
- Every count above is calibrated: the tokenizer is re-run with a pattern present in every file and
  with a pattern present in none, and must return a large number and zero respectively.

### The marker list survives, demoted

The past-tense markers (`used to | formerly | was called | no longer | renamed | previously | until |
observed | did not exist | never existed | the first version`) are **a reading order, never a
filter**. They tell the builder which of the 321 to read first. **An occurrence carrying no marker
still gets an entry**, which is precisely what the round 2 miss did not.

**Three confirmed historical cases**, all verified in the tree, all inside class P1, all requiring
`frozen`:

- `src/gramps_live_api/cli.py:37` says `_PLUGIN_GLOB` **used to** name `gramps_live_api_apply.gpr.py`,
  the registration the R9 retirement deleted. Sweeping it asserts the prior existence of a file that
  never existed under any name.
- `gramps_plugin/gramps_live_api_host.py:826-828` records *"Observed as
  `ModuleNotFoundError: No module named 'gramps_live_api_writer'` on the first real request"*.
  Sweeping it makes the source claim an error naming `AgentDataEntry_writer` was observed, which it
  was not.
- `tests/unit/test_host_arming_check.py:3-5` quotes ruling **R4 verbatim**, including the path
  `src/gramps_live_api/host/`. Sweeping it rewrites a quotation.

### Rule 1: the three dated directories, and no classifier at all

> **`docs/plans/`, `docs/reviews/` and `docs/rulings/` are not modified by this change**, except
> that every page in them that carries the old name gains **one identical line** at its top and
> nothing else. They are dated records of work done under the old name. A statement about the past
> that names the old name is true, and rewriting it makes it false.
>
> **One dated paragraph is added to `README.md`**, recording that the project was called
> `gramps-live-api` until the rename, **which names changed and which did not**, and that every
> document in those three directories describes work done under that name and is left as written.

**The set is derived by the sweep's own pattern, not by a classifier:**

```
git grep -l -I -i -E -e 'gramps[-_. ]?live[-_. ]?api' \
  -- docs/plans docs/reviews docs/rulings \
     ':(exclude)docs/plans/rename-to-agentdataentry.plan.md'
```

**Measured today: 18 files.** Control, the same command with the exclusion removed: 19. The three
directories hold 22 files, so three carry no occurrence and get nothing
(`154-prior-events-in-the-dialog`, `176-full-name-search`, `preview-write-agreement`). This plan's
own page is excluded by path, mechanically and for a stated reason: on that page the old spelling is
the subject of the mapping in section 3, not stale guidance.

**The line each of the 18 gets, and nothing else:**

> ⚠️ **Written before the project was renamed to `AgentDataEntry`.** Apart from this line the page
> is left as it was written; `README.md` records which names the rename changed and which it did not.

It is **one claim, written eighteen times**, not eighteen claims. It names no old spelling, so it
adds nothing to the census. It is true on every page in those directories. And it does **not** tell
the reader to substitute the new name everywhere, which would be false on
`docs/rulings/README.md:26`, whose single occurrence is the frozen `.gramps-live-api-copy`.

### ⛔ Why the derivation was retired, which is round 2's blocker 1 made impossible

Revision 2 selected the bannered pages with a `git grep --all-match` over the project's
self-declaration convention (`not built`, `plan only`, and four more), returning five documents.
**`docs/rulings/R3-injection-under-live-reads.md` matches none of those phrases**, yet its header is
a live STATUS block that says *"the code matches it"* and cites
`src/gramps_live_api/host/reads.py`, a path commit 1 moves. Its body, from 2026-08-21, is a record.
**One document, both kinds**, and the STATUS block was added after the ruling.

That is the same failure as round 1's blocker in a different directory, and the shape is the point:
**a per-document classifier keeps meeting documents that are not one kind.** So the classifier is
removed rather than widened. Under rule 1, R3 gets a banner because it is in the directory and
carries the name. **There is nothing left to misclassify.**

**A path-reference derivation was considered and rejected, measured.** Deriving the set from
citations of a path commit 1 moves returns **12 of the 18** (control without the exclusion: 13). It
saves six one-line insertions at the price of a fourth classifier on the same property, and it is
blind to live guidance carrying no path: `docs/plans/shippable.plan.md` prescribes
`python -m gramps_live_api_mcp` and `uvx --from "gramps-live-api[mcp]"`, neither of which is a path.
**When total coverage costs six extra lines that falsify nothing, deriving a subset buys nothing and
costs another instrument.**

### Why a banner and not sentence surgery, decided on rows rather than preference

`docs/plans/shippable.plan.md` carries the old name on **13 lines, 15 occurrences**, and they split:

| class | lines | rewriting them would |
| --- | --- | --- |
| instruction or source citation | 73, 78, 126, 127, 131 | fix live guidance |
| record of something observed | 44, 94, 118, 122, 218, 295, 297 | **falsify a captured traceback, a recorded `uvx` failure, a recorded distribution name, a recorded MCP registration, and a dated PyPI probe result** |
| frozen and already correct | 37 (`%APPDATA%\gramps-live-api\config.json`) | break a correct path |

Correcting the five would mean deciding, line by line, which of thirteen is which, in the one
document where it is hardest, and it writes five new claims into a page #227 will rewrite wholesale.
**One banner is one claim and falsifies nothing.**

**The trade, recorded in both directions.** A banner is weaker than a rewrite: a reader who skips it
still types `python -m gramps_live_api_mcp`. A rewrite is stronger on those five lines and wrong on
seven others. The banner is chosen on that measured split, and it is reversible: if #227 rewrites
`shippable.plan.md` it corrects those five lines as part of its own work, with the banner as its
notice.

**Rule 1 also makes both of the probe's measured falsifications impossible rather than repaired:**

- `docs/rulings/R8-channel-architecture.md:203` records a raw log under the old state directory
  name, a file the probe verified exists under that name. Untouched, so still true. (It is also
  covered twice over, since the state directory name is frozen.)
- `docs/rulings/README.md:26`, the single line revision 0 rewrote in that file, names
  `.gramps-live-api-copy`, which is frozen. That file gets the banner line and **zero other edits**.

### Rule 2: everywhere else, every occurrence gets an entry

Classes P1, P2, P3, C1 and C2 above. The instrument for P1 is run from a heredoc as a measurement;
**nothing is committed**, this is not a shipped script:

> Tokenize every `.py` file under `src`, `scripts`, `gramps_plugin` and `tests` with the standard
> library's `tokenize`. Take every `COMMENT` or `STRING` token whose text carries the old name, and
> emit one row per **occurrence** inside it, with its path and line. Report the number of files
> tokenized.

**P3 is new in this revision and it closes a gap no round has reached yet.** The 105 markdown
occurrences outside the three dated directories are a genuine mix, verified by reading them:
`docs/phase1-core-schema.spec.md:5` says *"What shipped is in `src/gramps_live_api/core/`"*, a live
path citation that must be swept, while `docs/roadmap.md:69`, `:117`, `:216`, `:218` and `:355` name
`.gramps-live-api-copy` and `.gramps-live-api-undo`, which are frozen. Section 10's residual classes
covered the frozen ones; nothing covered the **swept** ones one by one, and prose is exactly where a
record hides.

**The 6 occurrences in `scripts/hooks/pre-push` (class P2)** were checked by eye for this plan and
are all six current instructions, none historical. They still get six entries; a check by eye that
leaves no row is not a disposition.

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

⚠️ **Step 2 is superseded by section 17**, which moves the #220 comment to after the rename. The
sequence as amended is in section 17 and it governs. Everything this section argues about why the
GitHub rename precedes the push is unchanged.

**Why the GitHub rename goes before the push and not after the merge.** Putting it after the merge
means that between merge and rename the merged code's slug names a repository that does not exist,
and about 20 user facing documentation links 404. Putting it before means `pr_ready.py` is only ever
invoked from the branch, where it already carries the new slug, and only after GitHub already
answers to that slug. **That ordering makes the question of whether GitHub's GraphQL API follows
rename redirects moot, which is better than answering it**, since the answer is not something this
plan can pin.

**The window this leaves, stated:** between the GitHub rename and the merge, the nine other worktree
branches carry the old slug in `pr_ready.py` and it will fail against a repository that no longer
answers to that name. Those branches are paused for the duration. That is the whole cost and it
falls on the conductor, loudly, not on a user, silently.

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
creating the new one. That is one added sentence in a file already changing, and it is one of the
occurrences the build itself adds to the census (section 10, class 5).

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

⛔ **This plan does not post it, does not touch #220's branch, and runs nothing from it.** Section 17
rules that the wording goes to the owner for approval and the comment is posted **after** the
repository rename lands.

⚠️ **The draft carries two tenses on purpose, and that is what round 2's finding 3 actually
requires.** At section 17's amended step 4 the **repository** rename has happened, but the branch
has not been pushed and the **code** rename has not merged. A draft written as though everything
already happened would be wrong in the other direction.

> I have renamed this repository from `gramps-live-api` to `gramps-agent-data-entry`. GitHub
> forwards the old address, so this pull request and its link keep working, and your fork keeps its
> own name, so the `origin` remote you push to needs no change.
>
> One more change is still coming, and I am sorry for the disruption it causes here. The code
> itself is being renamed to match, on a branch that has not merged yet:
>
> 1. `src/gramps_live_api/` becomes `src/gramps_agent_data_entry/`, `src/gramps_live_api_mcp/`
>    becomes `src/gramps_agent_data_entry_mcp/`, and `gramps_plugin/gramps_live_api_writer.py` gets
>    a new filename. Three of the five files in this pull request are among them, so it will need a
>    rebase once that branch merges. The first commit on it is file moves only, with no content
>    changes, which is the case git handles best. If you would rather not do the rebase, say so and
>    I will do it for you.
>
> 2. If you have a second remote pointing at this repository, often called `upstream`, you can point
>    it at the new address now with:
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

### The census, in four parts

⛔ **Round 1 killed the round-0 equation and it deserved it.** It read `rewritten + residual == 572`
against a baseline taken on `main`, while this plan document itself adds occurrences the section 6
rules then keep. **A correct build could not have satisfied it.** What replaces it uses a
branch-head baseline **and** carries an explicit term for what the build adds.

**The instrument.** One `git grep`, no second `grep`, so no path can be mistaken for content:

```
git grep -I -o -i -E -e 'gramps[-_. ]?live[-_. ]?api' <rev> -- .   |  wc -l
```

`-o` prints one line per match **in the line content**; the `<rev>:<path>:` prefix contributes
nothing. Verified with a control: over `docs/plans/note-types.plan.md`, whose **path** contains
`note-types`, the pattern `note-types` returns 0, while the pattern `note` returns 151, exactly the
count from the file body alone.

**(a) The baseline is the head the build starts from, recorded before commit 1.**

```
git rev-parse HEAD        -> record B, copied from the command output, never typed
<the census command>      -> record census(B)
```

⚠️ **Measured on the current branch head, `census(B)` is 652, and it was 636 one revision ago.**
The difference is this page: it carried 64 occurrences at revision 1 and carries 80 at revision 2.
**It moves again when this revision is committed, which is exactly why the builder measures it and
this plan asserts no value for it.**

**(b) The equation, which is arithmetic over the build's own diff and cannot fail for the reason the
old one did:**

```
census(HEAD)  ==  census(B)  -  removed  +  added
```

```
removed = git diff -U0 --find-renames $B HEAD -- . | grep -E '^-'  | grep -v -E '^---'   \
            | grep -o -i -E -e 'gramps[-_. ]?live[-_. ]?api' | wc -l
added   = git diff -U0 --find-renames $B HEAD -- . | grep -E '^\+' | grep -v -E '^\+\+\+' \
            | grep -o -i -E -e 'gramps[-_. ]?live[-_. ]?api' | wc -l
```

`removed` is what the old equation called *rewritten*. `added` is the term it had no place for.

⚠️ **The two `grep -v` filters are load bearing:** a unified diff's `--- a/src/gramps_live_api/...`
and `+++ b/...` headers are path text on lines beginning with `-` and `+`, and without the filters
they are counted as content.

**Verified on this repository before it was written down.** Over `main..HEAD` the identity gives
`572 - 0 + 80 = 652`, matching the direct census. Over `main~80..main` it holds for the same pattern
(`45 - 9 + 536 = 572`) and for two unrelated controls, `def ` (`571 - 123 + 1550 = 1998`) and
`import` (`186 - 47 + 1050 = 1189`). It is path independent and holds whether git reports a move as
a rename or as a delete plus an add.

**(c) ⭐ Every occurrence on `B` is accounted for exactly once. This is section 6's exit condition
and it is the criterion this plan turns on.**

The builder lists every line of

```
git grep -I -n -i -E -e 'gramps[-_. ]?live[-_. ]?api' $B -- .
```

and produces a report in which **every occurrence appears exactly once**, marked `swept` or
`frozen`, with a reason. Granularity by class, per section 6:

| class | granularity | today |
| --- | --- | --- |
| P1 prose tokens in `.py` under the four trees | **one entry per occurrence**, path and line | 210 |
| P2 `scripts/hooks/pre-push` | **one entry per occurrence** | 6 |
| P3 markdown outside the three dated directories | **one entry per occurrence** | 105 |
| C1 `.py` code tokens | grouped | 141 |
| C2 `ci.yml`, `.gitignore`, `pyproject.toml`, `uv.lock` | grouped | 10 |
| D `docs/plans`, `docs/reviews`, `docs/rulings` | not swept; the set check below is its criterion | 180 |

**The entry counts must sum to `census(B)`.** ⚠️ **No occurrence may be dispositioned as
"reasonable"; every one carries a reason.** The tokenizer run reports how many `.py` files it
tokenized and that must equal `git ls-files '*.py'` over the four trees, 106 today, so a parse
failure cannot silently drop a file.

**(d) The residual on `HEAD` still falls into named classes.** Every line of the same command run on
`HEAD` is in exactly one of:

1. anything in `docs/plans/`, `docs/reviews/` or `docs/rulings/` (section 6 rule 1);
2. a frozen tree-local name (`-copy`, `-undo`, `-proposals`, `JOURNAL_FORMAT`) or documentation
   describing one (section 4);
3. the state directory name, its two `DIRECTORY_NAME` constants, and documentation naming that path
   (section 4);
4. an occurrence frozen by section 6 rule 2, each one already carrying its entry from (c);
5. **an occurrence the build itself added**, listed line by line. Predicted, and the whole predicted
   list: the `README.md` rename note, which now also names the frozen on-disk names, and the
   `docs/using.md` old-junction line. The 18 banner lines add none, by construction. **If `added`
   exceeds this list, the excess is reported before it is accepted.**

**What the residual is predicted to be, and it is a prediction.** Outside the three dated
directories, the four frozen tree-local names account for **29** occurrences today (copy 14, undo 11,
proposals 2, `JOURNAL_FORMAT` 2), and the state directory path, its two constants and the section 6
exclusions account for the rest. Inside those three directories the census is **180** today and the
build does not change it. **The total is measured and reported by the builder, never asserted here.**

### The records stay records, and this is checkable as a set

```
git diff --name-only $B HEAD -- docs/plans docs/reviews docs/rulings
```

must return **exactly** the set section 6 rule 1's command returns on `B`, measured today at 18, and

```
git diff --numstat  $B HEAD -- docs/plans docs/reviews docs/rulings
```

must show **1 insertion and 0 deletions on every row**. A banner is one inserted line. Any deletion
in those three directories is sentence surgery leaking in, and it fails the criterion. Any row with
more than one insertion is a second claim, and it fails too.

### The freeze, measured rather than inherited (section 17)

- Re-run section 4's component table on the branch head, with the three dated directories excluded
  **using `:(exclude)`**, and check the excluded count against the same command with the exclusion
  removed. `:!` silently excludes nothing on this box.
- Report the actual full-gate result for the frozen state, both legs, as a measurement of a
  configuration no probe arm executed.
- Confirm that **both** literal pins still reach their constant and still pass untouched:
  `tests/unit/test_host_plugin.py:756` on `UNDO_DIRECTORY`, and `tests/unit/test_config.py:209-220`
  on `config.DIRECTORY_NAME`.

### The rest

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
| 2 | the content sweep | packages, distribution, slug, env prefix, plugin id, `fname`, display name, `SERVER_NAME`, `HOOK_MARKER`, `_PLUGIN_GLOB`, `PLUGIN_FILES`, `HOST_IMPORT`, `REPOSITORY`. **Excludes** every frozen name, all of `docs/plans|reviews|rulings`, and every occurrence section 6 rule 2 marks `frozen` |
| 3 | `ruff format .` plus the one hand edit | the 5 files of F2 and the string literal of F1 |
| 4 | `glapi` to `gade` | 2 files, 6 occurrences (F12) |
| 5 | the F4 sentinel pin, plus docstrings on the frozen constants saying they are frozen and why | new test, comment only edits to the constants |
| 6 | the `README.md` dated note, the `docs/using.md` old junction line, and one banner line at the top of each page section 6 rule 1's command returns | 2 files plus the derived set, measured today at 18 |

**Commit 2's report is section 10(c)'s report, and it is the criterion.** It accounts for every
occurrence on `B` exactly once, one entry per occurrence for classes P1, P2 and P3, grouped entries
for C1 and C2, entry counts summing to `census(B)`. **The sweep is not reviewable without it**, and
this is the largest single piece of work in the build.

Commit 5's docstrings are load bearing, not decoration. A narrowing can be misread as licence to
revert what preceded it: a frozen constant with no recorded reason reads to the next reader as an
occurrence the sweep missed. **Each frozen constant says, in one line, that its value names
something already on disk and is deliberately not swept.** The docstring does not repeat the value,
which is already on the line above it, so it adds nothing to the census.

Commit 6's banner is one line per file and deletes nothing, which is what makes the set check in
section 10 sharp.

---

## 12. The one question, applied to this plan

**Would following this plan produce something you could show breaking?** Fifteen candidates were
tried: ten from round 0, three added by revision 2, and two more created by this revision. Fourteen
are dismissible with a named reason. One is not, and it is stated as the plan's live risk.

Dismissed, with the reason:

- *Frozen sentinel drifts across its three spellings.* Commit 5's pin makes it red on the core leg.
- *A fresh user meets `%APPDATA%\gramps-live-api\` under a project called Agent Data Entry.*
  Confusing; `check` names the exact path; nothing breaks.
- *`_PLUGIN_GLOB` no longer finds the existing junction.* It does: the junction points at the same
  directory, which now holds `AgentDataEntry.gpr.py`. The doctor reports `plugin: ok` under the old
  junction name.
- *A user following the rewritten `docs/using.md` gets two junctions.* Commit 6's added line.
- *A test asserts a frozen literal and the sweep breaks it.* Measured, and the count is **two**, not
  one: `test_host_plugin.py:756` and `test_config.py:209-220`. The freeze means the sweep reaches
  neither, and both keep acting as pins.
- *A saved environment override is silently dropped.* Measured: no `GRAMPS_*` variable is set
  persistently on this machine.
- *`pr_ready.py` runs against a repository that does not exist.* Section 7's ordering makes it
  unreachable within the branch, and names the branches that are paused.
- *#220's contributor loses their remote.* Measured: their `origin` is their own fork, which is not
  renamed.
- *A dated record is falsified.* Section 6 rule 1 means no page in those three directories has a
  sentence edited at all, and section 10's `--numstat` check makes 1 insertion and 0 deletions per
  row a criterion rather than an intention.
- *The census criterion cannot be satisfied by a correct build.* True of round 0 and the reason the
  equation changed. The replacement is arithmetic over the build's own diff, verified on two ranges
  of this repository's history with three patterns, and it carries an explicit `added` term.
- *A page in those directories carries live guidance and gets no banner, so the guidance breaks.*
  **Round 2 showed this happening at `docs/rulings/R3`, and revision 2's fix was a derivation
  regex.** The derivation is gone. Every page in the three directories that carries the old name
  gets the banner, so there is nothing left to classify and nothing left to miss. Revision 2's
  companion argument here, that every unbuilt-but-undeclared page is already built, is withdrawn as
  no longer load bearing; it also contained an error, since `176-full-name-search.plan.md` carries
  no occurrence of the old name at all and was never in the set.
- **New.** *A statement about the past is swept, and a source file then asserts a false record.*
  This is what three rounds have been about. The instrument is retired and replaced by an accounting
  over the sweep's reach: every one of the 652 occurrences on `B` is dispositioned exactly once, 321
  of them individually. **The named input would now have to be an occurrence that has a written
  disposition and the disposition is wrong**, which is a claim about a member of a finite list and is
  what the reviewer's next round should audit.
- **New.** *A record hides in markdown outside the three dated directories, where no round has
  looked.* Checked rather than reasoned: 105 occurrences in 11 files, and they are genuinely mixed,
  with `docs/phase1-core-schema.spec.md:5` a live path citation and five lines of `docs/roadmap.md`
  naming frozen on-disk names. They are class P3 and get one entry each.
- **New.** *The bounded criterion is too expensive to execute, so the build silently does a cheaper
  thing.* The cost is stated in section 6 as 321 dispositions and the entry-count arithmetic makes a
  short report fail rather than pass quietly. The cheaper boundary was measured and rejected because
  it drops `cli.py:37`.

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
- **Correcting the five instruction lines inside `docs/plans/shippable.plan.md`.** Section 6 records
  why the banner is taken instead, and #227 owns that page.

---

## 15. Issues to file (not fixed here)

One issue per finding, each quoting the probe verbatim; none folded into another. **All four remain
to file.**

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

All five are answered in section 17. They are kept here because the answers are only readable
against the questions.

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
files of how few tests assert a frozen string as a literal.

**The build MEASURES it rather than inheriting it.** Added to section 10:

- Re-run the component counts in section 4 on the branch head and report them, with a positive
  control in the same command shape.
- Report the actual full-gate result for the frozen state, both legs, as a measurement of a
  configuration no probe arm executed.
- Confirm that **both** literal pins still reach their constant and still act as pins:
  `tests/unit/test_host_plugin.py:756` on `UNDO_DIRECTORY`, and `tests/unit/test_config.py:209-220`,
  which creates a literal `gramps-live-api` directory and loads it through `config.DIRECTORY_NAME`.
  Round 0 of this plan said one test; there are two.

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

### F4 is filed as an issue; section 15's four remain

**F4 is issue #248**, filed with the negative control verbatim, so the defect does not depend on
this plan landing. **F4 is not one of section 15's items**, because this plan fixes it (section 5).
**All four of section 15's issues remain to file.** Round 0 of this plan said three remained, which
was the conductor's arithmetic error, not a decision; following it would have left one issue unfiled.

---

## 18. What each review round changed

### Round 1, 2026-09-06: five findings, three blocking, all dispositioned fixed

Nothing in section 17 was decided differently; only its two factual errors were corrected.

| finding | disposition |
| --- | --- |
| **P1** the census equation cannot pass honestly, because this page adds occurrences the section 6 rule keeps | **Fixed**, section 10. Baseline moves to the build's start commit, measured not asserted; the equation gains an explicit `added` term computed from the build's own diff; a residual class covers what the build adds, listed line by line. Verified against three patterns on two ranges of this repository's history. |
| **P1** the directory-as-unit rule freezes live guidance: `shippable.plan.md:126` prescribes `python -m gramps_live_api_mcp` | **Fixed**, section 6, and **re-fixed in round 2** by a different mechanism. Round 1's fix was a carve-out derived by `git grep --all-match` over the project's self-declaration convention, returning five documents. Round 2 broke it; see below. |
| **P2** the single historical exception is not single, and its deriving command matches paths | **Fixed**, section 6, and **replaced in round 2**. The command was returning 101 lines as written and 3 with content-only matching, against a claim of one. The token-scoped instrument that replaced it was itself broken by round 2; see below. |
| **P3** the freeze check misses `tests/unit/test_config.py:209-220` | **Fixed**, sections 4, 10, 12 and 17. Two tests pin a frozen literal, not one, and both are named. Section 4's table is re-measured on the branch head with `:(exclude)`, and the two quoted literals that are **not** pins are named too. |
| **P3** section 17's closing paragraph says F4 was filed from section 15 and three remain | **Fixed**, section 17. F4 is #248 and was never one of section 15's four items. All four remain to file. |

### Round 2, 2026-09-07: three findings, two blocking, and one structural change larger than all three

| finding | disposition |
| --- | --- |
| ⭐ **the property, raised above the findings** *"No statement about the past is falsified by the sweep"* is a universally quantified negative over an unbounded input space and is not closing | **Bounded**, section 6, and this is the revision's main change. The property is replaced by an accounting over **the sweep's reach**: the sweep can only rewrite occurrences of the old name, there are 652 on the current head, and every one is dispositioned exactly once, 321 of them individually. The exit condition is arithmetic (entry counts sum to `census(B)`) rather than a reviewer's silence. The cheaper boundary was measured and rejected: comments-and-docstrings gives 68 instead of 210 and **excludes `cli.py:37`**, an attribute docstring and one of the three confirmed cases. The residual is recorded: the criterion proves every judgement was made and recorded, not that each is right. |
| **P1 BLOCKER** R3 is both a record and current guidance, and the carve-out sees neither | **Fixed**, section 6 rule 1, structurally. The self-declaration derivation is **retired**, not widened. Every page in the three dated directories carrying the old name gets one identical banner line: 18 files today, control 19 without the exclusion. R3 is in the set by construction. The path-reference alternative the reviewer suggested was measured at 12 of 18 and rejected: it saves six lines and costs a fourth classifier, and it is blind to live guidance carrying no path. The banner wording was also corrected so it does not instruct a blanket substitution, which would be false on `docs/rulings/README.md:26`, whose only occurrence is frozen. |
| **P2 BLOCKER** the marker instrument misses `tests/unit/test_gate_diagnostics.py:91-97` | **Fixed by the bound above, not by a third marker list.** That span is now shown in section 6 as the reason marker-guessing cannot work: it needs four dispositions inside one function, three of them inside one docstring token, including three assertion strings that pin the literal text of `scripts/gate.py` and go red if they are **not** swept. It is one of the 321 individual entries. |
| **P3 FIX REGRESSION** the #220 draft still opens "I am about to rename" after the posting step moved | **Fixed**, section 9, and the tense is checked against section 17's amended step 4 rather than flipped wholesale. At that step the **repository** rename has happened but the **code** rename has not merged, so the draft carries both tenses. The exact `git remote set-url` command, the plain wording and the offer to do the rebase are kept. |

**Also corrected in this revision, not raised by either round:**

- **A gap in class coverage nobody had reached.** 105 occurrences in 11 markdown files outside the
  three dated directories were only covered by residual classes, never dispositioned one by one, and
  they are genuinely mixed: `docs/phase1-core-schema.spec.md:5` is a live path citation and five
  lines of `docs/roadmap.md` name frozen on-disk names. They are now class P3.
- **Stale census figures.** `census(HEAD)` is **652**, not 636, and this page carries **80**
  occurrences, not 64; both moved when revision 2 was committed and both move again with this one.
  The identity re-verifies: `572 - 0 + 80 = 652`.
- **Section 12's withdrawn bullet.** Revision 2 argued that every plan document not declaring itself
  unbuilt is already built, and listed `176-full-name-search.plan.md` among them. That file carries
  no occurrence of the old name at all and was never in the set. The bullet is withdrawn rather than
  corrected, because rule 1 no longer depends on the claim.

**Two method notes, recorded because each cost a wrong measurement here and will cost another later:**

- **`:!<path>` was accepted and silently excluded nothing** on this box, where `:(exclude)<path>`
  worked. Every exclusion in this plan is checked against the same command with the exclusion
  removed, and the two must differ.
- **A `git grep` piped into a second `grep` matches the file path as well as the line content**,
  which is how a count of 1 was really a count of 101. No command in this plan pipes one grep into
  another.
