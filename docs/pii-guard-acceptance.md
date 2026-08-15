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
> is a finding, whatever the file is named -- and its NAME is read the same way.** GEDCOM records
> counted per file; Gramps XML weighted by the real-versus-mentioned distinction, over a container
> list derived from the published schema, with the rows that derivation added gated on a Gramps
> marker in the same file; GEDCOM X keys gated on a structural marker.

⚠️ **The qualifier *"the guard has a property for"* is load-bearing and is not a hedge.** Without it
this criterion is universally quantified over all genealogy data, which is the unbounded spec this
document exists to replace.

⚠️ **"Which containers" is no longer a judgement, and that is what makes the Gramps half closable.**
The list is derived from the published schema and frozen as a committed table -- see the derivation
note in this directory. Every row of that table has a weight and a test, which is finite and
reached; the previous formulation, *every place where a container can hold prose or an identity
field*, was quantified over a format and could not be shown to have been satisfied.

`tests/unit/test_pii_guard_p2_genealogy.py` -- **93 tests**. ⚠️ **That is the FILE's count and not
this criterion's**; see the warning below, which is now on its fourth reason. The crux of each
mechanism:

| Mechanism | Named by |
| --- | --- |
| GEDCOM records counted per file, not consecutively | `test_an_annotated_walkthrough_is_a_finding` |
| Gramps XML weighted by real versus mentioned | `test_an_importer_spec_is_not_a_finding` -- the false-positive side is the point of the distinction |
| the container list is the published schema's, not a reviewer's | `test_every_container_the_published_schema_declares_has_a_weight` |
| a row that derivation added is gated on a Gramps marker | `test_every_spelling_the_derivation_added_scores_once_the_format_is_named` |
| GEDCOM X keys gated on a structural marker | `test_configuration_json_is_not_genealogy_without_the_format` |
| whatever the file is named | `test_gedcom_renamed_as_text_is_still_caught` |
| and the name itself is read | `test_a_committed_name_carrying_a_record_is_a_finding` |

The two formats are held to one vocabulary by
`test_the_compiled_scorer_agrees_with_the_vocabulary_for_every_row` and
`test_one_life_is_judged_the_same_in_both_formats`.

⚠️ **That count is the FILE's, and it is not the number of tests carrying B2. It moves for
reasons this criterion is not about, and it has now moved for four.** Twelve of them
arrived with #4 item 4, which taught the compiled patterns that read an element name to read
a namespace-prefixed tag: **nine** with the two commits that shared one alternation between the four
sites it then had, and **three** more with the commit that replaced the prefix's character class with
the XML `NCName` production, after a review round found that a legal alias containing a combining
mark was missed by every one of them at once. Both are changes to what the matcher can **see**, not
to what B2 claims, and the twelve divide three ways:

| The twelve | What they are |
| --- | --- |
| `test_a_namespace_prefix_does_not_change_what_a_filled_row_scores`, its attributed twin, and `test_a_prefixed_database_element_names_the_format_the_same_way` | **three**, and B2 evidence in the ordinary way -- a prefixed export is the same export. Derived from the vocabulary rather than exampled, so a new row extends them unedited. The `NCName` commit added no test here; it widened these three to quantify over an alias tuple, which is the same reason they are derived rather than exampled |
| the drawing exemption's two directions -- an ordinary unprefixed drawing still exempts its labels, and a container whose prefix this module cannot resolve does not | **two**, and the first half of each of them constrains what the guard must *not* report, which is B8's concern rather than this one |
| the shared alternation's construction: which patterns are built from it and that the drawing is deliberately not, longest-first ordering, `_DRAWING` refusing a prefixed drawing, the namespace fallback still reading a prefixed declaration, and -- from the `NCName` commit -- the production transcribed at every range boundary, the start and continue classes being distinct, and the class matching no markup | **seven**, asserting how the patterns are built rather than what a scan returns. They carry no criterion on their own |

So the twelve are not this criterion growing. What carries B2 is the mechanisms in the table
above and the two agreements beneath it; the number is a file's length, and the file is shared.

**Six more arrived with #4's items 1, 5 and 6-XML** -- the change that derived the container list
from the published schema. Unlike the twelve, **three of these do carry B2**, and the split is worth
stating because it is the opposite of the last one:

