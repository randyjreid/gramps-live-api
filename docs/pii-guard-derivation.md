# Where the guard's container vocabulary comes from

The genealogy property weighs containers by what they mean. **Which containers exist is not a
judgement, and is no longer treated as one.** The list is derived from published specifications and
frozen as a committed table, `src/gramps_live_api/core/_specified_containers.py`, which is
machine-generated and never hand-edited.

This note is the audit trail for that file: what it was generated from, how to check it, and what
the check can and cannot prove.

## Why a derivation at all

Issue #4 was filed with five instances of one defect -- a principle applied to some containers and
not others -- and grew to six while open. Its original exit condition was *every place in either
format where a container can hold prose or an identity field*, which is universally quantified over
a format and cannot be shown to have been reached. It was re-specified: **the container list is
derived from the published specification and frozen, and the audit closes when every row has a
weight and a test.**

The derivation also answers the audit's own question mechanically. *Can this container hold prose
or an identity field* is `(#PCDATA)` versus `EMPTY` versus a child list -- read off the schema
rather than decided by whoever is reading it. What the audit still decides is the **category**, per
row, with a test.

## The three sources

| Artifact | Declared version | SHA-256 as fetched | Fetched |
| --- | --- | --- | --- |
| The Gramps XML DTD, from the project's own source tree at release tag `v6.0.8` | **1.7.2**, stated in the file's own header and in the namespace its `database` attribute fixes | `98a4763424fe53947bc589780b643e5e75b15c46f92e6e1228025c8d51e9c628` | 2026-08-15 |
| The HTML Standard's index of elements (WHATWG) | living standard -- see the warning below | `373ca0a2459147bc9784d362d7437848e6bebdd4a61ad36eabf24748b11ff77c` | 2026-08-15 |
| SVG 2, Appendix F: Element Index (W3C) | SVG 2 | `cdf201e0a6588896b7b1bae739ac80f7bbd44f25a2a76632a2f6762f94d02744` | 2026-08-15 |

Where each was fetched from:

- `https://raw.githubusercontent.com/gramps-project/gramps/v6.0.8/data/grampsxml.dtd`
- `https://html.spec.whatwg.org/multipage/indices.html`
- `https://www.w3.org/TR/SVG2/eltindex.html`

The digests are also carried in the generated module itself, as `SOURCE_DIGESTS`, so the file
states what it was made from without depending on this note surviving beside it.

⚠️ **All three digests were re-confirmed on 2026-08-15 when the table was regenerated** to add the
emission described below. None had moved, including the living standard's.

⚠️ **The declared version is 1.7.2, not the 1.7.1 the plan for this work recorded.** Both current
release tags carry 1.7.2 and 107 element declarations; the 1.7.1 figure came from an earlier
reading and is superseded. Recorded rather than quietly corrected, because the number was used to
size the change.

⚠️ **A release TAG is pinned, not a branch.** The same file on the development branch is a moving
target, so its digest would be stale the day after it was taken and the reproduction check below
would fail for a reason that has nothing to do with this repository.

### Why the last two are needed at all

The schema declares `title`, `style`, `code`, `map`, `object`, `source` and `header`. **Those are
HTML and SVG element names.** Weighted at even the smallest weight, four filled ones reach the
threshold, and this repository is full of markup. So a schema spelling that the published markup
indexes also list is deliberately unweighted -- and the collision is read off those indexes rather
than off a list somebody maintains, on exactly the ground `FILESYSTEM_ROOTS` and the drawing
exemption are accepted: closed, externally specified, and not growing at our discretion.

### What the schema FIXES, and why the guard needs it

The table records an attribute's declared *type* — `CDATA` — and, since the marker gate, the value
the schema **fixes** it at, as `FIXED_ATTRIBUTE_DEFAULTS`. One row: the namespace the DTD requires
the `xmlns` attribute of its document element to carry.

That row is what stops the guard's namespace constant being the one thing in the marker gate
maintained by hand. The namespace is a *value*, and until this emission there was nothing in the
table to bind it to.

⚠️ **The gate now reads that row and nothing else, and it used to read three markers.** The other
two were a doctype whose `Name` was the document element, and that element carrying an `xmlns`
attribute at all. Both read *structure* and never a value, so a document declaring an unrelated
namespace or identifier was read as Gramps -- the generic-XML false positive the gate exists to
remove. **Bound to this row they would have matched nothing the substring test does not**, since the
guard's constant is asserted to be a substring of the reassembled value; the doctype could not be
bound at all, because the only Gramps-specific evidence it carries beyond the namespace is the public
identifier and the DTD does not declare its own. So they were deleted rather than tightened. The
argument, the measurement and the residual it creates are in CONTRIBUTING.

⚠️ **The value is emitted SPLIT at each `/`, and is never written whole.** This module is tracked
content the repository's own guard scans, and the guard scores that namespace as a substring
wherever it appears — its constant's own note records the published range showing it **43 times**
when an anchor came off. This emission puts such a value into a tracked `.py` file for the first
time. The split is deterministic given the value, so the byte-for-byte reproduction check below is
untouched; rejoin the pieces with a forward slash.

