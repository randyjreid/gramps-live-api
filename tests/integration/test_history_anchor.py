"""The anchored history walk, against the plan's six acceptance criteria.

⛔ **Every test here is about the same question: may the prefix be skipped?**
A wrongly skipped commit reads exactly like a scanned one, so each shape that
could produce a wrong *yes* gets its own case rather than being covered by a
neighbour.

The criteria are `docs/plans/57-anchored-history-walk.plan.md`. Each test names
the one it discharges.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from gramps_live_api.core import history_anchor, pii_guard
from tests.fixtures.repositories import commit_all, git, init_repository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A repository with three commits, so a prefix exists to skip."""
    root = init_repository(tmp_path / "repo")
    (root / "one.md").write_text("# One\n", encoding="utf-8")
    commit_all(root, "one")
    (root / "two.md").write_text("# Two\n", encoding="utf-8")
    commit_all(root, "two")
    (root / "three.md").write_text("# Three\n", encoding="utf-8")
    commit_all(root, "three")
    return root


def _anchor_at(root: Path, revision: str, *, digest: str | None = None) -> str:
    """Record an anchor at ``revision``, under the rules in force unless told otherwise."""
    commit = git(root, "rev-parse", revision)
    history_anchor.write_anchor(
        root,
        history_anchor.Anchor(
            commit=commit,
            digest=history_anchor.rules_digest(root) if digest is None else digest,
        ),
    )
    return commit


# ---------------------------------------------------------------------------
# Criterion 1 -- an anchor that is not an ANCESTOR of HEAD forces a full walk.
# One test per shape, because each is a different way of producing a wrong yes.
# ---------------------------------------------------------------------------


def test_an_anchor_that_is_an_ancestor_is_used(repository: Path) -> None:
    """The affirmative case, so the refusals below are not vacuous.

    ⚠️ Without this, every criterion 1 test would pass against a build that
    never used an anchor at all.
    """
    first = _anchor_at(repository, "HEAD~2")

    plan = history_anchor.plan_scan(repository)

    assert plan.anchor == first, plan
    assert plan.revision_range == f"{first}..{plan.head}"
    assert not plan.is_full


def test_no_anchor_file_walks_fully(repository: Path) -> None:
    plan = history_anchor.plan_scan(repository)

    assert plan.is_full, plan
    assert plan.revision_range == plan.head


def test_an_empty_anchor_file_walks_fully(repository: Path) -> None:
    history_anchor.anchor_path(repository).write_text("", encoding="utf-8")

    assert history_anchor.plan_scan(repository).is_full


def test_a_hand_edited_anchor_file_walks_fully(repository: Path) -> None:
    history_anchor.anchor_path(repository).write_text("not json at all", encoding="utf-8")

    assert history_anchor.plan_scan(repository).is_full


def test_an_anchor_file_of_the_wrong_shape_walks_fully(repository: Path) -> None:
    """JSON that parses and says nothing usable is not an anchor."""
    history_anchor.anchor_path(repository).write_text(
        json.dumps({"commit": 17, "digest": None}), encoding="utf-8"
    )

    assert history_anchor.plan_scan(repository).is_full


def test_a_sha_from_a_different_repository_walks_fully(repository: Path, tmp_path: Path) -> None:
    """⛔ It does not resolve here, and it must not be treated as a near miss."""
    stranger = init_repository(tmp_path / "stranger")
    (stranger / "elsewhere.md").write_text("# Elsewhere\n", encoding="utf-8")
    foreign = commit_all(stranger, "elsewhere")

    history_anchor.write_anchor(
        repository,
        history_anchor.Anchor(commit=foreign, digest=history_anchor.rules_digest(repository)),
    )

    assert history_anchor.plan_scan(repository).is_full


