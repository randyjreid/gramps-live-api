⚠️ **Written before the project was renamed to `AgentDataEntry`.** Apart from this line the page is left as it was written; `README.md` records which names the rename changed and which it did not.
# Plan: the derivation round trip (#238)

## Context

Three tables in this repository are frozen derivations: a generator in `scripts/` reads a
published or installed source, and prints a committed module in `src/gramps_live_api/core/`.
The discipline's stated verification is **re-fetch, compare digest, re-run, and the diff is
empty**. The last step has no test behind it.

What the suite proves today is that each generator parses its source correctly and emits the
same bytes twice. Nothing proves those bytes are the ones actually committed. So the pin has
the shape of a derived table with the guarantees of a hand written one, and `_unrenderable.py`
is now on the write path: `core/render_guard.py` imports it and `host/document.py:1738` calls
`refuse_unrenderable` on every rendered approval.

It has cost something already. When `Zl` and `Zp` joined the class, a documented figure in the
audit went stale in the same change that moved it and nothing failed; a human found it in
review, and a fourth stale copy elsewhere was found by a hand sweep afterwards.

**Intended outcome:** the reproduction step runs on every suite run, offline, and a failure
names what drifted rather than printing a diff of thousands of lines.

---

## Measured findings (probe, not reasoning)

Run read only on the current head with the project interpreter (CPython 3.12.13), loading each
generator by path and calling its `emit` with the arguments the committed module records:

| pair | round trip against `read_text(encoding="utf-8")` | against raw bytes |
| --- | --- | --- |
| `derive_unrenderable` / `_unrenderable` | **holds** | **fails** |
| `derive_note_types` / `_note_types` | **holds** | **fails** |
| `derive_specified_containers` / `_specified_containers` | **holds** | **fails** |

Two facts follow, and both change the shape of the answer:

1. ⛔ **`emit` is drivable offline for all three.** No `emit` touches the filesystem, the
   network or `unicodedata`; only `main()` reads paths, and loading a script by path under a
   name that is not `__main__` never runs it. **The published source files are not needed.**
2. ⛔ **A byte comparison is wrong on this platform.** `core.autocrlf` is `true` and
   `.gitattributes` forces LF only for `scripts/hooks/*` and `*.sh`, so every committed module
   is CRLF in the working tree here and LF on a Linux runner, while `emit` returns `\n`
   throughout. Measured: all three files carry CRLF, none carries a BOM, and raw byte equality
   is false for all three. The comparison must read the committed file with universal newlines.

Negative controls, same probe:

| control | result |
| --- | --- |
| generator `_HEADER` edited, table not regenerated | round trip **fails** (caught) |
| `derive_note_types.EXCLUDED_FROM_ACCEPTED` narrowed, table not regenerated | round trip **fails** (caught) |
| `derive_note_types.IGNORED_LIST` renamed, table not regenerated | round trip **fails** (caught) |
| a range removed from `UNRENDERABLE_RANGES` | round trip **still passes** (NOT caught) |

---

## ⚠️ The vacuity, stated before the design

The round trip feeds the committed file's own recorded data back into `emit`. **For the data
arguments it is vacuously true**, and that must be said rather than glossed:

| pair | arguments that are the file's own data (vacuous) | what the round trip genuinely binds |
| --- | --- | --- |
| `_unrenderable` | `SOURCE_DIGESTS`, `UNICODE_VERSION`, `UNRENDERABLE_RANGES` | `_HEADER`, every emitted docstring line, the `0x%04X` and quoting rules |
| `_note_types` | `SOURCE_DIGESTS`, `GRAMPS_VERSION_TUPLE`, `GRAMPS_PACKAGING_VERSION`, `NOTE_TYPE_ROWS` | `_HEADER`, **`REAL_LIST`, `IGNORED_LIST`, `EXCLUDED_FROM_ACCEPTED`**, the emitted `ACCEPTED_NOTE_TYPES` comprehension source, the one element tuple comma rule |
| `_specified_containers` | all five data arguments | `_HEADER` and every emitted docstring |

