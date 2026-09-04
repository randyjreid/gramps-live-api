# Plan — a note's type on the document route

**FULL tier.** It changes the graph schema and the writer, which is the
publication-of-personal-data surface. ⛔ **Not built. This page is the
deliverable.**

## The ruling this page is written to

⭐ **The tool may write only note types a user can select and edit in Gramps'
own interface.** ⛔ **Custom note types are refused.**

⛔ **The reason is a safety property, not a preference.** *If the agent writes a
type the user cannot pick by hand, the user cannot correct a wrong one.* The tool
must never create something its owner cannot edit. Everything below is an attempt
to find the mechanism that actually implements that sentence — and the mechanism
turned out not to be the one the enum's names suggest.

⚠️ **Two earlier recommendations on this page are superseded**: the two-member
closed set `{research, todo}`, and its replacement, *every built-in the class
declares*. What survives both is the part neither of them was wrong about — **an
unrecognised type is refused by name rather than passed to Gramps**, which is the
opposite of what `_event_type` does for events and is deliberate.

## Why this exists

**R9 asks whether to retire the note flow.** The one real capability that flow
has and the document route does not is **a caller-chosen note type**.

⛔ **Retiring without this makes two note types unwritable.** So R9 and this page
are ruled together.

## What is true today, verified by reading and running

| | |
| --- | --- |
| the note flow's types | `schema.NOTE_TYPES = frozenset({"research", "todo"})` (`schema.py:380`) |
| how it spells them for Gramps | `apply.NOTE_TYPE_ATTRIBUTES = {"research": "RESEARCH", "todo": "TODO"}` (`apply.py:349`) — attribute **names**, never the integers, ⭐ **already asserted total over `NOTE_TYPES` by test** |
| how the shim applies it | `gramps_plugin/gramps_live_api_apply.py:158` — `note.set_type(NoteType(getattr(NoteType, note_type)))` |
| what the document route accepts | `NODE_KEYS["notes"] = {"text", "attach_to"}`, plus `gramps_id` for every group (`_only_known_keys:453`) |
| what the document route writes | ⛔ `gramps_plugin/gramps_live_api_writer.py:527` — `note.set_type(NoteType(NoteType.TRANSCRIPT))`, **hardcoded, every note** |
| what the preview shows | `+ Note:` and the text. ⛔ **No type at all** (`document.py:1313–1318`) |

## What Gramps actually declares — derived, not remembered

Read from the installed runtime's `gramps/gen/lib/notetype.py`:

| | |
| --- | --- |
| the installation declares | `VERSION_TUPLE = (6, 0, 8)`; the AIO build then overwrites `VERSION` to `AIO64-6.0.8--1` |
| the file read | 4806 bytes, SHA-256 `c67cfc820a346bc0bb1ec0497494a781090e69c00df79c30d2c998ddbaa1d348` |

`NoteType` declares its rows in **two lists that are concatenated**:

| list | rows | what Gramps does with them |
| --- | --- | --- |
| `_DATAMAPREAL` | **12** | offered to a person in the ordinary way |
| `_DATAMAPIGNORE` | **17** | returned by `get_ignore_list`. ⭐ **Verified in `gramps/gui/`, not inferred from the name** — see the section below, because what it does is narrower than "these cannot be chosen" |
| `_DATAMAP` | **29** | `_DATAMAPREAL + _DATAMAPIGNORE`, and the class's actual vocabulary |

**Nineteen of the 29 are excluded, and none of it is a hand-partition:**

- the **17** in `_DATAMAPIGNORE` — by the ruling, for the reason established in
  the next section.
- `CUSTOM` (0) — ⛔ the owner has ruled custom note types out, and this is the
  door they would come through.
- `UNKNOWN` (-1) — not a filing decision. It is what Gramps holds when it does
  not know, and a caller choosing it is asking for the absence of a choice.

⭐ **So the accepted vocabulary is 10**, computed as
`_DATAMAPREAL - {CUSTOM, UNKNOWN}`:

| wire name | attribute | int | Gramps' key |
| --- | --- | --- | --- |
| `general` | `GENERAL` | 1 | `General` |
| `research` | `RESEARCH` | 2 | `Research` |
| `analysis` | `ANALYSIS` | 27 | `Analysis` |
| `transcript` | `TRANSCRIPT` | 3 | `Transcript` |
| `source_text` | `SOURCE_TEXT` | 21 | `Source text` |
| `citation` | `CITATION` | 22 | `Citation` |
| `report_text` | `REPORT_TEXT` | 23 | `Report` |
| `html_code` | `HTML_CODE` | 24 | `Html code` |
| `todo` | `TODO` | 25 | `To Do` |
| `link` | `LINK` | 26 | `Link` |

⭐ **`todo` and `link` both survive the narrowing**, which had to be checked
rather than assumed: they are the two rows written with the two-argument
translation call that the first derivation pass silently dropped, and `todo` is
one of the two types this work exists to write. ⭐ **`transcript` survives too**,
which criterion 5 depends on — it is the default, and a default outside the
accepted set would be unwritable through the very route that defaults to it.

### ⚠️ The derivation hazard, found the hard way

A first pass over this file with a regex for `(NAME, _("Label"), "Key")` returned
**27 rows and looked complete**. It was not. `TODO` and `LINK` are written
`_("To Do", "notetype")` — the **two-argument** translation call, used where a
word needs a disambiguating context — and the pattern skipped both. ⛔ **`todo`
is one of the two types the whole note flow exists to write**, so the silent
result of trusting that pass would have been a table that dropped the type this
work is for, while looking like a full enumeration.

**That is the argument for generating and committing the table** rather than
writing one out: the failure was invisible in the output and obvious in a diff.

### ⚠️ The key strings are NOT the attribute names

| attribute | Gramps' key string |
| --- | --- |
| `SOURCE_TEXT` | `Source text` |
| `REPORT_TEXT` | `Report` |
| `HTML_CODE` | `Html code` |
| `TODO` | `To Do` |
| `PERSONNAME` | `Name Note` |

The wire vocabulary is the **lowercased attribute name** — `source_text`,
`report_text`, `html_code`, `todo` — because that is what `getattr` resolves and
what `NOTE_TYPE_ATTRIBUTES` and `_event_type` already use. ⛔ **The key strings
are recorded in the table and used by nothing**, deliberately: they are how
Gramps spells these in XML and in its own interface, and a later reader comparing
the two vocabularies should not have to re-derive them.

## ⭐ What Gramps' interface actually offers — read from `gramps/gui/`

⛔ **The enum's names do not encode the UI behaviour, so this was read rather
than assumed.** The result narrows the set, but not for the reason the name
`_DATAMAPIGNORE` suggests, and two of the three findings cut the other way.

**Which list does the note-type chooser read?** Neither list directly.
`gramps/gui/editors/editnote.py:218` builds a `MonitoredDataType` with
`ignore_values=self.obj.get_type().get_ignore_list(self.extratype)`, and
`MonitoredDataType` (`gramps/gui/widgets/monitoredwidgets.py`) starts from
`get_val().get_map()` — the **whole** `_I2SMAP`, which is built from `_DATAMAP`
minus `_BLACKLIST`, and `NoteType` sets no `_BLACKLIST` — then deletes the
ignored keys. **So the offered set is computed as `get_map()` minus
`get_ignore_list(extratype)`; it is not a list anything publishes.**

⛔ **Is there an API naming the selectable set? No.** `get_standard_names()`
returns every standard name **including the ignored ones**, so it is not it.
`get_menu()` returns `_MENU`, which `NoteType` never defines, so it is empty.
`get_ignore_list` is the only thing in the neighbourhood, and it names the
complement. **There is nothing to derive from except `_DATAMAP` and
`get_ignore_list`**, which is what criterion 1 does.

### ⚠️ Two findings that cut AGAINST narrowing, and are reported because the ruling is the owner's

⭐ **1. An ignored type on a note that already has it is NOT removed from the
chooser.** The loop is
`if key in ignore_values and key not in (None, default): del map[key]`, and the
docstring says it outright: *"list of values not to show in the combobox. If the
result of get_val is in these, it is not ignored"*. So a note the tool wrote with
`Event Note` opens showing `Event Note`, and the user can change it to any offered
type. ⛔ **The owner's stated reason — that a wrong type must be correctable —
therefore holds for all 27, not only for the 10.**

