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
| **Not a miss but a deliberate false positive, recorded here because it is the same trade read backwards: a NAMESPACE-PREFIXED drawing is not a drawing**, so `<x:svg>` holding short `text` elements is reported rather than exempt — whatever `x` is bound to, including the SVG namespace itself. | Added when the drawing exemption's use of the shared qualified-name alternation was deleted. A prefix is matched by **shape** here and never resolved, and that mechanism points in opposite directions depending on what reads it: for the three patterns that **score** an element, matching more elements means more *findings* — conservative; for an **exemption**, matching more containers means more *suppression* — fail-open. The input that proved it is a prefix bound to a namespace that is not SVG: the container had the shape of a drawing, the exemption applied, and a name, a date of birth and a place went from a finding to nothing by being wrapped in a tag whose meaning nothing checked. **A conditional exemption is where fail-open lives.** Both repairs that keep the fourth site were rejected — resolving the prefix means reading namespace bindings, which is a parser, refused repeatedly here; and requiring the namespace URI somewhere in the document is *still a condition on an exemption*, and wrong in the case that matters, because a document may bind that URI to a different prefix entirely. **Where it eventually belongs is issue #33's rendering boundary:** a structural guard over what the preview *emits*, across all rendered fields, can answer "is this really a drawing" — that is the right home for the question, rather than a condition bolted onto an exemption in the scanner. Of the two directions, failing closed is the one this module's stated posture requires. Asserted by test in both directions, on the same payload: the unprefixed drawing still exempts its labels, the prefixed one does not. |
| **The detail inside a failure message cannot be revealed, not even locally.** The flag that reveals matched values does not reveal it. | The redacting wrapper renders when the failure is raised, so what reaches the printing site is already finished text and a flag has nothing left to un-redact. Making it work means the failure carrying the wrapped value intact all the way to that site -- **a second route to a wrapped value, running through the paths that are exercised least.** That is what was refused when the ordering comparison was declined, for the same reason: the wrapper is worth having only while there is exactly one audited way to the value, and error handling is the worst place to add a second. **Kept:** the message names the kind of error in clear and carries the detail redacted, both asserted by test, so an operator learns what failed and where. **Lost:** diagnosing one of these means reproducing the failure, not re-reading the message. |
| **A container the published schema declares whose spelling is also an HTML or SVG element name scores nothing** -- `title`, `style`, `code`, `map`, `object`, `source` and `header`. A real export earns nothing from its `<title>` or `<source>` elements. | Added with #4's derived container table, and it is what makes that table affordable. At even the smallest weight four filled ones reach the threshold, and two ordinary documentation fragments were measured doing exactly that -- see the table above. The collision is read off the published HTML and SVG element indexes rather than a list maintained here, on the ground `FILESYSTEM_ROOTS` is accepted on: closed, externally specified, and not growing at our discretion. **What is lost is small and stated:** such an export is caught many times over by the eighty-odd spellings that collide with nothing. **The rejected alternative is a document-level structural gate** -- score them once the file has proved it is Gramps -- which is the more precise answer and is a second document-level condition on the XML scorer; refile it if a real export is ever measured slipping. ⚠️ The rule applies only to rows that table ADDS: `text` and `address` collide too and keep their weights, asserted by test, because zeroing a row already caught is a retraction dressed as a widening. |
| **A container that can hold a sentence but is not narrative about a person scores 1, not 4** -- `description`, `cause`, `page`. | Added with the same table. Prose weight is for containers whose *purpose* is narrative about a person, which the schema says of `note` and `text` and does not say of a caption on a media object or a URL. **What is lost:** a whole biography written into a single `<description>` scores 1 and escapes on its own. **What promoting them would cost:** one filled element clearing the threshold in any schema document that shows an example -- precisely the document Phase 1 is about to write -- and a finding nobody can act on is a finding contributors route around. Two of them together are still caught. The deny-list is the backstop, here as elsewhere. |
| **Custom and extension elements the published schema does not define stay uncovered**, and so do schema versions other than the pinned one. | The stated residual of #4's exit condition, recorded when that condition was re-specified rather than discovered afterwards. A derivation closes the list the specification declares and says nothing about what a vendor adds to it, and a container introduced by a later version is not in the table until the table is re-derived. The deny-list is the backstop. |

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

### Recorded decision: the container list is derived, and markup spellings earn nothing

Which containers exist stopped being a judgement in #4's Change C1. The list is derived from the
published Gramps XML schema and frozen as a committed table — see the derivation note in `docs` —
which took the Gramps vocabulary from 29 spellings to 110. Both directions, measured against the
previous head:

| Payload | Before | After | Without the unweighted category |
| --- | --- | --- | --- |
| researcher block (a name and an address) | 0 | **6** | 6 |
| name detail — call name, nickname, suffix | 0 | **6** | 6 |
| a source credited to a person | 0 | **5** | 5 |
| place block | 0 | **4** | 5 |
| event block | 0 | **4** | 4 |
| repository block | 0 | **4** | 4 |
| an ordinary HTML fragment: four colliding tags | 0 | **0** | **4 — reported** |
| a documentation page: `header`, `source`, `object`, `map` | 0 | **0** | **4 — reported** |
| a genuine export fragment *(control)* | 5 | 5 | 5 |
| an importer specification *(control)* | 0 | 0 | 0 |
| one long note, the prose floor *(control)* | 4 | 4 | 4 |

The third column is the same change with the deliberately-unweighted category switched on to
structural weight. **That column is the whole argument for the category:** the schema declares
`title`, `style`, `code`, `map`, `object`, `source` and `header`, and two ordinary documentation
fragments reach the threshold exactly without it. The collision is read off the published HTML and
SVG element indexes, which is the ground `FILESYSTEM_ROOTS` and the drawing exemption stand on.

⚠️ **The alternative this section recorded as rejected was afterwards ruled IN, and it is the
next section.** The two indexes cannot see the collision that actually mattered — `type`, `file`,
`status` and `description` are schema spellings that are also ordinary XML names, and they are in
neither index. The unweighted category answered the collision it was shown. The gate below answers
the other one, and it is scoped to **rows** rather than to files, which is what the "second
document-level condition" objection above was really about.

⚠️ **One claim this change was planned against did not reproduce, and it is recorded rather than
quietly dropped.** The existing markup false-positive test — a document holding a filled `<title>`
— was named in advance as the thing a careless widening turns red. Measured, its document scores
**0 in all three columns**: it holds two filled elements and only one of them, `title`, is a schema
spelling at all. The real exposure is the two fragments above, and the test was never the tripwire
it was described as.