| The six | What they are |
| --- | --- |
| `test_every_container_the_published_schema_declares_has_a_weight` and `test_a_committed_name_carrying_a_record_is_a_finding` | **two**, and B2 evidence of a new kind. The first bounds *which containers* this criterion ranges over -- the sentence above is only checkable because that set is finite and external. The second extends the criterion to the committed NAME, which is why the wording above gained a clause rather than keeping the same claim over a bigger table |
| `test_the_address_payload_issue_four_was_filed_with_is_a_finding` | **one**, B2 evidence in the ordinary way, and green on arrival: it re-measures the input #4 item 1 was filed with rather than assuming the item was still open |
| `test_a_spelling_the_published_markup_indexes_also_use_earns_no_weight` | **one**, and it constrains what the guard must *not* report -- **B8's concern rather than this one**, exactly as the drawing rows are. It is what makes a hundred-row vocabulary affordable in a repository full of markup |
| `test_no_spelling_the_vocabulary_already_had_changes_what_it_scores` and `test_no_spelling_is_claimed_by_two_categories` | **two**, asserting properties of the table rather than what a scan returns. The first is the control on the widening -- it is how "this audit adds rows and retracts none" stops being a promise -- and the second was written because a spelling really was placed in two categories, where the later silently won |

⚠️ **The six are why the sentence at the top of this criterion changed, and a criterion whose
wording moves is not a count moving.** Read the claim, not the number.

**Nine more arrived with the marker gate** -- the change that made a container the derivation added
score only where the document names the Gramps format. It exists because some of what the published
schema declares are ordinary XML names: four filled `<type>` elements, or a `<file>`, a `<status>`,
a `<description>` and a `<type>`, reached the threshold in a document about unrelated XML. The nine
divide the same three ways, and **only two of them carry B2**:

| The nine | What they are |
| --- | --- |
| `test_every_spelling_the_derivation_added_scores_once_the_format_is_named` and `test_a_prefixed_document_still_names_the_format` | **two**, and B2 evidence in the ordinary way. The first is what stops the gate being a deletion -- every added row is re-measured, with a marker present, against the weight its category declares, so a gate that simply zeroed those rows would pass the constraint tests and fail this one. The second carries the prefixed-export claim into the gate: a document's private alias must not cost it its own marker |
| `test_generic_xml_names_are_not_genealogy_without_the_format`, `test_a_document_about_unrelated_xml_is_not_a_finding`, `test_every_spelling_the_derivation_added_is_gated_on_the_format`, and `test_a_researcher_block_without_the_format_is_the_gates_recorded_cost` | **four**, constraining what the guard must *not* report -- **B8's concern rather than this one**, exactly as the drawing rows and the markup-collision row are. The first two are the reproductions; the third is the same property derived over the table, so a row a later schema version adds is gated with no test edited. The fourth is the residual, asserted in both directions: the accepted cost is that a genuine fragment quoted *without* its marker is no longer caught, and its second half is the control that the gate removed the unmarked case and nothing else |
| `test_the_attested_snapshot_still_records_the_moment_it_claims_to`, `test_each_marker_the_gate_reads_is_the_one_the_schema_declares`, and `test_the_namespace_the_gate_reads_is_the_default_the_schema_fixes` | **three**, asserting properties of the tables rather than what a scan returns. They carry no criterion on their own. The first pins the membership of the frozen pre-audit snapshot, which is what buys back the independence lost when that snapshot moved into the guard for the gate to read; the other two bind each marker to the source it is derived from, so none of them is a spelling somebody chose |

⚠️ **Two pre-existing tests in this file changed their probe and are not among the nine**, because
they are not new. `test_the_compiled_scorer_agrees_with_the_vocabulary_for_every_row` and
`test_a_spelling_the_published_markup_indexes_also_use_earns_no_weight` -- and the two
prefix-equivalence tests with them -- now measure through a probe that names the format. Without
that they would measure some sixty rows at zero and be asserting the gate rather than the weight.
The invariant-1 test deliberately did **not** change: what it claims is that an attested row still
scores with **no** marker present, and a marked probe cannot see that.

⚠️ **A separate file arrived with the same change and is counted nowhere above.**
`tests/unit/test_derive_specified_containers.py` -- **7 tests** -- asserts the derivation script's
own properties. It carries no criterion here: it is about a build step's fail-closed guarantee, not
about what a scan returns.

