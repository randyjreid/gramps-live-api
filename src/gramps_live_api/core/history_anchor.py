"""Which commits still need scanning, given what has already been proved clean.

``test_every_commit_this_repository_publishes_is_clean`` walks the whole history
on every run, and the walk grows with the repository -- 12 s at 36 commits,
34.6 s at 74, 71.8 s at 193, measured. **A commit that was clean once stays
clean, because history is immutable**, so the walk was re-proving a settled fact
about 190-odd commits in order to check three new ones.

This module records how far a clean scan got, and answers one question on the
next run: *may the prefix be skipped?* ⛔ **Every branch of that answer that is
not provably safe returns the whole history.** A wrongly skipped commit reads as
scanned, and nothing downstream can tell the difference -- which is why the
conservative direction is taken at every single step here rather than argued
about at each one.

⚠️ **This module cannot change a VERDICT, only a RANGE.** Nothing in it feeds
the scanner's rules; a bug here is a coverage bug, and coverage is what
``covers`` asserts positively rather than assumes.

Where the anchor lives, and why it is not where the plan recommended
--------------------------------------------------------------------

The approved plan requires the anchor to be **per-checkout and never committed**,
and recommended "an ignored file under the existing state directory".
⛔ **``host.paths.state_directory`` does not satisfy that requirement**: it is a
**per-user** directory under ``APPDATA``, shared by every checkout and every
worktree on the machine. This repository routinely has several worktrees open at
different heads, and one anchor shared between them would be an anchor recorded
against a history the next reader is not on.

⭐ **The git directory satisfies the requirement the recommendation stated.**
``git rev-parse --absolute-git-dir`` is **per-worktree** -- it answers
``.git/worktrees/<name>`` inside a linked worktree -- it is never committed
because it is not in the work tree at all, and it therefore needs no
``.gitignore`` rule, so ``test_no_path_is_both_untracked_and_unignored`` and the
ordering constraint on that file's last block are both untouched.

⚠️ **A shared anchor would have failed safe rather than open** -- the ancestry
check would reject it -- but it would have failed *constantly*, each worktree
invalidating the others, and an optimisation that never fires is one somebody
deletes.
"""

from __future__ import annotations

import hashlib
import json
import marshal
import subprocess
import types
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from gramps_live_api.core import pii_guard

ANCHOR_FILENAME = "pii-guard-anchor.json"

MARSHAL_VERSION = 2
"""⛔ **Pinned, and the pin is load-bearing in BOTH directions. Measured.**

``marshal.dumps`` defaults to version 4, which uses ``FLAG_REF`` -- it encodes
the object GRAPH, sharing references to interned strings. ⚠️ **That makes the
bytes depend on how the code object arrived**, not only on what it says: the
same function hashed **differently when freshly compiled than when unmarshalled
from a ``.pyc``**, with identical ``co_code``, ``co_consts``, ``co_filename``
and ``co_firstlineno``.

Measured over three runs, one function, nothing edited between them:

    compiled from source   v2=91301609944f  v3=caabe13603ba  v4=bc460a773719
    loaded from a .pyc     v2=91301609944f  v3=d7c48f5067aa  v4=b35160c64b75

⛔ **Version 4 would have been a correctness-shaped bug wearing a performance
mask.** Every run that recompiled would disagree with every run that did not, so
the anchor would be invalidated on alternate runs -- the optimisation quietly
halved, and nothing failing to say so.

⭐ **Version 2 predates ``FLAG_REF``**, so it encodes the code's CONTENT. It is
also sensitive enough: measured distinct fingerprints for a nested function's
constant, a nested function's name, an added ``try``/``except``, a changed string
constant and an added docstring -- no collisions among them.
"""

UNDETERMINED = "undetermined"
"""⛔ The digest could not be computed, so no anchor may be trusted.

⚠️ **This is a value, not an exception, because it has to be COMPARED.** A
digest that cannot be computed must not merely fail loudly -- it must be
unequal to every anchor ever written, and it must be unwritable itself. Both
are checked, because a sentinel that could be stored would certify a prefix
under rules nobody could name.
"""