**Exposure over this repository's own content, before and after.** Before: two filled element
literals in all tracked content, both on one line of one test file, and neither was a vocabulary
spelling, so that file scored 0. ⚠️ **This change was planned against that pair costing 2, and it
was 1** — `body` is not in the schema at all, so only `title` was ever going to gain a row. After:
the same probe finds four literals, the two new ones being regex fragments in the derivation script
and not schema spellings; exactly one tracked file contains a filled element the vocabulary knows,
`<title>`, which weighs **0**. So **no tracked file scores anything at all**, before or after. The
counterfactual is where the category shows: without it that file would score 1, against a threshold
of 4.

**Cost.** The alternation went from 29 alternatives to 110. Over the widest corpus available — 401
blobs, 11.4 MiB, every blob the history reaches — scoring took **0.066 s before and 0.071 s after,
best of three: 1.11×**, against a bound of 2×. End to end the tip scan went 2.34 s → 2.54 s and the
published-range walk over 91 commits ran in 15.5 s, clean. ⚠️ Every figure here is from a **Windows
11 development machine on Python 3.12.13**; the runner is an order of magnitude faster on the
history walk, for the reason recorded against B8.

**Three weights that a reader will want to promote, and why they stay structural.** `description`,
`cause` and `page` can each hold a sentence, and `<description>` reads like prose. Prose weight is
for containers whose *purpose* is narrative about a person — which the schema says of `note` and
`text` and does not say of a caption on a media object. Promoting them would make one filled element
clear the threshold in any schema document that shows an example, which is the document Phase 1 is
about to write.

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
fails three tests including the one asserting **this repository** is clean. **The gate is what
separates a genealogy vocabulary from a list of common English keys.**

⚠️ **This paragraph used to end "the XML side needs no such gate", and that stopped being true the
moment the container list was derived.** It was true of the 29 spellings a reviewer had named:
`surname`, `dateval`, `placeobj` and `childref` are format-specific words. It is not true of the
~80 the published schema added, some of which — `type`, `file`, `status`, `description` — are words
any XML document may use. The XML side now has the same shape of gate, scoped to those added rows;
see the section below.

### Recorded decision: a derived row scores only where the document names the format

The section above widened the Gramps vocabulary from 29 spellings to 110 by deriving it from the
published schema. **Some of what the schema declares are ordinary XML names.** `<type>`, `<file>`,
`<status>` and `<description>` are containers of the Gramps format *and* words any document about
any XML may use, so four filled ones reached the threshold in a Markdown, Python or YAML file with
no Gramps namespace, no database element and no marker of the format anywhere in it.

**The rule: a spelling this audit ADDED scores only when a Gramps marker appears in the same text.
A spelling the vocabulary held before the audit scores exactly as it always did, with no marker
required.**

⚠️ **The gate is scoped to ROWS, not to files, and that is the whole of why it is safe.** A
file-level condition on the XML scorer would suppress a pre-existing catch in a file carrying no
marker — a note holding a biography, a bare name block — which is a retraction rather than a
narrowing. Cutting the gate's domain out of the frozen pre-audit snapshot makes that impossible by
construction: a pre-existing row is not in the domain, so no measurement is needed to show the gate
did not reach it.

**What a marker is, and where it comes from.** A hand-written list of markers would be the
enumeration this project refuses, one level up from the one the derivation just removed:

| Marker | Source it is bound to, by test |
| --- | --- |
| the declared namespace, **as the value of an `xmlns` attribute in a start tag** | the `#FIXED` default the schema gives the `xmlns` attribute of its document element, emitted into the frozen table as `FIXED_ATTRIBUTE_DEFAULTS` |

⚠️ **Shape and value, together, in one condition — because the gate has been wrong twice on this
one axis and each time it held exactly one of the two halves.**

- **Shape without value.** It was THREE markers, and two of them read *structure* and never a value:
  a doctype whose `Name` was the document element, and that element carrying an `xmlns` attribute at
  all. So `<database xmlns="urn:example:ledger">` beside four filled `<type>` elements re-enabled
  every derived row and scored **5, reported**; the doctype spelling scored **4, reported**. A
  document that has explicitly named *another* format was read as Gramps.
- **Value without shape.** Those two were deleted and a plain substring test over the decoded text
  was left. A **prose sentence** naming the namespace — an import note, a changelog entry, this
  project's own documents — beside four generic `<type>` elements then scored **6, reported**.

Each half was rejected only for lacking the other, so the marker requires both **at one position**:
the schema-fixed value as the value of an `xmlns` attribute reachable from a start tag's name
through complete attributes. XML 1.0 §3.1's `STag`, `Attribute`, `Eq` and `AttValue` are transcribed
rather than approximated, and here that is not academic: the cheap approximation `<[^<>]*xmlns=`
accepts the namespace quoted inside **another attribute's value**, which is the first thing a
reviewer constructs next.

⚠️ **And that is ONE compiled pattern, not a composition.** An `or` over two results is the defect
being fixed wearing a conjunction. An `and` is wrong too, and it is the wrong one worth naming:
`shape.search(text) and value in text` is satisfied by a document declaring an unrelated namespace in
a file that mentions the Gramps one three paragraphs down. **Two conditions verified at two positions
are not one condition.**

⭐ **How this came to be a bare substring test, recorded because the next reader's cheapest move is
to simplify it back to one.** The conductor prescribed binding the structural marker to the namespace
value. The plan gate **disputed it, and was right**: bound to the value, a shape marker is a strict
subset of the substring test and can never add a match — tightened they were dead weight, loose they
were the false positive, so they were deleted rather than tightened. **That proof was valid and its
premise was unsound.** It holds only because the substring test matched *anywhere*, and that
unrestricted reach is itself the defect the next round found. Nobody questioned the premise,
including the conductor who approved the dispute. **A subset argument is only as good as the set it
is taken inside**, and this stands as evidence that a dispute needs re-examining on the same terms a
prescription does.

**The doctype could not be bound either way**, which is why it is gone rather than anchored: the only
Gramps-specific evidence it carries beyond the namespace is the public identifier, which appears in
no artifact this repository has frozen — the DTD does not declare its own — so correcting it would
need exactly the hand-typed literal this design forbids. The choice was never *tighten or delete*; it
was *delete, or keep something known-broken*.

