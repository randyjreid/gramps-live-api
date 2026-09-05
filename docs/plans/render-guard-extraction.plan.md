# Plan: extract the render guard to the document route (#228)

## Context

`core/schema.py` holds the project's only implementation of the render guard: the refusal of
any character that can reorder or hide part of the sentence a person reads and approves before
anything is written to a tree. It was written for the retired note flow's `preview`. On `main`
at `afae92a` the guard is uncalled (nothing in src, scripts, or tests imports `core/schema.py`;
the operation registry inside it is empty) and untested (the retirement deleted
`tests/unit/test_schema_preview_guard.py`, 642 lines, 24 tests, whole; the gate is green with
the guard fully broken). Meanwhile the document route, the only write path an agent can reach,
renders its approval sentence with no character refusal at all.

This plan moves the guard to a module the document route imports, wires it at that route's
rendering seam, re-derives the deleted property tests from what the document route declares,
answers the `_note_type_unknown` question, and deletes the rest of `core/schema.py`.

## Findings that shape the plan (verified on main)

- **The document route HAS a single rendering seam.** `document.preview(graph, resolution)`
  (`src/gramps_live_api/host/document.py:1240-1710`) is the one function that renders the
  approval sentence. Both approval-time call sites go through it: the dialog
  (`gramps_plugin/gramps_live_api_host.py:640`) and the journalled approved text (`:669`).
  `caller_preview` is agent-facing and by its own docstring "not the approval surface".
- Nothing imports `core/schema.py`. Deleting it breaks no import; R9 predicted exactly this
  end state ("After the retirement nothing surviving imports `core/schema.py`").
- The frozen table `core/_unrenderable.py` (Unicode 17.0.0, digests pinned), its generator
  `scripts/derive_unrenderable.py`, and `tests/unit/test_derive_unrenderable.py` survive in
  substance; only the generated docstring's consumer sentence ("and ``schema.py`` imports it")
  goes stale.
- The document route declares its fields in one place: `NODE_KEYS`
  (`src/gramps_live_api/host/document.py:443`). That replaces the retired operation registry as
  the derivation source for the property tests.
- `preview`'s own machinery inserts only spaces, `=`, `-`, U+00B7 and the final `"\n".join`;
  `_wrap` (document.py:1113) splits payload text on `"\n"` first and textwrap's defaults
  replace `\t`, `\r`, `\x0b`, `\x0c` with spaces. So no element of the renderer's output list
  legitimately contains a class character, including U+000A.
- `preview(parsed, None)` neither crashes nor elides payload text: with no resolution every
  node renders under CREATING NEW or ALSO WRITTEN with all payload strings intact, so an
  unresolved call scans a SUPERSET of what the approval dialog will show. ⛔ **That
  superset is why the propose-time gate was removed rather than why it was safe.** See the plan
  change below. The guard runs only where a resolution is in hand.
- An exception raised inside the plugin's approval path is caught by the broad
  `except Exception` at `gramps_plugin/gramps_live_api_host.py:775`: fail closed, nothing
  written, owner told the write failed.

## What moves

New module `src/gramps_live_api/core/render_guard.py`, importing `core/_unrenderable.py`
unchanged. It receives, from `core/schema.py`:

- the design-rationale comment block (schema.py:1560-1673: the costs to legitimate script
  data, the implicit-reordering non-goal, the Unicode 17.0.0 pin and its two prices), moved
  whole with only path references updated;
- `_RANGE_STARTS` (schema.py:1676) and `_class_of` (schema.py:1685), the latter made public as
  `class_of` since the new consumer lives in another package;
- a fresh exception `UnrenderableTextError(label)` replacing `UnrenderableFieldError`. It
  keeps the rule that the message names the published fact (`Cc`, `Cf`, `Cs`, `Co`,
  `Default_Ignorable_Code_Point`) and NEVER the character or any payload value. It drops
  `field_path`: the document renderer has no per-fragment provenance, and its `SchemaError`
  base dies with schema.py. The label rides as an attribute for tests;
- a new `refuse_unrenderable(lines: Sequence[str]) -> None`: scan every character of every
  line, raise on the first that `class_of` labels, no characters skipped. This replaces the
  fragment-based `_refuse_unrenderable`/`_emitted` pair, which is meaningless without
  `Fragment` and dies with schema.py.

Not moved: `Fragment`, `_emitted`, `_is_unrenderable` (trivial; tests call
`class_of(c) is not None`), `preview`, `full_display`, and everything else in schema.py.

## Where it is wired