DENYLIST_ABSENT = "absent"
"""⛔ A marker, never a hash of nothing.

An absent deny-list and an empty one are different rule sets to a reader and
must not collide in the digest. ``sha256(b"")`` is a real, guessable digest, so
an empty file and a missing file would otherwise agree.
"""

FULL_SCAN_ENVIRONMENT_VARIABLE = "GRAMPS_LIVE_API_FULL_HISTORY_SCAN"
"""Set to ``1`` to ignore any anchor and walk the whole history.

⛔ **This is not a backstop.** CI sets it because CI pays about ten seconds for
the entire suite and has no reason to use the anchor at all -- and because the
complete path must keep running somewhere, so the anchor mechanism cannot rot
unnoticed. It is NOT a safety net for a wrongly skipped local scan: the workflow
triggers ``on: push``, so GitHub has already stored the objects before a runner
starts, and on a public repository that is publication. **The gate that prevents
publication is the local one.**
"""


@dataclass(frozen=True)
class Anchor:
    """A commit proved clean, together with the rules that proved it."""

    commit: str
    digest: str
    replaces: str = ""
    """The state of ``refs/replace/*`` when this anchor was written.

    ⛔ Git applies replacement objects while traversing history, so adding,
    changing or removing one can change an old commit's effective tree --
    **without moving HEAD, without moving the anchor, and without changing the
    rules digest.** A prefix proved clean would then certify content those
    commits no longer hold, ``anchor..HEAD`` would never look at it, and the tip
    scan cannot recover it either, because it was deleted before the tip.
    """


@dataclass(frozen=True)
class Plan:
    """The range this run will scan, and what it is entitled to skip.

    ``anchor`` is the commit whose ancestry this run does NOT rescan. It is
    ``None`` for a full walk, and ``reason`` then says why -- carried so the run
    can print it, because a skipped optimisation that says nothing is
    indistinguishable from one that is broken.
    """

    head: str
    revision_range: str
    anchor: str | None
    digest: str
    reason: str

    @property
    def is_full(self) -> bool:
        return self.anchor is None


def _git(root: Path, *arguments: str) -> str:
    """Run git anchored on ``root``, in the guard's own anchored environment.

    ⚠️ The environment matters here for the same reason it matters in the walk
    test: git honours ``GIT_DIR`` and ``GIT_WORK_TREE`` ahead of the working
    directory, so an unanchored probe answers about whatever those name -- and
    it answers **successfully**. The probe and the scan it guards must not be
    able to disagree about which repository they mean.
    """
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        env=pii_guard._git_environment_anchored_on_the_target(),
    )
    return completed.stdout.strip()