⭐ **2. The ignored types ARE selectable — in the context they name.**
`gramps/gui/editors/displaytabs/notetab.py` passes `extratype=[self.notetype]`
for both Add and Edit, and `get_ignore_list(exception)` removes the exception
from the ignore list. Each object editor supplies its own: `editperson` passes
`NoteType.PERSON`, `editevent` `EVENT`, `editplace` `PLACE`, `editchildref`
`CHILDREF`, and so on — **16 of the 17 are supplied by some editor.** So a user
adding a note from a person's Notes tab *is* offered `Person Note`.

⚠️ **The one exception is `SOURCEREF`**, which no editor passes. It is the only
built-in note type reachable by no chooser anywhere except on a note that already
carries it.

### ⛔ Why the set is still 10

**The ruling requires select *and* edit, and only 10 satisfy both wherever the
note lives.** The asymmetry is precise and it is the whole argument:

| | a `_DATAMAPREAL` type | a `_DATAMAPIGNORE` type |
| --- | --- | --- |
| offered on **any** note | ⭐ yes | ⛔ no — only in its own object's Notes tab |
| offered on a note attached to **something else** | ⭐ yes | ⛔ **no** |
| visible and changeable once present | yes | yes |

⭐ **This route attaches notes to arbitrary nodes**, so the second row is the one
that governs. A note the tool writes with `Event Note` while attached to a person
opens in the person's Notes tab, which offers `_DATAMAPREAL` plus `Person Note`
— the user can *remove* the type but could never have *chosen* it there, and
cannot put it back. ⛔ **The 10 are exactly the set closed under the user's own
editing, wherever the note sits.** That is a derivation of the owner's property
rather than a partition of the enum, which is what the ruling asked for.

⚠️ **And it is the reversible direction.** If the owner re-rules on finding 1 or
2 above, widening to 27 is a one-line change to the derivation and re-derives
nothing, because the committed table records which list every row came from.

### ⚠️ The context question, and why the answer is still a flat 10

**The chooser's offered set is position-dependent, so the honest next question is
whether this route's own notes have a stable position.** They do not, and that is
what settles it.

⛔ **A note's `attach_to` is unconstrained.** `document.py` validates it with
`check("a note", target)` and passes no `must_be`, unlike a citation's source or a
family's parents. So a note may name **any** of the seven groups (`people`,
`places`, `events`, `source`, `citations`, `families`, `notes`), it may name
**several**, and it may name **none**. The kinds that carry a contextual note type
are `person`, `place`, `event`, `source` and `family`; `citation` maps to
`CITATION`, which is already one of the 10; a note attached to a note has no
contextual type at all.

**So the set that satisfies the owner's test varies by graph:**

| what the note attaches to | selectable in that position |
| --- | --- |
| nothing | the 10. It is edited from the Notes view, where `extratype` is `None` |
| exactly one node of kind K | the 10, plus K's contextual type |
| several nodes of differing kinds | the 10. A type has to be selectable in **every** tab the note appears in, and each tab adds only its own |

⭐ **The 10 is the intersection**, and it is the only answer that holds without
asking what the rest of the graph looks like.

### ⭐ Recommended: keep the flat 10. The owner may widen it.

**What widening would buy:** a note attached to exactly one person could carry
`person`, one attached to one event could carry `event`, and so on for `place`,
`source` and `family`. Five types, in the single-target case only.

**Four reasons not to, in order of weight:**

1. ⛔ **Gramps already sets those types itself.** `notetab.py` does
   `note.set_type(self.notetype)` before it opens the editor, so a note created
   from a person's Notes tab is a `Person Note` by default. **The attachment
   already carries the fact**, and a caller setting it explicitly adds nothing a
   user could not get. What the caller genuinely contributes is the filing
   decision, transcript against research against todo, and those are all in the 10.
2. ⚠️ **It makes validation depend on graph topology.** The accepted set for a
   note would become a function of `attach_to`, so the refusal message differs by
   position and the preview has to render which set applied.
