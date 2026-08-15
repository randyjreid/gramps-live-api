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
