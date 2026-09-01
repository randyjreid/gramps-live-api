# Phase 1 — `core/schema`

> ⛔ **A RECORD OF WHAT PHASE 1 WAS SPECIFIED TO BE, NOT CURRENT INTENT.** It is
> undated and written in the imperative, which reads as a live plan; it is not
> one. What shipped is in `src/gramps_live_api/core/`, and the tests are the
> current statement of behaviour.


**Milestone:** `Phase 1 - core/schema` · **Tracking issue:** #19

This is the authoritative specification for Phase 1. It was drafted before the phase began, redacted,
and committed here at intake — because a specification that lives only in a scratch directory is a
specification the next reader cannot find.

⚠️ **Every path and every genealogical value in this document is described rather than spelled.** The
guard scans everything committed, and a document about an operation model that quotes genealogy
formats is exactly the kind that trips it. `docs/pii-guard-acceptance.md` is written under the same
constraint and explains why.

---

## Goal

Define the **operation model** — the vocabulary in which an agreed genealogical fact is expressed
before it is written to the tree — and validate it as far as the frozen Phase-1 rule table allows,
**without a database**.

This is the contract every later phase speaks. `core/apply` executes these; `bridge/server` accepts
them over HTTP; the MCP client emits them. Getting the vocabulary wrong is expensive later, which is
why it comes before the write path.

## Why this exists — the workflow it has to serve

A human reads a record, extracts facts, and **agrees them**. Only then is anything written. The
operation model is what "the agreed extraction" looks like in machine-readable form, so that what was
agreed and what is written are provably the same thing.

Two consequences bind the design:

1. **Every operation must be renderable as human-readable prose for review before it executes.**
   If an operation cannot be described in one sentence a person can check against a record, it is the
   wrong granularity.
2. **Every fact-asserting operation carries provenance.** A fact enters the tree because a specific
   piece of evidence supports it, and an operation that asserts a fact with no citation is the
   failure mode this whole project exists to avoid.

   ⚠️ **"Fact-asserting" is load-bearing here and is a classification, not a judgement made afresh
   per operation** — see the provenance rule below, which partitions the registry. An operation
   classified `NON_FACT`, such as `add_note`, requires **no citation field at all**. That is not a
   weaker version of the same requirement; it is a different kind of operation, and what it must
   carry instead is the recorded one-line rationale for why it is exempt. An earlier wording said
   *"every operation"*, which left the schema and the negative tests for a note undecidable.

---

## ⭐ The validation boundary — state it, do not blur it

Schema validation without a database is **necessarily incomplete**. The danger is a module that feels
authoritative and silently defers the real checks to `core/apply`.

- **Phase 1 validates** — shape, required fields, enum membership, type correctness, internal
  consistency (a date range whose end precedes its start), reference *syntax*, provenance presence,
  and — where a field declares one — an explicit **not recorded** value, which is shape like any
  other value.
- **Phase 3 validates** — existence (does this handle resolve?), referential integrity, duplicate
  detection, and anything requiring tree state.

⚠️ **Whether the record truly omits the part is on NEITHER side of that table.** It is the
researcher's reading of a document, and no phase checks it — the same standing the boundary already
takes on whether a citation supports what it is attached to. What Phase 1 decides is that the value
is well-formed where it appears, and nothing more.

The explicit value adds **no rule and no row**: a marker at a field whose declaration does not admit
it is already reported as a wrong type at that path, by the same rule that judges every other value
the wire delivers.

A validated operation is **well-formed, not correct.** The module docstring says so, and a test
asserts that a syntactically perfect reference to a nonexistent object passes Phase 1. The result
type is named `WellFormed`, not `Valid`, so the distinction is hard to misread.

⚠️ **This boundary is a frozen table, not prose.** *"Validate as far as is possible without a
database"* was the original wording and it has no fixed point — a reviewer can always name one more
check that is possible. Each validation rule is declared in a table mapping its id to `PHASE_1` or
`PHASE_3`, and a structural test asserts that every rule the validator can emit appears in the table
and that no `PHASE_3` rule can fire from `validate`. The exit condition is *"the table is total and
nothing outside it fires"*, which closes.

**Residual, stated rather than chased:** *which* rules belong on which side is judgement, not proof.
The table makes the classification visible and reviewable; it does not make it correct.

---

## Decisions

