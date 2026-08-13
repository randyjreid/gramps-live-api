# Contributing

Two things in this project are not negotiable: work is **test-first**, and **no personal data is
ever committed**. Everything else is ordinary judgement.

## Setting up

```sh
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## The gates

All four must pass before anything merges. CI runs them on Python 3.10, 3.11 and 3.12.

```sh
ruff check .
ruff format --check .
mypy src
pytest
```

A fifth job runs the PII guard. Run it yourself before you push:

```sh
PYTHONPATH=src python -m gramps_live_api.core.pii_guard .
```

```powershell
# Windows PowerShell -- there is no inline environment prefix
$env:PYTHONPATH = "src"; python -m gramps_live_api.core.pii_guard .
```

Inside a Git working tree that scans **tracked content**, read from the index -- what is staged is
what will be committed. That is not the working tree, which is a different thing again: it hides
blobs history still reaches and shows untracked files that were never published.

⚠️ **The index and the working tree are different questions, and the guard never swaps one for the
other quietly.** Inside a work tree it reads the index, because that is what a commit publishes;
outside one it walks the filesystem. Anything in between — Git unable to answer, targets in two
repositories, a repository target named beside a plain directory — is **refused with exit 2**, not
answered the other way. Stage something, leave an innocuous copy on disk, and a walk would report
clean over what the next commit publishes; that is the fail-open this refusal exists for, and the
reasoning that the walk is a "safe subset" of the index scan is wrong.

⚠️ **Tracked content is a claim about a repository, not about a directory.** Name a subdirectory and
the whole repository is scanned anyway; the run says so on its first line. This is deliberate and it
replaced the opposite behaviour, which was the most dangerous defect any review round found here: a
subdirectory target listed only that subtree while the verdict still spoke for the repository, so a
committed family tree one directory up came back **clean, exit 0**. The scope word and the set it
describes are now produced by one value and cannot disagree.

To scan the commits a push would publish, give it a range:

```sh
PYTHONPATH=src python -m gramps_live_api.core.pii_guard --range origin/main..HEAD .
```

**Scanning nothing is never a pass**, and that is one rule rather than one per mode. A range that
covers no commits, a range with no file content in it, a target holding no scannable file, a working
tree with nothing tracked, a file that cannot be read, a directory that cannot be listed -- each is
refused with exit 2 rather than reported as clean. Every scan says how much it covered, in every
mode, because a count of findings on its own cannot tell a run that looked at everything from one
that looked at almost nothing.

The rule is asserted **once, against whatever the run claims to cover** -- not once per mode. Three
rounds asserted non-emptiness per mode, every assertion was true, and a fourth defect still got
through, because a number nothing is compared against proves nothing. That is also why the coverage
line always carries its count, and why the emptiness check now looks at the whole run: a tip that
tracks nothing used to block the add-then-delete range that `--range` exists for.

**What is never scanned, and is not a gap you have found:** commit messages, annotated tags and
`git notes`. The coverage line names all three on every run.

**Reading the count.** A finding is reported once per *place it was found*, not once per problem.
One offending line in one file can therefore appear several times in a range scan: once as tracked
content and once for each blob version of that file inside the range. The number is a count of
sightings, so treat it as an upper bound on the number of distinct things to fix, and read the
source and line to tell them apart -- redacted, the source still carries its scope, its depth and
each component's length, which is enough to see that two lines concern one file. Run it locally to
see which file. Collapsing them is defensible and deliberately not done —
knowing *which* historical blobs still carry something is the point of scanning history at all.

⚠️ **Stage your changes before you scan.** Reading the index is what makes the guard judge what
will actually be committed, and the price is that unstaged edits are invisible to it. Scanning a
dirty tree and then committing gives you a clean answer about the *previous* content -- this
document has been caught by exactly that once already.

## Test-first

Red, green, refactor. **No line of production code without a failing test that demanded it**, and
the failing test is expected to be shown, with its assertion text, in the commit or the review.

Two habits that make that meaningful rather than ceremonial:

- **Assert per property.** A test for one property must fail naming *that* property. If breaking
  the genealogy sniffing makes a path test fail, the tests are not telling you what broke.
- **Break one thing at a time** when you check that a test really covers what you think. A test
  that still passes when you disable the code it names is not a test.

## The privacy policy

This repository is public. The tree it exists to serve is not.

`src/gramps_live_api/core/pii_guard.py` enforces two properties over every file in the checkout:

- **P1** No path that identifies a person or a machine. See the recorded decision below: this was
  amended, and the amendment matters. A short allowlist covers genuinely portable locations,
  matched as **exact strings**, never as prefixes.
- **P2** No genealogy data the guard has a property for, whatever it is named — **and no content it
  cannot prove safe.** Classification is **positive**: content passes only if it decodes as UTF-8,
  contains no control characters text does not use, matches no genealogy property, *and* carries a
  file type on the known-safe list. Everything else is a finding. Decodability proves nothing —
  UTF-16 text decodes as UTF-8 to interleaved NULs.

  ⚠️ **"Whatever it is named" holds for formats the guard has a property for, and the safe-type gate
  is what carries everything else.** The two halves do different work and the difference matters: a
  format with a property is caught in a Markdown file as surely as in a `.ged`, while an
  unrecognised format in a safe-typed file rests on the type gate alone — which is the first entry
  in the residual table, *a family tree fits inside perfectly valid Markdown*. This wording used to
  claim the stronger thing, and GEDCOM X proved it false: the payload was refused as a text file,
  because text is not a safe type, and passed clean as Markdown, Python and YAML. It has a property
  now. The next unrecognised format will not, until someone writes one.

**There is no P3.** Credentials were a third property for four rounds; it is gone. See the recorded
decision below.

### Recorded decision: credentials are not scanned for

Four rounds, four mechanisms, and each failed the same way -- by judging the value:

| mechanism | how it failed |
| --- | --- |
| provider prefixes | unknown providers passed |
| a digit requirement | alphabetic tokens passed |
| word segments plus an entropy floor | failed in **both** directions at once |
| length, position and an annotation | the annotation was trivially bypassable |

The last one is the clearest argument for stopping. Its suppression channel -- a fifth mechanism,
introduced to make the fourth tolerable -- read annotation text sitting *inside a string literal* as
a real annotation, with the closing quote satisfying the mandatory reason, so a credential published
with neither. It arrived broken in the round that added it.

**Why deletion rather than a fifth attempt.** This repository's threat model is personal and
genealogical data. P1 and P2 carry that risk. The repository holds no credentials, Phase 0
introduces none, and there is no deploy, integration or secret in CI for one to protect. Four rounds
of engineering went into a property that was never the risk here.

**What would reopen it.** A later phase that handles real credentials -- a deploy key, a third-party
API integration, anything where a leaked secret has consequences. At that point adopt a dedicated
secret scanner rather than writing a fifth mechanism. It was declined twice on the grounds that it
solves a larger problem than this repository has; that reasoning stops holding the moment real
credentials exist.

### Adding a file type

P2 fails closed, so the first `.cfg`, `.json` or `.png` anyone commits will fail the build. That is
the design, not a bug: a new file type is a decision about what this repository may contain.

Add the extension to `SAFE_EXTENSIONS`, or the exact filename to `SAFE_BASENAMES`, in
`pii_guard.py`, and **say in the commit message why that type cannot carry a family tree**. The
failure message names the constant, so the fix is a one-line change rather than a bug report.

The **type itself** is a matched value and follows the destination rule with every other one: in CI
you see that a type could not be proved safe, and locally you see which type. It has to be that way
round — a file with no extension has only its name to offer as a type, and that name is exactly the
kind of thing this guard exists to keep out of a public log.

Keep the list short. `.txt` and `.json` are deliberately absent: they are exactly the extensions a
renamed export hides under, and admitting them puts the work back on signature matching, which is
the losing side of that race.

**Recorded addition: `uv.lock` (issue #11).** The owner's ruling is that the lockfile is tracked, and
`.lock` is on no safe list, so committing it made the guard refuse it — the gate working, not a bug.
It is added to `SAFE_BASENAMES` as **one named file**, not to `SAFE_EXTENSIONS` as an extension:
nothing about `.lock` is safe, and a class admits every future lockfile including ones that carry
local source paths. The reason this named file cannot carry a family tree is that it is not authored
— `uv` generates it from `pyproject.toml`, and it holds package names, versions and registry hashes.
**Being on the list exempts it from the type gate and from nothing else:** its contents still go
through P1, P2 and the deny-list, and were measured clean when it was added.

### The rule that outranks both

**The committed pattern set contains no personal information.** No real names, no surnames, no
usernames. A committed deny-list of personal data *is* the leak the guard exists to prevent.

So: **if you find yourself adding a pattern to catch one specific string, stop.** The property is
wrong, or the string belongs in your local deny-list. Say so in the issue rather than adding the
case.

### Your local deny-list

Personal literals live in a file you write for yourself and never commit. It is gitignored, along
with anything else matching `.pii-denylist*`.

Create one at the repository root -- one literal per line, `#` for comments, blank lines ignored:

