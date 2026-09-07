⚠️ **Written before the project was renamed to `AgentDataEntry`.** Apart from this line the page is left as it was written; `README.md` records which names the rename changed and which it did not.
# Plan for #225: the hook test whose shell is supplied by whoever launched pytest

## Context

`tests/integration/test_pre_push_hook.py` drives the real `scripts/hooks/pre-push`
through a POSIX shell, and it picks that shell with `_sh()`:

```python
for candidate in ("sh", "bash"):
    found = shutil.which(candidate)
```

The answer is supplied by the launching environment, not by the test. Measured on the
owner's machine today, from PowerShell:

| probe | result |
| --- | --- |
| `Get-Command sh` | not found |
| `Get-Command bash` | the Subsystem launcher under the system directory, not a Git shell |
| `git --exec-path` | `.../Programs/Git/mingw64/libexec/git-core` |

So the file under test is executed by a different operating system, with a different
filesystem and a different PATH, whenever pytest is launched from a shell where `sh`
does not resolve. This is the shape the project has recorded before: a check whose
definition comes from where it runs is not a check on what it names. The standing
remedy is to freeze the definition rather than resolve it at run time, and this
repository already contains that remedy, written for this exact hazard, in
`tests/fixtures/shell.py`.

## What breaks, on the current head

Input: `pytest tests/integration/test_pre_push_hook.py -k MISSING` launched from
PowerShell in the project checkout.

Output, run today at `0265394`:

```
E       AssertionError: an unrunnable gate must not be treated as a pass
E       assert 0 != 0
E        +  where 0 = CompletedProcess(args=['<the Subsystem launcher>', ...
```

The same file with Git for Windows' `usr/bin` prepended to PATH: `13 passed, 1 skipped`.
One variable moved, the shell, and nothing else.

## One correction to the framing, because it changes what the plan must prove

The issue's later comments say the passing case tests nothing and that the red is the
run doing its job. Measured, the direction is the other way for this specific test: under
WSL the hook finds WSL's own `python3`, the guard genuinely runs (its output says
`1 commit, 1 entries scanned`), the clean push is correctly allowed, and the test goes
**red** on correct hook behaviour. That is a false red, which is what the issue body
originally said.

There is a real "measures less than it claims" defect here, and it is a different one.
Measured inside Git for Windows' `sh` on this box:

```
command -v python3  ->  <the user profile>/AppData/Local/Microsoft/WindowsApps/python3
python -c ''        ->  "Python was not found; run without arguments to install
                         from the Microsoft Store", non-zero
```

The ambient interpreters on this machine are the Microsoft Store shim, which the hook
correctly rejects. **So on the green run, the shadow directory is not load-bearing: the
test would be green with an empty shadow directory.** The green proves the hook refuses
when no interpreter works; it does not prove the test built that condition. That residual
survives any fix that only pins the shell, and closing it is half of this plan.

Both readings lead to the same fix, so nothing below turns on the disagreement.

## The property, in one sentence

**When no candidate interpreter can execute, the pre-push hook refuses the push and says
in words that this is not a finding.**

A test of that property must **control** three things it currently inherits:

1. the shell binary that executes the hook,
2. that the shell resolves the PATH the test constructed, rather than one of its own,
3. that the interpreter candidates the hook will try are the failing ones the test planted.

Today all three are inherited. (2) is what WSL breaks. (3) is what the Store shim masks.

## The change

### 1. The shell stops being ambient: reuse `tests/fixtures/shell.py`

`posix_shell()` already derives the shell from `git --exec-path` on Windows, never from
PATH, and probes the candidate before returning it. Its docstring names the WSL launcher
as the thing it exists to refuse. It has exactly one consumer today,
`tests/fixtures/pushes.py:207`.

Extend it with a flavour, defaulted so the existing consumer is untouched:

- `posix_shell()` keeps returning **bash**, which is what `pushes.py` needs: it runs
  GitHub Actions `run:` bodies, and `ci.yml` uses `set -euo pipefail`, which is not a
  `/bin/sh` guarantee.
- `posix_shell(flavour="sh")` returns **sh**: the `usr/bin` then the `bin` shell under the Git distribution root on Windows (both verified present on this box),
  `shutil.which("sh")` on other platforms.

The hook test must take the `sh` flavour, not bash. Git runs hooks through `sh`, the hook
declares `#!/bin/sh`, and on Linux `sh` is dash. Silently upgrading the hook's shell to
bash on CI would retire the portability coverage that
`test_the_committed_hook_has_no_CARRIAGE_RETURNS` exists to protect.