def _loaded_code_digest(module: types.ModuleType) -> str:
    """A hash of the BYTECODE THIS PROCESS EXECUTED, not of any file.

    ⛔ **This is the whole of #204's fix, and the reason it closes.** Every
    earlier attempt hashed a PROXY for the running code -- the source file, then
    the source file read a little earlier -- and a proxy can disagree with what
    runs. CPython invalidates its bytecode cache on the source's ``(mtime,
    size)``, so a same-length edit inside one integer second leaves a stale
    ``.pyc`` acceptable: the old bytecode executes while the new source sits on
    disk, and any hash of that file names rules that never ran.

    ⭐ **``loader.get_code`` takes the same decision the import system took** --
    accept the cached bytecode or recompile -- so under a stale ``.pyc`` it
    returns the STALE code, which is exactly the code that ran. Measured: with
    the source edited to ``BBB`` and the cache still accepted, it answered the
    ``AAA`` build, unchanged.

    ⭐ **The module's TOP-LEVEL code object, which is why nothing is
    enumerated.** It carries the module body -- the bytecode that builds every
    pattern, table and severity -- and every function and class rides inside its
    ``co_consts``. An earlier draft walked the namespace for functions instead
    and **missed module-level data entirely**: a changed constant altered a
    verdict and moved no function's bytecode. Measured on the top-level object, a
    constant changing alone does move it.

    ⚠️ **The encoding is pinned to ``MARSHAL_VERSION``**; see its docstring for
    why the default would have halved the optimisation.

    ⚠️ **What this still cannot see, stated rather than left to be found.**
    ``get_code`` consults the cache again rather than returning an object kept
    from import, so a ``.pyc`` REPLACED between the import and this call would be
    read here and not there. That window is far narrower than the file read it
    replaces, and it fails in the safe direction -- a disagreement is a digest
    mismatch, which is a full walk. Beyond it: anything that changes a verdict
    without changing this module's bytecode -- a different ``re``
    implementation, a patched standard library, an interpreter giving the same
    bytecode different semantics. The UCD case is covered separately by
    ``unidata_version``; the rest are outside the module and are this design's
    named residual.
    """
    loader = getattr(module, "__loader__", None)
    get_code = getattr(loader, "get_code", None)
    if get_code is None:
        # ⛔ A loader that cannot hand back its code -- frozen, extension, or
        # something exotic -- is a state this cannot resolve, and every such
        # state takes the same exit.
        return UNDETERMINED

    try:
        code = get_code(module.__name__)
    except Exception:  # noqa: BLE001 - any failure means "cannot say", which is the full walk
        return UNDETERMINED

    if not isinstance(code, types.CodeType):
        return UNDETERMINED

    return hashlib.sha256(marshal.dumps(code, MARSHAL_VERSION)).hexdigest()


def anchor_path(root: Path) -> Path:
    """Where this checkout's anchor lives. Per-worktree, and outside the work tree."""
    return Path(_git(root, "rev-parse", "--absolute-git-dir")) / ANCHOR_FILENAME