3. ⛔ **It pushes topology into the writer.** Criterion 9 spent three review
   rounds arriving at a flat membership tuple, and a position-dependent set turns
   that back into a computation over the graph, in the component that cannot
   import the package.
4. ⭐ **Widening later is cheap and narrowing later is not.** Adding the
   contextual types is a change to the derivation plus one topology rule.
   Removing a type callers already use is a breaking change to the graph.

⚠️ **What this costs, stated plainly:** a caller cannot ask for `Person Note` on
a person's note, even though a user could select it there. The note is still
written, with a type from the 10, and the user can change it in Gramps. **No fact
is lost and nothing becomes uneditable**, which is the property the ruling
protects.

## Goal

**A note proposed through the document route may carry a `type`, validated
against a committed table derived from the installed Gramps' own `NoteType`,
shown in the preview, and written by the writer — and every graph that exists
today keeps working unchanged.**

## Mechanically checkable acceptance criteria

1. **The table is generated and committed, the way this repository already does
   it twice.** `scripts/derive_note_types.py` is stdlib-only, reads
   `gramps/gen/lib/notetype.py` from a path given as an argument, and prints
   `src/gramps_live_api/core/_note_types.py` on stdout, byte for byte. It emits
   **no timestamp**, so re-running it over the same input reproduces the
   committed file exactly. The committed module records the source's declared
   version and its SHA-256, carries all **29** rows — attribute name, integer,
   key string, and which of the two lists it came from — and names the **10**
   that are accepted. ⭐ **The accepted set is computed, not listed**, as
   `_DATAMAPREAL - {CUSTOM, UNKNOWN}`, so it cannot drift from the rows beside
   it.

   ⛔ **And it FAILS CLOSED on anything in those two lists it cannot parse.**
   The script does not skip an element it does not recognise; it refuses to emit
   a table at all and names the line. ⚠️ **Without this the whole scheme is
   decorative**, and the `TODO`/`LINK` near-miss above is the proof: a parser
   that silently skips what it does not recognise produces a table that is short
   by exactly the rows nobody thought about, and **every check downstream still
   passes** — criterion 2's count sees a self-consistent table, and criterion 3's
   comparison sees the committed rows equal the parsed rows, because both sides
   dropped the same row. The derivation is the only place this can be caught, so
   it is the place that must refuse.

   ⚠️ **A fixed expected count is not the guard either**, and writing `== 29`
   would read like one. A later `notetype.py` that adds a thirtieth row in an
   unrecognised shape leaves 29 parsed rows and passes. **The guard is that every
   element of `_DATAMAPREAL` and `_DATAMAPIGNORE` was understood**, not that a
   remembered number came back.

   ⭐ **The script's own parser is tested against synthetic inputs** covering
   every shape Gramps uses today — the one-argument `_("Label")` and the
   two-argument `_("Label", "context")` — plus at least one shape it must reject.
   ⚠️ These are fixtures written for the test, not a copy of the vocabulary, so
   they are not a second tally.

   ⚠️ **This differs from the two existing frozen tables in one way that must be
   stated rather than glossed.** `_unrenderable.py` and `_specified_containers.py`
   derive from *published standards* fetched once by a human, and their
   verification is *re-fetch, compare digest, re-run, diff*. This table's source
   is **a runtime installed on a machine** — it varies per machine and CI has
   none at all. The pattern still applies; the verification splits in two, and
   criteria 2 and 3 are that split.

2. ⛔ **The offline test never needs Gramps and always runs.** It asserts the
   committed table is internally consistent — 29 rows, the two lists partition
   them, the accepted set is exactly `_DATAMAPREAL` less `UNKNOWN` and `CUSTOM`
   and so has 10 members, `transcript` is among them because criterion 5 defaults
   to it,
   no duplicate attribute name or integer — and that the parser validates against
   **the table itself**, never a copy. ⚠️ **A literal list in the test would be a
   second tally**, which is the counter bug this repository has already paid for.

