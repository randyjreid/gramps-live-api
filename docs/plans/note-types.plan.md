# Plan — a note's type on the document route

**FULL tier.** It changes the graph schema and the writer, which is the
publication-of-personal-data surface. ⛔ **Not built. This page is the
deliverable.**

## The ruling this page is written to

⭐ **Support every built-in Gramps `NoteType` from the start** — not a
hand-picked subset. ⛔ **Custom note types are refused.** An earlier revision of
this page recommended the two-member closed set `{research, todo}` and argued for
it; that recommendation is **superseded**, and its argument is kept below only
where it still bears on a live decision.

⚠️ **This inverts the recommendation, not the mechanism.** The reason the closed
set was recommended — *an unknown type must be refused by name rather than
silently becoming a custom type nobody was told about* — is unchanged, and is
still exactly what this design does. What changed is which set is closed: a
vocabulary of two that this project wrote, or the vocabulary Gramps declares.

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
| `_DATAMAPIGNORE` | **17** | ⭐ returned by `get_ignore_list`, which callers use to **keep them out of a type chooser** — they are the types Gramps assigns itself for a note belonging to a person, an event, a media object and so on |
| `_DATAMAP` | **29** | `_DATAMAPREAL + _DATAMAPIGNORE`, and the class's actual vocabulary |

**Two of the 29 are excluded, and neither is a judgement call:**

- `CUSTOM` (0) — ⛔ the owner has ruled custom note types out, and this is the
  door they would come through.
- `UNKNOWN` (-1) — not a filing decision. It is what Gramps holds when it does
  not know, and a caller choosing it is asking for the absence of a choice.

⭐ **So the accepted vocabulary is 27**, every one of them a built-in the
installed Gramps declares. Nothing is picked: two are excluded by a stated rule.

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
   key string, and which of the two lists it came from — and names the **27**
   that are accepted.

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
   them, `UNKNOWN` and `CUSTOM` excluded, the accepted set exactly the other 27,
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
   **every graph that exists now is unaffected**. This is the backward-compatible
   half, and the one most easily broken by a default landing in the wrong place.

6. **The preview shows the type — ⛔ at BOTH render sites.** A type written but
   not rendered is a byte reaching the tree that was not shown in the approval,
   which is the one property the whole document route exists to hold.

   ⚠️ **There is no single note-rendering site, and assuming one is how this
   criterion would be half-met.** Verified:

   | | where | what it emits |
   | --- | --- | --- |
   | **attached** notes | `document.py:1313–1318`, inside the per-node walk | `+ Note:` then the text |
   | **undrawn** notes | `document.py:1596–1602`, the leftovers loop | `Note      (attached to …):` then the text, under `ALSO WRITTEN` |

   ⛔ **A typed note whose edge is undrawn — attached to nothing, or to a node the
   walk never reached — renders through the second site only.** **Criterion 6
   requires one typed note through each site.**

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

8. ⛔ **`custom` and `unknown` are refused like any other unknown word**, and a
   test names them specifically. They are the two rows the table carries and does
   not accept, so they are the two a lookup written slightly wrong would let
   through.

9. ⛔ **The writer accepts a name only if it is a MEMBER of the accepted set** —
   and then resolves it through `getattr` on the attribute name, never a pinned
   integer, which is the discipline `_event_type` and the apply shim already use.
   The package-side validation is the real gate; this is the second line, and it
   exists because the writer is reachable with a graph the package did not
   validate.

   ⭐ **The writer therefore inlines the twenty-seven accepted names, and a test
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
   instead. **Membership in a twenty-seven-element set is bounded and closes.**
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
    and it certainly cannot at twenty-seven. Advertise the key; let **criterion
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
| `server.py:200` | `note_type must be one of: {schema._one_of(schema.NOTE_TYPES)}` in `PROPOSE_NOTE_DESCRIPTION` | ⭐ **fits.** Measured: that description is **1705** of 2048 today; the listed vocabulary goes from 14 characters to **249**, so it becomes **1940** — 108 spare |
| `test_apply_operation.py:310–314` | asserts `NOTE_TYPES - set(NOTE_TYPE_ATTRIBUTES)` is empty | ⚠️ **watches nothing once the map is derived from the table** — a test that cannot fail. Replaced by criterion 3's assertion that every accepted attribute name exists on the installed `NoteType` |
| `test_mcp_server.py:178–181, :310` | asserts every `NOTE_TYPES` member appears in the description, and in a refusal | unchanged, and now covers 27 |

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

## ⭐ The one question the ruling does not settle

**Should the 17 `_DATAMAPIGNORE` types be accepted, or only the 12 in
`_DATAMAPREAL`?**

⛔ **This page takes the ruling literally and accepts all 27**, because "every
built-in, not a hand-picked subset" reads most naturally as *everything the class
declares that is a real filing decision*, and because the alternative asks this
project to decide that a Gramps interface convention is also an API constraint.

**But the question is live, and the argument on the other side is not weak:**

| | accept 27 (this page) | accept 10 (`_DATAMAPREAL` less the two) |
| --- | --- | --- |
| what it is | everything declared | everything Gramps offers a person in a chooser |
| ⭐ for | no judgement call; the ruling followed as written | the 17 are types Gramps assigns **itself** to record what a note hangs off — `Event Note` on a note attached to an event. A caller setting one by hand asserts something Gramps normally derives |
| ⛔ against | a caller can put `Child Reference Note` on a note attached to a person, and Gramps will hold it | it is a subset, which is the thing the ruling refused — even though this subset is **derived** rather than picked |
| cost of being wrong | a note carries an odd type; nothing is lost, and it is editable in Gramps | a type the owner legitimately wants is refused |

⚠️ **Narrowing later is a one-line change to the derivation and re-derives
nothing**, because the table records which list each row came from. That
asymmetry is why this page defaults to the wider reading: it is the cheaper
mistake to correct, and the record needed to correct it is already committed.

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
| **a live check before anything is written** — the writer compares its inlined names against the running `NoteType` once, and refuses the **whole document** with a message naming the drift | the honest one, and the only one that cannot fail after approval. Costs a startup or per-write pass over 27 names |
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

⚠️ **And a smaller one.** If the preview cannot show the type without changing the
rendering of untyped notes, criterion 6 collides with criterion 5, and the
collision is the thing to bring back rather than to resolve by picking one.

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
recommended. ⛔ **Not a hand-written twenty-seven-row list.** That is the one
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