```sh
cat > .pii-denylist <<'EOF'
# Names and places that must never appear in a commit.
Ashenmoor
Quorvane
EOF
```

The guard loads it if it is there, works without it if it is not, and **never scans it** -- every
literal in it would otherwise match itself and the command above would fail on a clean checkout.
That holds however the file is reached: walked to, or named directly as the target. The exemption
used to live only in the walk, so naming the file printed every literal in it.

Every variant of the name is gitignored, and that rule has to stay **last** in `.gitignore`: Git
applies the last matching rule, so a negation written after it silently re-admits whatever it
matches. Check with the exit code, never by reading the file and never from `-v` output, which
prints the matching line even when that line is a negation:

```sh
git check-ignore -q .pii-denylist.md ; echo $?   # 0 means ignored
```

Everyone's file is different, and that is the point. There is no shared list, because a shared
list would have to be committed.

## What the guard prints, and where

Redaction follows the **destination**, not the rule:

- **In CI, or into a pipe or a file: always redacted.** A public Actions log is world-readable and
  retained. Printing the matched path there republishes exactly what the guard exists to contain --
  the guard becomes the leak.
- **At an interactive terminal: shown in full.** The value is already in a file on your disk, so
  the terminal is not a new exposure, and a finding you cannot act on is a finding you route
  around.