**The prefixed case is carried by a shared production, not by blindness.** A substring test over the
whole text was blind to prefixes **by construction**, which made Change A's equivalence property free
at this site and is no longer available. `<x:database xmlns:x="…">` names the format because the
declaration's name is `xmlns:` followed by the **same transcribed `NCName`** the element patterns
read — one production, three readers, no second table to keep in step. It is asserted in both
directions and over every alias, because the positive half alone is satisfied by a gate that accepts
everything.

⚠️ **`pii_guard` does not import `_specified_containers`.** That module is data, not behaviour, and
the scan does not change if it is deleted. The markers are composed constants in the guard, bound by
test to the frozen table — the same standing the vocabulary itself has.

#### Both directions, measured

Every figure below is from a **Windows 11 Pro 10.0.26100 development machine, CPython 3.12.13 via
`.venv\Scripts\python.exe`**. The gate's own columns are against the pre-change head `fcc56b2`; the
marker-deletion columns are against `3f9f46c`, the head the reviewer found on; the **anchoring**
columns are against `92e6c88`, the head the round-4 reviewer found on. **Every table was re-walked on
the current head rather than carried forward**, and where a figure moved — or was wrong — it is
corrected below rather than quietly adjusted. A runner is an order of magnitude faster on the history
walk, for the reason recorded against B8.

**(a) What the gate removes — the direction this change is for.**

| Payload, no marker anywhere | Before | After | Re-walked now |
| --- | --- | --- | --- |
| four filled `<type>` elements | 4 — **reported** | 0 | 0 |
| `<file>`, `<status>`, `<description>`, `<type>` | 4 — **reported** | 0 | 0 |

⭐ **What ANCHORING removes, and it is the same direction one turn further out.** Measured against
`92e6c88`:

| Payload | Before | After |
| --- | --- | --- |
| a prose sentence naming the namespace + four filled `<type>` elements | 6 — **reported** | 0 |
| that sentence on its own | 0, marker **read as named** | 0, marker not named |
| `<database xmlns="urn:example:ledger">` + four filled `<type>` elements | 0 | 0 |
| the same, spelled as a doctype naming an unrelated identifier | 0 | 0 |
| the namespace quoted inside **another attribute's value**, + a researcher block | 8 — **reported** | 0 |

⚠️ **The last row is the one the transcription buys and the approximation loses.** An element whose
`desc` attribute *describes* a declaration has declared nothing; under the substring gate that text
named the format and the fragment beside it was a finding. It is measured through a wrapper the
vocabulary does not hold, so the figure is the gate's and not the wrapper's — the same probe written
round an element that *does* carry weight measures 12, and that number would have been the wrapper's
as much as the gate's.

**(b) The retained side — the control, and the half that can break silently.**

| Payload | Before (`fcc56b2`) | Now |
| --- | --- | --- |
| a bare name block, no marker | 4 | 4 |
| a note holding a biography, no marker | 8 | 8 |
| a person fragment, no marker | 9 | 9 |
| a whole export | reported by the **database element signature**, before any scorer runs | unchanged |

⭐ **And the half anchoring could have broken silently: a genuine document must still name itself.**
Every row here is a real declaration carrying a researcher block, measured on the anchored head:

| A declaration, and the fragment beside it | Score |
| --- | --- |
| `xmlns="…"`, unprefixed, double-quoted | 8 — **reported** |
| the same, single-quoted | 8 — **reported** |
| `xmlns:g="…"` on `<g:…>` | 8 — **reported** |
| `xmlns:x="…"` where `x` is `a` + COMBINING ACUTE ACCENT | 8 — **reported** |
| a start tag truncated before its `>` | 8 — **reported** |
| the namespace fragment fixture, and a whole export | 4 and 8 — **reported**, unchanged |

The last row is what says anchoring did not quietly require the document element: a fragment
declares the namespace on whatever wrapper it has.

⚠️ **Three of those four figures were wrong when they were written, and the correction is recorded
rather than made silently.** This table read `4 / 4 / 6 / 9`. Re-walked at `fcc56b2` — its own
*Before* head — the same fixtures measure `4 / 8 / 9`, and the whole export is not scored at all: it
trips `_GENEALOGY_TEXT_SIGNATURES`, which short-circuits `_sniff_genealogy` before the scorer, so a
score for that row was never a thing to record. The three stale numbers are the pre-derivation
weights, carried forward from an earlier document instead of re-measured after the vocabulary went
from 29 rows to 110. **The claim the table makes was true and is still true** — every one of these is
unchanged by the gate, by the marker deletion, and by the derivation repair — but a number that once
matched is the worst kind of stale, because it reads as considered.

Every row of the vocabulary is held to this by the per-row tests rather than by these four
examples: the attested spellings are re-measured **without** a marker, and every added spelling is
re-measured **with** one against the weight its category declares.

**(c) ⭐ The residual — the cost the owner ruled in, measured rather than described.**

| Genuine Gramps fragment, quoted without its marker | Before | After | Re-walked now |
| --- | --- | --- | --- |
| a researcher block — `<researcher>` wrapping `<resname>`, `<rescity>`, `<respostal>` | 6 — **reported** | 0 | 0 |
| an events block — two `<event>`s, each with a `<type>` and a `<description>` | 4 — **reported** | 0 | 0 |
| the same researcher block, format named | 8 — reported | 8 — reported | 8 — reported |
| the same events block, format named | 6 — reported | 6 — reported | 6 — reported |

⭐ **A second residual arrived with the marker deletion, and it is the whole of what that deletion
cost.** A genuine Gramps document naming itself **only** by a PUBLIC-only doctype — no namespace
anywhere in the text — no longer enables derived rows. Measured against `3f9f46c`:

| Genuine Gramps fragment under `<!DOCTYPE database PUBLIC "-//Gramps//DTD …">` | Before | After |
| --- | --- | --- |
| the same researcher block | 6 — **reported** | 0 |
| the same events block | 4 — **reported** | 0 |

⚠️ **This is not newly discovered, and it is not presented as such.** The marker block's own honest
note recorded, when the doctype marker was written, that this single case *was* that marker's entire
reach: a whole export carrying a doctype or a namespaced document element already trips
`_GENEALOGY_TEXT_SIGNATURES`, which short-circuits `_sniff_genealogy` before any scorer runs. What
the deletion removes is the case that note had already named.

⭐ **A third and a fourth arrived with the ANCHORING, and between them they are the whole of what it
cost.** Both measured against `92e6c88`, neither assumed.

**Residual (a) — a genuine fragment quoted beside a bare MENTION of the namespace.** The direct
price of closing the reproduction: an import note that names the format in prose and pastes a block
out of an export used to be caught, and is not.

