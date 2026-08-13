# What it means for the PII guard to be finished

This document is the acceptance condition for `pii_guard`. It replaces *"review until a reviewer
finds nothing"* -- which is not a condition anybody can meet -- with eight bounded properties, each
asserted by test.

The distinction matters because the earlier criterion was a universally quantified negative over an
unbounded input space: *no input carrying personal data passes.* A reviewer asked to construct a
bypass against that will construct one indefinitely, and every one will be real. The rounds were
sampling an infinite space, not converging on it. What follows is finite, frozen, and checkable.

⚠️ **Every path in this document is described rather than spelled.** The guard scans everything
committed, this is a document *about a path detector*, and it is therefore the document most likely
to trip it -- which has already happened here more than once: a comment describing the trap sprang
the trap, and a `CONTRIBUTING` section documenting the detectors reported itself. Describe the
construction; do not spell it.

## The eight criteria

### B1

> **A path that identifies a person or a machine is a finding, wherever it appears in committed
> content.** Four detectors: drive-letter/UNC (including extended-length forms), a leading slash
> under a real filesystem root with ≥2 components, any leading slash in a path-bearing position, and
> the tilde home form. Applies to file *contents*, committed *filenames*, and symlink *targets*.

`tests/unit/test_pii_guard_p1_paths.py` -- **38 tests**, the whole file, including the
false-positive controls that keep routes, links, markup and approximations out of it.

⚠️ **That count is the FILE's, and it is not the number of tests carrying B1. Three of the
thirty-eight are evidence for B8**, which constrains what the guard must *not* report --
`test_the_normaliser_folds_a_separator_run_of_any_length`,
`test_every_portable_path_is_allowlisted_however_its_separators_repeat`, and
`test_a_repeated_separator_does_not_allowlist_a_path_that_identifies_somebody`. They live here
because this is the file where the path detectors are exercised, not because they are B1's evidence.
The remaining **thirty-five** carry B1: the four rows below stand for the catch side, and the rest
are the controls that bound it. One of those thirty-five,
`test_a_url_authority_is_not_a_repeated_separator`, is cited by B8 as well, deliberately -- it is a
false-positive control on the detectors B1 names *and* the recorded exception to the fold B8 names.

**The two numbers drift apart silently, which is why the distinction is written down rather than
left to be read off.** A file's count moves whenever a test is added for *any* criterion, so a
number that once matched the criterion's evidence stops matching it without anything announcing the
change -- and a later repair that takes the file's count for the criterion's own then overstates
what the criterion rests on, which is the opposite of what this document is for.

| Detector | Named by |
| --- | --- |
| drive-letter and UNC, including the extended-length spellings | `test_an_extended_unc_volume_path_is_a_finding`, `test_an_extended_drive_path_is_still_a_finding` |
| a leading separator under a real filesystem root | `test_a_repeated_separator_is_the_same_separator` |
| any leading separator in a path-bearing position | `test_a_route_shaped_string_in_a_path_position_is_still_a_finding` |
| the tilde home form | `test_a_bare_named_home_directory_is_a_finding_where_a_path_belongs` |

*Wherever it appears* is a separate claim and is asserted separately, in
`tests/integration/test_pii_guard_over_git.py`: `test_a_path_bearing_filename_is_a_finding` for
committed filenames, `test_a_committed_symlink_target_is_scanned` for symlink targets, and
`test_both_modes_reach_the_same_verdict_on_the_same_name` and
`test_the_two_scanners_agree_about_a_symlink` for the two enumerations agreeing.

The three surfaces reach **one** detector table through **one** line scanner, so this criterion is
derived rather than restated three times. That is why the separator fix
(`test_every_path_spelling_agrees_with_itself_however_its_separators_repeat`) needed no per-surface
work, and why `test_a_url_authority_is_not_a_repeated_separator` records the one place the same rule
deliberately does *not* apply.

### B2

> **A file carrying genealogy data the guard has a property for scores at or above the threshold and
> is a finding, whatever the file is named.** GEDCOM records counted per file; Gramps XML weighted by
> the real-versus-mentioned distinction; GEDCOM X keys gated on a structural marker.