def test_an_anchor_that_resolves_but_is_not_reachable_walks_fully(repository: Path) -> None:
    """⭐ The criterion's whole point: ANCESTRY, not resolvability.

    ⛔ After a rebase or a force-push the old commit usually **remains in the
    object database**, so ``git rev-parse --verify`` still answers -- it
    verifies only that the name identifies an object. An anchor that resolves
    but is not reachable from ``HEAD`` would certify a prefix that is not in
    this history at all.

    ⚠️ The abandoned commit is proved to still resolve *inside this test*, so
    the case cannot quietly degrade into the missing-object one above and keep
    passing for the wrong reason.
    """
    git(repository, "checkout", "--quiet", "-b", "sidetrack", "HEAD~1")
    (repository / "side.md").write_text("# Side\n", encoding="utf-8")
    abandoned = commit_all(repository, "a commit on a branch that gets left behind")
    git(repository, "checkout", "--quiet", "main")

    history_anchor.write_anchor(
        repository,
        history_anchor.Anchor(commit=abandoned, digest=history_anchor.rules_digest(repository)),
    )

    assert git(repository, "rev-parse", "--verify", f"{abandoned}^{{commit}}") == abandoned, (
        "the abandoned commit must still resolve, or this test is exercising "
        "the missing-object case instead of the unreachable one"
    )
    assert history_anchor.plan_scan(repository).is_full


# ---------------------------------------------------------------------------
# Criterion 2 -- an anchor recorded under different rules forces a full walk.
# ---------------------------------------------------------------------------


def test_an_anchor_recorded_under_different_rules_walks_fully(repository: Path) -> None:
    """⛔ Criterion 1's twin, and the one the issue was missing.

    An anchor certifies *these commits under these rules*. Rules that have
    changed since have never been applied to the prefix, so the prefix is not
    proved under them.
    """
    _anchor_at(repository, "HEAD~2", digest="a digest from some earlier set of rules")

    plan = history_anchor.plan_scan(repository)

    assert plan.is_full, plan
    assert "rules changed" in plan.reason, plan.reason


def test_a_changed_denylist_changes_the_digest(repository: Path) -> None:
    """The deny-list changes what counts as a finding, so it is in the digest.

    ⚠️ **Absent and empty must not collide.** ``sha256(b"")`` is a real,
    guessable digest, so a marker is used for absence rather than a hash of
    nothing.
    """
    absent = history_anchor.rules_digest(repository)

    denylist = repository / pii_guard.DENYLIST_FILENAME
    denylist.write_text("", encoding="utf-8")
    empty = history_anchor.rules_digest(repository)

    denylist.write_text("# a comment only\n", encoding="utf-8")
    populated = history_anchor.rules_digest(repository)

    assert absent != empty, "an absent deny-list and an empty one are different rule sets"
    assert empty != populated
    assert absent != populated


def test_a_replacement_ref_added_after_the_anchor_walks_fully(repository: Path) -> None:
    """⛔ Git REPLACEMENT REFS change what history IS, without moving anything.

    ⚠️ Git applies ``refs/replace/*`` while traversing, so adding, changing
    or removing one can change an old commit's effective tree -- while HEAD, the
    stored anchor and the rules digest all stay exactly as they were. A prefix
    proved clean would then certify content those commits no longer hold,
    ``anchor..HEAD`` would never look at it, and the tip scan cannot recover it
    either, because that content was deleted before the tip.

    ⭐ **A BLOB is replaced here, deliberately.** Replacing a COMMIT also
    breaks reachability, so the ancestry check catches that shape on its own and
    a test using it would pass without ever reaching this one. A blob
    replacement leaves the graph untouched and changes only what a tree holds --
    which is exactly the case nothing else covers.
    """
    _anchor_at(repository, "HEAD~2")
    assert not history_anchor.plan_scan(repository).is_full, "the anchor must be usable first"

    victim = git(repository, "rev-parse", "HEAD:one.md")
    stand_in = git(repository, "rev-parse", "HEAD:two.md")
    git(repository, "replace", "--force", victim, stand_in)

    plan = history_anchor.plan_scan(repository)

    assert plan.is_full, plan
    assert "replacement refs" in plan.reason, plan.reason
    assert is_ancestor_still_true(repository, plan), (
        "ancestry must still hold, or this test is exercising criterion 1 instead"
    )