⚠️ **The parser reads the whole `AttType` production, and that is a repair rather than a
refinement.** The attribute type used to be matched as `(…)|[A-Z]+`, which read a composite
`foo NOTATION (gif) #IMPLIED` as an attribute named `notation` — and, because the later match
consumed the declaration's tail, the fail-closed remainder check passed as well. **The fabricated
row is visible in a re-derivation diff and the attribute it displaced is not**, which is the actual
exposure: a check that cannot see what it claims to check. The type is now XML 1.0 §3.3.1's closed
production, longest alternative first, so an unknown token cannot match and the refusal happens.
`DefaultDecl` also accepts a single-quoted `AttValue`, which it previously refused. Neither changed
a byte of the committed table — the pinned schema declares no composite type and no single-quoted
default — and both are asserted offline in `tests/unit/test_derive_specified_containers.py`.

⚠️ **And the fail-closed guarantee is now STRUCTURAL rather than a check, which is the second
repair to the same mechanism.** That remainder check validated the **tail** of an `ATTLIST` body and
nothing else: given `bad WIDGET #IMPLIED good CDATA #IMPLIED`, the scan skipped the definition it
could not read, the later match carried the consumed offset to the end, the remainder was empty, and
the script emitted a partial table while reporting that it never would. Same shape as the defect
above — something the pattern could not read was passed over and the check succeeded anyway — and the
silent omission is again the exposure a re-derivation diff cannot show.

So the mechanism was **replaced rather than given a third check**. `attributes_of` consumes the body
left to right and **cannot advance past a byte it did not match**, which means *nothing was skipped*
stops being a property somebody has to verify by reading two checks and confirming both are placed
correctly. The refusal now quotes the *first* unreadable text rather than whatever survived to the
tail. The two properties are asserted as a non-vacuity pair — an unreadable definition at the start,
in the middle **and** at the end each stops the derivation, and a list of readable definitions is
read whole and in declaration order — so neither can be satisfied by weakening the other. The
committed table is again unchanged: the pinned schema has no gap for the repair to find, confirmed by
a full re-derivation over digest-matching artifacts returning an empty diff.

## What is NOT committed, and why

The fetched artifacts themselves. A `.dtd` or an `.html` file is refused by the fail-closed
file-type gate, and widening that constant to admit a build input is a change to a different
property -- the one B3 states. The digests above are what stands in for the bytes.

## How to check the derivation

Fetch each artifact, confirm its digest matches the table above, then:

```sh
python scripts/derive_specified_containers.py <dtd> <html index> <svg index> \
    > src/gramps_live_api/core/_specified_containers.py
git diff --exit-code src/gramps_live_api/core/_specified_containers.py
```

**An empty diff is the check.** The script emits no timestamp for exactly this reason: a fetch date
is a fact about a fetch rather than about a specification, and stamping one would make every
re-derivation differ from the file it is checking.

⚠️ **CI never fetches anything, and no test performs network I/O.** The offline suite asserts the
committed table against the *weighting* table instead --
`test_every_container_the_published_schema_declares_has_a_weight` and its twin
`test_the_compiled_scorer_agrees_with_the_vocabulary_for_every_row`. Between them, every row of the
frozen table has a weight and a test, which is issue #4's exit condition stated mechanically.

⚠️ **The HTML index is a LIVING STANDARD, so its digest will eventually stop matching, and that is
not a gate failing.** It means the published index moved. The correct response is a deliberate
re-derivation whose diff is read -- not a suppression, and not a silent pass. There is no frozen
alternative to fall back on: W3C retired its own HTML Recommendation and now redirects
`/TR/html52/` to the WHATWG document, so the living standard *is* the published element index.

## What this closes, and what it does not

**Closes:** the container list is finite, externally specified, and every row of it is weighted and
tested. A row added by a later schema version extends both derived tests without either being
edited.

**Does not close** -- recorded rather than chased:

- **Custom and extension elements the published schema does not define.** The deny-list is the
  backstop, here as for every other residual.
- **Schema versions other than the pinned one.** A container added in a future version is not in
  this table until the table is re-derived.
- **The judgement in the middle.** The schema says which containers exist and which can hold
  character data. It does not say which of them carry identity, and that assignment is this
  project's, per row, defended by the tests rather than by the specification.
- ⭐ **A genuine fragment quoted without its marker, scoring only on rows this derivation added.**
  Some of the containers the schema declares are ordinary XML names, so a derived row scores only
  where the document names the format -- and the price is that a researcher block quoted on its own
  goes from **6 to 0**, and an events block of two events from **4 to 0**. Measured, both
  directions, in CONTRIBUTING. What is not lost, and what makes it affordable: the 29 spellings the
  vocabulary held before the derivation -- the rows that name a person on their own -- score exactly
  as they did, marker or no marker.
- ⭐ **A genuine document naming itself ONLY by a PUBLIC-only doctype, with no namespace anywhere.**
  The gate read three markers and now reads one, because the other two read structure rather than a
  value and so read an unrelated format as Gramps. The price is this single case: a researcher block
  under `<!DOCTYPE database PUBLIC "-//Gramps//DTD …">` goes from **6 to 0**, and an events block of
  two events from **4 to 0**. Measured, both directions, in CONTRIBUTING. It is not a case newly
  discovered by the deletion -- the doctype marker's own note recorded, when it was written, that
  this *was* its entire reach, because any larger document carrying a doctype already trips a
  genealogy text signature before a scorer runs.
- **A committed NAME can essentially never carry a marker**, so a derived row will never score on
  one. That is a residual of the gate rather than a defect in its scoping; the committed name that
  is a finding today rests on the GEDCOM record signature, not on the XML scorer.