| Genuine Gramps fragment, beside a prose mention of the namespace | Before | After |
| --- | --- | --- |
| the same researcher block | 8 — **reported** | 0 |
| the same events block | 6 — **reported** | 0 |
| either of them under a real **declaration** | 8 / 6 — reported | 8 / 6 — reported |

**Residual (b) — a declaration whose quotes are JSON-ESCAPED.** A Gramps export embedded in a JSON
blob reaches the gate spelled `xmlns=\"…\"`, because `_decoded` deliberately does **not** fold `\"`
— a structure character — and the anchored pattern reads the `AttValue` production, which a
backslash is not part of. The substring test did not care.

| A genuine declaration with escaped delimiters, + a researcher block | Before | After |
| --- | --- | --- |
| `{"note": "<database xmlns=\"…\">"}` + the researcher block | 8 — **reported** | 0 |

⚠️ **The pattern is deliberately NOT widened to absorb residual (b), and that is a decision rather
than an omission.** Admitting an optional backslash would make it read something that is not the
`AttValue` production, in a module whose recorded principle is *one normalisation at the funnel, not
two patterns taught one more spelling each* — see the serialization section below, whose defect class
is now on its eighth instance. If escaped delimiters are to be folded, `_decoded` is the site, and
that is #50's shape rather than this gate's. **Filed there, not half-fixed here.**

**A comment or a CDATA section quoting a start tag is still read as a declaration**, and that is
recorded as a residual rather than a repair postponed: it fails toward **reporting**, which is the
direction a guard may fail in, and closing it needs a comment stripper — machinery this project has
already watched fail open once. Its sharpest spelling is not reachable in any case: a comment quoting
the real `<database … gramps…>` line trips `_GENEALOGY_TEXT_SIGNATURES`, which short-circuits
`_sniff_genealogy` before any scorer runs. Measured: such a comment beside a researcher block scores
8 and is reported, before and after.

⚠️ **Anchoring does NOT touch #50 and does not half-fix it.** The gate still reads **decoded** text
and `_decoded` still does not fold character references, so `gr&#97;mps` evades both sites exactly as
it did. What moves is only *where* the evasion has to sit: previously anywhere in the text, now
inside the declaration's `AttValue`. The production admits `Reference` there and the pattern's value
class admits `&` for that reason — so a `_decoded` that folds character references closes the marker
site with **no change to this pattern**.

⚠️ **Neither residual is negligible and neither is described as such.** What makes it affordable is narrower and
is stated precisely: **the 29 attested spellings — the rows that name a person on their own — score
exactly as they do today, marker or no marker.** A fragment carrying `<person>`, `<name>`,
`<first>`, `<surname>`, `<street>`, `<city>`, `<text>`, `<note>`, `<dateval>`, `<placeobj>` or
`<childref>` is unaffected. The rows that predate the audit are the rows that carry a person.

⚠️ **Two corrections to the numbers this change was planned against**, recorded rather than quietly
adjusted. The researcher block was predicted at **7** and measures **6**: `<researcher>` wraps child
elements, so it is not a *filled* element and contributes nothing — the 6 is `resname`, `rescity`
and `respostal` at address and identity weight. And an events block of **one** event was predicted
to be a finding; it scores **2**, below the threshold, before and after. It was never a finding to
lose, so the row above uses two events, which is the smallest events block that was one.

⚠️ **The name path is a hole in the gate, stated plainly.** `scan_blob` runs the genealogy
properties over the committed *path* as well as the contents, and one short filename can essentially
never carry a marker — so a derived row will never score on a name. That is a residual of the gate,
not a defect in its scoping, and it costs nothing today: the committed name that is a finding is a
GEDCOM record and rests on the record signature rather than on the XML scorer.

**(d) B8's two rows, walked and not inferred from each other.**

| Row | Result |
| --- | --- |
| tip — `python -m gramps_live_api.core.pii_guard .` | 0 findings over 45 tracked entries |
| published range — `--range HEAD` | 0 findings over 105 commits, 206 entries scanned |
| `test_every_commit_this_repository_publishes_is_clean` and `test_this_repository_is_clean` | both **ran** on a complete checkout, both passed |

Both rows were **walked again** on the head that anchors the marker, not inferred from the tip and
not carried forward — as they were on the head that deleted the two markers and the head that
recorded it. **The verdict — 0 findings — is what must not move.** The commit and entry counts grow
with the history and did: 98 → 102 → 105 commits and 187 → 198 → 206 entries, and the commit carrying
this sentence necessarily adds one more, which is why the row above is read for its verdict rather
than its arithmetic.

⚠️ **Anchoring is safe here by construction and the walk is run anyway.** Every match of the anchored
pattern contains the namespace, so its match set is a strict **subset** of the deleted substring
test's: no tracked file can begin to name the format that did not already. That is an argument about
the data, and the lesson recorded further down this file is that such an argument does not carry to
the code that reads it — so the row is measured, not deduced.

**(e) ⚠️ The code's own constants, under every spelling the code treats as equivalent.** A sweep
over tracked content does not read the values living inside the code, and that is exactly what let
an earlier allowlist regression through a careful measurement. Every tracked file was read and
searched for every vocabulary spelling as a filled and as an attributed element, and for the
namespace and for what the gate reads, under **case** variants (the element patterns are
`IGNORECASE`), **prefixed and unprefixed** forms, **separator** variants — backslash, escaped
solidus, doubled, percent-encoded — and the **escaped forms `_decoded` folds** (`/`, `&#47;`).

⚠️ **Re-walked for the anchoring round against `92e6c88`, with the CODE and the CORPUS chosen
separately**, because the anchored pattern is itself new text in a tracked file:

| What the sweep found | Before (`92e6c88`) | After |
| --- | --- | --- |
| the namespace, in any of **19** spellings, in any tracked file | none | **none** |
| **tracked files the gate reads as naming the format** | none | **none** |
| filled vocabulary elements | one — `<title>` in `test_pii_guard_p1_paths.py`, weight 0 | unchanged |
| attributed vocabulary elements | nine | **ten** — see below |
| highest un-thresholded score of any tracked file | **0**, against a threshold of 4 | **0** |

⚠️ **That 19 is THIS sweep's construction, not a figure carried forward from the nine the deletion
round reported.** It is six separator spellings — as written, backslash, JSON's escaped solidus,
doubled, percent-encoded, `&#47;` — crossed with four casings and deduplicated. A count of a spelling
set is a fact about the set, so it is stated with its construction or it means nothing.