**The source follows the same rule as the matched value, and did not always.** A path is data: in
this archive a directory is likelier to carry a surname than a filename is. Redacted, a source keeps
its scope (`history`, or nothing for the tip), its depth, and the length of each component; the line
number is always in clear. That is enough to tell two findings apart and to see that two lines
concern one file. To see *which* file, run it locally — the same answer the matched value has always
had.

Deliberately **not** a digest or a per-run identifier. A hash of a path is a confirmation oracle for
anyone holding a guess, which here means anyone with a surname to try.

Override with `--show-matches` or `--redact`. When both are given, `--redact` wins.

## The history baseline

CI scans the range a push publishes (`before..after`), so every commit is checked as it arrives and
content added and deleted within one push is still caught. It does **not** re-scan the history that
existed before the properties were tightened in fix round 1.

That history is not clean under the current rules. Auditing the whole branch reports **27 finding
instances covering 7 distinct (file, match) pairs** -- the same handful of strings, each counted
once per blob version that contains it:

```sh
PYTHONPATH=src python -m gramps_live_api.core.pii_guard --range main..HEAD .
```

Every one is a **P1 false positive**: a string shaped like an absolute path that is not one. The
matches are described rather than quoted, because quoting them would reproduce them in a tracked
file and the guard would report this page -- which it did, on the first draft.

| Where | What matched | Why it is not personal data |
| --- | --- | --- |
| `.gitignore` | the stock mkdocs entry, root-anchored with a leading slash | Verbatim from the GitHub Python `.gitignore` template. Names a build directory, not a person. Replaced with a directory match at the tip. |
| `pii_guard.py` | two one-word examples in a code comment | The comment argued why one-component paths were *not* matched; the examples were the invented words "or" and "word". Comment and rule are both gone. |
| `pii_guard.py` | a fragment of the guard's own regex character class | Punctuation from inside an `re` pattern, read as a path once P1 loosened. Not data of any kind. Fixed by composing the patterns from constants. |
| `synthetic.py` | two docstring illustrations of a UNC path builder, and one of a POSIX one | Every component was the literal word "part". Rewritten in `e4f8e1e` -- which is precisely why the tip is clean and the blobs are not. |

Note that the fix-round commits themselves inherit the `pii_guard.py` entries: every commit made
before the P1 rewrite landed still carries the old comment and character class in its blob.

**Why baselining is safe here:** this guard exists to stop **personal** data reaching a public
repository, and all 27 instances -- the 7 distinct pairs above -- are boilerplate, punctuation or
an invented placeholder. None of it identifies anybody. Rewriting a published default branch and a
published initial commit to erase them would be disproportionate to the risk.

Most of them stop being findings at all under the amended P1, since they were never paths that
identified anyone; the baseline is recorded as it was measured rather than quietly shrinking to
match the new rule.

⚠️ **So the command above no longer reports 27, and that is the point of keeping the number.** Run
it today and it reports far fewer. Nothing was rewritten and nothing was suppressed: the count fell
because P1 was amended in fix round 2, and most of those 27 sightings were strings shaped like a
path that identified nobody — the very false positives the amendment removed. **27 is what the
history contained when it was audited under the old rule**, and it stays here because a baseline
that silently tracks the current rule records nothing at all. The audit is the artefact; the live
count is just today's reading of it. If you need to know what is reachable *now*, run the command
and read the output — do not expect it to match this table.

### The genealogy sightings — measured, and the tally that was not

⚠️ **This section used to carry a per-round tally reading six, then ten, then nineteen. None of
those numbers is reproducible, and the corrected figure is four.** Replaying the documented command
under *every committed version of the guard on this branch* gives 1, then 3, then **4 from
`de9b4fe` onward — including the very rounds that recorded 10 and 19.** No guard this branch ever
committed reports nineteen.

The likely explanation, offered as inference rather than fact: those readings were taken mid-build
with corrected-but-not-yet-committed fixture literals staged, so they counted tip findings that
existed for the length of one build and were gone by the commit. The tally recorded a peak as if it
were settled history.

**This is the failure this document warns about two sections further down** — *a figure nobody could
reproduce ended up in the history baseline* — recurring in the paragraph that was supposed to be the
cure. A running tally maintained by addition is the mechanism: each round wrote what it believed it
had added, and nobody re-ran the whole command. So the tally is gone, replaced by the measurement
and the way to repeat it.

**What is actually in history: four findings, all P2, every one a historical blob of
`tests/fixtures/synthetic.py`** — one scoring GEDCOM X identity keys, three the record-density
check. Each is a version of that file from before it was corrected to assemble its record lines at
runtime rather than write them as literals. **Every name in them is invented**, which is the fixture
rule doing its job: what is left in history is a placeholder, not a person. Baselined on exactly the
reasoning below, and the clearest illustration of why the fixture rule exists.

**Re-measure rather than adjust.** If this number changes, run the command and replace it — never
add to it. The count is a reading, not a ledger.

**If a hit in history were personal data, the answer would be the rewrite, not the baseline.** A
reachable blob containing a real name, a real path or real genealogy data is a live leak that no
later commit can fix: `git filter-repo` (or equivalent), force-push, and rotate anything exposed.
Baselining is for content that has been read and found harmless, never for content nobody has
looked at.

## Fixtures

- **Invented surnames only.** Never a real one, not even a common one, and not a relative's. The
  fixtures in `tests/fixtures/` use invented names throughout.