3. ⛔ **A Gramps-present test asserts the table still matches the installed
   runtime, and SKIPS when there is none.** Same shape as
   `tests/integration/test_round_trip.py:53`'s `runtime_or_skip()`. It re-reads
   `notetype.py` from the discovered installation and asserts the committed rows
   equal what it declares. On a mismatch it fails naming both digests and the
   regeneration command, because the honest reading of a mismatch is *"this table
   was derived from a different Gramps"* and the repair is to re-derive.

   ⚠️ **A digest comparison alone must not be the assertion.** The digest moves on
   any edit to that file, including ones touching no note type at all, so a
   digest-only test fails on upgrades that change nothing this depends on. **The
   rows are the property; the digest is provenance.**

4. **`notes` accepts an optional `type`.** `NODE_KEYS["notes"]` gains `"type"`.
   A graph that omits it still parses.

5. **Omitted means `TRANSCRIPT`.** ⭐ Asserted by a test that takes a graph with
   no `type` and shows the written type is unchanged from today's behaviour, so
   **every graph that exists now is written exactly as it is written today**.
   This is the backward-compatible half, and the one most easily broken by a
   default landing in the wrong place.

   ⚠️ **This guarantee is about the WRITE, and deliberately not about the
   RENDER.** Criterion 6 changes what an untyped note looks like in the approval,
   which is a visible change for every graph that exists now. The reason is in
   criterion 6 and the trade is stated there.

6. **The preview shows the type — ⛔ at BOTH render sites.** A type written but
   not rendered is a byte reaching the tree that was not shown in the approval,
   which is the one property the whole document route exists to hold.

   ⚠️ **There is no single note-rendering site, and assuming one is how this
   criterion would be half-met.** Verified:

   | | where | what it emits |
   | --- | --- | --- |
   | **attached** notes | `document.py:1313–1318`, inside the per-node walk | `+ Note:` then the text |
   | **undrawn** notes | `document.py:1596–1602`, the leftovers loop | `Note      (attached to …):` then the text, under `ALSO WRITTEN` |

   ⛔ **A typed note whose edge is undrawn, attached to nothing or to a node the
   walk never reached, renders through the second site only.** **Criterion 6
   requires one typed note through each site.**

   ⛔ **And one UNTYPED note through each site, asserting the preview shows
   `transcript`.** This is the case that a typed-only test cannot catch, and the
   gap is not hypothetical: an implementation that renders the type only when the
   `type` key is present passes every typed case above, while a note whose written
   type is `TRANSCRIPT` shows no type at all in the approval. **That is a value
   reaching the tree that the approval did not display**, which is the single
   property this route exists to hold, and it would be reached by the most natural
   way to write the rendering.

   ⚠️ **This is the collision the falsifier below predicted, and it is resolved
   here rather than left open.** The preview cannot show the effective type
   without changing how untyped notes render, so **every existing untyped graph's
   approval text changes**: where it read `+ Note:` it will name `transcript`.

   ⭐ **Resolved in favour of showing what will be written**, because criterion
   5's promise is about the written value and that value is unchanged, while the
   alternative is an approval that displays less than the write performs. ⛔ **The
   owner can overrule this**, and it is flagged rather than buried because it
   changes what he sees in a dialog he already knows.

7. **A refused type names the set.** `type: "gossip"` is refused by name and the
   message lists what is accepted, in the shape `_only_known_keys` already uses.

   ⛔ **And `type` must BE a string, checked before anything is done with it.**
   The graph arrives as JSON and the parser today checks a node is an object with
   known keys, so `type: []` and `type: 42` are both reachable. `document.py`
   already applies exactly this check to three other leaves — `local` (`:708`),
   `source_id` (`:733`) and `referenced` (`:758`) — and this is the fourth.

   ⚠️ **Write the default as ABSENCE OF THE KEY, never as falsiness.** The
   natural spelling — `if not value or value in TABLE` — is the shape
   `schema._note_type_unknown` uses today, and it is safe there only because
   `_text` has already coerced. Copied here without that coercion it reads
   `type: []` and `type: 0` as **omitted** and silently writes `TRANSCRIPT`,
   which is a chosen value becoming a default without anybody being told. ⛔ A
   present `type` that is not a string is **refused**; only an absent one
   defaults.
   ⛔ **Refused, never passed through to Gramps** — which is the opposite of the
   choice `_event_type` makes, and the difference is deliberate. `_event_type`
   turns an unrecognised word into a CUSTOM type carrying that word, and the
   recorded cost is the owner's own: *"An unrecognised type silently creates a new
   custom type in the tree and nothing tells me it's new."* An event type comes
   off a document and its vocabulary is open in practice; a note's type is a
   filing decision drawn from a list Gramps itself publishes.