The specific thing this catches is the `FIXED_ATTRIBUTE_DEFAULTS` emission, which puts the namespace
value into a tracked `.py` file. It is emitted split at its own separator for exactly that reason,
and the first row is the check that the split works: the value appears contiguously nowhere, in any
spelling asked for. The fixture module's new `<catalogue xmlns="…">` builder is the same rule applied
one level out — it composes the value at runtime and stores none of it.

⚠️ **One row moved, and it is the sweep reading its own text.** The attributed count goes from nine
to ten because the guard's rewritten marker block spells the round-2 reproduction twice where it
spelled it once. Every one of the ten carries an **unrelated** namespace or an elided one, and the
second row is what that means: no tracked file names the Gramps format, so ten mentions are worth
exactly nothing and the repository's own headroom is unchanged at **0** against a threshold of 4.

**(f) Criterion 13 — the 2× wall-clock bound.** The gate now runs **one pattern search and zero
substring tests** per scored text, where it ran one substring test and none; the pattern's attribute
loop is the one place a regression could hide, so this is a real check rather than a formality.
Measured best of three, with both code versions run over the **same** corpus (this repository at the
current head) so the figures isolate the change, and with each run's loaded module path confirmed
before its figure was believed:

| | Before (`92e6c88`) | After | Ratio |
| --- | --- | --- | --- |
| tip scan, 45 entries | 2.00 s | 2.00 s | **1.00×** |
| published-range walk, 105 commits / 206 entries | 19.14 s | 18.90 s | **0.99×** |

⚠️ **Read the ratios, not the seconds.** Absolute figures move between sessions on the same machine —
the marker gate's own pair was 2.83 s and 33.40 s, and the deletion round's 1.97 s and 19.71 s. Each
pair is internally comparable and no two pairs are comparable with each other. The bound is a ratio
for that reason.

### Recorded decision: every XML production is transcribed, and a test keeps the set closed

**Five review rounds on `pii_guard` found the same defect five times: a Python shorthand standing in
for an XML production.** `\s` for `S`, `\b` for the end of a `Name`, `\w` for `NameChar`, a bare
substring for a URI. Each was repaired where it was reported, and the next round found the next one.

**The round that closed it did not repair three more sites; it enumerated all of them and adopted a
rule that decides each one, then made a test hold the rule.** The rule:

> **Transcribe an approximation whose looseness ADDS structure the document does not have** — a
> marker firing, an exemption applying, a name ending where XML says it does not. **Leave, with a
> recorded reason, an approximation whose looseness only makes the guard read more content as data.**

That is the module's own scorer-versus-exemption line one level down, and it is decidable **per
pattern** rather than per input, which is why the set closes at twenty rows: **nine transcribed,
seven left with reasons, two deleted or reached deliberately, and two decided in the plan.**

⚠️ **One of the nine has since been RETIRED, so the current split is eight transcribed and three
deleted-or-retired.** The twenty sites are unchanged; `scheme` moved between two of the columns.
See the transcription table below and the URI-scheme section after it.

⚠️ **THE AUDIT IS PROSE AND PROSE DOES NOT FAIL WHEN SOMEBODY ADDS PATTERN TWENTY-ONE.**
`test_no_pattern_reading_an_xml_production_uses_a_python_shorthand` is what keeps the set closed.
Every compiled pattern the module holds is **walked off the module** — a listed enumeration would be
the same defect pointed backwards — and each needs a row naming the shorthands it may hold **and the
reason**. The rows for the GEDCOM, JSON and path patterns are the point rather than filler: *"this
one reads no XML production"* is exactly the sentence whose absence is indistinguishable from nobody
having looked.

**Its non-vacuity is demonstrated rather than asserted.** Four mutations were applied to the real
files, each restored in a `finally`, and the test caught all four: a new pattern nobody weighed, the
marker's `S` widened back to `\s`, the drawing's name end dropped back to `\b`, and a licence row's
recorded reason deleted. The tree was verified clean afterwards.

**What was transcribed, and what each one bought:**

| Production | Source | The input it was losing |
| --- | --- | --- |
| `S` | XML 1.0 §2.3 | `<wrapper` + U+00A0 + `xmlns="…">` read as a declaration — at **three** constants, the third of which no reviewer named |
| end of `Name` | Namespaces §3 | `<type-extra id="x"/>` scored as `<type>`, and `<type:extra>` scored as its own prefix |
| `scheme` — ⚠️ **retired, see below** | RFC 3986 §3.1 | `xmlns="urn:not-gramps:…"` read as this namespace |
| `S` and end of `Name`, in `_DRAWING` | as above | `<svg-chart …>` opening the exemption — **a live fail-open** |

⚠️ **`scheme` was retired one round later, and the property it bought is RE-ATTRIBUTED rather than
deleted.** Transcribed *faithfully*, RFC 3986's `scheme` admits every syntactically valid scheme —
so `xmlns="ftp://…base…/1.7.2/"` named this format, which is the reproduction the next section is
about. The transcription is gone and **`urn:not-gramps:…` is still refused**, now by the tolerance
table rather than by the production, so this row records where a still-live property came from. A
document that simply dropped the row would leave the next reader thinking the refusal went with it.

**Left standing, with reasons** — the seven rows are in the licence table itself, and the two worth
repeating here are `_GRAMPS_FILLED_ELEMENT`'s ETag `</\1\s*>` and `_GRAMPS_ATTRIBUTED_ELEMENT`'s
`[^>]*?\w+\s*=\s*["']`. Both are loose, both sit in a **scorer**, and there a loose reading is one
more finding rather than one fewer. The second is visibly the `<[^<>]*xmlns=` shape the marker block
condemns; it is recorded rather than repaired, so a sixth round finds it dispositioned instead of
reporting it again.

**`_XML_PROLOG` was deleted rather than transcribed.** Two shorthands, no reader anywhere in the
repository. Machinery nobody reads is a candidate for deletion, not for hardening.

#### Both directions, measured

Every figure below is from a **Windows 11 Pro 10.0.26100 development machine, CPython 3.12.13 via
`.venv\Scripts\python.exe`**, against the pre-change head **`5745d05`**.

**(a) What the transcription removes — the direction this change is for.**