def is_ancestor_still_true(root: Path, plan: history_anchor.Plan) -> bool:
    """⚠️ Proves the refusal above came from the replacement, not from ancestry."""
    stored = history_anchor.read_anchor(root)
    assert stored is not None
    return history_anchor.is_ancestor(root, stored.commit, plan.head)


def test_an_advancing_run_records_the_replacement_state(repository: Path) -> None:
    """⛔ Recorded on the way out, or the next run compares against nothing."""
    victim = git(repository, "rev-parse", "HEAD:one.md")
    stand_in = git(repository, "rev-parse", "HEAD:two.md")
    git(repository, "replace", "--force", victim, stand_in)

    plan = history_anchor.plan_scan(repository)
    assert history_anchor.advance(repository, plan, clean=True)

    written = history_anchor.read_anchor(repository)
    assert written is not None
    assert written.replaces == history_anchor.replacement_state(repository) != ""

    git(repository, "replace", "--delete", victim)
    assert history_anchor.plan_scan(repository).is_full, (
        "REMOVING a replacement ref must invalidate the anchor too, not only adding one"
    )


# ---------------------------------------------------------------------------
# Issue #204 -- a stale .pyc must not let the digest describe rules that never
# ran. Reproduced across PROCESSES, because an already-imported module cannot
# show the effect in this one.
# ---------------------------------------------------------------------------

_VICTIM_OLD = "\n".join(
    [
        "RULE = 'AAA'",
        "def verdict():",
        "    return 'old'",
        "",
    ]
)
# ⚠️ Same byte length, so CPython's (mtime, size) check cannot tell them apart.
_VICTIM_NEW = _VICTIM_OLD.replace("'AAA'", "'BBB'").replace("'old'", "'new'")

_PROBE = "\n".join(
    [
        "import hashlib, importlib, json, pathlib, sys",
        "sys.path.insert(0, sys.argv[1])",
        "sys.path.insert(0, sys.argv[2])",
        "from gramps_live_api.core import history_anchor",
        "import victim",
        "source = pathlib.Path(sys.argv[1], 'victim.py').read_bytes()",
        "print(json.dumps({",
        "    'ran': victim.verdict(),",
        "    'code': history_anchor._loaded_code_digest(victim),",
        "    'file': hashlib.sha256(source).hexdigest(),",
        "}))",
        "",
    ]
)


def _run_probe(home: Path, probe: Path, source_root: Path) -> dict[str, str]:
    finished = subprocess.run(
        [sys.executable, str(probe), str(home), str(source_root)],
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(json.loads(finished.stdout.strip()))


def test_a_stale_pyc_cannot_make_the_digest_describe_rules_that_never_ran(
    tmp_path: Path,
) -> None:
    """⭐ Issue #204, reproduced exactly and then refused.

    ⛔ **The defect.** CPython invalidates its bytecode cache on the source's
    ``(mtime, size)``. A same-length edit inside one integer second leaves the
    existing ``.pyc`` acceptable, so the OLD bytecode executes while the NEW
    source sits on disk. Any hash of that file then names rules that never ran,
    and an anchor stamped with it licenses skipping a prefix nobody checked
    under them.

    ⭐ **The fix.** The digest is taken from the loaded code objects, so it moves
    when the RUNNING code moves and not when the file does. Both halves are
    measured here in one test: the file hash changes across the stale import and
    the code digest does not, which is the whole difference.

    ⚠️ **This test holds one half only.** It proves the HELPER follows the
    running bytecode; that ``rules_digest`` actually *uses* the helper is held by
    ``test_the_digest_is_the_three_inputs_and_nothing_else``. Reverting the
    digest to a file read leaves this test passing and fails that one, which is
    how the pair was checked.
    """
    home = tmp_path / "home"
    home.mkdir()
    victim = home / "victim.py"
    # ⚠️ BYTES on both sides. ``write_text`` translates newlines on Windows and
    # ``write_bytes`` does not, so mixing them made the "same length" edit three
    # bytes shorter -- which the size assertion below caught, as it should.
    victim.write_bytes(_VICTIM_OLD.encode("utf-8"))
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE, encoding="utf-8")
    source_root = REPOSITORY_ROOT / "src"

    before = _run_probe(home, probe, source_root)
    assert before["ran"] == "old"
    stat_before = victim.stat()

    victim.write_bytes(_VICTIM_NEW.encode("utf-8"))
    os.utime(victim, (stat_before.st_atime, stat_before.st_mtime))
    stat_after = victim.stat()

    # ⛔ The mutation is proved to have landed, and to be invisible to the cache
    # check, BEFORE any verdict is read. A control that quietly failed to apply
    # would otherwise read as proof.
    assert victim.read_bytes() == _VICTIM_NEW.encode("utf-8"), "the edit did not reach the file"
    assert stat_after.st_size == stat_before.st_size, "the edit changed the size"
    assert int(stat_after.st_mtime) == int(stat_before.st_mtime), "the edit moved the mtime second"

    during = _run_probe(home, probe, source_root)

    if during["ran"] == "new":
        pytest.skip(
            "this platform recompiled despite an unchanged (mtime, size), so the "
            "stale-bytecode window #204 describes does not exist here"
        )

    assert during["file"] != before["file"], (
        "the file hash must move -- otherwise this test proves nothing about a "
        "digest that reads the file"
    )
    assert during["code"] == before["code"], (
        "THE FIX: the digest follows the bytecode that ran, and the old bytecode "
        "ran, so the digest must not have moved with the file"
    )

    # And once the cache genuinely turns over, the new code DOES move it.
    victim.write_bytes(_VICTIM_NEW.encode("utf-8"))
    os.utime(victim, (stat_before.st_atime, stat_before.st_mtime + 10))
    after = _run_probe(home, probe, source_root)

    assert after["ran"] == "new", "the cache did not turn over, so this half proves nothing"
    assert after["code"] != before["code"], (
        "when the running code finally changes, the digest must change with it"
    )


