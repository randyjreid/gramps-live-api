# Where the rendering guard's unrenderable class comes from

`preview()` renders the one sentence a person approves before anything is written to a tree. Its
guard refuses characters that can **reorder or hide** part of that sentence. **Which characters
those are is not a judgement, and is no longer treated as one.** The class is derived from the
published Unicode Character Database and frozen as a committed table,
`src/gramps_live_api/core/_unrenderable.py`, which is machine-generated and never hand-edited.

This note is the audit trail for that file: what it was generated from, how to check it, and what
the check can and cannot prove. It follows the precedent set by the guard vocabulary's own
derivation note, and deviates from it in one stated place, recorded below.

## Why a derivation at all

The class used to be read from the **running interpreter** — `unicodedata.category(character)`
starts with `C` and is not `Cn`. Two review findings on PR #44 were consequences of that one
decision:

- **The class moved between interpreters.** Measured by absolute interpreter path on Windows 11
  x86-64 CPython: **139,742 / 139,744 / 139,751** code points on 3.10.20 / 3.11.15 / 3.12.13, with
  **9** flipping (U+0890, U+0891 and U+13439–U+1343F) and the *older* interpreter the permissive
  side. The same operation previewed on one supported Python and was refused on another.
- **The class was under-inclusive.** U+034F is `Mn`, U+115F and U+1160 are `Lo`, U+FE00 is `Mn`.
  All four are invisible and all four reached the screen.

A derived table answers both at their shared root: the verdict becomes a fact about the published
standard rather than about the interpreter. Measured after the change: **143,787 code points,
identical on all three**, divergence **0**.

## The two sources

| Artifact | Declared version | SHA-256 as fetched | Fetched |
| --- | --- | --- | --- |
| `extracted/DerivedGeneralCategory.txt` — General_Category, one range per line | **17.0.0**, stated in the file's own first line | `d62e5bab70ca74f099343f71224fa051cb1fdd61a1ab45c0488c44cfc0b6102e` | 2026-08-15 |
| `DerivedCoreProperties.txt` — the derived core properties, including `Default_Ignorable_Code_Point` | **17.0.0**, stated in the file's own first line | `24c7fed1195c482faaefd5c1e7eb821c5ee1fb6de07ecdbaa64b56a99da22c08` | 2026-08-15 |

Where each was fetched from:

- `https://www.unicode.org/Public/17.0.0/ucd/extracted/DerivedGeneralCategory.txt`
- `https://www.unicode.org/Public/17.0.0/ucd/DerivedCoreProperties.txt`

The digests are also carried in the generated module itself, as `SOURCE_DIGESTS` under the labels
`general-category` and `core-properties`, so the file states what it was made from without
depending on this note surviving beside it.

⚠️ **Pinned by VERSION DIRECTORY, never by `.../Public/UCD/latest/`.** A `latest` path has no
stable digest — it moves the day a release lands — so a reproducibility story told against it is a
fiction. The version directory is immutable, which is what makes the row above checkable next year.

⚠️ **The pin is NEWER than any interpreter this project supports bundles** — 17.0.0 against UCD
13.0.0, 14.0.0 and 15.0.0. That is deliberate and it is what makes *every character refused before
this change stays refused* hold on all three legs. Its cost is recorded in the guard's own costs
block: the class refuses 3,779 / 3,776 / 3,769 code points that 3.10 / 3.11 / 3.12 respectively
call unassigned.

### Why these two files and not `UnicodeData.txt`

The prescription for this work named `UnicodeData.txt`, the primary file. It is not used, for two
reasons that are about the failure mode rather than about taste:

- **`UnicodeData.txt` declares no version anywhere in its content.** It carries no comments and no
  header, so the version this table claims would be attested only by the URL somebody typed.
  Both files above state their version in their own first line, and the derivation script reads it
  from there and refuses if the two disagree — which is what the "declared version" column is
  supposed to mean.
- **`UnicodeData.txt` expresses `Co` and `Cs` only as `<…, First>` / `<…, Last>` row pairs.** A
  parser that does not pair them drops about **139,500** of the class's 139,700-odd code points —
  the private-use areas and the surrogates, which are most of it — and still emits a
  plausible-looking module. **That is a check that cannot see what it claims to check**, and it is
  the failure this project has now been bitten by three times. Both files above write every range
  out in full, in one shape (`0000..001F ; Cc`), so one parser reads both.

### Why BOTH files, and not just one

The class is the **union of two published facts, and neither contains the other**:

- `Default_Ignorable_Code_Point` reaches **outside** the General_Category group "Other" — U+034F is
  `Mn`, U+115F and U+1160 are `Lo`. That is the under-inclusiveness finding.
- The group reaches **outside** default-ignorable — the controls (`Cc`), the surrogates (`Cs`) and
  the private-use areas (`Co`), which the guard still refuses.

A table supplementing a surviving `unicodedata.category` call would have left the second half
interpreter-derived, and the version dependence would have come straight back for it. So both
halves are derived and committed, and **`unicodedata` no longer appears in the guard at all** —
including in the refusal message, which used to name `unicodedata.category(character)`. Under a
pinned table that call reports `Cn` for code points the table guards as `Cf`: a refusal naming the
one category the class does not hold.

### What is NOT in the table, and why there is no exclusion clause