1. **Enforcement seam: inside `document.preview`, immediately before the `"\n".join(out)` at
   document.py:1710**, as `render_guard.refuse_unrenderable(out)` over the assembled lines.
   Per-line scanning with no carve-out is deliberate: the renderer never puts U+000A inside a
   line (all appends are single lines; `_wrap` splits multiline note text into separate lines
   first), so a legitimate multiline note passes, while a payload newline smuggled through a
   raw f-string field (e.g. `people[0].given = "Alpha\n  I9990  Beta Example"`, which would
   forge a dialog line) is refused as the Cc character it is. This one seam covers the dialog
   and the journalled approved text at once, and a field added to the renderer later is
   covered without the guard being edited, which is the doctrine the guard's own comment
   states.
2. Approval-time refusals (possible only from tree-read display text or a proposal stored
   before this change) land in the plugin's existing catch-all at
   gramps_live_api_host.py:775: fail closed, nothing written.

## ⛔ PLAN CHANGE, owner approved 2026-09-05: the propose-time gate is REMOVED

**One wiring point, the rendering seam. The agent-facing gate above is deleted from this plan.**

The finding that removed it, from the Codex plan review round, quoted verbatim:

> **[P2] Gate only the resolved approval rendering** BLOCKING. For a valid graph that attaches
> found person `I0001`, sets the dropped `given` field to `Al` + `chr(0x200B)` + `pha`, and
> creates a source/citation, this unresolved call classifies the person as CREATING NEW and
> emits `given`, producing a `ToolRefusal` naming `Cf`. The actual approval render with a found
> `Resolution` emits the safe tree display and only names `given` as NOT applied; the writer
> ignores its value. The wrong output is therefore a refusal instead of a stored proposal,
> changing the guard from checking the approved sentence into rejecting an unrendered field.

Verified in source before the change: `preview` builds `creating_people` as the people whose id
is not in `resolved`, so with no resolution every person is classified as being created and its
full payload renders, while the `dropped_fields` branch never runs.

⛔ **The owner's grounds are stronger than the finding, and they are already recorded in the
guard's own source.** `core/schema.py`'s comment block states that the guard is over what
`preview` EMITS, not over what any field may hold, and a per-field character rule at validation
time was weighed there and rejected. A propose-time gate is that rejected design. The same block
records the cost concretely: this character class refuses ideographic variation selectors,
"exactly the kind of thing a genealogical source spells a surname with". So the removed gate
would have refused a Han surname sitting in a field that attachment drops, for a sentence nobody
would ever have seen.

⚠️ **This is a deletion of a component the design already rejected, not new design**, which
is why it did not take a second plan review round.

## How the property is tested again

New `tests/unit/test_document_render_guard.py`, cases DERIVED from `NODE_KEYS` (published by
the module under test the way the registry was; a key added to any group later is covered
without this file changing). All characters built with `chr` so the file stays plain ASCII;
every value invented. Shape, ported from the deleted file's structure:

- **The derived matrix**: for each (group, key) in `NODE_KEYS` whose value is free text in a
  minimal well-formed creating-only graph, build a clean twin, then inject each of the three
  guarded characters (`chr(0x202E)` override, `chr(0x200B)` zero-width, `chr(0x07)` control)
  into the value and assert `document.preview` raises `UnrenderableTextError`. Cases whose
  injection breaks `parse` (the closed vocabularies, e.g. a note `type`) are dropped, not
  asserted on, exactly as the deleted file dropped cases `validate` rejected.
- **The R3 control replacing the two-sided vacuity check**: on a creating-only graph every
  declared free-text key renders (verified: given/surname/gender, titles, event fields,
  source fields, citation page, note text), so the deleted file's rendered/unrendered split
  collapses. Assert positively that every derived case's clean value appears in the clean
  twin's preview output; a case that stops rendering fails loudly instead of going vacuous.
  Plus one explicit unrendered-side case: on an ATTACHING node under a found stand-in
  `Resolution`, the payload name fields are dropped (`dropped_fields`), and a guarded
  character in one must NOT be refused by the approval render... unless it still renders; the
  build probes which and asserts the true behaviour, keeping the boundary documented either
  way. Role guidance from validation: use an invented non-default role like "Witness"; never
  derive expectations from `role: "Primary"`, whose value-conditional suppression
  (document.py:1204) makes the clean twin and the injected twin render differently.
- **Tree-read coverage the note flow never had**: a stand-in `Resolution` whose `display`
  carries `chr(0x200B)` must be refused by `document.preview(graph, resolution)`.
- **The published-source cross-checks**, ported nearly verbatim: every character
  `unicodedata.bidirectional` calls explicit bidi formatting (the nine UAX #9 types, spelled
  in the test, second source on purpose) is guarded; every character the running interpreter
  files as assigned General_Category `C*` is guarded (the regression sweep); the four
  invisible-outside-Other code points (0x034F, 0x115F, 0x1160, 0xFE00) are guarded.