- **Assemble sensitive-looking fixtures at runtime.** A fixture that must look like something the
  guard rejects -- an absolute path, a credential, a genealogy record -- is built from parts when
  the test runs, never written as a literal. A literal would be a genuine finding in this
  repository, and the only ways to make the build pass again would be to delete the test or to
  weaken the guard. See `tests/fixtures/synthetic.py`.
- Files that need to exist on disk are written to pytest's `tmp_path`, never into the tree.

## Accepted residuals

Things the guard knowingly does not catch. Each was raised in review, considered, and accepted --
they are recorded here because the next reviewer will find them again, and the rationale needs to
be where they will look. **Reopen any of these with evidence; do not reopen them by re-finding
them.**

| What is not caught | Why it is accepted |
| --- | --- |
| **A file whose contents are not validated against its type.** A `.toml` is not parsed to check it is TOML. | Parsing would not show it is not genealogy. A family tree fits inside perfectly valid Markdown. The fail-closed *type* gate plus content sniffing already carry this weight; a parser adds surface without adding a property. |
| **A path whose FIRST component uses a character our pattern excludes** (`*`, `?`, `|`, quotes, braces). | Rewritten in round 9 after re-measuring: the old wording claimed any such path escaped, and that is not what the code does. An excluded character in a middle or final component still leaves a rooted prefix, and the prefix is caught — verified for both positions. Only a character landing in the first component, before enough components exist to form one, breaks the match. Widening the class is still refused: matching almost any byte after a slash makes the precision problem worse and pulls against the P1 amendment. "POSIX permits this byte" is a fact about filesystems, not about identity. |
| **A personal path under a non-standard root, in prose.** | See the P1 recorded decision above. Covered by the deny-list, which is where names belong. |
| **An unrooted path reached through a subscript** (`config["path"] = …`) **or split across a line continuation.** | Measured, not assumed: a **rooted** personal path is caught in both of those positions today, by shape. Only a path that identifies nobody by shape leaks, and only through those two syntaxes. Closing them means teaching the detector to parse subscript syntax and to fold expressions across line continuations — the start of a parser, enumerating syntax forms with no property behind them. A documented residual beats another mechanism. |
| **A short `text` element inside an `<svg>` scores nothing, positioned or not** — so a name in an unpositioned label inside a drawing is not counted. | Added in the Codex round-1 fix, which changed the short-prose discriminator from *"the element carries an attribute"* to *"the element sits inside a drawing"*. The old question was the wrong one and let data out whatever the answer: ordinary `xml:space` counted as proof of a positioned chart label and returned an exact name-date-place payload clean. Both obvious repairs enumerate — a list of positioning attributes fails open on the next one nobody listed, and the list pointed backwards fails by admitting whatever is new — so the axis changed instead. `<svg>` is accepted as an enumeration on the same grounds as `FILESYSTEM_ROOTS`: closed, externally specified, and the only markup in general use whose `text` elements are positioned labels. **What this costs in the other direction is not a residual but a deliberate false positive:** a chart fragment pasted *without* its `<svg>` wrapper is now reported, asserted by test. Of the two directions, failing closed is the one this module's stated posture requires. A Gramps-generated SVG chart was already exempt under the old rule, because its labels are positioned; this widens that exemption to unpositioned labels in the same drawing and does not create it. |
| **A bare tilde home path — an account name with nothing under it — standing in free prose**, with no path-bearing identifier or call around it. | Added in the Codex round-1 fix, which closed the same shape *in a path-bearing position* and stopped there deliberately. The obvious repair is to make the trailing component optional in the tilde pattern, and that pattern is shape with nothing corroborating it: every approximation, version constraint and duration written with a tilde becomes an account name, which is a fail-open traded for a false positive across ordinary prose. Position is the corroboration shape lacks, so the two detectors share one spelling of a home path and require different amounts of it — asserted by test in both directions. The deny-list is the backstop here, as it is for the other P1 residuals. |
| **A path or a member name spelled with `\uXXXX` escapes for its STRUCTURE characters** — the quote, the braces, the colon, the angle brackets, the backslash. | Added in the Codex round-1 fix. Decoding these manufactured structure the source did not contain: prose inside one string value that quoted four member names decoded into four apparent structural keys and was reported as an export. An escape can only occur *inside* a string literal, so a delimiter it decodes to is content of that string and provably not a delimiter of the document — producing one is not reading the document, it is writing a different one. **What is still decoded:** the escaped solidus (`\/`), which is the spelling that actually occurs and the one the fix was adopted for, and escaped letters in a member name. **What is lost:** a drive-letter path whose colon and backslashes are themselves written as escapes — a spelling no test and no observed document uses. A false positive on a document that merely *describes* the format is not the cheap side of this trade — it is a finding nobody can act on, so contributors learn to route around the gate. |
| **A JSON string literal whose only closing delimiter is an escaped one** — an unterminated string. It is measured as nothing rather than as a filled key. | Added with the logical-length fix. Reading a literal correctly means finding its true end, and a document with no unescaped end has none. It previously matched *because of* the defect being fixed: the capture stopped at the wrong delimiter and scored whatever preceded it, which was two characters of a truncated payload. A genuinely truncated document — no closing delimiter at all — matched under neither spelling, so what is lost is the narrow case where the *only* one is escaped. **The obvious repair is a fallback to the old pattern, and it is refused on the standing grounds:** two matchers with two ideas of where a string ends is how the vocabulary came to differ between formats in the first place. Direction is fail-open by 2 points, below the threshold on its own. Asserted by test. |
| **A file URI that ends at a remote authority.** | Narrower than it sounds, and measured: a remote authority *with a path* is already caught. Only the form with no path component at all escapes -- a bare host and nothing else, which names a machine but carries no user, no share and no file. The UNC spelling of the same thing is caught. |
| **GEDCOM records wrapped in HTML tags.** A record inside a span or a table cell counts zero. | The decoration stripper handles whitespace, quote markers, diff markers, bullets, pipes and list markers — the ways text arrives in a Markdown repository. Hand-tagged HTML is not one of them, and widening the class to cover it buys a case nobody here will write at the cost of the surface that class has already been re-argued over twice. |
| **What an XML comment or a processing instruction SAYS is not measured** — so a prose element holding only a comment is worth what a bare short note is worth, and one of them escapes. | Added with the fix that stopped a comment ending the element it sits in. **A comment contains no character data, so the measured quantity excludes it by definition; this is a definition, not an imprecision erring short.** The alternative — measure the comment's own text, on the grounds that a name in a committed comment is published all the same — was implemented and measured before being declined, and it lost on both axes rather than being a trade. It reports ordinary documentary comments (a `TODO`, a placeholder, a commented-out example each score 4 on their own); it keeps the chart-label false positive this reading removes; and it does not reach the far commoner shape, a comment that is not inside a prose element at all, which neither reading measures. **What is conceded is the ceiling already recorded, not a new one:** one such element scores identity weight and escapes, two reach the threshold and are caught — exactly what a bare short note does, asserted by test in both directions. **The deny-list is the backstop**, here as for every other residual in this table. A comment holding a whole *export* is still caught either way: the filled-element scan finds the elements inside the comment's text regardless of the comment around them. |
| **The detail inside a failure message cannot be revealed, not even locally.** The flag that reveals matched values does not reveal it. | The redacting wrapper renders when the failure is raised, so what reaches the printing site is already finished text and a flag has nothing left to un-redact. Making it work means the failure carrying the wrapped value intact all the way to that site -- **a second route to a wrapped value, running through the paths that are exercised least.** That is what was refused when the ordering comparison was declined, for the same reason: the wrapper is worth having only while there is exactly one audited way to the value, and error handling is the worst place to add a second. **Kept:** the message names the kind of error in clear and carries the detail redacted, both asserted by test, so an operator learns what failed and where. **Lost:** diagnosing one of these means reproducing the failure, not re-reading the message. |