Unassigned code points, and every readable category. **`Cn` is stated explicitly in
`DerivedGeneralCategory.txt` — it is not absent from the source.** What keeps it out is that the
derivation names the categories it *wants* (`Cc`, `Cf`, `Co`, `Cs`) plus one property, so there is
no `!= "Cn"` anywhere downstream to get wrong. The exclusion is structural rather than a special
case, and the arithmetic the old `Cn` argument rested on — 9 divergent code points against 5,327 —
retires with it, because the class no longer moves between interpreters at all.

## What is NOT committed, and why

The fetched artifacts themselves. A `.txt` is refused by the fail-closed file-type gate, and
widening that constant to admit a build input is a change to a different property. The digests
above are what stands in for the bytes. Fetch them **outside** the repository.

## How to check the derivation

Fetch each artifact, confirm its digest matches the table above, then, from the repository root:

```sh
python scripts/derive_unrenderable.py <DerivedGeneralCategory.txt> <DerivedCoreProperties.txt> \
    > src/gramps_live_api/core/_unrenderable.py
git diff --exit-code src/gramps_live_api/core/_unrenderable.py
```

**An empty diff is the check.** The script emits no timestamp for exactly this reason: a fetch date
is a fact about a fetch rather than about a standard, and stamping one would make every
re-derivation differ from the file it is checking.

⚠️ **On Windows, redirect through `cmd /c`, not with PowerShell's `>`.** PowerShell rewrites the
stream with a BOM and CRLF line endings, so the byte-for-byte check above **fails on a correct
re-derivation** and looks like a defect in the script. `cmd /c` redirects at byte level:

```
cmd /c "python scripts\derive_unrenderable.py <general category> <core properties> > src\gramps_live_api\core\_unrenderable.py"
```

That is issue #47, which owns the repair to the guard vocabulary's note. It is stated here because
this is the second derivation it can bite, not because this note is fixing it.

⚠️ **CI never fetches anything, and no test performs network I/O.** The offline suite asserts the
committed table against a *second* source instead — the running interpreter's own database, in
`test_every_character_this_interpreter_calls_other_but_assigned_is_guarded`, which is the whole of
the old class and therefore the assertion that nothing was lost. Two sources that must agree is a
test; a table checked only against itself is not.

## The one deviation from the precedent it follows

The guard vocabulary's derivation note records that **nothing imports** its generated module: there
the table is a checklist beside a hand-written weighting, and a test binds the two. **Here
`core/render_guard.py` imports the generated module directly**, because the table *is* the class. A
hand-maintained copy bound by a test would be the exact thing this derivation exists to remove, and
the principle that note states — *derived means nothing is maintained by hand without a test that
would fail* — is satisfied more strongly by importing than by copying.

## What this closes, and what it does not

**Closes:** the class is a fact about a named Unicode release. It is identical on every supported
interpreter — 143,787 code points, one membership digest, measured on 3.10.20, 3.11.15 and
3.12.13 — and the four invisible characters round 4 named are refused.

**Does not close** — recorded rather than chased:

- **The class is pinned to 17.0.0 and does not track a later release.** A character assigned after
  it is emitted until somebody re-derives the table. That is a fail-open, and it is the price of
  determinism: bounded by the standard's release cadence, mechanical to repair, and visible in a
  diff — none of which was true of the dependence it replaces.
- **The class refuses characters some scripts use legitimately**, and the set is wider than it was:
  the zero-width joiner and non-joiner, the Mongolian free variation selectors, the variation
  selectors used in ideographic variation sequences, the Hangul fillers. Recorded in full, with the
  argument for taking the trade, in the costs block `core/render_guard.py` carries. It is a real
  cost and it is not negligible.
- ~~**A character past the preview's elision limit is never emitted and so never refused.**~~
  **Retired when the guard moved to the document route**, which elides nothing: `document.WRAP_AT`
  wraps and never truncates, because R3's ruled criterion is that no byte reaches the tree that was
  not rendered in full. There is no elision point for a character to hide past.
- **Implicit reordering is not covered and must not be.** A strong right-to-left letter reorders
  the neutrals around it under UAX #9 with no formatting character present at all; covering it
  would mean refusing ordinary names.
- ~~**`preview()`'s single-line rule normalises through `str.split()`, whose whitespace set is
  interpreter data this table does not pin.**~~ **Retired when the guard moved to the document
  route, and the retirement changed a verdict rather than only a rationale.** The note flow's
  `preview` collapsed the whole rendered sentence through `str.split()` before scanning, so a
  whitespace control could never be refused, and the residual above recorded that the collapsing
  set was unpinned interpreter data. `document.preview` performs no such collapse. Note text still
  passes through `_wrap`, which uses `textwrap` and removes whitespace controls, but a field
  interpolated straight into a rendered line, a person's `given` or a place `title`, does not.
  ⛔ **So a tab in a name IS now refused, labelled `Cc`, where it was silently
  accepted before.** That is not a regression to repair: it is the same mechanism that refuses a
  payload newline forging a line of the approval sentence, and exempting one takes the other. The
  trade is recorded as #236 and pinned by tests in both directions. The measured figures in the
  retired bullet, 29 whitespace code points and 143,777 refused, described the collapsing route and
  do not describe this one.