⚠️ **The count was UNCHANGED by the fourth site's deletion, and that is a coincidence rather
than evidence nothing happened.** That change removed the test asserting a mismatched-prefix pair is
not a drawing -- the backreference it was about no longer exists, and its input is still reported for
a reason that has nothing to do with the tags disagreeing -- and added the reproduction that deletion
was made for: a prefix bound to a namespace that is not SVG. One out, one in. **A count that did not
move is not a count that was not checked**, and the four rows above were re-read against the file
rather than carried forward.

⚠️ **This is the fifth time a documented count in this repository has gone stale, and the general
repair is filed as #36 rather than built here.** The count is corrected at the change that moved it,
which is the cheapest place; what #36 owes is the mechanism that makes a stale one fail rather than
read as considered. The sixth change to touch this file looked for this number **before** adding a
test to it rather than after, which is the cheap half of that repair available today.

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

`tests/integration/test_repository_hygiene.py` -- **12 tests**, the whole file. The ones this
criterion rests on are asserted by reading the workflow itself rather than by describing it.

⚠️ **Only four of the twelve are evidence for B7 — the four named in the table below.** The count is
the file's, as B1's is, and the two numbers are not the same number. The other eight assert
neighbouring properties and say nothing about publish events: that every Python source file is
tracked, that no workflow expression is interpolated into a shell body, that every skip names a seam
twin that exists, and — added with the workflow-directory rule — that no path is both untracked and
unignored and that the workflow directory is ignored. They live here because this file is where
repository-shape assertions live.

The remaining three are **not** evidence for B7 either:
`test_every_job_that_runs_the_suite_checks_out_whole_history`, added with issue #31, together with
`test_a_comment_cannot_stand_in_for_an_active_fetch_depth` and
`test_a_comment_in_the_with_block_cannot_break_the_check`, which were added to close a fail-open in
that test's own reading of the workflow. B7 is about the guard job's coverage of the events that
publish content; all three are about the job that runs the *suite*, and about whether its checkout is
complete enough for B8's history assertion to run rather than skip. Neighbouring shapes, different
claims — which is exactly the conflation the count paragraph above exists to prevent.

The twelve counts test **definitions**, which is what the names above are. One of them is
parametrized over two workflows, so `pytest` collects thirteen items from the file; that number moves
for reasons this criterion has nothing to do with.

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

**The second half runs in CI, on every push and every pull request.** The gates job checks out whole
history (`fetch-depth: 0`), so the history assertion executes on all three Python legs rather than
skipping, and that shape is itself asserted by
`test_every_job_that_runs_the_suite_checks_out_whole_history`. Until issue #31 it was the other way
round: the job that ran the suite checked out a single commit and the job with whole history did not
run the suite, so **the assertion skipped on every ordinary CI run** and a detector change that
started reporting an older reachable commit passed CI.

It costs a walk of the history on each leg, and **the two costs are an order of magnitude apart, so
the platform has to be named with the number.** Locally the walk measured 34.6 seconds over 74
commits on a Windows development machine. On the runner, at this branch's head, the *whole suite* --
that walk included -- finished in 9.22, 7.96 and 10.61 seconds on the 3.10, 3.11 and 3.12 legs, which
bounds the walk there at roughly ten seconds. **That supersedes the ~1.7 minutes of added runner time
reasoned from the local figure in commit `04b8efe`**, whose message cannot be corrected because it is
already pushed. The reason is recorded rather than invented here: issue #12's cost model has the walk
spawning a `git` process per commit at a measured 32 ms per spawn on Windows, which is a
development-machine tax and not a runner one. ⚠️ **Three legs of one run over a 74-commit repository
is not a benchmark**, and the walk still grows with the history on both platforms.

**What the guard job runs on every push is a different claim, and it stays one.** It scans the range
the event publishes rather than everything reachable, and it is a scan rather than an assertion about
one. This half asserts everything reachable from the tip, which is the superset. Neither subsumes the
other, and that distinction is part of why the gap mattered: a scan reporting clean over what one
push carried never was a statement about the repository.

⚠️ **The residual: this half still fails closed by SKIPPING, not by failing.** It refuses to scan a
checkout it cannot prove complete -- a range scan over commits that were never fetched reports clean
over the part it cannot see -- and names
`test_the_job_refuses_a_checkout_it_cannot_prove_is_complete` as its seam twin. A skip is a report of
*not measured* and is never a clean verdict, so the CI step runs `pytest -rs`: a skip named in the
report can be noticed, and a skip folded into a count is exactly what let issue #31 survive.

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