On a non-Windows platform the PATH lookup stays, and this is deliberate: there, PATH
cannot hand back a shell from another operating system, so the failure this issue is
about is not reachable. Say so in the docstring rather than leaving it to be re-derived.

Then delete `_sh()` from `tests/integration/test_pre_push_hook.py` and have `_push()`
call the fixture. That is the only call site.

### 2. The probe gets stronger, and it probes the actual hazard

`posix_shell()` currently probes `command -v git`. WSL passes that probe when Git is
installed inside WSL. Replace it with a probe of the property the caller depends on:

- write a marker executable into a temporary directory,
- run the candidate with that directory **prepended to PATH** exactly as the test does,
- require `command -v <marker>` to answer with a path inside that directory.

WSL fails this: interop appends the translated Windows PATH **after** the Linux PATH, which
is precisely why WSL's own `python3` won over the planted stubs. Apply the probe to both
flavours; it is the same hazard for `pushes.py`.

### 3. When no suitable shell exists

Recommendation: **skip on Windows, raise everywhere else.**

- On Windows a POSIX shell is a component of Git for Windows. A machine without one
  cannot run this hook at all, which is the reason `_sh()`'s original skip message gave,
  and it is still correct.
- On Linux, `bash`/`sh` missing means a broken container, and a silent skip there is
  issue #31 again. The suite must fail closed.

The skip reason names every path tried, and CI already runs `pytest -rs`, so a skip that
started firing would be visible by name. `posix_shell()` keeps raising; the hook module
converts that `RuntimeError` into `pytest.skip` only when `os.name == "nt"`.

⛔ Under no branch does WSL become the fallback. `the Subsystem launcher` is not
under the Git root, so it is unreachable by construction rather than by exclusion list.

### 4. The suite proves its own setup, in two layers

**Layer 1, a precondition inside the hook's own shell.** In `_push()`, on the
`interpreter is None` branch where the shadow is built, run one probe through the same
shell, the same `env`, and the same `cwd` the hook is about to get, and require that:

- `command -v python3` and `command -v python` both answer with a path inside the shadow
  directory, and
- each of those exits non-zero when run with `-c ''`.

If not, fail with the phrasing this file already uses three times: *"the fixture did not
build the case"*. Placing it in `_push()` rather than in one test covers both
`interpreter=None` callers, which is deliberate:
`test_a_DELETION_is_allowed_even_with_no_interpreter` asserts an exit of 0 and the absence
of a message, and a working interpreter satisfies it just as well as a shadowed one, so it
is vacuous without this check too.

Layer 1 is the layer that fires on every machine. It is what would have reported the WSL
run as a broken fixture rather than as a broken hook.

**Layer 2, a negative control.** One test that builds the same repository and the same
environment **without** the shadow directory, and asserts the push is allowed. That shows
the shadow is what causes the refusal.

⚠️ Measured: this control cannot run on the owner's Windows box, because the ambient
`python` and `python3` there are the Store shim and the push is refused with or without
the shadow. So it probes first, through the same shell, whether any candidate the hook
would try can execute, and **skips with that as the stated reason** when none can. On CI,
where `actions/setup-python` puts a real interpreter on PATH, it runs and it bites. Record
in the test's docstring that this control is CI-carried, so nobody later reads its local
skip as coverage.

### 5. Blast radius, measured rather than assumed

- `_sh()`: one call site, `_push()` at line 170. `_push()` is called by **11 of the 14
  tests** in the file. Two of them pass `interpreter=None`.
- `posix_shell()`: one call site, `tests/fixtures/pushes.py:207`, reached from
  `tests/integration/test_pushed_range.py`. Unchanged by the default flavour.
- Repository-wide, `shutil.which` for a shell appears in exactly these two files.

Files to change: `tests/fixtures/shell.py`, `tests/integration/test_pre_push_hook.py`.
No source file changes, and no change to `scripts/hooks/pre-push`.

### 6. What CI actually runs, and what it does not change

`.github/workflows/ci.yml` is the only workflow, and all three jobs are `ubuntu-latest`.
There is no Windows leg. On Linux `sh` resolves to a same-OS shell, the shadow applies, and
the hook finds nothing runnable, so **CI has always exercised the real assertion**, and this
defect has always been developer-machine-only.

Two consequences for the fix:

- The fix cannot be validated by CI. The meaningful verification is a run from PowerShell
  on the owner's box, red before and green after, plus a Git Bash run that stays green.
- The fix must not rest on CI staying Linux. Adding a Windows leg later would otherwise
  reintroduce the WSL fallback silently. Pinning the shell removes that possibility rather
  than deferring it.

## The hazard this plan is judged on, stated plainly

**Would following this plan let the test pass on a machine where the hook is broken?**

Pinning the shell alone would: on this box the test is green whether or not the shadow
does anything, because ambient `python` is the Store shim. Layer 1 is what closes it, and
it is the reason the plan is not just "call `posix_shell()`". If layer 1 is dropped during
the build, the residual is back and the change is cosmetic.

Two residuals that remain after the whole plan, accepted and recorded:

- The negative control (layer 2) does not run on the owner's machine. Layer 1 does, and it
  is the stronger of the two, but a Windows-only reader sees one control, not two.
- The test still covers only "no candidate can execute". A hook that found an interpreter
  which then misbehaved in some other way is not in this property and is not tested here.

## Acceptance criteria, mechanically checkable

1. `grep -n "shutil.which" tests/integration/test_pre_push_hook.py` returns nothing, and
   `_sh` no longer exists in that file.
2. `tests/fixtures/shell.py` exposes the flavour argument; calling it with no argument
   returns the same bash path it returns today, and
   `pytest tests/integration/test_pushed_range.py` is green and unchanged in outcome.
3. A test asserts that on Windows the resolved shell path is under
   `Path(git --exec-path).parents[2]`, so `the Subsystem launcher` cannot be
   returned.
4. From PowerShell, with no `sh` on PATH:
   `pytest tests/integration/test_pre_push_hook.py -rs -q` reports **14 passed or
   13 passed, 1 skipped**, with the only skip being the existing Windows mode-bit skip
   plus, if it fires, the layer-2 control naming its reason. No failures.
5. From Git Bash: the same file, same outcome.
6. Layer 1 exists in `_push()` and its failure message contains
   `the fixture did not build the case`.
7. Mutation control, run once by the build and reported, not committed: force the Windows
   candidate list to `[the Subsystem launcher]` and the file must fail with the
   shell probe's message, not with `assert 0 != 0`. Restore in a `finally`.
8. Mutation control, run once and reported, not committed: delete the shadow stub creation
   and confirm layer 1 fails the two `interpreter=None` tests by name on the owner's box.
9. Gates green from the conductor's own shell: `ruff check .`, `ruff format --check .`,
   `mypy src/gramps_live_api`, and the full `pytest -rs`.
10. `git status` shows only the two intended files.

## Out of scope

- `scripts/hooks/pre-push`. Both shells agree about the hook given the same interpreter
  situation; the defect is in the harness. No hook edit belongs in this change.
- Making the test pass under WSL, or accommodating WSL in any way.
- Adding a Windows CI leg.
- A repository-wide ratchet forbidding PATH shell lookups in tests (see question 5).
- Retitling or closing #225. That is issue hygiene and belongs to the conductor.

## Questions left to the build, numbered

1. **Flavour API shape.** A `flavour="bash" | "sh"` argument on `posix_shell()`
   (`lru_cache` keys on it), or a separate `hook_shell()`. Recommendation: the argument,
   defaulted to bash so `pushes.py` is untouched. Disputes welcome if the cache or the
   typing gets ugly.
2. **Probe scope.** Apply the PATH-prepend probe to both flavours, or only to `sh`?
   Recommendation: both, it is the same hazard, and `pushes.py` inherits the same WSL
   risk. If the probe measurably slows the suite, say so with the number.
3. **Skip or raise on a missing shell.** Recommendation as written: skip on Windows, raise
   elsewhere. The owner may prefer raise everywhere; if so, the raise message must still
   name every path tried.
4. **Layer 1's failure mode.** Fail the test, or skip it? Recommendation: fail. A fixture
   that cannot build its case is a defect in the fixture, and this file's existing
   `the fixture did not build the case` assertions all fail rather than skip.
5. **Repository-wide ratchet.** A hygiene test asserting no module under `tests/` resolves
   a shell by name from PATH. Recommendation: only if it is a short assertion in the
   existing `test_repository_hygiene.py`; otherwise file it and do not build it here.

Presented for approval. Nothing was written or modified in the repository; `git status`
was clean before and after, and the only commands run were reads, probes, and two pytest
runs.