| Payload | Before | After |
| --- | --- | --- |
| `<wrapper xmlns="urn:not-gramps:…base…">` + four filled `<type>` | 6 — **reported**, marker `True` | 2, below the threshold |
| `<wrapper` + U+00A0 + `xmlns="…/1.7.2/">` + four filled `<type>` | 6 — **reported**, marker `True` | 2, below the threshold |
| a real declaration + four `<type-extra id="x"/>` | 6 — **reported** | 2, below the threshold |
| every vocabulary row suffixed by a `NameChar`, filled and attributed | **103 of 110 rows scored**, under each of 8 suffixes, in both shapes | **0** |
| a start tag separated by a character Python calls whitespace and XML does not | 26 characters × 5 positions named the format | **0** |
| `<svg-chart>` + a name, a date of birth and a place + `</svg>` | 0 — **suppressed** | 6 — **reported** |

⚠️ **All three reproductions still score 2, and that 2 is `#51`.** It is
`_GRAMPS_NAMESPACE_WEIGHT`, charged for the namespace appearing as a bare substring anywhere in the
text, and this round does not touch it. Demonstrated rather than reasoned: replacing the namespace
in each reproduction takes the raw score from 2 to **0**. Against a threshold of 4 all three close —
**but a fix to `#51` will move these numbers**, and whoever takes it should find that written here.

**(b) The retained side — the control, and the half that breaks silently.**

⚠️ **The transcriptions TIGHTEN every matcher, so they can remove findings.** Both directions:

| Payload | Before | After |
| --- | --- | --- |
| every vocabulary row written as ITSELF, filled and attributed | 103 of 110 scored | **103**, unchanged |
| a genuine declaration + a researcher block, unprefixed double-quoted | 8 — reported | 8 |
| the same, single-quoted | 8 | 8 |
| `xmlns:g="…"` on `<g:…>` | 8 | 8 |
| `xmlns:x="…"` where `x` is `a` + COMBINING ACUTE ACCENT | 8 | 8 |
| a start tag truncated before its `>` | 8 | 8 |
| the namespace fragment fixture, and a whole export | 4 and 8 | 4 and 8 |
| an ordinary drawing's labels | 0, exempt | **0, exempt** |
| a prefixed drawing's labels | 4 — reported | 4 — reported |
| an alias bound to something that is not SVG | 6 — reported | 6 — reported |
| prose mention · unrelated namespace · unrelated doctype · the namespace inside another attribute's value | 0 · 0 · 0 · 0 | 0 · 0 · 0 · 0 |
| researcher and events blocks, unmarked / beside a mention / under a declaration | 0 / 0 / 8 and 6 | unchanged |

The last two rows are the previous rounds' residuals, re-walked rather than carried forward.

**(c) The scope extension, reported rather than slipped in.** Putting the name's end inside
`_qualified()` reaches `_GENEALOGY_TEXT_SIGNATURES`' database signature, which was otherwise out of
that round's scope. **The effect on genuine input is nil, measured:**

| Probe | Before | After |
| --- | --- | --- |
| `<database xmlns="…gramps…">` | signature, P2 | signature, P2 |
| `<g:database xmlns:g="…">` | signature, P2 | signature, P2 |
| the same with a newline after the name | signature, P2 | signature, P2 |
| `<database-x …>`, `<database.new …>`, `<database:extra …>`, `<database` + U+0301 | signature, P2 | **no signature, no finding** |

**Residual:** a one-line fragment whose element name merely *begins* with `database`, declaring the
namespace and carrying no genealogy content, is no longer a finding on its own. It is not an element
called `database`, so this is an over-report removed rather than data escaping — and a document with
actual content still scores through the marker and the rows.

**(d) B8's two rows, walked and not inferred from each other.**

| Row | Result |
| --- | --- |
| tip — `python -m gramps_live_api.core.pii_guard .` | 0 findings over 45 tracked entries |
| published range — `--range HEAD` | 0 findings over 117 commits, 222 entries scanned |
| `test_every_commit_this_repository_publishes_is_clean` and `test_this_repository_is_clean` | both **ran**, both passed |

The verdict is what must not move and did not; the counts grow with the history and did, 105 → 117
commits and 206 → 222 entries. ⚠️ **Those two numbers are stale the moment they are written** — the
commit carrying this sentence adds one, and every commit after it adds another — **which is why this
row is read for its verdict rather than its arithmetic.** `0 findings` is the claim; `117` is the
timestamp on it.

**(e) ⚠️ The code's own constants, under every spelling the code treats as equivalent** — re-walked
with the CODE and the CORPUS chosen separately, because this round's new patterns and their
docstrings are themselves new text in a tracked file. Nineteen namespace spellings, the same
construction as before: six separator spellings crossed with four casings, deduplicated.

| What the sweep found | Before (`5745d05`) | After |
| --- | --- | --- |
| the namespace, in any of **19** spellings, in any tracked file | none | **none** |
| tracked files the gate reads as naming the format | none | **none** |
| filled vocabulary elements | one — `<title>` in `test_pii_guard_p1_paths.py` | **two** — see below |
| attributed vocabulary elements | ten | **thirteen** — see below |
| highest un-thresholded score of any tracked file | **0**, against a threshold of 4 | **0** |

⚠️ **THIS SWEEP CAUGHT A REGRESSION THIS ROUND HAD ALREADY COMMITTED, and no gate did.** A docstring
explaining why the substring reading was wrong wrote the reproduction out verbatim, putting the
namespace **contiguously into a tracked file for the first time in this repository's history**. It
was not a finding — a bare mention scores 2 against a threshold of 4 — so `pytest`, `ruff`, `mypy`
and the guard itself were all green. What it did was take **this repository's own headroom from 0 to
2**, which is the margin this row exists to measure and which no test asserts. Fixed in `feeff36`,
and recorded here because a measurement that only ever confirms what was expected is not being run
for a reason.

**The rows that moved are the sweep reading this round's own explanatory text**, and four of the
five are in *this section*. The filled count gains a `<type>` mention inside a docstring about
`<type-extra>`; the attributed count gains a `<type …>` beside it and the two `<database …>` probes
in the scope-extension table above. Every one is a gated derived row in a file that names the format
nowhere, so every one is worth **nothing** — which is what the un-thresholded row says, and why that
row rather than the counts is the one to read.

⚠️ **The count moved once WHILE THIS SECTION WAS BEING WRITTEN, and that is the recursion rather
than a mistake:** the sweep reads the committed corpus, so a table describing the sweep changes what
the sweep finds. It was re-walked with the documentation staged, which is the only order that gives
a number describing the tree the reader will have. **An unstaged fix reads as no fix at all** — the
sweep reads what `git` holds, not the working tree, and that cost a confused minute during the
regression above.

**(f) Criterion 13 — the 2× wall-clock bound.** Best of three, both code versions over the **same**
corpus (this repository at the current head), each run's loaded module path printed and read before
its figure was believed:

| | Before (`5745d05`) | After | Ratio |
| --- | --- | --- | --- |
| tip scan, 45 entries | 1.95 s | 2.19 s | **1.12×** |
| published-range walk, 117 commits / 222 entries | 20.80 s | 20.62 s | **0.99×** |
| path scan over `src` and `tests` | 0.43 s | 0.42 s | **0.98×** |

⚠️ **Read the ratios, not the seconds**, for the reason recorded above this section. The tip scan is
the one that moved, and it is the expected direction: the marker's value fragment grew from a
substring to a URI, and four character classes replaced four one-character shorthands. 1.12× against
a bound of 2×.

### Recorded decision: the namespace value is the fixed value plus a declared tolerance list

**Three rounds each found a new dimension of looseness in ONE check and each closed that dimension
only:** the namespace anywhere in the text → anchored to attribute position; any URI *containing*
the base → anchored to the base at a URI boundary; **any scheme whatever** → this section. A URI's
`scheme` was transcribed from RFC 3986 §3.1, which admits every syntactically valid scheme, so
`<wrapper xmlns="ftp://…base…/1.7.2/">` beside four filled `<type>` elements named the format and
produced a P2. *Namespaces in XML* compares namespace names by **exact string match**, so that
document has declared a different namespace however similar its authority and path.

**That sequence is the signature of a rule built permissively and narrowed by findings**, and the
question this round had to answer was whether to close the third dimension or the construction. Two
answers were costed:

| | **(a)** constrain the scheme | **(b)** invert the construction |
| --- | --- | --- |
| source | replace `_URI_SCHEME`'s reader with a two-spelling alternation derived from the frozen value | the same alternation, emitted from a tolerance table carrying a reason per row |
| tests | 1 — the scheme sweep, both directions | +2 — the table is closed, reasoned and non-vacuous; the scheme binding strengthened |
| compiled result | **identical regex** | **identical regex** |
| what is left over | an alternation somebody wrote | a list a test holds closed |

⭐ **(a) AND (b) COMPILE TO THE SAME REGEX, and that is the honest core of the trade.** After (a)
there is no loose element left in the prefix either — every part is a fixed literal or an explicitly
optional one — so *"a fourth dimension can appear"* is a weaker argument here than it sounds, and it
is not why (b) was chosen.

**The real argument is that this module has already run the experiment, on a different constant.**
Five rounds repaired one Python shorthand at a time and what closed the set was
`_XML_SHORTHAND_LICENCE` — a row per pattern, a reason per row, walked off the module so the next
entry has to pass a rule rather than be noticed. **Same shape, already proven in this repository**,
rather than borrowed by analogy from the transcription audit. What (b) buys is **the artifact, not
the pattern**: a tolerance somebody has to justify in writing, held closed by a test that objects to
a blank reason and to a row that has stopped earning its place.

**The argument against it, recorded rather than skipped.** The table is itself new machinery, and
the diminishing-returns rule warns that machinery added in response to a finding is the next round's
surface. Its mitigations are deliberate: five rows of **plain data** feeding the **one compiled
pattern that already existed** — no second reader and no second pattern — and **(a) is a strict
simplification of (b)**, so if a later round finds against the table the candidate action is
deletion back to (a) rather than more hardening, and that retreat costs one commit. Writing that
down is what makes the choice reversible rather than merely defended.

**The ordering is load-bearing:** the value is *equality with the reassembled `#FIXED` value, **then**
these five declared relaxations* — not a pattern widened until the known spellings fit. Equality with
the whole fixed value would pin `1.7.2`; the version tail is the first relaxation, which is exactly
why equality alone is not what is written.

| position | fragment | why it is tolerated |
| --- | --- | --- |
| prefix | the fixed scheme, `:`, `//` | the `#FIXED` value's own spelling — the only one the specification's exact-match rule endorses, and bound to `FIXED_ATTRIBUTE_DEFAULTS`' first piece by test |
| prefix | the fixed scheme, `s`, `:`, `//` | the same authority over TLS — see the paragraph below |
| prefix | `//` | protocol-relative: a document may quote the namespace without committing to a transport |
| prefix | *(empty)* | the bare base, which an export or a quotation may write alone. Already load-bearing and already tested |
| tail | `/` | what opens the version segment, after which everything is free — **so a later schema revision still names the format** |

⚠️ **`https` is kept, and it is the weakest of the five reasons — flagged here and in the row itself
rather than buried.** Under exact-string comparison it is as different a namespace as `ftp` is, and
**it is the one row whose fragment is the fixed scheme plus a hand-written `"s"`**. It stays because
the marker identifies the format a document is **about** rather than the namespace a parser would
bind, and because the tolerance fails toward **reporting**, which is the direction this guard may
fail in. **Dropping it is one table row and one line of `_uris_that_are_the_namespace`**, and that is
recorded so the owner can take it later at that price.

**`_URI_SCHEME` was deleted rather than hardened.** It lost its only reader, and this module's own
rule — the one that removed `_XML_PROLOG` — is that machinery nobody reads is a candidate for
deletion. It is a plain string rather than a compiled pattern, so **no licence row moved**: 29
patterns walked off the module, 29 rows, confirmed by running the test rather than by reasoning.
`_GRAMPS_NAMESPACE_VALUE` went with it, for the same reason: `_marker_reading` builds the value it
used to hold.

#### Both directions, measured

Every figure below is from a **Windows 11 Pro 10.0.26100 development machine, CPython 3.12.13 via
`.venv\Scripts\python.exe`**, against the pre-change head **`84cb944`**.

**(a) What the tightening removes — the direction this change is for.** Every row is the reproduction
shape: a declaration on the weightless wrapper, beside four filled `<type>` elements, measured over
**both quotings and all three aliases** — 6 declarations per row, all six agreeing.

| Declared value | Before | After |
| --- | --- | --- |
| `ftp://…base…/1.7.1/` | 6 — **reported**, marker `True` | 2, below the threshold, marker `False` |
| `gopher://…`, `x-made-up://…`, `javascript://…` | 6 — **reported**, three times | 2, three times |
| the fixed scheme **UPPER-CASED** — the comparison is exact, and the gate is deliberately case-sensitive | 6 — **reported** | 2 |
| the fixed scheme with one letter **appended**, and the same letter **prepended** | 6 — **reported**, twice | 2, twice |

⚠️ **The appended-and-prepended pair is the important one**: it is the shape a word boundary got
wrong two rounds ago on a different constant, where a name that merely *begins* with a spelling was
read as it. Both are asserted rather than assumed.