- **Controls**: an ordinary preview is byte-identical with the guard present (no stripping by
  the back door); the refusal message repeats no value the payload carried; a multiline,
  tabbed note renders without refusal (the legitimate-whitespace control).

The table's own tests (`test_derive_unrenderable.py`) are untouched.

## `_note_type_unknown` (the #228 comment's question)

**It does not survive; it is deleted with schema.py, and nothing replaces it there.** Grounds:
the registry is empty, so no operation carries `note_type` and the rule reads a `getattr`
default forever; no test anywhere references `RuleId.NOTE_TYPE_UNKNOWN`; and the property it
enforced lives on the document route as `document.note_type_of` (document.py:500) over the
same frozen table (`NOTE_TYPES = ACCEPTED_NOTE_TYPES`, document.py:36), already pinned by
`tests/unit/test_note_types_table.py:195` and `test_note_type_on_the_document_route.py`. A
rule that can never fire, guarding a registry with nothing in it, duplicating a live check
that has its own tests, is dead weight whose deletion loses no coverage.

## What is left of `core/schema.py`, and whether it is deleted

**Deleted whole**, in the same change, after the guard cluster moves. Everything outside the
guard serves the retired operation model (empty registry, eight rules with no operations to
judge, wire conversion for types nothing constructs, `preview`/`full_display` with no
callers). Nothing imports the module; grep confirms only prose references remain. Alongside
the deletion, in the same change:

- `scripts/derive_unrenderable.py`: the emitted docstring sentence naming `schema.py` as the
  importer is updated to name `core/render_guard.py`, and `core/_unrenderable.py` is updated
  in lockstep in the same commit so re-derivation still diffs empty (its ranges are untouched;
  `test_derive_unrenderable`'s determinism test still passes).
- Stale prose pointers updated: `host/document.py:47-49` and `:510` (comments naming
  `schema.NOTE_TYPES` and `schema._note_type_unknown`), `docs/schema-render-guard-derivation.md`
  path references, `CONTRIBUTING.md:476-484`, `core/_note_types.py:7`,
  `scripts/derive_note_types.py:342`. Rulings under `docs/rulings/` are historical records and
  are not edited.

## Critical files

- `src/gramps_live_api/core/render_guard.py` (new)
- `src/gramps_live_api/core/schema.py` (deleted)
- `src/gramps_live_api/host/document.py` (one guard call in `preview`; stale comments)
- `scripts/derive_unrenderable.py` + `src/gramps_live_api/core/_unrenderable.py` (lockstep
  docstring update)
- `tests/unit/test_document_render_guard.py` (new; must be `git add`ed or the repository
  hygiene test fails)

## Acceptance criteria (each mechanically checkable)

1. `git grep -lE "core\.schema|core import schema" -- src scripts tests` returns nothing;
   `src/gramps_live_api/core/schema.py` does not exist.
   ⚠️ **The `.` is escaped and the match is `-E`, which is not pedantry.** Unescaped,
   `core.schema` also matches `core/schema` in prose, so the command returns the two files
   whose comments record that the module is gone, and the criterion reads as failing on the
   very head that satisfies it. Found by the round 1 review, which ran the command rather
   than reading it.
2. A graph whose note text carries `chr(0x202E)` is refused by `document.preview` with a
   message naming `Cf` and repeating no payload value (named test). `propose_document` stores
   such a proposal without complaint: the guard is on the approval render, not on acceptance.
3. `document.preview` refuses a graph whose person `given` carries `chr(0x0A)` followed by
   forged-line text (named test for the per-line wiring).
4. A `Resolution.display` carrying `chr(0x200B)` makes `document.preview(graph, resolution)`
   raise (named test).
5. The derived matrix generates at least one case per `NODE_KEYS` group that has a free-text
   key, and its non-vacuity assertion fails if any derived clean value stops rendering.
6. Both published-source sweeps pass: all nine UAX #9 explicit formatting types guarded; all
   assigned interpreter-reported `C*` code points guarded.
7. A multiline note containing `chr(0x09)` renders without refusal (legitimate-whitespace
   control).
8. `scripts/derive_unrenderable.py` and `core/_unrenderable.py` change in the same commit,
   `UNRENDERABLE_RANGES` byte-identical to before, and `test_derive_unrenderable.py` passes.
9. Full suite green except documented baseline; gates green on a clean tree.

## Out of scope

- Newline/structure forgery hardening beyond the guard's class semantics (the per-line wiring
  happens to refuse payload U+000A as Cc; no separate line-forgery mechanism is designed).