def test_the_digest_is_the_same_whether_the_code_was_compiled_or_cached(tmp_path: Path) -> None:
    """⭐ **Load-bearing for the feature, not tidiness.**

    ⛔ ``marshal``'s default version encodes the object GRAPH, sharing
    references to interned strings, so the same function hashes differently when
    freshly compiled than when unmarshalled from a ``.pyc`` -- with identical
    ``co_code`` and ``co_consts``.

    ⚠️ **That would have been a correctness-shaped bug wearing a performance
    mask.** Every run that recompiled would disagree with every run that did not,
    so the anchor would be invalidated on alternate runs: the optimisation
    quietly halved, and nothing failing to say so. ``MARSHAL_VERSION`` is pinned
    below the reference-sharing versions for exactly this reason, and this is the
    test that holds the pin.
    """
    home = tmp_path / "home"
    home.mkdir()
    victim = home / "victim.py"
    victim.write_bytes(_VICTIM_OLD.encode("utf-8"))
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE, encoding="utf-8")
    source_root = REPOSITORY_ROOT / "src"
    cache = home / "__pycache__"

    shutil.rmtree(cache, ignore_errors=True)
    compiled = _run_probe(home, probe, source_root)
    assert cache.exists(), "no bytecode cache was written, so both runs compiled"

    cached = _run_probe(home, probe, source_root)

    assert compiled["code"] == cached["code"], (
        "the digest moved between a compiled import and a cached one, so it "
        "encodes how the code ARRIVED rather than what it says -- the anchor "
        "would be invalidated on alternate runs"
    )