⚠️ **Neither is spelled out here, and that is not squeamishness.** The first draft of this row wrote
the two schemes with their delimiter, and **the guard reported it as a P1 drive-letter path** — one
letter against a colon and two slashes is exactly that. The test composes each scheme WHOLE before
the delimiter is joined to it for the same reason, which is a comment the test file already carries
the hard way.

⚠️ **All seven still score 2, and that 2 is `#51`** — `_GRAMPS_NAMESPACE_WEIGHT`, charged for the base
appearing as a bare substring anywhere in the text. This round does not touch it. Against a threshold
of 4 all seven close.

**(b) The retained side — the control, and the half that breaks silently.**

⚠️ **This change TIGHTENS, so it can remove findings.** Both directions:

| Payload | Before | After |
| --- | --- | --- |
| the schema's own scheme, and the same over TLS | 6 — reported, 6 | **6, 6** |
| protocol-relative, the bare base, the bare base with a version | 6, 6, 6 | **6, 6, 6** |
| a genuine declaration + a researcher block, in all six forms | 8 — reported, six times | **8, six times** |
| prose mention · unrelated namespace · namespace inside another attribute's value · NBSP before `xmlns` · `<type-extra/>` × 4 | 2 · 0 · 2 · 2 · 2, none reported | unchanged |
| a URI merely CONTAINING the base, eight spellings | 2, none reported | unchanged |
| `<svg-chart …>` wrapping a name, a date of birth and a place | 6 — **reported** | 6 — **reported** |
| an ordinary drawing's labels, and notes inside one | 0, exempt | 0, exempt |
| a prefixed drawing's labels | 4 — reported | 4 — reported |
| the namespace fragment fixture, and a whole export | 4 and 8 | 4 and 8 |
| researcher and events blocks, unmarked / declared | 0 / 8 and 0 / 6 | unchanged |
| the **29 attested spellings** | identical | **identical** |
| the licence table: patterns walked off the module / rows | 29 / 29, non-vacuous | **29 / 29**, non-vacuous |
| container table and derivation script, `git diff --exit-code` against `84cb944` | — | **0** |

**(c) Each tolerance row removed in turn — what it is holding up, measured rather than argued.**
Seven spellings the gate is required to accept, and this is the table's non-vacuity:

| Row removed | Spellings that stop |
| --- | --- |
| the fixed scheme | 1 — the canonical spelling |
| the same over TLS | 1 |
| `//` | 1 |
| the empty prefix | **4** — the bare base and all three version spellings |
| **the tail** | **6** — every spelling carrying a version segment, of which **three are the version alone** |

⚠️ **The last row is the later-schema-revision property asserted rather than argued.**
`_GRAMPS_XML_NAMESPACE` is untouched and still stops short of the version segment; what changed is
that the tolerance is a declared row instead of an emergent property of the pattern, and
`test_every_namespace_tolerance_is_declared_with_a_reason_and_earns_its_row` fails if removing it
stops nothing.

**(d) B8's two rows, walked and not inferred from each other.**

| Row | Result |
| --- | --- |
| tip — `python -m gramps_live_api.core.pii_guard .` | 0 findings over 45 tracked entries, exit 0 |
| published range — `--range HEAD` | 0 findings over 124 commits, 230 entries scanned, exit 0 |
| `test_every_commit_this_repository_publishes_is_clean` and `test_this_repository_is_clean` | both **ran**, both passed, neither skipped |

⚠️ **`0 findings` is the claim; `124` and `230` are the timestamp on it.** Those counts grow with the
history — 117 → 124 commits and 222 → 230 entries — and the commit carrying this sentence adds
another, which is why this row is read for its verdict rather than its arithmetic.

**(e) ⚠️ The code's own constants, under every spelling the code treats as equivalent** — re-walked
with the CODE and the CORPUS chosen separately, because this round's new table and its reasons are
themselves new text in a tracked file, and **re-walked again with this documentation STAGED**: the
sweep reads what `git` holds, so an unstaged fix reads as no fix. Nineteen namespace spellings, the
same construction as before — six separator spellings crossed with four casings, deduplicated.

| What the sweep found | Before (`84cb944`) | After |
| --- | --- | --- |
| the namespace, in any of **19** spellings, in any tracked file | none | **none** |
| tracked files the gate reads as naming the format | none | **none** |
| filled vocabulary elements | two | **two** |
| attributed vocabulary elements | thirteen | **thirteen** |
| highest un-thresholded score of any tracked file | **0**, against a threshold of 4 | **0** |

⚠️ **Nothing moved, and that is worth stating rather than skipping.** The round before this one put
the namespace contiguously into a docstring and **only this sweep caught it** — no gate did, because
at 2 against a threshold of 4 it is not a finding. Every new docstring, comment, table row and
fixture in this round was written under that rule, and this table is what says the rule held. The
new prose deliberately writes `…base…` where the reproduction wants the value.

⚠️ **This round's own slip was caught by a GATE rather than by this sweep, which is the other half of
the same lesson.** Table (a) above first spelled the appended and prepended schemes out with their
delimiter, and the guard reported a **P1 drive-letter path** on the staged documentation — a
finding, not a headroom measurement, so it failed loudly and was fixed before the commit. The two
detectors catch different halves: the guard sees a spelling that IS a finding, and this sweep sees a
spelling that merely eats the margin.

**(f) Criterion 13 — the 2× wall-clock bound.** Best of three, both code versions over the **same**
corpus (this repository at the current head), each run's loaded module path printed and read before
its figure was believed — and the before-code was loaded from a detached worktree at `84cb944`, so
the two runs differ in code and in nothing else.

| | Before (`84cb944`) | After | Ratio |
| --- | --- | --- | --- |
| tip scan, 45 entries | 1.86 s | 1.87 s | **1.01×** |
| published-range walk, 124 commits / 230 entries | 26.00 s | 26.26 s | **1.01×** |
| path scan over `src` and `tests` | 2.42 s | 2.32 s | **0.96×** |

⚠️ **The tip figure does NOT move past last round's 1.12×.** An alternation of four literals costs no
more than the RFC character class it replaced, which is the expected direction and is now measured
rather than assumed. Re-walked in the same session against **`5745d05`** — the head *before* the
transcription audit, so the pair spans both rounds together — the tip scan is 1.92 s against 1.87 s,
**0.97×**. That is not a retraction of the 1.12×: **read the ratios, not the seconds**, and no two
pairs measured in different sessions are comparable with each other, which is exactly why the bound
is a ratio.

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