⚠️ **The qualifier *"the guard has a property for"* is load-bearing and is not a hedge.** Without it
this criterion is universally quantified over all genealogy data, which is the unbounded spec this
document exists to replace.

`tests/unit/test_pii_guard_p2_genealogy.py` -- **66 tests**. The crux of each mechanism:

| Mechanism | Named by |
| --- | --- |
| GEDCOM records counted per file, not consecutively | `test_an_annotated_walkthrough_is_a_finding` |
| Gramps XML weighted by real versus mentioned | `test_an_importer_spec_is_not_a_finding` -- the false-positive side is the point of the distinction |
| GEDCOM X keys gated on a structural marker | `test_configuration_json_is_not_genealogy_without_the_format` |
| whatever the file is named | `test_gedcom_renamed_as_text_is_still_caught` |

The two formats are held to one vocabulary by
`test_the_compiled_scorer_agrees_with_the_vocabulary_for_every_row` and
`test_one_life_is_judged_the_same_in_both_formats`.

### B3

> **Content the guard cannot prove safe is refused, not passed.** The file-type gate fails closed: an
> unrecognised type is a finding rather than a pass, and content sniffing runs regardless of
> extension.

The crux is a single test: `test_an_unprovable_file_type_is_a_finding`, in
`tests/unit/test_pii_guard_p2_genealogy.py`. Its companion
`test_the_unprovable_type_finding_says_how_to_allow_the_type` is what stops the fail-closed default
being routed around rather than answered -- the message names the constant to add to.

Sniffing regardless of extension: `test_sqlite_database_is_caught_by_file_magic`,
`test_alternate_encoded_genealogy_is_a_finding`, and -- for the one mode that is exempt from the
extension gate -- `test_non_textual_content_hidden_in_a_symlink_blob_is_a_finding` in
`tests/integration/test_pii_guard_over_git.py`.

### B4

> **The deny-list catches its literals, is never itself published, and following the documented
> workflow leaves the gate passing.** Matches in contents and in filenames, case- and
> normalisation-insensitive; a committed deny-list is a finding at the tip and anywhere in history.

`tests/unit/test_pii_guard_denylist.py` -- **11 tests**.

| Claim | Named by |
| --- | --- |
| catches its literals | `test_denylisted_literal_is_a_finding` |
| in filenames as well as contents | `test_a_denylisted_name_used_as_a_filename_is_a_finding` (over git) |
| case- and normalisation-insensitive | `test_denylist_matching_ignores_case`, `test_matching_survives_unicode_normalisation` |
| never itself published | `test_the_denylist_is_never_scanned_as_content`, plus `test_every_denylist_variant_is_gitignored` over a tree |
| a committed deny-list is a finding at the tip and in history | `test_a_committed_denylist_at_the_tip_is_a_finding`, `test_a_committed_denylist_in_history_is_a_finding` |
| the documented workflow leaves the gate passing | `test_following_the_documentation_leaves_the_command_passing` |

The last of those is the one that makes this criterion honest: a guard whose documented workflow
fails its own gate is a guard people switch off.

### B5

> **No entry point, error path, or rendering route prints a matched value or a scan target.**
> Structural, not per-call-site: the wrapper types, with exactly one audited reveal.

`tests/integration/test_pii_guard_never_prints_secrets.py` -- **10 tests** -- and
`tests/unit/test_pii_guard_reporting.py` -- **17 tests**.

*Structural* is the whole criterion, so the tests that carry it are the ones that enumerate nothing:
`test_no_route_off_a_secret_yields_cleartext` walks every attribute of the wrapper rather than a
hand-written list of routes somebody thought of, and `test_no_route_off_a_finding_prints_its_source_raw`
does the same for rendering. *Exactly one audited reveal* is a pair:
`test_reveal_is_called_in_exactly_one_place` and
`test_a_source_is_rendered_in_full_from_exactly_one_place`.

Entry points and error paths: `test_no_entry_point_prints_a_matched_value` and
`test_no_entry_point_prints_the_scan_target`, both driven over every argument shape the command
accepts.

### B6

> **A scan reports what it actually covered, and never reports clean over nothing.** Coverage is one
> value carrying both the enumeration and the words for it; an empty range, an unresolvable range, or
> an untracked named target is refused, never reported clean.