8. ⛔ **The 19 rows the table carries and does not accept are refused like any
   other unknown word**, and a test names them. `custom` and `unknown` are two of
   them, and the other 17 are the `_DATAMAPIGNORE` rows — these are the names a
   lookup written slightly wrong would let through, because they are all present
   in the table and differ from the accepted ones only by which list they came
   from. ⭐ **`event`, `person` and `sourceref` are worth naming in the test
   individually**: they read like perfectly reasonable note types, which is
   exactly why a reader of the refusal message needs to see them refused.

9. ⛔ **The writer accepts a name only if it is a MEMBER of the accepted set** —
   and then resolves it through `getattr` on the attribute name, never a pinned
   integer, which is the discipline `_event_type` and the apply shim already use.
   The package-side validation is the real gate; this is the second line, and it
   exists because the writer is reachable with a graph the package did not
   validate.

   ⭐ **The writer therefore inlines the ten accepted names, and a test
   asserts that list equals the committed table's accepted set.** There is
   precedent for the test: `tests/unit/test_attachable_bound.py` and
   `test_write_summary.py` already import the writer **by path** with
   `importlib.util.module_from_spec`, without Gramps. ⚠️ The writer
   **deliberately does not import the package** (`writer.py:33`), so the list
   cannot be shared at runtime — but a copy that a test binds to its source is not
   the thing "no duplicate that nothing checks" forbids. **An unchecked copy is.**

   ⛔ **This REVERSES what this criterion said for three revisions**, and the
   reversal is the point rather than an embarrassment, so the reasoning is left
   standing:

   > It said the writer needed no copy, because `getattr` plus a few refusals
   > would do. Three consecutive review rounds each found a genuine, different
   > hole in that list of refusals — `isinstance(value, int)` for `_DATAMAP`,
   > which is a list; `isinstance(name, str)` for `type: []` and `type: 42`;
   > `hasattr` for `type: "gossip"`, which resolves to nothing at all. Each fix
   > was correct and each round found the next one.

   ⚠️ **That is a universally quantified negative over an unbounded space** —
   *no attribute reachable by `getattr` produces an uncontrolled result* — and
   this project's rule for that shape is to stop reviewing it and bound it
   instead. **Membership in a ten-element set is bounded and closes.**
   Every one of the three findings, and every one nobody has constructed yet, is
   refused by the same single check, because none of those names is in the set.

   ⭐ **And the sharpest of the three is the argument against ever going back.**
   `NoteType._DEFAULT` **is an int** — it equals `GENERAL` — so under the
   exclusion list `type: "_default"` passed `hasattr`, passed
   `isinstance(value, int)`, was neither `CUSTOM` nor `UNKNOWN`, and **silently
   wrote a General note**: not a crash, a working undocumented alias. It was
   stopped only by a name-shape rule added for an unrelated reason. ⛔ **A guard
   list whose coverage of the worst case is incidental is not a guard.**

   ⚠️ **`CUSTOM` and `UNKNOWN` need no special handling under membership**, and
   adding it would suggest the set were not trusted. They are not in the accepted
   set, so they are refused by the same check as `gossip`. Criterion 8's test
   still names them, because they are the two rows the table carries and does not
   accept, and that is worth a test that says so.

10. ⛔ **The tool description advertises `type`, and it must.**
    `test_the_ADVERTISED_shape_is_exactly_what_the_parser_accepts` compares
    `PROPOSE_DOCUMENT_DESCRIPTION` against `NODE_KEYS` **in both directions**, so
    adding the key without advertising it fails that test.