**Removed in round 9: the classic-Mac line-ending row.** It said a carriage-return-only GEDCOM was
not caught. It is caught, and has been since the density property arrived — Python splits lines on a
bare carriage return, so that property closed the hole as a side effect and nobody noticed. **Every
row above was re-verified by running it**, which is how this one and the excluded-character wording
were found. A residual table that lists a closed hole trains the next reader to skip the table, and
an imprecise row is worse than a stale one because it reads as considered.

⚠️ **Behaviour change, round 4: a symlink target containing a space is refused.** A symlink keeps
its exemption from the file-type gate only while its blob is positively a path, which is what stops
a genealogy document hiding under that mode. The test reuses the path-component definition, and a
space is not in it. This is fail-closed and correct; do not "fix" it back open without replacing
the property it rests on.

**Where the residuals stop and the guarantee starts: `docs/pii-guard-acceptance.md`.** The rows above
say what the guard knowingly does not catch. That document says what it *does* -- eight bounded
properties, each with the tests that assert it, plus the statement of what none of them claims. Read
it before arguing that a finding here is a gap: the question a residual has to answer is whether the
input falls inside the stated terms of a property the guard already holds.

### Recorded decision: how genealogy records are recognised

**Do not replace the decoration-stripping with "match the record shape anywhere in the line".** It is
the obvious simplification, it looks more property-shaped than stripping a class of characters, and
it was measured and rejected. The next person to propose it will reason exactly as the reviewer who
proposed it did, and only a measurement stops that.

Measured over every tracked file in this repository, and against eight ways of pasting an export:

| Candidate | False positives here | Evasions caught |
| --- | --- | --- |
| **Prefix-free** — the record pattern anywhere in a line | 0 | **misses a diff fence**, and any quoted form |
| **Strip decoration, then match at line start** | 1, since fixed | all 8, including a bare three-line fragment |

**Round 9 replaced adjacency with a count per file, and measured the thresholds the same way** — over
all 30 tracked files *and* all 121 blobs in the published range, because a property that is free at
the tip and expensive in history is not free:

| Candidate | Tip | History | Notes |
| --- | --- | --- | --- |
| Records, 3 consecutive (what it replaced) | 0 | 6 | adjacent runs only; a walkthrough with prose between records passed |
| **Records anywhere in a file, ≥3** | **0** | 7 | counting across a file subsumes counting consecutively |
| Gramps XML elements, ≥3 | 2 | 13 | reports two of the project's own test files |
| Gramps XML elements, ≥4 | 1 | 7 | reports the fixture module |
| **Gramps XML elements, ≥5** | **0** | **0** | catches a person fragment carrying name, gender and birth |
| the namespace **on its own** | 0 at the tip | **43** | reports the guard's own source and every historical copy of it |
| the namespace plus ≥2 elements | 0 | 2 | superseded in round 10 |