- Guarding `caller_preview`'s own output. ⚠️ **CORRECTED: the reason first written here
  cited the propose-time gate, which the owner-approved plan change above deletes.** The real
  reason, which stands on its own, is that `caller_preview` is agent-facing and is not the
  approval surface: its output returns to the agent that supplied the graph, so a character
  that agent put in its own payload coming back to it changes nothing about what a person
  approves or what is written. Measured: it does not render note text, but it does render
  person names, so a guarded character in `given` reaches its output unguarded. Filed as #237
  rather than fixed here.
- Implicit bidi reordering by strong RTL characters (recorded non-goal in the moved comment
  block, unchanged).
- Re-deriving the table against a newer Unicode release.
- Any change to `note_type_of`, the note-type table, or the writer plugin's behaviour.

## Questions deliberately left to the build

1. ~~Exact wording of the propose-time refusal.~~ **Answered by the plan change above: there is
   no propose-time refusal.** What remains of this question is the wording of the approval-time
   refusal, which question 2 covers.
2. Whether the plugin adds a friendlier owner-facing message for an approval-time refusal, or
   leaves the existing catch-all (fail closed either way).

   **ANSWERED BY THE BUILD: the existing catch-all, unchanged.** The plugin is out of scope by
   this plan's own out-of-scope list ("any change to ... the writer plugin's behaviour"), and the
   catch-all at `gramps_live_api_host.py:775` already fails closed and already tells the owner the
   write failed. The refusal message was written to be readable where it lands: it names the
   published fact (`Cc`, `Cf`, `Cs`, `Co`, `Default_Ignorable_Code_Point`), says what such a
   character does, and says nothing was written -- and it repeats no payload value, which matters
   precisely because that catch-all puts the traceback in a dialog. A friendlier message is a
   plugin change with no use-derived trigger behind it.
3. Which `NODE_KEYS` entries the derivation must drop because injection breaks `parse`
   (discovered by probe at build time, mirroring the deleted file's drop rule).

   **ANSWERED BY PROBE. 13 of the 28 declared keys are dropped**, and all 13 for one of two
   reasons. **A local id something else refers to**: `people.id`, `places.id`, `source.id`,
   `families.id` -- injecting into the id leaves the reference dangling and `check` refuses it.
   **A reference or a list of references**: `events.place`, `events.people`, `events.family`,
   `citations.source`, `citations.attach_to`, `notes.attach_to`, `families.parents`,
   `families.children` -- the injected value names nothing in the graph. Plus one closed
   vocabulary: `notes.type`, refused by `note_type_of`.

   ⚠️ **Two `id` keys are NOT dropped and are not carried either: `events.id` and `citations.id`.**
   Nothing in a minimal graph refers to them, so `parse` accepts the injection -- and the renderer
   never prints a local id, so nothing reaches a screen. **The plan predicted the deleted file's
   rendered/unrendered split would collapse on a creating-only graph. It does not.** The build
   kept the split: those two are asserted NOT refused, which is the control that shows the guard
   stayed at the rendering boundary, and they are pinned by name because a local id appearing in
   the render is a defect `document.py` already records having had.
4. Whether the `dropped_fields` attaching-node case renders or not under a found `Resolution`
   (probe, then assert the true behaviour).

   **ANSWERED BY PROBE: it does NOT render, so it is NOT refused.** Under a found `Resolution` the
   ATTACHING section prints `f"  {node.gramps_id}  {node.display}"` from the tree and names the
   payload field only as one that was NOT applied; the payload value itself reaches no screen and
   the writer ignores it. Probed with `given = "Al" + chr(0x202E) + "phaward"`: the override is
   absent from the rendered text. **The same graph with no resolution IS refused**, and the test
   asserts both beside each other, because that difference is exactly the finding that removed the
   propose-time gate from this plan.
5. Whether `render_guard` also exports `is_unrenderable` for the sweeps or the tests use
   `class_of(c) is not None` directly.

   **ANSWERED BY THE BUILD: no `is_unrenderable`.** The tests call `class_of(c) is not None`. A
   second public name for one question is a second thing to keep in step, and the module has one
   consumer that does not want the boolean -- `refuse_unrenderable` needs the label to put in the
   refusal.
6. Where the new test file's stand-in `Resolution` comes from: hand-built like
   `test_document_preview.py`'s `_resolution()` helper, or a shared fixture extracted from it.

   **ANSWERED BY THE BUILD: hand-built, three lines.** Extracting a shared fixture would couple
   two files' graphs, so a change to either one's fixture would move the other's assertions --
   and `test_document_preview.py`'s `_resolution` is bound to that file's graph and its invented
   display text. What the new file DID take from that one is its `node`/`graph_of` keyword-argument
   habit, which is not style: `pii_guard` reported this file twice while it used dict literals,
   scoring 40 for identity keys and then 6 for the graph's own group keys.