`tests/integration/test_pii_guard_scope.py` -- **33 tests**, the file exists for this criterion.

The first half is one test: `test_the_scope_word_and_the_count_cannot_disagree`. Coverage being one
value is what makes that assertable at all; two values would need every call site to keep them in
step. `test_the_scan_states_how_much_it_covered` is the reported form.

The second half is three refusals, each with a named test:

| Refused | Named by |
| --- | --- |
| an empty range | `test_a_range_covering_no_commits_is_refused` |
| an unresolvable range | `test_an_unresolvable_whole_history_range_is_refused_not_reported_clean` |
| an untracked named target | `test_an_untracked_file_inside_a_repository_is_refused` |
| a target holding nothing scannable | `test_a_target_holding_no_scannable_file_is_refused` |

### B7

> **Every event that publishes content is scanned, over the range that event publishes.** Push
> (including first push with a zero SHA, and force push), pull request, fork PR, tag push; the job
> refuses a checkout it cannot prove is complete.

`tests/integration/test_repository_hygiene.py` -- **9 tests**, the whole file. The ones this
criterion rests on are asserted by reading the workflow itself rather than by describing it.

⚠️ **Only four of the nine are evidence for B7 — the four named in the table below.** The count is
the file's, as B1's is, and the two numbers are not the same number. The other five assert
neighbouring properties and say nothing about publish events: that every Python source file is
tracked, that no workflow expression is interpolated into a shell body, that every skip names a seam
twin that exists, and — added with the workflow-directory rule — that no path is both untracked and
unignored and that the workflow directory is ignored. They live here because this file is where
repository-shape assertions live.

An earlier revision of this paragraph said *two* of the nine were unrelated, counting only the two
added last. That understated it by three and so overstated what B7's coverage rests on, which is the
opposite of what this document is for.

| Claim | Named by |
| --- | --- |
| no event is scanned at its tip only | `test_no_scan_step_reads_only_the_tip` |
| pull request, including from a fork | `test_every_pull_request_gets_a_history_scan` |
| tag push | `test_a_tag_push_does_not_report_clean_over_a_deleted_ancestor` |
| the job refuses a checkout it cannot prove is complete | `test_the_job_refuses_a_checkout_it_cannot_prove_is_complete` |

⚠️ **The zero-SHA first push and the force push are the thin spot, and this document says so rather
than citing a test that does not exist.** Both are handled in a shell step that resolves the pushed
range, and **no test drives that step directly.** What is asserted is the guard side of the same
guarantee -- that a range covering no commits and a range that cannot be resolved are both refused
rather than reported clean (B6 above) -- together with the blanket
`test_no_scan_step_reads_only_the_tip`. A defect confined to the shell arithmetic would be caught by
those refusals only if it produced an empty or unresolvable range, and not if it produced a range
that is merely too narrow.

### B8

> **The guard's own normaliser reads a run of separators of any length as one join; a location the
> allowlist holds is not a finding under the spellings named below; and this repository reports
> nothing -- at its tip and across the commits it publishes.** The first half is those two claims,
> over the normaliser and over the allowlist constant, asserted to different strengths and kept
> apart below; the second is a measurement of this repository at this commit.

B1–B7 constrain what the guard must **catch**. Nothing constrained what it must **not** report, so a
guard that reported every line in this repository satisfied all seven of them. Over-reporting is a
**security** failure here rather than an ergonomic one, which is what makes this a criterion and not
a preference: *a finding nobody can act on is a finding contributors route around*, and a
routed-around gate protects nothing. The same reasoning is already recorded against widening the
path-component class, against decoding structure escapes, and in the threshold-4 decision -- applied
criterion by criterion in prose, and until now stated as a criterion nowhere.

| Claim | Named by |
| --- | --- |
| a run of separators of any length is one join -- the rule the allowlist comparison is made of | `test_the_normaliser_folds_a_separator_run_of_any_length` |
| every entry of the allowlist, under every combination of short runs plus one long run at each separator position, in each surrounding a detector reads a value from | `test_every_portable_path_is_allowlisted_however_its_separators_repeat` |
| not vacuous: a value the allowlist does **not** hold, in the same surroundings and the same spellings, is still a finding and still reports the whole value | `test_a_repeated_separator_does_not_allowlist_a_path_that_identifies_somebody` |
| the tip reports nothing | `test_this_repository_is_clean` |
| every commit this repository publishes reports nothing | `test_every_commit_this_repository_publishes_is_clean` |
| the range scanner does report when there is something to report | `test_a_blob_deleted_later_in_the_push_is_still_found` |