**Round 10 replaced the element count with a weighted score, because counting was the wrong
question.** The list had been chosen for elements that appear *in quantity* in a full export — a
fair basis for measuring density, and the wrong basis for deciding which elements carry a person.
`<name><first><surname>` is three elements and a whole identity; three structural tags are nobody.

Two axes, one mechanism:

- **Real versus mentioned.** Only a *filled* element counts — an open tag, text of its own, a
  closing tag — or one carrying a quoted attribute, since a handle is export syntax. A backticked
  `` `<person>` `` in a mapping table is a word about the format and scores nothing.
- **Weighted by meaning.** A filled prose container (`<note>`, `<text>`, ≥ 20 characters **of what the
  content denotes** — see the recorded decision on serialized text below) scores 4; a filled name part
  2; anything else real 1; the namespace 2. **The threshold is 4.**

⚠️ **Every component has a row, and each one is load-bearing.** This table is what the round-9
failure bought — a change measured on one of its two parts predicted 9 findings and produced 45.

| Remove this | What happens |
| --- | --- |
| **the real/mentioned distinction** | a genuine importer specification scores **18** and is reported; with it, **2** |
| the prose weight | a note holding a biography falls to 1 and escapes |
| the identity weight | a bare name block falls to 2 and escapes |
| the namespace weight | the round-9 namespace fragment falls to 2 and regresses |
| threshold → 5 | the name block, the biography and the namespace fragment (all 4) escape |
| threshold → 3 | catches one more shape and halves the margin over documents people write |

Measured at the tip: **no tracked file scores at the threshold.** In history: 16 sightings, all
blobs of the two fixture files that carried literal name blocks before this round assembled them.

⚠️ **The measured ceiling of content detection — one number, three costumes.** This is the answer
to "why not just lower the threshold", and the reason to trust it is that the same figure keeps
arriving from directions that share no rule:

| The whole payload | Score |
| --- | --- |
| one filled name part — a given name, no surname, no prose | **2** |
| one filled surname, alone or inside a person | **2** |
| one short note — a name in a `text` element under the prose floor | **2** |

Three different rules — the name-part weight, the identity weight, D3's short-prose credit —
independently stop at the same place, because **all three are one name-fact and a name-fact is worth
2.** The ceiling is a property of the weighting, not an artefact of any one rule; that is why adding
a fourth rule will not move it, and why the honest thing is to state it rather than chase it.

Catching any of them needs **threshold 2**. Today **no tracked file scores above 0**, so that looks
affordable — and the story of this very paragraph is why it is not. **It scored 2 until it was
rewritten**, because the old wording illustrated the ceiling with a real filled XML element;
replacing that fragment with the table above took the whole file to 0. One example element, written
the natural way, is the entire distance between a clean document and a reported one at threshold 2.

That is the cost, and it is prospective rather than visible: phases 1–7 add importer specifications,
schema notes and sample payloads — documents whose job is to show these element names carrying
values. At threshold 4 they can do that. At threshold 2 the first one that writes an example instead
of describing it is a finding, and the escape is to make this project's documentation worse.
Measured, declined, and re-measurable — the numbers above come out of the property tests.

This is the boundary of what content detection reaches here, not a to-do: a single name with nothing
else attached is where the property stops. Two of anything crosses it. The deny-list is the backstop
for a name that matters to you.

⚠️ **The namespace is evidence, not a verdict, and the range is what proved it.** Treating it as a
finding by itself looked free — the tip was clean, because the constant is composed from parts. Over
the published range it fired 43 times, on this guard's own source and on every historical copy of
it: *a guard that detects a string contains that string.* Composing the constant hides the symptom
at the tip and does nothing for history.

So a file that names the format is not genealogy data, and a file that names the format **and
carries its elements** is. Do not promote the namespace back to a finding on its own; the number to
look at before trying is the 43, not the zero.

⚠️ **The same shape guards the JSON side, and it is load-bearing — do not remove it as an
unnecessary condition.** A GEDCOM X prose, address or contact key counts **only when a structural
marker is present in the same file**. The one-line reason, which belongs beside the rule because
without it the condition reads as timidity:

> Ungated, a JSON object holding a `text` key and nothing else scores prose weight — so an ordinary
> UI configuration file with a label reading *click here to continue* is reported as a person's
> life story.

That is not hypothetical framing; it is the payload the property test uses, and removing the gate
fails three tests including the one asserting **this repository** is clean. The XML side needs no
such gate because Gramps element names are format-specific spellings, while `text`, `street` and
`url` are words any configuration file may use. **The gate is what separates a genealogy vocabulary
from a list of common English keys.**

### Recorded decision: serialized text versus the logical value

**The prose floor counts characters of MEANING, not characters of source, and it does so in both
formats.** Read the two length functions in `pii_guard.py` before changing anything near it.

This is the sixth finding of one class: *a rule reasoning about text as it is written when the thing
it means to judge is what that text says.* The first five were fixed correctly and in isolation, and
the class did not move — escaped separators judged in raw spelling; escaped GEDCOM X keys judged in
raw spelling; `"` decoding into structure the source did not contain; a prose capture ending at
an escaped delimiter; and a floor measuring an escape's six characters instead of the one it denotes.