def rules_digest(root: Path) -> str:
    """A digest of everything that can change a verdict.

    Three inputs, and the plan's falsifier was tested against each before this
    was approved:

    - **the guard module's LOADED BYTECODE**, which carries every pattern, table
      and severity -- see ``_loaded_code_digest`` for why it is the code objects
      and not the file.
      Nothing else under ``core/`` feeds a verdict -- ``_specified_containers``
      is not imported at runtime by design and ``_unrenderable`` is not
      referenced by the guard at all. ``test_the_digest_covers_every_input_to_a
      _verdict`` fails if that stops being true.
    - **the local deny-list**, or a marker for its absence. It is never
      committed and is per-developer, but it lives at a known path and it
      changes what counts as a finding.
    - **``unicodedata.unidata_version``**. The interpreter's UCD reaches a
      verdict through ``normalize("NFC", ...).casefold()``, and that string
      differs across exactly the interpreters this project supports: measured
      3.10 -> 13.0.0, 3.11 -> 14.0.0, 3.12 -> 15.0.0.

    ⚠️ **The digest is weaker than it looks, in two named ways.**
    ``unidata_version`` pins the *release*, not the fold behaviour -- a proxy,
    though a conservative one. And the UCD reaches a verdict through
    ``_comparable`` only, which the deny-list scan alone calls, so on a machine
    with no deny-list it contributes nothing.

    ⛔ **No deny-list content leaves this function.** Each input is reduced to
    its own hash before anything is combined, so the digest -- which is written
    to a file and printed in explanations -- can never carry a surname.
    """
    guard = _loaded_code_digest(pii_guard)
    if guard == UNDETERMINED:
        return UNDETERMINED

    denylist = root / pii_guard.DENYLIST_FILENAME
    parts = {
        # ⛔ **The hash the guard took of ITSELF, during the import that
        # compiled it** -- not a fresh read of the file. Reading the file here
        # certifies whatever it says now, while the scan runs the functions
        # already in memory: an edit landing between that import and this call
        # would be recorded as the rules in force while the OLD code scanned,
        # and the anchor would license skipping commits nobody checked under
        # the new rule. ⚠️ The end-of-run rehash cannot catch it -- the file is
        # stable at both reads, and both read the wrong thing.
        "guard": guard,
        "denylist": (
            hashlib.sha256(denylist.read_bytes()).hexdigest()
            if denylist.is_file()
            else DENYLIST_ABSENT
        ),
        "unidata": unicodedata.unidata_version,
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()


def read_anchor(root: Path) -> Anchor | None:
    """The recorded anchor, or ``None`` if there is not a usable one.

    ⛔ **Every failure to read returns ``None``**, which forces a full walk. A
    truncated file, a hand-edited one, one holding JSON of the wrong shape, one
    written by a future version -- none of them may produce a skip, and none of
    them is worth distinguishing here, because the answer is the same.
    """
    location = anchor_path(root)
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    commit = raw.get("commit")
    digest = raw.get("digest")
    replaces = raw.get("replaces")
    if not isinstance(commit, str) or not isinstance(digest, str):
        return None
    if not isinstance(replaces, str):
        # ⛔ Absent is not "there were no replacement refs". An anchor written
        # before this field existed says nothing about them, and defaulting to
        # the empty string would read as a positive claim that there were none.
        return None
    if not commit or not digest:
        return None
    return Anchor(commit=commit, digest=digest, replaces=replaces)


def write_anchor(root: Path, anchor: Anchor) -> None:
    """Record ``anchor``, replacing whatever was there."""
    anchor_path(root).write_text(
        json.dumps(
            {"commit": anchor.commit, "digest": anchor.digest, "replaces": anchor.replaces},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def replacement_state(root: Path) -> str:
    """A fingerprint of every ``refs/replace/*`` ref, or the empty string for none.

    ⚠️ Recorded rather than refused outright: a checkout that uses replacement
    refs and does not change them is no less trustworthy than one with none.
    What must not happen is the set changing under a recorded anchor.
    """
    listing = _git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/replace")
    if not listing:
        return ""
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def is_ancestor(root: Path, commit: str, head: str) -> bool:
    """Whether ``commit`` is reachable from ``head``.

    ⛔ **Ancestry, not resolvability, and the difference is the whole point.**
    After a rebase or a force-push the old commit usually **remains in the
    object database**, so ``git rev-parse --verify`` still resolves it -- that
    verifies only that the name identifies an object. An anchor that resolves
    but is not reachable from ``HEAD`` would certify a prefix that is not in
    this history at all, and ``anchor..HEAD`` would then quietly scan the wrong
    set.
    """
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head],
        cwd=root,
        capture_output=True,
        text=True,
        env=pii_guard._git_environment_anchored_on_the_target(),
    )
    return completed.returncode == 0


def plan_scan(root: Path, *, full: bool = False) -> Plan:
    """Decide what to scan, resolving ``HEAD`` exactly once.

    ⛔ **``HEAD`` is resolved to a SHA here and used everywhere after.** The walk
    takes about 82 seconds, which is ample for a checkout to switch branches. A
    run that scanned ``anchor..old_head`` and then checked its coverage against
    ``HEAD`` as a *name* could pass against a different head that happened to
    have the same number of commits -- **a count is not an identity**, and two
    siblings of one anchor can share one.
    """
    head = _git(root, "rev-parse", "HEAD")
    digest = rules_digest(root)

    # ⛔ **Every branch below returns a FULL WALK. There is exactly one way out
    # of this function with an anchor, and it is the last line.** The states
    # that fall here, each named rather than left implicit:
    #
    #   - a full walk was asked for
    #   - the digest could not be computed at all
    #   - no anchor is recorded
    #   - the anchor is unreadable, truncated, hand-edited or of the wrong shape
    #     (``read_anchor`` answers None for all of them)
    #   - the rules that proved the prefix are not the rules running now
    #   - the anchor is not an ancestor of this HEAD
    #   - the replacement refs have moved under it
    #
    # ⭐ The full walk is always correct, so erring toward it is free
    # correctness; erring toward the anchor is the leak. The default is the
    # slow answer, and the fast one is reached only by surviving every check.
    if full:
        return Plan(head, head, None, digest, "a full walk was requested")

    if digest == UNDETERMINED:
        return Plan(head, head, None, digest, "the rules in force could not be determined")

    stored = read_anchor(root)
    if stored is None:
        return Plan(head, head, None, digest, "no usable anchor is recorded")
    if stored.digest == UNDETERMINED:
        # ⛔ Unreachable through ``advance``, which refuses to write it. Checked
        # anyway: a hand-written anchor file is one of the shapes criterion 1
        # exists for, and this sentinel must never compare equal to a real run.
        return Plan(head, head, None, digest, "the recorded anchor names no determinable rules")
    if stored.digest != digest:
        return Plan(
            head, head, None, digest, "the guard's rules changed since the anchor was recorded"
        )
    if not is_ancestor(root, stored.commit, head):
        return Plan(head, head, None, digest, "the recorded anchor is not an ancestor of HEAD")
    if stored.replaces != replacement_state(root):
        return Plan(
            head, head, None, digest, "git replacement refs changed since the anchor was recorded"
        )

    return Plan(head, f"{stored.commit}..{head}", stored.commit, digest, "")


def covers(root: Path, plan: Plan) -> bool:
    """Whether this run plus the anchor account for every commit behind ``HEAD``.

    ⛔ **Asserted, not assumed.** The commits scanned this run **plus** the
    commits the anchor certifies must equal the commits reachable from the one
    resolved head. With ancestry established, ``count(A..B) + count(A)`` is
    exactly ``count(B)`` -- which is why criterion 1's ancestry check is what
    makes this arithmetic true rather than merely plausible.
    """
    scanned = pii_guard.count_range_commits(root, plan.revision_range)
    certified = pii_guard.count_range_commits(root, plan.anchor) if plan.anchor is not None else 0
    return scanned + certified == pii_guard.count_range_commits(root, plan.head)


def advance(root: Path, plan: Plan, *, clean: bool) -> bool:
    """Move the anchor to the scanned head, if this run is entitled to.

    ⭐ **The anchor advances, and that is decided rather than implied.** An
    anchor frozen at one commit means every later run rescans a growing tail, so
    the saving is temporary and the cost climbs back toward a whole-history
    walk -- the optimisation would quietly stop optimising.

    Four conditions, and all of them are about **one immutable snapshot**:

    - the scan was **clean**;
    - it **covered** everything it needed to;
    - ``HEAD`` has not moved since it was resolved;
    - the **rules have not changed** under the running scan.

    ⛔ **A full walk always qualifies, and requiring a digest match would have
    broken the mechanism at both ends.** On a fresh checkout there is no stored
    digest to match, so nothing could ever write the first anchor; and after a
    rules change the recovering full walk could not write one either. The
    optimisation would never start and could never recover.

    ⚠️ **The rules are re-hashed here, at the end.** Hashing them only at the
    start certifies whatever they said at that moment, and a walk takes about 82
    seconds -- ample for an editor to save or another process to rewrite the
    deny-list. The anchor would then record rules that were never applied to a
    single commit.
    """
    if not clean:
        return False
    if plan.digest == UNDETERMINED:
        # ⛔ An anchor is a claim that a prefix was proved under NAMED rules. If
        # the rules cannot be named, there is no claim to record.
        return False
    if not covers(root, plan):
        return False
    if _git(root, "rev-parse", "HEAD") != plan.head:
        return False
    ending = rules_digest(root)
    if ending == UNDETERMINED or ending != plan.digest:
        return False

    write_anchor(
        root, Anchor(commit=plan.head, digest=plan.digest, replaces=replacement_state(root))
    )
    return True