**The cases are derived, not enumerated** -- from the allowlist constant itself, and from the
normaliser's stated rule that a run of joins is one join. Adding an entry to the allowlist extends
the property's coverage **without the test being edited**, which is the whole point of deriving it: a
test naming three examples is satisfied by three special cases, and the regression that exposed this
gap survived a careful measurement over tracked content precisely because the allowlist's own entries
are not tracked content. The one place the fold deliberately does not apply -- a run that is syntax
rather than a join -- is recorded where the normaliser is, and named by
`test_a_url_authority_is_not_a_repeated_separator`.

⚠️ **An earlier wording of this criterion said *any spelling the normaliser folds*, and that was
more than its tests asserted.** The two claims in the first half are asserted to different
strengths, so they are stated apart rather than carried by one sentence. The normaliser's rule --
one or more separators, with no upper bound -- is a property of a single function rather than a
scan, so it is asserted directly against the fold the allowlist comparison calls, at every separator
position of every entry, at run lengths up to 1024. That is not literally unbounded, and no test is;
it is past anything a narrowing would leave behind. The allowlist half is a **scan**, and its
spellings are a cross-product of run lengths -- exponential in the number of separators, which is
why that bound is small and stays small. It is widened *linearly* instead: one long run at each
separator position in turn, for every entry.

**The residual, stated rather than closed: the allowlist half is a sample of an unbounded space.**
The short-run combinations and the long runs are not crossed with each other, so a fold that failed
only on two long runs at once would pass it. What keeps that a residual rather than a hole is the
claim above it -- the fold is one function, asserted on its own at any length worth naming, and the
allowlist half is what proves the four detectors and the comparison still agree about the value it
produces.

**Measured, rather than argued.** Narrowing the quantifier to short runs -- the regression this
criterion exists to catch -- leaves the suite as it stood before these tests entirely green
(257 passed, 5 skipped, run in a worktree at that commit) and fails exactly the first three rows
above, and nothing else in the suite (3 failed, 255 passed, 5 skipped). The property and its control
fail in opposite directions: a location that identifies nobody starts reporting, and a path that
identifies somebody stops.

The last row is what stops the second half being a formality. A range enumeration that quietly stops
running leaves a zero-findings verdict reading exactly like a clean one, so the commit count is
asserted before the verdict and the scanner is separately proved able to report, over a fixture
repository rather than over this one.

⚠️ **Neither half is a false-positive guarantee, and B8 does not claim one.** The first bounds
respellings of values the allowlist **already holds**; it says nothing about a safe document nobody
has written yet. The second is a measurement of *this* repository at *this* commit, and it asserts
everything reachable from the tip rather than the range any one push publishes -- that arithmetic
lives in the workflow, which is the thin spot B7 states directly above. A closed corpus of
representative safe documents was the third candidate shape considered and was declined: it is the
only one that grows without bound as a fixture-maintenance burden, and a corpus is only ever as
strong as itself.

⚠️ **And the second half does not run in CI today. Stated here rather than left to be discovered.**
The job that runs the suite checks out a single commit, so the history assertion **skips on every
ordinary CI run**; the job that has whole history does not run the suite. So that half is asserted
when the suite runs against a complete checkout -- locally, or anywhere the checkout is not
truncated -- and nowhere else.

What still runs on every push is the guard job itself, over the range the event publishes. That is
not the same claim: it covers what the push publishes rather than everything reachable, and it is a
scan rather than an assertion about one. **The consequence is exact: a detector change that starts
reporting an older reachable commit passes CI.** Closing it is one line of workflow -- give the suite
a complete checkout -- and is deliberately not done here, because this issue's scope excluded the
workflow and a criterion is the wrong place to discover that a change of scope was needed. It is
filed as issue #31, and this paragraph is written to be narrowed when that lands.