**The seventh and eighth are the same class read backwards**, and they landed on the measurement this
section describes: text judged by what it would say *somewhere else* when the format is reading it
literally. Both are recorded in the warning below.

**Both directions are real, and they are one defect.** A value containing a quoted phrase measured as
one character, so a whole life scored as a caption and passed. A four-character caption written as
four escapes measured twenty-four, so ordinary content was reported as a family tree. One lets data
out, the other reports a caption, and both are the floor reading the serialization.

**The rule is a property of prose, so it is stated for both serializations or it is not stated.**
Gramps XML has the identical defect with character references — `&amp;&amp;&amp;&amp;` is four
characters written as twenty. Landing the fix in JSON alone would leave the same rule stated in one
format and unstated in the other, which is the divergence the shared vocabulary table exists to end.
It went in with the JSON half.

⚠️ **This section used to say the XML side ran in the false-positive direction ONLY, because a
reference is always longer than what it denotes and cannot terminate the content capture the way a
raw `<` can. That was true of references and false of the measurement, and the next round produced
both fail-opens it ruled out.** The measurement collapsed a reference *where XML does not read one*
— inside a CDATA section, whose content is literal — and *for a character XML forbids* — a code
point Unicode has and the `Char` production excludes. Each shortened the value and dropped a prose
element below the floor. The lesson is narrower than "the claim was wrong": a direction-of-failure
argument about the **data** does not carry to the **code that measures it**, and this one was stated
about the first and believed about the second.

#### Two layers, and they ask different questions

| Layer | The question it can answer | Where |
| --- | --- | --- |
| `_decoded`, at the funnel | *Is this escape safe to decode **without knowing its context**?* | `scan_text` |
| `_json_logical_length` / `_xml_logical_length`, at the value | *This is provably inside a string literal or inside element content, so what does it **say**?* | the two floor call sites |

`_decoded` refuses to decode structure-producing escapes because at the funnel it **cannot know**
whether it is inside a string literal. The value extractor knows **by construction** — it matched a
key, a colon and an opening quote, or an open tag and its close, to get there. That is the whole
reason these functions are allowed to decode what `_decoded` refuses, and why they are **not**
interchangeable with it.

⚠️ **Both return an `int`, and that is the guardrail rather than a style choice. Do not "simplify"
either into returning the decoded string.** Decoded text handed back as a string makes `<` and
`&lt;` a way to manufacture the structure the source does not contain — the exact finding
`_STRUCTURE_CHARACTERS` exists to prevent, re-created one level down. A function that cannot return a
string cannot be misused that way by the next person who needs a length.

**Imprecision errs LONG — toward the finding, never away from it** — and every case is named: an
unrecognised escape, a surrogate pair, an entity needing a DTD, a malformed reference, a numeric
reference naming no character XML permits, and a reference straddling the edge of a CDATA section.
Each counts as the source spells it. The XML entity set is the five the specification defines and
needs no DTD to resolve, and the permitted code points are the XML 1.0 `Char` production — both
accepted on the grounds `FILESYSTEM_ROOTS` and `_DRAWING` are: closed, externally specified, and they
do not grow. `Char` is a *permitted*-list, which is normally the enumeration pointed backwards; it is
allowed here because a code point it fails to recognise is not collapsed, so the error runs long.

#### Why not parse the JSON — declined on the merits, not deferred

The obvious answer to a class this persistent is to stop pattern-matching and classify the *parsed*
object. **It was weighed with five findings on the board and declined**, and the next person to
propose it should meet the measurement rather than re-derive it:

- **It adds a path, it does not replace one.** Partial pastes, JSON inside a Markdown fence, JSONL,
  JSON-with-comments and truncated documents do not parse — and those are what a leak actually looks
  like. *Nobody commits a well-formed export by accident; they paste a fragment.* So the parser
  covers the case that does not leak and leaves the regex path carrying the case that does, while the
  module grows a second classifier. **Two classifiers with two vocabularies is the documented
  mechanism by which the formats diverged in the first place.**
- **It closes nothing on the XML side**, and the class spans both formats — as the sixth finding
  proved. **An XML parser is refused for the same reason and one more:** the guard scans fragments,
  a parser refuses a fragment, and refusing means *no measurement*, which fails in the direction that
  misses rather than the one that reports. It also returns strings, which the `int` guardrail above
  exists to forbid, and it brings entity-expansion hazards a length function does not have. Recorded
  in `_xml_logical_length` itself, because that is where it will be proposed.
- Residual row 1 already says it for the type gate: *parsing would not show it is not genealogy.*

**Deleting the floor was weighed too, and declined.** It draws findings because it was *measured
wrong*, not because it is the wrong idea — which is the test for a deletion candidate, and it fails
it. JSON has no container to ask *"is this a label?"* of, the way the XML side asks `_DRAWING`, so on
that side the floor is the whole discriminator. Removing it reports a two-character caption under a
note key as a family tree.

**On the fixture module's headroom: it is a rule being enforced, not a margin being consumed.** The
worry was that the next Gramps fixture anyone adds would be the element that tips this file over.
Under the weighted score it does not work that way — **a fixture built by assembly contributes
nothing at any threshold, and one written as a literal trips the guard over this repository in CI.**
That is the assemble-at-runtime rule made mechanical rather than remembered, and it is why two
rounds running found literals here: the rule was documented and unenforced. It is enforced now.