11. ⛔ **And it must fit the delivery budget, which is nearly full.** Measured:

    | | chars | |
    | --- | --- | --- |
    | `DESCRIPTION_BUDGET` | 2048 | |
    | `PROPOSE_DOCUMENT_DESCRIPTION` today | 2032 | 16 spare |
    | with `,"type"` added to `notes` | **2040** | ⭐ fits, 8 spare |

    ⭐ **The vocabulary cannot go in the description.** It could not at two members
    and it certainly cannot at ten, whose written-out form is 98 characters
    against 8 spare. Advertise the key; let **criterion
    7's refusal** carry the values, which is where a caller meets them anyway and
    which costs no budget at all.

    ⚠️ **This is a real constraint on the design, not a formatting note.** If a
    later change needs more than eight characters there, something already in it
    has to come out, and what to remove is a judgement about what a caller most
    needs — not a trim.

## What supersedes `NOTE_TYPES`, reference by reference

⛔ **Not guesswork — this is every occurrence in the tree.**

| where | what it is | what happens to it |
| --- | --- | --- |
| `schema.py:380` | `NOTE_TYPES = frozenset({"research", "todo"})` | **becomes the accepted set from the table.** The name stays: it is what `validate` reads and what the note flow's description interpolates |
| `schema.py:549` | a docstring calling it "the type a field declares … ours rather than [Gramps']" | ⛔ **that sentence becomes false** and must be rewritten — the vocabulary is now Gramps' |
| `schema.py:862, :868` | `if not note_type or note_type in NOTE_TYPES`, and the refusal naming `_one_of(NOTE_TYPES)` | unchanged in shape; the set behind them widens |
| `apply.py:349` | `NOTE_TYPE_ATTRIBUTES`, two entries | ⭐ **stops being a hand-written map.** Name → attribute is `name.upper()` for every row and the table carries both, so it is derived from the table or dropped in favour of the table's own lookup |
| `apply.py:358` | the docstring claiming it is asserted total over `NOTE_TYPES` | rewritten with whatever mechanism replaces it |
| `apply.py:488` | `note_type=NOTE_TYPE_ATTRIBUTES[note.note_type]` | one lookup, retargeted |
| `server.py:200` | `note_type must be one of: {schema._one_of(schema.NOTE_TYPES)}` in `PROPOSE_NOTE_DESCRIPTION` | ⭐ **fits.** Measured: that description is **1705** of 2048 today; the listed vocabulary goes from 14 characters to **98**, so it becomes **1789** — 259 spare |
| `test_apply_operation.py:310–314` | asserts `NOTE_TYPES - set(NOTE_TYPE_ATTRIBUTES)` is empty | ⚠️ **watches nothing once the map is derived from the table** — a test that cannot fail. Replaced by criterion 3's assertion that every accepted attribute name exists on the installed `NoteType` |
| `test_mcp_server.py:178–181, :310` | asserts every `NOTE_TYPES` member appears in the description, and in a refusal | unchanged, and now covers 10 |

⚠️ **The R9 dependency, restated and now larger.** If R9 retires the note flow,
`schema.NOTE_TYPES` **must not be deleted with it** — the document route now
depends on it. R9's removal list names `core/proposals.py` and the `AddNote` parts
of `core/schema.py`, and this constant sits inside that blast radius. **That is a
line in R9's execution, not a surprise to discover afterwards.**

## Out of scope

- Retiring the note flow. ⛔ That is R9 and it is the owner's.
- Any change to how notes attach, or to `attach_to`.
- Editing a note that already exists — the route attaches and creates, never
  modifies, and this does not change that.
- Note types on anything but notes.
- ⛔ **Custom note types**, in any form. Ruled out.

## ⭐ What is now the owner's to re-rule, if he wants to

**The set is settled at 10 and this page is written to it.** What is recorded
here is the evidence that could reasonably move it, because it was found while
confirming the mechanism and it does not all point the same way.

⚠️ **The ruling's stated reason is satisfied by a wider set than its stated
rule.** *A wrong type must be correctable* holds for all 27: an ignored type on a
note that already carries it stays in the chooser and can be changed. If
correctability alone is the property, the set is 27 and this page is too narrow.

⚠️ **And the ignored types are choosable, in context.** 16 of the 17 are offered
in their own object's Notes tab. If *"a user can select it in Gramps"* means
"somewhere in Gramps", the set is again 27.

⛔ **This page reads the rule as the conjunction it states — select AND edit,
for the note where it actually sits — and 10 is the only set that satisfies it
wherever this route puts a note.** It is also the conservative direction: it can
refuse something the owner wanted, which he will notice, rather than write
something he cannot re-choose, which he may not.