These were open questions in the draft. All are ruled; a spec carrying open questions after they are
answered is the stale-artifact defect this phase is separately fixing in `README.md` (#24).

**D1 — Dates: the Gramps dependency.** Genealogical dates are not dates. They are ranges,
approximations, spans, partial dates, dual dates, and non-Gregorian calendars, and the model must
express uncertainty rather than flatten it — the motivating case is a birth year attested by several
sources that divide evenly between two adjacent years, which a single-value model cannot hold.

**Verified against a named release, because a decision whose evidence cannot be reproduced is not a
recorded decision.** Assessed at **Gramps 6.0.8**, read from that release's PyPI JSON metadata on
2026-08-12:

| Fact | Value at 6.0.8 |
| --- | --- |
| Wheel | `gramps-6.0.8-py3-none-any.whl` — pure Python, no compiled extension |
| Mandatory dependency | `orjson`, and nothing else |
| GTK bindings | `PyGObject` and `pycairo`, behind the `gui` and `all` extras |
| `requires_python` | **not declared** |

So a dependency in `core/` is **possible**, and "no Gramps dependency" was a choice rather than a
constraint.

⚠️ **This assessment is version-bound and nothing currently pins it.** `pyproject.toml` declares no
dependency on Gramps and therefore no constraint, so a later resolve could select a release whose
metadata or import behaviour differs from the table above — applying a ruling to a package nobody
checked. **#21 records the version it actually verifies and constrains the dependency to a range
that assessment covers**, rather than inheriting this table on trust. Re-read the metadata rather
than citing this document if the release moves.

**Ruled: use Gramps' `Date` model directly.** A wrong date silently written into a tree is the
expensive failure here, and a hand-rolled model mapped in `core/apply` puts a lossy translation layer
exactly where bugs live.

⚠️ **Conditional on an import check that runs first.** Metadata proves declared dependencies, not the
import graph — it does not prove the data-model module imports without GTK present. If the import
fails on any of 3.10, 3.11 or 3.12, **fall back to a hand-rolled model and record why.** The
distribution also declares no minimum Python version, so our own CI matrix is the only thing
enforcing our floor.

**D2 — References.** Gramps has internal handles (opaque and stable) and Gramps IDs (user-visible and
mutable). **Recommended, not mandated:** handles as machine identity, Gramps IDs as the
human-readable rendering, with the preview required to show the ID and never a bare handle — an
operation a person cannot check is not reviewable. The plan gate for #20 may override this with
reasoning. External identifier systems are out of scope.

**D3 — Closed or extensible operation set. Ruled: closed.** The provenance partition below is what
makes this phase's most important property assertable, and it requires a closed registry. An open set
makes that property unfalsifiable, which is the Phase 0 failure mode relocated into the vocabulary.
If extensibility is ever wanted it arrives with forced classification at registration, as a
later-phase decision.

**D4 — Delete operations. Ruled: not in Phase 1** (#25). Modelling delete is harmless in itself —
Phase 1 writes nothing — but it puts a delete operation into the vocabulary `core/apply` is expected
to implement, and the backup mechanism exists precisely to precede that. The closed registry makes
adding it later cheap.

---

## The provenance rule

**No operation may assert a genealogical fact without a citation reference.**

⚠️ **The exceptions are a partition, not a list.** The draft said *"a note or a to-do is not a
genealogical fact and is the obvious exception; name any others you find"* — an open exception list
pointed forward, which is a fail-open by construction on the one property that matters most here.

Instead: every registered operation is in **exactly one** of `FACT_ASSERTING` or `NON_FACT`. A
structural test asserts the partition is total and disjoint over the registry, so **an operation
added without being classified fails the build.**

**What this does not catch:** a misclassification — a fact-asserting operation placed in `NON_FACT`.
The partition proves totality, not correctness. Every `NON_FACT` member therefore carries a one-line
recorded rationale, and that is what review checks.

---

## The operation set

Derived from real research work rather than invented. `add_citation` is the most common single
operation: attaching evidence to an object that already exists.

| Operation | Issue | Why it is here |
| --- | --- | --- |
| `add_citation` | #20 | Attach evidence to an existing object |
| `add_note` | #20 | Research notes and to-dos, attached to any object |
| `add_event` / `update_event` | #23 | Birth, death, burial, residence, immigration — the bulk of the work |
| `add_source` | #23 | A register or record set, cited in a recognised citation style |
| `add_media_reference` | #23 | Link an evidence image already on disk |
| `add_person` | #22 | Newly discovered individuals |
| `add_place` | #22 | Places must match an external place authority's naming, not be invented |
| `update_name` | #22 | Variants, spelling corrections, and misread transcriptions |
| `link_child_to_family` / `link_spouse_to_family` | #22 | The relationships that are the actual product |
| `delete_event` | #25 | **Deferred** — see D4 |

⚠️ **#40 adds no operation type.** A record naming one part of a name is expressed by a **value**,
not by another row in this table.

`add_citation` and `add_note` are built first, together, because they exercise both sides of the
provenance partition while needing no date model.

---

## Acceptance criteria

**Recorded here, in version control.** The issues carry working copies and are where the work is
tracked, but an issue is mutable, external, and unreadable from an offline checkout — so a
specification that pointed at issue numbers instead of stating its own exit conditions would be the
same defect this document was committed to fix, in a different medium.

Where the two ever disagree, **this file is authoritative** and the issue is stale.

Every issue below additionally carries the standing gates: `ruff check .`, `ruff format --check .`,
`mypy src` and `pytest` all clean; the PII guard reporting zero findings over tracked content and
over the pushed range; CI green on 3.10, 3.11 and 3.12. Fixtures use invented surnames only, and no
date, name or place from any real tree.

### The spine — #20

1. A **closed** operation registry. A structural test asserts every registered type is in exactly one
   of `FACT_ASSERTING` / `NON_FACT`; a type in neither, or in both, fails.
2. `add_citation` and `add_note` registered and validated, each with at least one positive and one
   negative test **per required field**.
3. `validate(op)` returns a `WellFormedResult` — the name contains `WellFormed`, not `Valid`. The
   module docstring states that well-formed is not correct. A test asserts a syntactically
   well-formed reference to a nonexistent object **passes**.
4. Validation rules declared in a frozen `PHASE_1` / `PHASE_3` table, with a structural test that
   every rule the validator can emit is in the table and no `PHASE_3` rule can fire from `validate`.
5. Every failure carries a non-empty field path naming a field that exists on the operation, asserted
   over every negative case; and a case with at least three simultaneous distinct errors reports all
   three rather than stopping at the first.
6. Serialise, deserialise, compare equal, for both types. An unknown field is rejected — not ignored
   — at the top level **and** nested at least one level deep. The module's **reserved key**,
   `UNCONVERTIBLE_KEY`, is refused the same way — structurally, at the door, naming the path it sits
   at — at every declared path and below one, in each of the two containers a decoder produces:
   `test_the_reserved_key_is_refused_with_the_path_it_sits_at`. At a reference **root** it stays the
   pre-existing unknown-field refusal instead, because a mapping there is how the wire spells an
   object — `test_the_reserved_key_at_a_reference_root_is_still_unknown`. The two matrices are
   asserted to **partition** every declared path, since two independent comprehensions can drop one
   from both — `test_the_two_reserved_key_matrices_partition_every_declared_path`. Both refusals are
   a `SchemaError` carrying a field path, so nothing a caller handles them by moves; the refusal is
   on the **raising** side of the boundary, so it adds no `RuleId` and no `RULES` row.
7. `preview()` asserted structurally over the registry: non-empty, single-line `str`, containing no
   opaque handle, no `None`, and no default `repr`.

### Not recorded — #40

Every declared field of an operation is required, so a register naming only one part of a name has
no well-formed operation at all. #40 gives the vocabulary a way to say **the record does not give
this part** without collapsing it into optionality, which here already means *this is a reference
root*.

⚠️ **The issue is split, and this heading carries both halves so the deferrals are on the record
rather than in a scratch file.** The **spine** — the marker, its derivation, its wire spelling — is
built now. The **application** — the operations that declare it, and their fixtures — waits for the
reshape in #41, per the accepted OQ5.

⚠️ **The counts below belong to the criteria, not to the files.** Each criterion names the tests
that carry it; the totals of `tests/unit/test_schema_absence.py` and
`tests/unit/test_schema_wire_shape.py` will move later for reasons #40 has nothing to do with, and a
file's count read as a criterion's evidence is a number that goes stale with nothing announcing it.

**Spine criteria — this build.**

1. A single-member marker, closed like the other vocabularies, whose one member spells itself for
   the wire and which the module offers alongside the single key a payload spells it under —
   `test_the_marker_has_exactly_one_member`, `test_the_member_spells_itself_for_the_wire`,
   `test_the_module_offers_the_member_and_its_wire_key`.
2. The fields admitting the marker are **derived from the declaration**, as reference fields already
   are, and the two derivations are disjoint over the same class. A plain text field and a reference
   root are both excluded, and no registered type declares the marker yet —
   `test_absence_is_read_off_the_declaration`,
   `test_a_field_that_cannot_hold_the_marker_is_not_an_absence_field`,
   `test_absence_and_reference_are_disjoint_on_the_same_class`,
   `test_a_class_declaring_no_marker_has_no_absence_field`.
3. The wire spelling converts in both directions, quantified over the enum so a second member is
   covered before it exists; anything that is not the canonical spelling is **not** read as a marker
   and does **not** raise — including an unhashable value under the key, which has a test of its own
   so the type check ahead of the lookup is not removed as redundant —
   `test_the_canonical_spelling_comes_back_as_the_member`, `test_every_member_survives_both_conversions`,
   `test_anything_that_is_not_the_spelling_is_not_a_marker`,
   `test_an_unhashable_value_under_the_key_does_not_raise`.
4. **No new rule and no new row.** A marker at a field whose declaration does not admit it is
   reported as a wrong type **at that path**, both when built as an object and when met from the
   wire, and the two routes agree on the rule and the path — differing only in naming what actually
   arrived, which is the recorded consequence of reading the declaration on the way in —
   `test_a_marker_where_nothing_declares_one_is_judged_at_that_path`,
   `test_the_two_routes_disagree_only_about_what_arrived`. **The matrix reaches reference leaves and
   not only top-level fields:** the exclusion is of a reference **root**, where a mapping is how the
   wire spells an object, and that reason does not reach a leaf, where a mapping is a value in place
   of a declared `str`. The leaf half is a **fence** — green both before and after the change in
   criterion 5, because `validate` reads the object rather than the payload — so it states the
   verdict at a depth nothing had asked it at rather than evidencing new behaviour.
5. **The serialiser's JSON-shaped claim is asserted rather than made — as a property over paths
   *and* over the module's own value grammar, not at whichever depth or shape someone thought of.**
   *Every value the wire carries is JSON-emittable*, quantified over **paths derived from the
   declaration at every depth they reach** and over **values composed from the kinds `_to_wire`
   branches on**. Checked by a structural walk that names the offending path and by the encoder
   itself — `test_a_value_a_decoder_could_have_produced_never_reaches_the_fault_marker_either` and
   `test_to_dict_emits_json_for_any_other_value_the_grammar_composes` (the generated values,
   **partitioned**: see the sampler note below),
   `test_to_dict_emits_json_for_the_deepest_value_at_every_declared_path` (the two dimensions
   crossed), `test_to_dict_emits_json_for_a_marker_at_a_field_that_does_not_declare_it` (every
   declared path against every unemittable atom, whose name records this criterion while its matrix
   is wider than the name), and
   `test_to_dict_emits_json_for_a_container_holding_a_value_the_module_models` (the shapes the
   second round reported, kept by name rather than folded into the generated set, because a
   generator's breadth is a budget somebody will trim and a reported shape must not be trimmable by
   arithmetic).

   ⚠️ **THE CLAIM IS NARROWED, and the one it replaces was FALSE.** For three rounds this criterion
   read *the conversion is TOTAL, and totality is required rather than preferred because there is no
   bound to show.* A property quantified over every value that can be constructed has **no fixed
   point**: interrogating a value runs the value's own code, so a reviewer can construct a fresh
   pathological value every round, indefinitely, and each one is genuine. Three rounds of hardening
   found it false in a new place each time, which is a property being **sampled** rather than a
   conversion being finished — the repository's own rule that an unbounded property cannot be closed
   by review, met head-on.

   ⭐ **What closes:** *`to_dict` is total over **decoder-producible** values — every payload
   `from_dict` accepts converts to a JSON-emittable wire carrying no fault marker, at any depth to
   the encoder's own ceiling.* The space is bounded **in kind** rather than in size, which is the
   whole argument; it is stated in full at the bounded sub-property below.

   ⚠️ **A narrowing can be misread as licence to revert what preceded it, so each surviving piece is
   re-justified on the NARROWED claim's own terms rather than left standing on the old one** — the
   reference recursion, the explicit stack, the cycle handling and the key reservation each carry
   their own reason below, and a piece whose only warrant was the abandoned totality claim would be
   deleted rather than kept.

   **Arbitrary in-process values are best-effort, by design rather than by concession.** `Operation`
   is a transport dataclass whose fields accept anything precisely so `validate` can be the only
   judge, so *reference leaves are the last depth* stays true of the **declaration** — `ObjectRef`'s
   three leaves are all `str`, so the declared depth is exactly 2 — and false of the values. A
   bounded enumeration would still be an enumeration of nothing in particular: patch the containers
   and dicts of lists remain, then lists of dicts of references, one reviewer round at a time. A
   conversion written for the 14 paths that exist today would close them and state nothing about why
   those were the right 14.

   ⚠️ **The residual, recorded with its evidence rather than defended.** Interrogation runs the
   object's own code — `list(value)` calls its `__iter__` and its `__len__`, `isinstance` reads its
   `__class__` — so an object can raise before any branch decides anything. Measured at
   `target.handle` of the `add_note` example:

   | value | `to_dict` | `validate` |
   | --- | --- | --- |
   | released `memoryview` | `ValueError`, CPython's own message | `FIELD_WRONG_TYPE` at the path |
   | `Sequence` whose `__iter__` raises | `ValueError`, **the caller's own message** | as above |
   | `Sequence` whose `__len__` raises | `ValueError`, **the caller's own message** | as above |

   In every case the exception arrives **as itself**, neither masked as the fault marker nor
   swallowed — `test_an_exception_from_the_callers_own_object_propagates_as_itself`. The
   `memoryview` is the one of the three that is a **standard library type** and it reaches the
   sequence branch by no accident: `_collections_abc` carries `Sequence.register(memoryview)`, so it
   is stable across 3.10–3.12 rather than an artefact of one version.

   ⚠️ **These three are NOT a closable set and must not be read as an enumeration to extend.**
   `__iter__`, `__len__`, `__eq__`, `__hash__`, `__getitem__` and a raising `__class__` are **one
   defect with no enumeration**, because the defect is that interrogation runs the object's code
   rather than any particular dunder. A fourth is always constructible — which is exactly why the
   claim above is bounded instead of being defended here.

   ⭐ **The remedy, stated where a caller meets it rather than in a commit message: `validate` reads
   the object WITHOUT transporting it**, and returns `FIELD_WRONG_TYPE` at the field path in every
   case measured. A caller wanting a verdict on a pathological value calls `validate`, which is what
   it is for. Recorded on `to_dict`'s own docstring, the public surface.

   ⚠️ **No broad exception handler is added, and the reason is written where the change would be
   made.** A blanket `except Exception` emitting the fault marker would make **our own defect
   indistinguishable from the caller's bad data**: every future bug in the conversion would surface
   as a well-formed payload naming the caller's type, and the one signal that says *something here
   is wrong and it is not yours* would be gone. That is the trade this module has now refused four
   times, and the fence test above is what makes adding one fail a test rather than pass review.

   ⚠️ **The recursion into a reference's leaves is required by the BOUNDED claim too**, not only by
   the in-process side that motivated it — a decoder puts a nested `dict` at `target.handle` as
   readily as anything else. Recorded because the narrowing otherwise reads as licence to delete it.

   ⚠️ **A value the module cannot model emits a marker under `UNCONVERTIBLE_KEY` naming its type,
   and does not raise.** The trade, stated: a marker reaches `validate`, which already returns
   `FIELD_WRONG_TYPE` at that path, and reports the fault where every other value fault is reported;
   a typed transport error reports it out of a surface that has no field path, and is therefore this
   finding with a better name. The module already draws exactly this line — a **structural** fault
   raises, a **value** fault does not, because refusing one would be a second validator with no
   vocabulary for saying where. The cost taken: an invalid operation's payload is lossy at that leaf.
   **Unmodellable and modellable-but-misplaced share the surface and differ only in the payload**,
   so a caller's handling never depends on a distinction it cannot predict; a modellable value keeps
   its faithful spelling and only an unmodellable one is replaced. The marker names the **type and
   never the value**, which is `RuleViolation`'s rule obeyed by the transport.

   ⚠️ **Termination is the other half of "total", and it has TWO halves of its own — cycles and
   depth. For two rounds only the first was written down.**

   ⚠️ **The two halves sit on OPPOSITE sides of the narrowed claim, and saying so is what keeps
   either from being deleted for the wrong reason.** **Depth is inside it** — a decoder produces a
   payload nested as deep as its own ceiling without difficulty, so a conversion that stops short of
   that ceiling makes the bounded claim false. **A cycle is not decoder-producible at all**, JSON being a tree, so cycle
   termination serves the best-effort side. It stays regardless, and on its own merits rather than
   on the claim's: without it the walk does not terminate, and non-termination is the one failure
   mode where nothing propagates as itself either — because nothing propagates at all.

   **Cycles.** `x = []; x.append(x)` is constructible in process, so the conversion carries the
   identities of the containers **on the current path** and marks one already there. On the path
   rather than accumulated across the walk: a value reachable twice from different branches is not a
   cycle, and an accumulating set would mark the second sibling — a fail-closed defect on a
   perfectly emittable payload, which `test_a_value_appearing_twice_is_not_read_as_a_cycle` exists
   to catch.

   ⚠️ **Depth.** The conversion was a structural recursion, so it had a ceiling of its own, and that
   ceiling was **below the decoder's**. ⚠️ **The numbers that follow are one box's measurements —
   Windows CPython 3.12.13 at the default recursion limit of 1000 — and none of them is a property
   of `json`.** There: the conversion stopped at depth **995**, while `json.loads` and `json.dumps`
   both reached **2997**. Between those two numbers a payload was decoder-producible, was accepted
   by `from_dict` and could not be carried — `RecursionError`, which is neither of the two outcomes
   this criterion allows. **That band sits inside the bounded sub-property below, so it was a
   correction to a claim that was false, not a residual.** The conversion now carries an **explicit
   stack**: depth is bounded by memory rather than by the interpreter's frame budget, measured
   usable at depth **200 000** in 0.371 s on that same box. ⭐ **The ceiling that remains is
   CPython's own json module rather than this module's — decoder and encoder draw on the same
   interpreter budget, so above whichever of them binds first a payload is neither
   decoder-producible nor encoder-emittable, and the band is CLOSED rather than narrowed** —
   `test_a_value_nested_past_the_frame_limit_reaches_the_wire`.

   ⚠️ **Where that ceiling sits is an interpreter's answer, not a constant, and one interpreter's
   answer was written into the test file as a literal `2000`.** On 3.12 the C json module carries a
   recursion budget of its own; on 3.10 and 3.11 it draws on the same budget Python frames do, so
   the ceiling lands far lower there **and moves with the caller's stack depth**. The literal was
   comfortably inside the band on 3.12 and blew the stack inside the tests' own builders on 3.10 and
   3.11. `_PAST_THE_FRAME_LIMIT` is now **measured at import** by `_deepest_nesting_json_carries`,
   which doubles and then bisects on `json.dumps(json.loads(...))` — both directions in one trial,
   so the answer is the lesser of the two ceilings — from a deliberately padded stack, and raises on
   a degenerate answer so that a broken probe can read neither as a test failure nor as a pass. The
   trial spends the container levels the depth tests wrap around the value (`_WRAPPING_LEVELS`, 4,
   counted off the four tests) before it measures, so what it answers is a depth those tests can use
   and nothing is subtracted from it afterwards. ⚠️ **The pad depth is itself a chosen number**,
   recorded as one on the constant that holds it rather than argued away.
   ⚠️ **Recorded residual: on 3.10 and 3.11 the derived depth lands below the old recursion's 995,
   so the names `_PAST_THE_FRAME_LIMIT`, `..._past_the_frame_limit` and `..._below_the_frame_limit`
   are false there.** Kept rather than rippled through four test names and the references below;
   stated in the constant's own docstring.

   ⚠️ **Catching `RecursionError` and emitting the fault marker is much the smaller change, and it
   was rejected on merits.** It would turn a deep decoder-producible payload into silent data
   loss, making the marker appear for exactly the payloads the bounded claim says it never appears
   for; and `RecursionError` fires when the **interpreter's** budget runs out rather than at a
   property of the value, so the emitted payload would be a function of the caller's stack depth —
   measured, the old ceiling was 995 from a module-level call and **895 from one a hundred frames
   down**. The same operation would serialise differently depending on where it was called from.

   ⚠️ **A work list does not unwind, so the path scoping that came free from the call stack is now
   maintained deliberately**: the ancestors live in a list **truncated to the popped entry's own
   depth** before that entry is processed, which depth-first order makes exact. Both halves of that
   discipline are pinned, because one test cannot do it — an implementation that never truncates
   passes the cycle test, and one that truncates too far passes the sibling test:
   `test_a_value_appearing_twice_is_not_read_as_a_cycle_at_depth` and
   `test_a_cycle_closed_below_the_frame_limit_still_terminates`. Carrying a `frozenset` per stack
   entry — literally the old expression, and by far the smaller diff — was prototyped and rejected
   on **measurement**: quadratic in depth, 8.731 s at depth 30 000 against 0.349 s for the truncated
   path at 200 000.

   ⚠️ **The output container is pre-populated with its keys in source order before its children are
   pushed**, because a LIFO stack completes children in reverse and a mapping filled in completion
   order would reverse every JSON object's keys — both canonical payloads would move with nothing
   saying so, since the fence checks JSON-ness and not bytes.
   `test_a_mapping_keeps_its_key_order_on_the_wire` asserts it in bytes, and is a shape guard rather
   than evidence.

   **The generator's budget, stated because a sample's size is a cost every future run pays.
   ⚠️ These numbers are the CRITERION's, and they are the constants in the file; they are not any
   file's test count, which moves for reasons this criterion has nothing to do with.**

   | | |
   | --- | --- |
   | atoms, one per branch the conversion takes | **6** |
   | composers, one per container it knows about | **5** |
   | exhaustive composition depth | **1** — 6 + 30 = **36** values |
   | one spine value per depth 2–6 | **5** values |
   | generated values, placed at each type's first reference leaf | **41** |

   **The exhaustive depth is 1 and not 2 deliberately.** Depth 2 was measured at 186 values and 380
   cases — a **44%** suite growth, of which the second exhaustive level alone was 74%. What that
   level buys is the cross product of the composers *with each other*, which is what a structural
   recursion gives for free once each branch is right, so it is the level that was cut; composition
   is still exercised by the spine, five composers deep, for five values. **The spine depth stays at
   6** because depth is the dimension both previous rounds were wrong about and it costs one value
   per level.

   ⚠️ **And it stays at 6 even though the frame limit is now the depth question**, which is the one
   place that reasoning could have been read the other way. Raising the spine past the old ceiling
   would cost ~991 extra values ≈ **1 982 extra cases** on an **82**-case criterion, and past the
   encoder's ~5 982 — a 2× to 6× suite growth to sample one dimension, where every level past the
   first cycle of composers is the same five branches again. **Depth past the frame limit is bought
   by the four named tests above instead, for four cases.** The generator's own tripwire
   `test_the_generated_values_reach_the_stated_depth` measures with a recursive helper that shares
   the old ceiling, so raising the spine past it would force that helper iterative too, for no gain;
   sweeping the suite's remaining recursive walks belongs to the general repair, not here.

   ⚠️ **The sampler is PARTITIONED on what a decoder can produce — relabelled, not truncated — and
   the budget above does NOT move.** Two different claims are true of the generated values, and
   asserting them together stated the weaker one about both. The **9 of 41** values a decoder could
   have produced now carry the **strong** claim — JSON-emittable *and the fault marker never
   appears*, which is the bounded claim sampled across the grammar's breadth. The other **32** carry
   the honest **best-effort** one — JSON-emittable, marker permitted, since for a value nothing
   models the marker is the correct answer — and are labelled in the file as evidence rather than as
   something that closes.

   **Why partition rather than scope it down**, measured: those nine values *are* the closer's own
   `_DECODED_VALUES` under other names, so a strictly rescoped sampler would not become a sampler
   that closes something — it would become a **duplicate of the closer**. It would cost **−46
   cases** (`GENERATED` 41 → 25 and its matrix 82 → 50, `_UNEMITTABLE` 3 → 2 so the every-declared-
   path marker matrix 42 → 28, `_KINDS` 7 → 4), deleting the **generative coverage of the fault
   marker at every declared path** — which this criterion names as *inside* the bounded claim and
   does not revert. Same 82 cases, then, and the half that can carry the strong claim now carries
   it. The partition's own tripwire is the **83rd** case:
   `test_the_partition_covers_the_generated_values_and_neither_half_is_empty`, which catches an
   empty strong half reading as the thing that closes, a blind predicate waving everything through
   as producible, and a value dropped from **both** halves by two independent comprehensions.

   **Tripwires, because an empty matrix, a shallow one and a narrow one all read as coverage.** Each
   is computed by the test file's own walk rather than by asking the module, and each is green on
   arrival and is not evidence: `test_the_generated_marker_matrix_is_not_empty`,
   `test_the_marker_matrix_reaches_a_nested_path`,
   `test_the_generated_value_set_is_not_empty_and_names_each_value_once`,
   `test_the_generated_values_reach_the_stated_depth` (the **measured** maximum depth equals the
   stated 6, so a composer that stops composing fails here rather than reading as coverage) and
   `test_every_kind_the_conversion_branches_on_is_generated` (a composer dropped from the table
   deletes a kind while still generating plenty). The nested-path guard is not decoration — the
   first version of this criterion asserted the claim at the top level only and stayed green while a
   marker inside a reference was emitted raw and `json.dumps` raised, leaving an invalid operation
   **untransportable rather than reportably invalid**.

   ⭐ **The bounded sub-property is what CLOSES this criterion**, per the rule that an unbounded
   property cannot be closed by review: the generative property above **samples** an infinite space,
   so a reviewer asked to construct a value outside the sample will succeed every round, for ever.
   The claim that closes is *for every payload a JSON decoder could have produced and `from_dict`
   accepts, `to_dict` emits JSON **and the fault marker never appears**, **at any depth to the
   encoder's own ceiling*** —
   `test_a_payload_a_decoder_could_have_produced_never_reaches_the_fault_marker` (breadth, over
   every required path) and
   `test_a_payload_a_decoder_could_have_produced_reaches_the_wire_at_depth` (the same paths at
   `_PAST_THE_FRAME_LIMIT`). The space is
   bounded **in kind**: a decoder emits `dict`, `list`, `str`, a number, a bool and `null`, a JSON
   object is string-keyed, and the only other things `from_dict` builds are an `ObjectRef` of
   decoded values and the marker — every one of which takes a branch that converts.
   ⚠️ **The decoder qualifier is load-bearing rather than a hedge**: `from_dict` takes a `Mapping`,
   so a caller can hand it one built in process holding a value nothing models, and the marker would
   appear for that — the unbounded side, by design.

   ⚠️ **The DEPTH clause was claimed before it was asserted, and that is the gap this round
   closed.** For one round the closer was quantified over `_DECODED_VALUES`, whose deepest member
   nests **3** levels, while the depth work above reached the interpreter's ceiling with a value
   built **in process** — never through `from_dict` — and asserted JSON-emittability without ever
   asking about the marker.
   **Two dimensions, each asserted with the other held at its cheapest**, which is round 1's defect
   and round 2's defect a third time. The deep case builds its value with `json.loads`, so
   *decoder-producible* is a fact about the value rather than the test file's opinion of it;
   measured, **11 of the 14 paths are accepted and 3 refused structurally**, zero fault markers.
   Writing it went **red in the test file's own machinery** — `_names_the_fault_marker` was a
   recursion and died at that depth — which is the third walk to have needed an explicit stack, and
   the rule that a walk in that file is written iterative from the start is now recorded on it
   rather than learned a fourth time.

   **Recorded consequences, met here rather than discovered later.**

   - **No valid operation's payload moves.** Every value a registered type carries is a `str` or an
     `ObjectRef` of `str`s, which take branches that already existed. Verified by dumping both
     canonical payloads before the change and comparing bytes after — and again, by the same
     method, when the conversion became iterative.
   - ⚠️ **Above the encoder's own ceiling the `RecursionError` moves from the transport to the
     encoder.** `to_dict` now *succeeds* there and returns a structure `json.dumps` cannot encode.
     This is a change in **where** an unencodable value fails rather than a regression: it used to
     fail earlier and harder, at the conversion's own ceiling — 995 against 2997 on the box
     measured above. It is recorded rather than implied, and it is not a band: nothing above the
     encoder's ceiling is decoder-producible either, because both draw on the same interpreter's
     budget, so no payload reaches it from the wire. **The ceiling is named by where it comes from
     rather than by a number**, since the number is a different one on 3.10 and 3.11.
   - A **tuple** at a field now emits a JSON array instead of raising, so that operation is no
     longer round-trip identical. Correct — JSON has no tuple — and reachable only on an operation
     that is invalid either way. No fixture carries one.
   - The marker at a **reference root** comes back through `from_dict` as
     `UnknownFieldError("target.unconvertible")`. That is the pre-existing structural surface for an
     undeclared key inside a reference, unchanged by this work — and now **pinned** rather than
     merely recorded, since the reservation below could have taken it over and must not.

   ⚠️ **The marker's key is RESERVED, and until it was the bounded claim above was FALSE rather than
   narrow.** `UNCONVERTIBLE_KEY` is an in-band signal, and it was not injective: `{"unconvertible":
   "set"}` at a declared field is decoder-producible, `from_dict` accepted it untouched, and
   `to_dict` re-emitted it **byte-identical** to a genuine conversion failure. So *the fault marker
   never appears* was false on a payload the claim covers, and green only because no sampled value
   spelled the key. `from_dict` now refuses it at the door with a field path. Three things about the
   refusal, each load-bearing:

   - **On key PRESENCE, not on the marker's exact one-key shape.** The detector the closer runs
     (`_names_the_fault_marker`) reads a payload as a marker when any mapping *contains* the key, so
     a narrower refusal would leave payloads the detector still calls markers — and the closer would
     go on being *untriggered* instead of becoming *true*. Matching the detector exactly is the
     argument, and it is why the two new values are in `_DECODED_VALUES` and not only in a
     hand-written case: `test_a_decoded_value_naming_the_fault_marker_is_refused_at_every_path` is
     what keeps the closer's `except SchemaError: continue` from being the vacuous way to pass.
   - **An explicit stack — the FOURTH walk to need one.** The depth case above pushes a
     decoder-produced list nested to the interpreter's own json ceiling through `from_dict`, so a
     recursive refusal would die on exactly the payload the claim says is carried.
   - ⚠️ **`dict` and `list` by `isinstance`, so a `Mapping` that is not a `dict` carrying the key is
     NOT refused — a cost taken rather than silently taken.** A decoder produces exactly `dict` and
     `list`, so this is the bounded claim's own boundary; a `MappingProxyType` built in process is
     the best-effort side, and widening the walk to every `Mapping` would refuse values no decoder
     can hand in, on a claim that does not ask for it.

   The walk also **marks containers it has already visited**, so a cyclic in-process payload
   terminates. Accumulated across the walk rather than scoped to the current path — the opposite of
   `_to_wire`, and deliberately: a container that did not raise once cannot raise later, so
   revisiting only costs time and the fail-closed defect path-scoping prevents there has no
   counterpart here. It is on the **best-effort** side by the same reading as cycles above, and it is
   pinned in both directions, because one test cannot do it —
   `test_a_cyclic_payload_value_carrying_no_reserved_key_still_arrives` and
   `test_a_cyclic_payload_value_carrying_the_reserved_key_is_still_refused`.

   ⭐ **The precedent, recorded because it outlives this key: an in-band signal must be INJECTIVE —
   by reservation or by escaping.** Those are the two shapes there are. This key takes reservation
   because it has exactly one producer and the refusal is cheap; escaping would have to be undone on
   the way out and asserted in both directions. ⚠️ **It decides the shape of #53 whenever use
   unparks that — nothing here acts on #53 and nothing here unparks it.**

   `UNRECORDED_KEY` is deliberately **not** reserved and is **not** the same defect: it is
   discriminated by **position** — only a field whose declaration admits the marker reads it — so a
   payload spelling it anywhere else is an ordinary value `validate` judges at its path.

   The sweep over the canonical examples, `test_a_canonical_example_serialises_to_something_json_can_emit`,
   is a **regression fence**: green before this work and after, and not evidence of it.
6. **No canonical example carries the marker.** The preview guard's matrix skips any path whose
   example value is not text, so a marker among the examples would drop that field out of the guard
   matrix with nothing reporting it. The tripwire states that mechanism in its own failure message,
   and lives outside the guard file because that file is registry-derived and is not edited —
   `test_no_canonical_example_carries_the_marker`.
7. **The composition is armed and empty, and the emptiness is asserted.** The round-trip over fields
   declaring the marker is written now and quantified over the registry, so it generates no cases
   until a declaration exists and needs no edit when one does —
   `test_a_declared_marker_round_trips_in_both_directions`. Its companion,
   `test_no_registered_type_declares_the_marker_yet`, asserts the emptiness and **fails on purpose**
   when that stops being true, instructing its own deletion, so an empty matrix cannot read as
   coverage.

**Recorded deferrals.** Each is a decision on the record rather than a thing nobody did.

- **A positive assertion of namelessness is not this marker.** *The record does not say* and *the
  person bore none* are deliberately not distinguished. The second asserts a fact about a real
  person, so it needs its own warrant and belongs in the fact vocabulary with a citation obligation
  — **future CITED work**, and the single-member enum is what makes it cheap to add.
- **The cross-field rule is NOT built** (accepted OQ3): an operation with both parts of a name
  unrecorded is well-formed.
- **The application half waits on #41's reshape** (accepted OQ5). Determinacy and the
  unknown-is-a-value framing are cited as pending there (accepted OQ6) and are deliberately not
  written here.

**Application half — #41, and the criterion this build leaves it.** Recorded here because it is the
only thing that closes the spine's residual: the wiring of the two conversions inside deserialisation
is not executable while no registered type declares the marker.

> An operation declaring `str | Unrecorded` round-trips the marker through `to_dict` / `from_dict`
> in both directions and validates clean carrying it, asserted by the registry-quantified suite #40
> left armed. `test_no_registered_type_declares_the_marker_yet` is deleted in the same commit.

### The date model — #21

1. A committed recorded decision answering D1, carrying the verified metadata and stating which
   option was taken — **plus a test that imports whatever the choice implies and passes on 3.10,
   3.11 and 3.12 in CI.**
2. A named, closed list of date kinds — exact; partial (year only, and year with month); approximate;
   range; span; dual-dated; non-Gregorian — with a structural test that every member constructs,
   round-trips, and renders a preview.
3. A range or span whose end precedes its start is not well-formed, and the error names **both**
   fields. Positive control: end equal to start *is* well-formed.
4. **Contested facts are not collapsed.** Two mutually exclusive candidate values, each with its own
   citation, survive a round-trip with **every candidate still paired to the citation that supports
   it**. No test satisfies this by discarding a candidate, and none by detaching one from its
   citation. Asserted in both directions.

   **The criterion names the property, deliberately not where it lives.** Whether the candidates sit
   inside one date value or across several operations is the plan gate's choice below; the round-trip
   assertion is written against whichever locus that plan picks. An earlier wording required *the
   model* to hold both candidates, which silently ruled out one of the two answers the note then went
   on to permit.

   ⚠️ **Open question for #21's plan gate — *where*, given D1.** Gramps' `Date` expresses a single
   date and carries no per-candidate provenance, so a bare `Date` cannot hold this property alone.
   **Answer it in the plan, with a recommendation, before this becomes an exit condition.** Two
   answers are acceptable:

   - **a candidate aggregate of our own, whose individual values are Gramps `Date` objects** — this
     does not violate D1, which governs how a *date value* is represented and not what may hold
     several of them; or
   - **a contested fact expressed as several operations**, one per candidate, each carrying its own
     citation — arguably the more Gramps-native shape, since Gramps expresses competing assertions
     through citations rather than through a multi-valued date.

   What is **not** acceptable is discovering the conflict during the build.
5. Ordering and comparison are either implemented and tested against a named table of pairs, or
   explicitly not provided with the refusal asserted by test.

### Identity-side operations — #22

1. `add_person`, `add_place`, `update_name`, `link_child_to_family`, `link_spouse_to_family`
   registered, and the partition test from #20 covers them **without being modified**.
2. Positive and negative tests per required field, per type.
3. The two `link_*` operations validate reference syntax on both ends, and a test asserts a
   well-formed link between two nonexistent objects **passes**.
4. Provenance classification recorded per type with a one-line rationale. `update_name` is argued
   rather than assumed — a spelling correction taken from a transcription is a sourced claim.
5. `add_place`'s external-authority naming rule is documented, not validated: it sits on the
   `PHASE_3` side of the rule table and a test asserts it cannot fire from `validate`.

### Evidence-side operations — #23

1. `add_event`, `update_event`, `add_source`, `add_media_reference` registered, and the partition
   test from #20 covers them without being modified.
2. Positive and negative tests per required field, per type.
3. Every type carrying a date uses the model from #21 directly; a structural test asserts no
   registered type declares an ad-hoc date field.
4. All four are `FACT_ASSERTING`, and a test asserts each **fails** validation without a citation.
5. `add_media_reference` references an image by path syntax only; a well-formed reference to a
   nonexistent file passes, and a test asserts its fixtures do not trip the guard's path property.

### The remaining two

**#24** — the `README.md` roadmap table matches the milestones row for row, the Status section names
the current phase correctly, and a line records that the milestones are the authority when artifacts
disagree. **#25** — deferred; its criteria apply only once the backup mechanism exists.

### Why three of these are structural

The provenance partition (#20 criterion 1), the rule table (#20 criterion 4) and the preview (#20
criterion 7) are asserted over the registry rather than over a hand-written list of cases, for the
reason `B5` in `docs/pii-guard-acceptance.md` gives: an enumeration fails on the case nobody listed,
and this project's most persistent defect shape is one spelling taught to one matcher. The same
reason is why #22 and #23 each require the inherited structural tests to pass **unmodified** — a test
that must be edited to admit a new type was restated, not derived.

⚠️ **One thing the criteria deliberately do not claim.** *"A sentence a person can check against a
record"* is a human judgement and is **not** an acceptance criterion — it is a reviewer checklist
item. The mechanical preview checks are proxies for it. The proxy carrying real weight is *no bare
handle*: a preview naming an opaque handle is not reviewable at all.

## Out of scope — do not build

- Any database access, any `DbTxn`, any `commit_*` — that is `core/apply`
- The HTTP layer, MCP code, GTK code
- The backup mechanism
- Existence or referential-integrity checking of any kind
- Any operation that writes
- Any delete or destructive operation
- Free-text date parsing, date arithmetic, and calendar conversion
- External identifier systems

## Stop and report rather than deciding

- Any question that cannot be answered without building the write path first
- Any need for a dependency beyond the current set. ⚠️ **The D1 Gramps dependency is already ruled
  and is not a stop condition** — nor is the import check that gates it, which necessarily comes
  before anything is added to a dependency list that is currently empty. Any *further* dependency
  stops, Gramps-side or otherwise. An earlier wording exempted only a "second" Gramps-side
  dependency, which left the implementer told to stop for the very thing D1 decided.
- Any contradiction between criteria
- Any gate that cannot pass without weakening it

## Working rules

- **TDD.** Red, green, refactor, one thing at a time. No production line without a failing test that
  demanded it, and the failing test is shown with its assertion text in the commit or the review.
- A plan gate precedes every build, every fix round, and every refactor. Produce the plan and stop.
- Branch per issue off the merged default branch. Never commit to it directly.
- Conventional commits.
- Fixtures use **invented surnames only**, and no date, name or place from any real tree.
- Do not trust your own account of state: run the commands and report what they say.