⚠️ **These numbers are a snapshot of THIS repository at 30 files, and the zero will not stay zero by
itself.** Phases 1–7 add importer specs, schema notes and sample payloads — documentation *about
genealogy formats*, which is precisely what these properties count. **Re-measure when the repository
grows substantially, or when a phase lands that discusses a format in depth.** The instrument is in
the tests: the property is driven over every tracked file, so a threshold that has stopped being
affordable shows up as a failing test rather than as a mystery. A measured number with no
re-measurement trigger becomes folklore — which is exactly how a figure nobody could reproduce ended
up in the history baseline above.

The prefix-free form fails on the commonest paste there is: a diff marker abuts the digit with no
space, so `+0 HEAD` never matches. **Some notion of leading decoration is unavoidable in a
line-oriented format.** What the density property removes is the dependence on a level-0 record being
*present* — and that was the part no character class of any width could ever fix.

The single false positive was `tests/fixtures/synthetic.py`, which wrote half its GEDCOM lines as
literals while its own module docstring says to assemble them at runtime. Fixing the fixture took the
measurement to zero; that is a fixture obeying its own rule, not a guard being loosened.

⚠️ **The accepted residual: three consecutive lines of *number, uppercase word* are a finding
wherever they appear.** Concrete examples, so you recognise it rather than rediscover it as a bug:

- release notes reading `3 NEW endpoints`, `2 OLD routes removed`, `1 API change` on consecutive lines
- a table of counts whose rows begin with a number and an upper-case abbreviation
- a list of test identifiers of the same shape

None exists in this repository. The escape is the convention this project already runs on --
**describe, do not quote** -- and a genuine need is one entry on the safe list away.

### Known behaviours, deliberately left alone

**A committed name that is not valid UTF-8 is now a finding, not a residual.** It used to be
recorded as one, and inaccurately: the description said the name decodes with replacement characters
so a deny-list entry might miss it, which described one of the two enumerations while the other
aborted the whole scan. Both now use one decoder, and a name that cannot be decoded cannot be
classified — which is the property the guard already holds for content.

**File types are matched with a lower-cased extension but a case-sensitive basename.** A file
committed as a differently-cased `LICENSE` therefore reads as an unknown type and is reported. This
is deliberate and left as it is: it fails closed, and quietly case-folding *names* would be its own
behaviour change in a guard whose whole job is noticing names.

A `file:` URL is **not** on this list — it was a genuine hole and was fixed. `file:` addresses the
local filesystem; `http(s)` does not. One scheme with a defined meaning is a property, not an
enumeration.

**A protocol-relative URL whose authority is a filesystem-root word is reported as a rooted path.**
This is the measured cost of the rule that a run of separators is the separator it repeats
(issue #3 item 2). The rule is stated once and used wherever a separator *joins* components; where
two separators are **syntax** it is deliberately not used, and those places are named in the code:
the UNC opening marker, the pair that opens a URL authority, and the leading separator of a
path-bearing position — that last one because `file` is itself a trigger for that detector, so a run
there is an authority rather than a repetition. What remains is the shape detector, which cannot tell
an authority from a doubled root marker when the first word after it is one of the real filesystem
roots. **Measured before it was accepted:** the old and new patterns were run against every line of
tracked content (10,292 lines) and 291 synthetic constructions covering every detector, template and
false-positive control; **no input without a repeated separator changed verdict**, and the repository
reports zero findings at the tip and over the range. Failing in this direction is the one this
module's stated posture requires.

**A file the scan cannot read aborts the whole scan.** So does a directory it cannot list, and so
does a local deny-list it cannot read or decode. None of them is skipped and none is treated as
empty: a run that quietly steps over something it could not open reports clean over content nobody
looked at, which is the one thing this gate must never do. If a locked or permission-denied path
stops your scan, fix the permission or exclude the path deliberately — the abort is the guard
working.

The unlistable *directory* was the last of these to be fixed, and it failed in the opposite
direction from the other two: the walk's default is to drop a directory it cannot list and carry on,
so a denied subdirectory holding a whole tree passed clean.

The message you get names the kind of error and nothing else. Both of these failures used to escape
as an interpreter traceback, and the text an interpreter puts in one names the file it could not
open — an absolute path on your machine, in whatever log the gate was writing to.

## Scope discipline

Each phase has a spec with explicit out-of-scope items. Work outside them gets flagged in review,
even when it is obviously a good idea -- file it as an issue instead.

In particular, nothing imports `gramps` or `gi` until the phase that introduces the bridge — with
**one recorded exception**, adjudicated rather than assumed.

The Phase 1 date-model ruling permits `gramps.gen.lib` inside `core/`, because a genealogical date
is the one value this project cannot afford to translate: a hand-rolled model mapped at the write
boundary puts a lossy layer exactly where a wrong date would be written silently. The exception is
**conditional on an import check passing on every supported Python** — until it passes, nothing
imports it, and if it fails the fallback is a hand-rolled model with the reason recorded.

`gi` is not covered by the exception, and neither is anything else. See
`docs/phase1-core-schema.spec.md`.

## Commits

Conventional commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`). The commit message says what
changed and why; for a test-first change it also records the red result that preceded it.