⛔ **So the round trip alone would NOT have caught the incident that motivated this issue.**
Had `Zl` and `Zp` been added to `UNRENDERABLE_CATEGORIES` and the table left unregenerated, the
round trip would pass: the table's own rows are its input.

**The complement that does catch it** is a second, non vacuous assertion, and it is why this
plan is two checks rather than one:

```
{label for _first, _last, label in UNRENDERABLE_RANGES}
    == set(derivation.UNRENDERABLE_CATEGORIES) | {derivation.DEFAULT_IGNORABLE}
```

The two sides come from two files and neither is derived from the other. Confirmed by probe:
against the current head it is true; against a table with the `Zl` and `Zp` rows removed and
the current script, it is false. That is the drift, reproduced.

Equality both ways is load bearing. A category named by the script and missing from the table
is the stale table case; a label in the table the script does not name is a hand edit or an
older generator.

**Its one assumption:** every category the script names has at least one code point in the
published source. True for `Cc`, `Cf`, `Co`, `Cs`, `Zl`, `Zp` under the pinned release, and a
General_Category with no members does not appear in the artifact at all. It fails loudly and
once if that ever stops holding, which is the safe direction.

**Not a second tally.** The assertion writes out no list; it reads the generator's own constant.
`test_document_render_guard.py::test_every_committed_label_names_a_published_fact` does write
seven labels out, deliberately, as the guard's own claim about what a refusal may name. That is
a different question asked of a different pair of things, and it is left untouched.

---

## The design

### One new file: `tests/unit/test_derived_tables_reproduce.py`

One property, stated once, parametrised over a case table. Not three copies in the three
existing `test_derive_*.py` files: those hold each generator's properties over synthetic input,
and this is a claim about the discipline that all three share.

Each case carries: the generator path, the committed module path, an adapter that rebuilds
`emit`'s arguments from the imported committed module, and a mutation used as a positive
control. Paths are built from `Path(__file__).resolve().parents[2]`, as
`tests/integration/test_note_types_drift.py` already does. ⛔ **The working tree file, never
`git show`**, which hands back the stored blob with the translation undone.

The generator is loaded by path with `importlib.util.spec_from_file_location` under a name that
is not `__main__`, the idiom already used in the three derivation tests and the drift test. It
is a fourth copy of a four line loader; consolidating the four is out of scope.

### Test 1: the round trip, per case

1. `raw = committed_path.read_bytes()`. If it starts with a UTF-8 BOM, fail with a message
   naming issue #47 and the `cmd /c` redirection, because a correct re-derivation redirected
   through PowerShell looks exactly like a defect otherwise.
2. `committed = committed_path.read_text(encoding="utf-8")`, universal newlines, so CRLF in the
   working tree becomes `\n`. ⚠️ **`encoding="utf-8"` and not `utf-8-sig`**: a BOM must fail,
   and step 1 is what makes it fail legibly.
3. `emitted = derivation.emit(*adapter(committed_module))`.
4. `assert not divergence, message`, never `assert emitted == committed`, so pytest does not
   dump both copies of a 450 line module.

### Test 2: the label binding, `_unrenderable` -- and the same for `_specified_containers`

The equality above, in the same file, sectioned beside the round trip so a reader meets the
round trip's limit next to the thing that covers it. `_note_types` needs no equivalent: its
three selection constants are emitted into the table and are already bound by test 1.

⛔ **This section said `_specified_containers` has no selection constant reaching its output, and
that was false.** `derive_specified_containers.emit` names none, which is what the claim was read
off, but the script's selecting constants reach the table **as data, in a column**: `content_model`'s
returns are the second column of `SPECIFIED_ELEMENTS`, and the name the parser gives an enumerated
attribute is the third column of every enumerated row. A round trip hands both straight back, so
renaming either left the committed table stale with nothing failing for it -- measured once per
constant on this branch, each run coming back with the same single documented baseline failure an
unmutated run does. The pair therefore gets a binding of its own, built in the fix round:
every content model the table carries must be one `content_model` returns, and the name the
parser gives an enumerated attribute must be carried by the table. The reverse direction for the
models is deliberately not asserted, and the file says why: a model no element in the schema
exhibits regenerates to the identical table, so its absence is not drift.