## ⚠️ Build-time question: the table is frozen, the runtime is not

**Raised in review and verified.** The committed table is derived from one
Gramps. The plugin registers against **whichever Gramps is running** —
`gramps_plugin/gramps_live_api_host.gpr.py` sets
`MODULE_VERSION = f"{VERSION_TUPLE[0]}.{VERSION_TUPLE[1]}"` from
`gramps.version`, deliberately and with its reason recorded there: a pinned
literal stops matching the day Gramps updates and the plugin silently stops
being registered. **So there is no version wall, and nothing in criteria 1–9
puts one there.**

⛔ **The failure that follows, named exactly.** If a later Gramps renames or
removes a built-in note type, a name in the frozen table is validated by the
package, passes the writer's membership check — and then `getattr` finds nothing
on the live class. **That happens after the owner approved the document**, which
is the one moment this route exists to make safe. Criterion 3's test is the only
thing watching for the drift, and it is a test: it can be skipped, and it does
not run at all on the machine doing the writing at the moment it writes.

⚠️ **This is recorded as a question for the build rather than specified here**,
and that is a deliberate call under this project's own rule: a finding that would
make the plan grow a new proof obligation, about behaviour of code nobody has
written, is cheaper and more accurately answered by the build than by another
round of specification. The three candidate answers are not equally costly and
choosing between them needs the code:

| | what it costs |
| --- | --- |
| **a live check before anything is written** — the writer compares its inlined names against the running `NoteType` once, and refuses the **whole document** with a message naming the drift | the honest one, and the only one that cannot fail after approval. Costs a startup or per-write pass over 10 names |
| **a supported-version wall** in the document path | contradicts the registration decision above, which exists precisely so the plugin does not stop working on upgrade |
| **accept it**, on the argument that built-in note types have been stable for many releases | free, and it is a claim about Gramps' future that this project cannot check |

⭐ **What is NOT acceptable is the current implied behaviour** — the drift
surfacing as an `AttributeError` partway through a write the owner has already
approved. Whichever answer the build takes, the failure must be a refusal of the
whole document, before any object is created.

## Falsifier

⛔ **If criterion 5 cannot be made to hold — if a default cannot be added without
changing what an existing untyped graph writes — the design is wrong**, and the
type must be required rather than optional, which is a breaking change to the
graph and needs its own ruling.

⚠️ **And a smaller one, which has now happened.** The preview cannot show the
effective type without changing how untyped notes render, so criterion 6 does
collide with criterion 5. **It is resolved inside criterion 6**, in favour of the
approval showing what the write will do, and the visible consequence is recorded
there. It is written up rather than left as an open falsifier because the two
criteria disagree only if criterion 5 is read as a promise about the render,
which it is not. ⛔ **If the owner reads it that way, criterion 6 is the one that
gives.**

⚠️ **And one from the build-time question above.** If the live vocabulary
cannot be checked before the first object is written — if the only place the
drift can be detected is partway through the write — then the document route
cannot keep its binding property under a Gramps it was not derived against, and
**that is a fact for the owner rather than something the build resolves by
picking an option.**

⚠️ **And one this revision adds.** If the derivation cannot be made reproducible —
if `notetype.py` cannot be parsed with the standard library alone into a table
that regenerates byte-identically — then the frozen-table pattern does not
transfer here, and the honest fallback is the closed set the previous revision
recommended. ⛔ **Not a hand-written twenty-nine-row list.** That is the one
outcome this page refuses, because it cannot be re-derived and diffed, and the
`TODO`/`LINK` near-miss above is what a hand-written list looks like when it is
wrong.

## Estimated shape

Larger than the previous revision, and in a different place. The route's own
change is the same size — `NODE_KEYS` gains a key, one validation branch, two
preview sites, one writer line. **What is added is the derivation**: a script, a
committed table, and the two-part verification of criteria 2 and 3. The
supersession of `NOTE_TYPES` touches nine sites, all enumerated above, and one of
them is a docstring that currently asserts something the change makes untrue.

⚠️ **The plan is FULL tier for what it touches, not for its size.**