What B8 buys is smaller than a guarantee, and it is the thing that was missing: **a widening can be
shown to have cost something.** A change that starts reporting a location the allowlist holds, or
starts reporting this repository, now fails a named test -- rather than being discovered by a
contributor who routes the gate around.

## What this guard does not guarantee

The guard states bounded properties (B1–B8 above), each asserted by test. **It makes no completeness
claim, and the input space it operates over is unbounded.**

Phase 0 ran review rounds across three reviewers until the round count stopped being the useful
question. Every reviewer was instructed to construct bypasses rather than to assess. They produced
**88 findings across nine local rounds**, a further **28 from the pull-request bot across
seventeen**, and more again from the delta rounds that followed. Every one was a real bypass; each is
closed, or recorded here or in the issue tracker. **That is evidence the properties are
load-bearing. It is not evidence there is no next one.** A reviewer asked to construct a bypass
against a universally quantified negative will construct one indefinitely — the rounds were sampling
an infinite space, not converging on it.

The measured boundary of content detection is stated rather than chased: **a single name-fact scores
2 against a threshold of 4.** Three independent rules — the name-part weight, the identity weight,
and the short-prose credit — stop at the same number, because all three are one name-fact. That
ceiling is a property of the weighting, not an artefact of any one rule, so a fourth rule will not
move it. Lowering the threshold to 2 is measured and declined: it makes this project's own importer
specifications unwritable.

**The deny-list is the backstop for anything the properties do not reach.** Named residuals, each
with its rationale and its measurement, are recorded in CONTRIBUTING.md.

## What is deliberately outside the criteria

**Credential detection.** Removed in round 4 after four mechanisms failed. A dedicated secret scanner
is the recorded answer if a later phase handles real credentials; there is no third property, and
writing a fifth mechanism is not the plan.

**Commit-message scanning for the path property** (issue #2). It recreates the documentation
recursion this document is written under: a commit message describing a path fix has to quote a path,
and the path property would catch it. That is friction which gets a gate switched off rather than
obeyed. The coverage line says commit messages are not scanned rather than counting them — a stated
gap, not a silent one.

**A Windows root-relative form, and symlink mode implying a path-bearing position** (issue #3, items
1 and 3). Each is a *new* detector, and new detectors are a later-phase decision rather than a build
activity. Item 2 of the same issue was not: it was an existing detector failing an input already
inside its own stated terms, which is why it was fixed here and these two were not.

**Systematic identity-weighting** across addresses, attribute payloads, GEDCOM prose,
namespace-prefixed XML, and committed pathnames (issue #4). Five instances of partially applying an
already-adopted principle. Recorded as a bounded audit for a later phase — deliberately not as a list
of five entries to add, because adding five entries is what partial application looks like the second
time.

## How Phase 0 was adjudicated

The outstanding set was adjudicated against B1–B7, item by item, and dispositioned four ways:

- **four items violated a criterion and were fixed** — issue #3 item 2, a repeated separator
  defeating the rooted-path detector, which satisfied every term B1 states and was matched by none of
  them; two against B2 in the final bot round, where the prose measurement collapsed a character
  reference in a place XML reads nothing and for a character XML forbids, each shortening a value and
  dropping a prose element below the floor; and one more against B2 in the round after it, where an
  XML comment inside a filled prose element stopped the content pattern reaching its own closing
  tag, so an element carrying a whole identity was not mis-scored but invisible;
- **three were already resolved** by commits on this branch;
- **the remainder were accepted with a recorded rationale**, in CONTRIBUTING.md, or **filed** as the
  issues named above.

**B1–B7 above is not a typo for B1–B8.** Phase 0 closed against those seven as frozen; B8 was added
afterwards, in Phase 1, and did not exist for this adjudication. It came out of it: an item that
violated no criterion, because no criterion constrained what the guard must not report.

The test for whether an item blocked was not its severity and not who found it. It was whether the
input fell inside the stated terms of a property the guard already claims. An input needing a
detector that does not exist is a later-phase decision; an input the existing detector should have
caught is a defect.

**No round count appears anywhere in this document as a pass condition.** That is the point of it. A
count of rounds measures how long somebody looked, and the whole reason Phase 0 did not converge is
that how long somebody looked was standing in for a condition that could be met.