### Test 3: positive controls, per case

⚠️ A round trip that has stopped being sensitive to its inputs passes forever. Two controls per
case, each asserting the comparison **fails** when it should:

- append an invented row to the largest data argument (for `_unrenderable`,
  `(0x10FFFE, 0x10FFFE, "Cf")`; for `_note_types`, a row naming `BADGER`; for
  `_specified_containers`, an invented element) and assert the emitted text differs from the
  committed file. This proves the adapter wired the argument through rather than passing a
  constant.
- `monkeypatch.setattr(derivation, "_HEADER", derivation._HEADER + "\n")` and assert the
  emitted text differs. This proves the comparison sees the generator's own text, which is the
  half that is not vacuous.

### Test 4: discovery, so a fourth table cannot escape

`sorted(p.name for p in (root / "scripts").glob("derive_*.py"))` must equal the case table's
generator names. A new derived table added without a round trip fails here. Naming is already
regular: `derive_X.py` produces `core/_X.py` for all three.

### What a failure says

The message must not claim to know which side moved, and must say what class of drift it is:

- the first differing line number, and both spellings truncated to about 200 characters;
- how many lines differ in total, and each side's line count;
- the sentence that does the work: **the data arguments came from the committed file itself, so
  a difference here is in the serialization, never in the rows**;
- the regenerate command the module's own header already names, and the `cmd /c` warning.

Worked shape, values invented: *"line 27 of `core/_note_types.py` differs from what
`scripts/derive_note_types.py` would emit; 3 of 141 lines differ. committed:
`GRAMPS_VERSION_TUPLE: tuple[int, ...] = (9, 8, 7)` / emitted: `...= (9, 8)`. The data came from
the committed file, so this is serialization drift: either the generator changed and the table
was not regenerated, or the table was hand edited."*

### Both pairs, and the third

**Recommend all three.** The two named in the issue have the identical gap; the third is the
precedent both follow and its adapter is four lines. Excluding it while shipping a discovery
test that demands it would be incoherent. ⚠️ Its own trigger is weaker than the other two (it
is not on the write path and nothing imports it), so striking it is a reasonable call at the
gate; the design does not depend on it.

### Documents and docstrings that this makes false

Sentence corrections, not banners: these describe something that shipped and is changing, not
an abandoned plan.

- `docs/schema-render-guard-derivation.md:36` says *"No test asserts that the generator
  reproduces the committed file, which is filed as #238."* Half of that line stays true:
  **nothing checks the page's own counts against the table**, and that stays recorded as open.
  The `#238` clause goes, replaced by naming the new test. The paragraph at line 140 that
  enumerates what the offline suite asserts gains the round trip beside the interpreter cross
  check.
- `tests/unit/test_derive_unrenderable.py` and `tests/unit/test_derive_specified_containers.py`
  each say *"The committed table is checked separately, by hand."* That becomes: the byte
  reproduction runs on every suite run in the new file; what stays a hand step is the re-fetch
  and the digest comparison.
- `tests/unit/test_derive_note_types.py`'s head gains one clause naming the offline round trip.
- `docs/pii-guard-derivation.md`'s *"the offline suite asserts ... instead"* paragraph gains the
  round trip, if the third pair is kept.

No documented test count covers any of these files (checked), and no test is added to an
existing file, so no count moves.

---

## Acceptance criteria

Mechanically checkable, all offline.

1. `tests/unit/test_derived_tables_reproduce.py` exists and its round trip test passes for
   `_unrenderable`, `_note_types` and `_specified_containers` on the current head, with no
   change to any committed table.
2. No test in the file performs network I/O, reads any fetched artifact, or requires a Gramps
   installation. None of them skips.
3. The round trip reads the committed file with universal newlines. Demonstrated by the suite
   passing on this Windows checkout **and** green on all three CI legs, which is where LF is.