def test_a_module_level_constant_alone_moves_the_digest(tmp_path: Path) -> None:
    """⛔ The gap an earlier draft of this fix had, pinned so it cannot return.

    ⚠️ That draft walked the module namespace for FUNCTIONS and hashed their
    code objects. Module-level data is not a function: the guard's patterns,
    tables and severities are built by the module body, so a changed constant
    could alter a verdict while every function's bytecode stayed identical --
    and the digest would not have moved.

    ⭐ Hashing the module's TOP-LEVEL code object covers both, because the
    body that builds those constants is itself bytecode. Here only the constant
    changes; the function is left alone.
    """
    home = tmp_path / "home"
    home.mkdir()
    victim = home / "victim.py"
    victim.write_bytes(_VICTIM_OLD.encode("utf-8"))
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE, encoding="utf-8")
    source_root = REPOSITORY_ROOT / "src"

    before = _run_probe(home, probe, source_root)

    only_the_constant = _VICTIM_OLD.replace("'AAA'", "'CCC'")
    assert "return 'old'" in only_the_constant, "the function body must be untouched"
    victim.write_bytes(only_the_constant.encode("utf-8"))
    moved = victim.stat().st_mtime + 30
    os.utime(victim, (moved, moved))

    after = _run_probe(home, probe, source_root)

    assert after["ran"] == "old", "the function was changed too, so this proves nothing"
    assert after["code"] != before["code"], (
        "a module-level constant changed a verdict input and the digest did not "
        "move -- function bytecode alone is not enough"
    )


def test_an_anchor_is_never_stamped_with_rules_that_did_not_run(tmp_path: Path) -> None:
    """⛔ The leak itself, stated as the property rather than the mechanism.

    ⚠️ **The old failure was not in which range run two walked** -- it was in
    what run two WROTE. Under a file-read digest, a stale-bytecode run scanned
    with the old rules and then stamped the anchor with the new ones, and the
    next process trusted that stamp and skipped a prefix those rules had never
    seen.

    The digest now equals the code that ran, so the stamp can only ever name the
    rules that did the scanning.
    """
    root = init_repository(tmp_path / "repo")
    (root / "one.md").write_text("# One\n", encoding="utf-8")
    commit_all(root, "one")

    plan = history_anchor.plan_scan(root)
    assert history_anchor.advance(root, plan, clean=True)

    written = history_anchor.read_anchor(root)
    assert written is not None
    assert written.digest == history_anchor.rules_digest(root)
    assert written.digest != history_anchor.UNDETERMINED


# ---------------------------------------------------------------------------
# Criterion 2 -- every doubt state falls to the SAME default: the full walk.
# ---------------------------------------------------------------------------


