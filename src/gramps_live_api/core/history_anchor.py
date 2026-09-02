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
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from gramps_live_api.core import pii_guard

ANCHOR_FILENAME = "pii-guard-anchor.json"

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


def anchor_path(root: Path) -> Path:
    """Where this checkout's anchor lives. Per-worktree, and outside the work tree."""
    return Path(_git(root, "rev-parse", "--absolute-git-dir")) / ANCHOR_FILENAME


def rules_digest(root: Path) -> str:
    """A digest of everything that can change a verdict.

    Three inputs, and the plan's falsifier was tested against each before this
    was approved:

    - **the guard module**, which carries every pattern, table and severity.
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
        "guard": pii_guard.SOURCE_SHA256_AT_IMPORT,
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

    if full:
        return Plan(head, head, None, digest, "a full walk was requested")

    stored = read_anchor(root)
    if stored is None:
        return Plan(head, head, None, digest, "no usable anchor is recorded")
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
    if not covers(root, plan):
        return False
    if _git(root, "rev-parse", "HEAD") != plan.head:
        return False
    if rules_digest(root) != plan.digest:
        return False

    write_anchor(
        root, Anchor(commit=plan.head, digest=plan.digest, replaces=replacement_state(root))
    )
    return True