4. A UTF-8 BOM on a committed table produces a failure whose message names issue #47 and
   `cmd /c`. Asserted over a temporary copy, never by touching a tracked file.
5. The label binding test passes on the current head, and **fails** when the `Zl` and `Zp` rows
   are dropped from the table it is handed. Both directions asserted.
6. Each case's two positive controls pass: an appended invented row makes the comparison fail,
   and a mutated `_HEADER` makes the comparison fail.
7. The discovery test equates `scripts/derive_*.py` with the case table, and fails if they
   diverge.
8. No failure message dumps a whole module: every assertion is over a small computed value, not
   over the two texts.
9. No test writes out a copy of any table's rows, labels, header text or counts. The only
   literals in the file are invented control values.
10. `docs/schema-render-guard-derivation.md` no longer claims no test asserts the reproduction,
    and still records that the page's counts are unchecked.
11. `pytest`, `ruff format --check`, `ruff check` and `mypy` pass, and the repository's own
    gate passes.

## Out of scope

- **Any change to a generator or to a committed table.** If a round trip fails on arrival, that
  is a finding to report, not a table to regenerate.
- **Re-deriving against a newer Unicode or Gramps release.**
- **Committing the fetched artifacts** so the data itself could be re-derived offline. That is
  the only thing that would make the check non vacuous for the rows, and it collides with the
  fail closed file-type gate that refuses a `.txt` in tracked content. Not opened here.
- **Any network step.** The re-fetch and digest comparison stay human.
- **The stale count in the audit note.** The round trip does not catch a prose figure drifting
  from the table, and a check for that is a different property with a different failure mode.
  File it as its own issue, with the incident quoted verbatim.
- **Consolidating the four copies of the by-path loader** across the derivation tests.
- **Editing `test_every_committed_label_names_a_published_fact`.** It states a different claim
  and stays as written.

## Residuals, recorded rather than chased

- ⛔ **The rows are still not checked against the published source by anything automatic.** What
  covers them is the recorded digests plus the human re-fetch, and, for `_unrenderable` only,
  the existing cross check against the running interpreter's own database in
  `test_every_character_this_interpreter_calls_other_but_assigned_is_guarded`. A table
  regenerated against a newer release and committed half-way would pass everything here.
- The label binding assumes every named category is non-empty in the published source.
- The round trip does not assert line endings, deliberately: those are a property of the
  checkout, not of the derivation.

## Questions left to the build

1. One parametrised test function over the case table, or one function per pair? A parametrised
   id must name the pair in the failure line either way.
2. Where the BOM check lives: inside the round trip, or its own test over a temporary copy.
   Criterion 4 wants a temporary copy; whether the production path also pre-checks is the
   build's call.
3. Whether the case table's adapter is a lambda per case or a small named function per pair.
4. Exactly how much context the failure prints around the first divergence: one line, or a
   window of three.
5. Whether the discovery test compares file names or stems.
6. Whether `_specified_containers`'s `markup` argument is rebuilt as `set(MARKUP_ELEMENT_NAMES)`
   or passed as the frozenset, given `emit` only calls `sorted` on it.
7. Whether the three docstring corrections ship in this commit or a second one.

## Verification

From the repository root, with the project interpreter (⛔ never 3.14, and never a bare
`uv run --python <version>` inside the project directory, which recreates `.venv`):

```
.venv\Scripts\python.exe -m pytest tests/unit/test_derived_tables_reproduce.py -v
.venv\Scripts\python.exe -m pytest tests/unit tests/integration -q
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src tests scripts
python scripts/gate.py
git status
```

`git status` must show only the new test file and the four docstring or document corrections.
Then the mutation evidence, reported with the build and not committed: drop the `Zl` and `Zp`
rows from a **copy** of `_unrenderable.py` under the scratch directory, point the label binding
at it, and record that it fails; restore is unnecessary because no tracked file was touched.
CI's full matrix must be green on the pushed head before any report calls this done, since the
CRLF finding above is precisely a difference between this box and the runners.