def test_an_undeterminable_digest_forces_a_full_walk(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ Not a best-effort anchor. The one default is the whole history."""
    _anchor_at(repository, "HEAD~2")
    assert not history_anchor.plan_scan(repository).is_full, "the anchor must be usable first"

    monkeypatch.setattr(history_anchor, "rules_digest", lambda _root: history_anchor.UNDETERMINED)

    plan = history_anchor.plan_scan(repository)

    assert plan.is_full, plan
    assert "could not be determined" in plan.reason, plan.reason


def test_an_undeterminable_digest_is_never_written_as_an_anchor(repository: Path) -> None:
    """⛔ An anchor is a claim that a prefix was proved under NAMED rules.

    If the rules cannot be named there is no claim to record, so the sentinel
    must be unstorable as well as unmatchable.
    """
    first = _anchor_at(repository, "HEAD~2")
    plan = history_anchor.plan_scan(repository)
    undeterminable = history_anchor.Plan(
        head=plan.head,
        revision_range=plan.head,
        anchor=None,
        digest=history_anchor.UNDETERMINED,
        reason="",
    )

    assert not history_anchor.advance(repository, undeterminable, clean=True)

    kept = history_anchor.read_anchor(repository)
    assert kept is not None and kept.digest != history_anchor.UNDETERMINED
    assert kept.commit == first


def test_a_stored_sentinel_never_matches_a_real_run(repository: Path) -> None:
    """⚠️ ``advance`` cannot write it, but a hand-edited anchor file can."""
    _anchor_at(repository, "HEAD~2", digest=history_anchor.UNDETERMINED)

    plan = history_anchor.plan_scan(repository)

    assert plan.is_full, plan
    assert "no determinable rules" in plan.reason, plan.reason


def test_every_doubt_state_lands_on_the_full_walk(repository: Path, tmp_path: Path) -> None:
    """⭐ The enumeration, asserted together rather than one test at a time.

    Each of these is covered on its own above; what this adds is that they share
    ONE outcome, so a future branch that returns something else stands out.
    """
    anchor_file = history_anchor.anchor_path(repository)
    stranger = init_repository(tmp_path / "stranger")
    (stranger / "x.md").write_text("# X\n", encoding="utf-8")
    foreign = commit_all(stranger, "x")

    def unreadable() -> None:
        anchor_file.write_text("not json", encoding="utf-8")

    def wrong_shape() -> None:
        anchor_file.write_text(json.dumps({"commit": 1, "digest": None}), encoding="utf-8")

    def stale_rules() -> None:
        _anchor_at(repository, "HEAD~2", digest="some earlier set of rules")

    def undeterminable_rules() -> None:
        _anchor_at(repository, "HEAD~2", digest=history_anchor.UNDETERMINED)

    def not_an_ancestor() -> None:
        history_anchor.write_anchor(
            repository,
            history_anchor.Anchor(
                commit=foreign,
                digest=history_anchor.rules_digest(repository),
                replaces=history_anchor.replacement_state(repository),
            ),
        )

    for name, arrange in (
        ("no anchor at all", lambda: anchor_file.unlink(missing_ok=True)),
        ("unreadable", unreadable),
        ("wrong shape", wrong_shape),
        ("rules that are not the rules now", stale_rules),
        ("rules that cannot be named", undeterminable_rules),
        ("an anchor outside this history", not_an_ancestor),
    ):
        anchor_file.unlink(missing_ok=True)
        arrange()
        assert history_anchor.plan_scan(repository).is_full, f"{name} did not force a full walk"


# ---------------------------------------------------------------------------
# Criterion 3 -- the digest covers everything that can change a verdict.
# ---------------------------------------------------------------------------


def test_the_digest_covers_every_first_party_input_to_a_verdict() -> None:
    """⛔ An enumeration that nothing checks is how this fails quietly.

    The digest hashes **one** first-party file, the guard module, on the
    strength of a claim: nothing else in this project feeds a verdict.
    ``_specified_containers`` is not imported at runtime by design and
    ``_unrenderable`` is not referenced by the guard at all.

    ⚠️ **That claim is checked here rather than trusted.** The guard's own
    imports are read from its source, and any first-party module among them
    would be a verdict input the digest does not cover.
    """
    source = Path(pii_guard.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    first_party = {name for name in imported if name.split(".")[0] == "gramps_live_api"}

    assert first_party == set(), (
        "the guard imports first-party modules that the rules digest does not "
        f"hash, so a change to one would not invalidate an anchor: {sorted(first_party)}"
    )


def _digest_inputs(root: Path) -> dict[str, str]:
    """The three inputs, spelled out the way ``rules_digest`` combines them.

    ⚠️ The guard's half is the hash of its LOADED CODE OBJECTS, not of its file.
    """
    denylist = root / pii_guard.DENYLIST_FILENAME
    return {
        "guard": history_anchor._loaded_code_digest(pii_guard),
        "denylist": (
            hashlib.sha256(denylist.read_bytes()).hexdigest()
            if denylist.is_file()
            else history_anchor.DENYLIST_ABSENT
        ),
        "unidata": unicodedata.unidata_version,
    }


def test_the_digest_describes_the_guard_that_is_running_not_the_file_on_disk(
    tmp_path: Path,
) -> None:
    """⛔ The digest must NOT move when the file moves, and that is the point.

    ⚠️ **An earlier version of this test asserted the opposite, and what it
    asserted was a fail-open.** If the digest is a fresh read of the file, an
    edit landing after the guard was imported gets recorded as the rules in
    force -- while the scan runs the functions already compiled into memory. The
    old code reports clean, the anchor is stamped with the NEW rules, and the
    next process skips commits nobody ever checked under them.

    ⭐ Rehashing at the end of the run cannot catch it: the file is stable at
    both reads and both read the wrong thing. So the digest takes the hash the
    guard recorded of itself during the import that compiled it.
    """
    root = init_repository(tmp_path / "repo")
    before = history_anchor.rules_digest(root)

    guard = Path(pii_guard.__file__)
    original = guard.read_bytes()
    try:
        guard.write_bytes(original + b"# a change that could alter a verdict")
        assert guard.read_bytes() != original, "the mutation never reached the file"
        during = history_anchor.rules_digest(root)
    finally:
        guard.write_bytes(original)

    assert guard.read_bytes() == original, "the guard module was not restored"
    assert during == before, (
        "the digest followed the file rather than the loaded module -- that is "
        "the fail-open, because the running code is still the old one"
    )


def test_the_digest_is_the_three_inputs_and_nothing_else(tmp_path: Path) -> None:
    """⭐ The combination is pinned, so the inputs cannot drift from the docstring."""
    root = init_repository(tmp_path / "repo")

    expected = hashlib.sha256(
        json.dumps(_digest_inputs(root), sort_keys=True).encode("utf-8")
    ).hexdigest()

    assert history_anchor.rules_digest(root) == expected


def test_the_digest_carries_no_denylist_content(repository: Path) -> None:
    """⛔ The digest is written to a file and printed. It may never carry a surname.

    Each input is reduced to its own hash before anything is combined, so a
    literal from the deny-list cannot appear in the result.
    """
    literal = "Quintablewick"
    (repository / pii_guard.DENYLIST_FILENAME).write_text(f"{literal}\n", encoding="utf-8")

    digest = history_anchor.rules_digest(repository)

    assert literal.lower() not in digest.lower()
    assert set(digest) <= set("0123456789abcdef"), "a digest is hex and nothing else"


# ---------------------------------------------------------------------------
# Criterion 4 -- coverage is asserted, not assumed.
# ---------------------------------------------------------------------------


def test_coverage_holds_for_an_accepted_anchor(repository: Path) -> None:
    """The commits scanned plus the commits certified equal the commits behind HEAD."""
    _anchor_at(repository, "HEAD~2")
    plan = history_anchor.plan_scan(repository)

    scanned = pii_guard.count_range_commits(repository, plan.revision_range)
    certified = pii_guard.count_range_commits(repository, plan.anchor or "")
    total = pii_guard.count_range_commits(repository, plan.head)

    assert history_anchor.covers(repository, plan)
    assert scanned + certified == total
    assert scanned == 2 and certified == 1, (scanned, certified)


def test_coverage_holds_for_a_full_walk(repository: Path) -> None:
    plan = history_anchor.plan_scan(repository)

    assert plan.is_full
    assert history_anchor.covers(repository, plan)


def test_coverage_fails_when_the_anchor_certifies_a_prefix_that_is_not_behind_head(
    repository: Path, tmp_path: Path
) -> None:
    """⛔ The control for the assertion itself.

    ``covers`` must be able to say **no**, or asserting it proves nothing. A
    plan is constructed by hand with an anchor that is not an ancestor -- the
    state ``plan_scan`` refuses to produce -- so the arithmetic is exercised
    where it should fail.
    """
    git(repository, "checkout", "--quiet", "-b", "sidetrack", "HEAD~1")
    (repository / "side.md").write_text("# Side\n", encoding="utf-8")
    unreachable = commit_all(repository, "unreachable from main")
    git(repository, "checkout", "--quiet", "main")
    head = git(repository, "rev-parse", "HEAD")

    dishonest = history_anchor.Plan(
        head=head,
        revision_range=f"{unreachable}..{head}",
        anchor=unreachable,
        digest=history_anchor.rules_digest(repository),
        reason="",
    )

    assert not history_anchor.covers(repository, dishonest)


# ---------------------------------------------------------------------------
# The anchor advances, and only when it has earned it.
# ---------------------------------------------------------------------------


def test_a_clean_covering_run_advances_the_anchor(repository: Path) -> None:
    """⭐ It advances, or the saving is temporary and the cost climbs back."""
    _anchor_at(repository, "HEAD~2")
    plan = history_anchor.plan_scan(repository)

    assert history_anchor.advance(repository, plan, clean=True)

    moved = history_anchor.read_anchor(repository)
    assert moved is not None and moved.commit == plan.head


def test_a_full_walk_can_write_the_first_anchor(repository: Path) -> None:
    """⛔ Requiring a digest match here would break the mechanism at both ends.

    On a fresh checkout there is no stored digest to match, so nothing could
    ever write the first anchor; and after a rules change the recovering full
    walk could not write one either. The optimisation would never start and
    could never recover.
    """
    plan = history_anchor.plan_scan(repository)
    assert plan.is_full

    assert history_anchor.advance(repository, plan, clean=True)
    written = history_anchor.read_anchor(repository)
    assert written is not None and written.commit == plan.head


def test_a_run_that_found_something_does_not_advance_the_anchor(repository: Path) -> None:
    first = _anchor_at(repository, "HEAD~2")
    plan = history_anchor.plan_scan(repository)

    assert not history_anchor.advance(repository, plan, clean=False)

    kept = history_anchor.read_anchor(repository)
    assert kept is not None and kept.commit == first, "a dirty run must preserve the anchor"


def test_a_head_that_moved_during_the_run_does_not_advance_the_anchor(repository: Path) -> None:
    """⚠️ The walk takes about 82 seconds -- ample for a checkout to switch branches.

    ⛔ Everything the anchor certifies must be about **one immutable snapshot**,
    so a head that moved under the scan forfeits the advance.
    """
    first = _anchor_at(repository, "HEAD~2")
    plan = history_anchor.plan_scan(repository)

    (repository / "four.md").write_text("# Four\n", encoding="utf-8")
    commit_all(repository, "a commit that lands while the scan is running")

    assert not history_anchor.advance(repository, plan, clean=True)
    kept = history_anchor.read_anchor(repository)
    assert kept is not None and kept.commit == first


def test_rules_that_changed_under_the_run_do_not_advance_the_anchor(repository: Path) -> None:
    """⚠️ Hashing only at the start certifies whatever the rules said then.

    A deny-list rewritten mid-walk would otherwise be recorded as the rules that
    proved the prefix, having never been applied to a single commit.
    """
    first = _anchor_at(repository, "HEAD~2")
    plan = history_anchor.plan_scan(repository)

    (repository / pii_guard.DENYLIST_FILENAME).write_text("Quintablewick\n", encoding="utf-8")

    assert not history_anchor.advance(repository, plan, clean=True)
    kept = history_anchor.read_anchor(repository)
    assert kept is not None and kept.commit == first


# ---------------------------------------------------------------------------
# Criterion 5 -- identity. Cheap, and it does not bind the risk.
# ---------------------------------------------------------------------------


def test_findings_over_a_fixed_range_are_unchanged_by_the_anchor(repository: Path) -> None:
    """The anchor selects a range; it may not change what a range reports."""
    head = git(repository, "rev-parse", "HEAD")
    start = git(repository, "rev-parse", "HEAD~2")

    direct = pii_guard.scan_repository(repository, revision_range=f"{start}..{head}")

    _anchor_at(repository, "HEAD~2")
    plan = history_anchor.plan_scan(repository)
    anchored = pii_guard.scan_repository(repository, revision_range=plan.revision_range)

    assert plan.revision_range == f"{start}..{head}"
    assert direct == anchored


# ---------------------------------------------------------------------------
# Criterion 6 -- the full walk stays reachable and stays run.
# ---------------------------------------------------------------------------


def test_the_full_walk_can_be_demanded_over_a_usable_anchor(repository: Path) -> None:
    """⛔ Not a backstop -- see the constant's own docstring. It keeps the path exercised."""
    _anchor_at(repository, "HEAD~2")

    assert not history_anchor.plan_scan(repository).is_full, "the anchor must be usable here"
    assert history_anchor.plan_scan(repository, full=True).is_full


def test_ci_runs_the_full_walk() -> None:
    """⭐ The criterion is that the complete path keeps running somewhere.

    ⚠️ Asserted against the workflow file, because a criterion that says "CI
    does this" and is checked by nobody is a criterion that stops being true the
    first time someone edits the workflow.
    """
    workflows = sorted((REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows, "no workflow files found"

    text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)

    assert history_anchor.FULL_SCAN_ENVIRONMENT_VARIABLE in text, (
        "CI must demand the full history walk: it pays about ten seconds for the "
        "whole suite, and the complete path has to keep running somewhere or the "
        "anchor mechanism rots unnoticed"
    )
