"""B7's thin spot: the step that decides what the guard is pointed at.

``docs/pii-guard-acceptance.md`` B7 claims every event that publishes content is
scanned over the range that event publishes, and then states -- rather than
citing a test -- that **no test drives the shell step computing that range.**
Everything asserted elsewhere is either structural (``test_repository_hygiene``
reads ``ci.yml`` and checks shapes) or guard-side (B6: an empty range and an
unresolvable range are refused).

Neither catches the dangerous case: **a range that is merely too narrow.** It
satisfies every structural assertion and every guard-side refusal, because the
guard resolves it and scans exactly what it was handed. Issue #18.

**The step is driven, not transcribed.** Its ``run:`` body, its ``env:`` block
and its ``if:`` condition are read out of ``ci.yml`` and executed, so a second
copy of the arithmetic cannot drift from the first. Each case is a real push
into a scratch remote outside the project tree, and the range the step computes
is compared against an oracle -- the commits the remote actually gained --
computed without reading anything the step reads.

**The relation asserted is coverage, not equality:** every commit the push
publishes is inside the range. Two arms widen deliberately (a first push of the
default branch scans everything reachable; a tag scans HEAD), and wider is
correct. Narrower is the defect.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gramps_live_api.core.pii_guard import main
from tests.fixtures.pushes import (
    ZERO_SHA,
    Push,
    StepResult,
    bare_remote,
    checkout,
    holds_commit,
    is_ancestor,
    publish,
    rev_list,
    run_step,
    working_clone,
)
from tests.fixtures.repositories import commit_all, git
from tests.fixtures.synthetic import gedcom_document
from tests.fixtures.workflow import (
    UnreadableCondition,
    named_step,
    runs_for,
    scan_steps,
    step_blocks,
    step_condition,
    step_environment,
    step_name,
    step_shell_body,
    workflow_text,
)

PUSHED_RANGE_STEP = "Determine the pushed range"
PULL_REQUEST_RANGE_STEP = "Determine the pull request range"
DEFAULT_BRANCH = "main"

MAIN = f"refs/heads/{DEFAULT_BRANCH}"
FEATURE = "refs/heads/feature"


# ---------------------------------------------------------------------------
# Events. One dictionary per event, mapping whole context references to values,
# and it answers BOTH questions asked of an event: which steps run for it
# (``runs_for``) and what its steps' env: blocks resolve to (``run_step``).
#
# The routing table below defines only the two references the conditions read.
# That is deliberate rather than partial: resolve_environment RAISES on a
# reference an event does not define, so a routing event can never be used to
# compute a range by accident.
# ---------------------------------------------------------------------------

EVENTS = {
    "a branch push": {"github.event_name": "push", "github.ref_type": "branch"},
    "a tag push": {"github.event_name": "push", "github.ref_type": "tag"},
    "a pull request": {"github.event_name": "pull_request", "github.ref_type": "branch"},
    "a scheduled run": {"github.event_name": "schedule", "github.ref_type": "branch"},
}


def push_event(push: Push) -> dict[str, str]:
    return {
        "github.event_name": "push",
        "github.ref_type": push.ref_type,
        "github.ref_name": push.ref_name,
        "github.sha": push.after,
        "github.event.before": push.before,
        "github.event.repository.default_branch": DEFAULT_BRANCH,
    }


def pull_request_event(base_sha: str, head_sha: str) -> dict[str, str]:
    return {
        "github.event_name": "pull_request",
        "github.ref_type": "branch",
        "github.ref_name": "1/merge",
        "github.sha": head_sha,
        "github.event.pull_request.base.sha": base_sha,
        "github.event.repository.default_branch": DEFAULT_BRANCH,
    }


# ---------------------------------------------------------------------------
# Fixtures and history builders. Everything under tmp_path, which is outside
# the project working tree.
# ---------------------------------------------------------------------------


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    return bare_remote(tmp_path / "remote.git")


@pytest.fixture
def work(tmp_path: Path) -> Path:
    return working_clone(tmp_path / "work")


def committing(work: Path, name: str, text: str, message: str) -> str:
    (work / name).write_text(text, encoding="utf-8")
    return commit_all(work, message)


def a_push_that_hides_a_tree(work: Path, remote: Path) -> Push:
    """The round-1 case, and the reason range scanning exists at all.

    Three commits: a baseline that is already on the remote, one that adds a
    family tree, and one that removes it again while adding something harmless.
    The tip is clean and the tree is still publicly reachable, so only a range
    covering the MIDDLE commit finds it.

    The harmless file in the last commit is load-bearing for the negative
    control below: a range narrowed to that commit alone must have something to
    scan, or it would be refused for covering nothing and the control would
    prove the wrong thing.
    """
    committing(work, "README.md", "# Title\n", "docs: readme")
    publish(work, remote, MAIN)

    committing(work, "family.ged", gedcom_document(), "add a tree")
    (work / "family.ged").unlink()
    committing(work, "NOTES.md", "# Notes\n", "remove the tree and add a note")
    return publish(work, remote, MAIN)


def pushed_range(push: Push, at: Path, scratch: Path, body: str | None = None) -> StepResult:
    return run_step(
        named_step(PUSHED_RANGE_STEP),
        push_event(push),
        checkout_dir=at,
        scratch=scratch,
        body=body,
    )


def assert_covers(result: StepResult, published: frozenset[str], at: Path) -> frozenset[str]:
    """Every commit the event publishes is inside the range the step computed."""
    assert result.exit_code == 0, f"the step refused to compute a range: {result.output!r}"
    assert result.range, f"the step exited cleanly and wrote no range: {result.output!r}"
    assert published, (
        "this event published nothing, so the coverage assertion below would hold "
        "vacuously and the case would prove nothing"
    )

    scanned = rev_list(at, result.range)
    assert scanned, "the range covers no commits, so the whole push goes unscanned"

    missing = published - scanned
    assert not missing, (
        f"{len(missing)} of the {len(published)} commit(s) this event publishes are "
        "outside the range the workflow computed, so nothing ever scans them -- a "
        "range that is merely too narrow, which every structural assertion and every "
        "guard-side refusal passes"
    )
    return scanned


# ---------------------------------------------------------------------------
# The six cases.
# ---------------------------------------------------------------------------


def test_a_first_push_of_the_default_branch_scans_everything_it_publishes(
    tmp_path: Path, remote: Path, work: Path
) -> None:
    """Case 1: a zero before-SHA must fail closed, not scan nothing.

    The default branch itself is new, so everything reachable is new. Falling
    back to ``origin/<default>..HEAD`` here is what once produced an EMPTY range
    and a clean report over nothing.
    """
    committing(work, "README.md", "# Title\n", "docs: readme")
    committing(work, "NOTES.md", "# Notes\n", "docs: notes")
    push = publish(work, remote, MAIN)

    assert push.before == ZERO_SHA, "this case is about a push with no before-SHA"

    at = checkout(remote, push.ref, tmp_path / "checkout")
    assert_covers(pushed_range(push, at, tmp_path / "scratch"), push.published, at)


def test_a_first_push_of_a_new_branch_covers_every_commit_it_publishes(
    tmp_path: Path, remote: Path, work: Path
) -> None:
    """The other zero before-SHA: a branch that is new while the remote is not."""
    committing(work, "README.md", "# Title\n", "docs: readme")
    publish(work, remote, MAIN)

    git(work, "checkout", "--quiet", "-b", "feature")
    committing(work, "one.md", "# One\n", "first")
    committing(work, "two.md", "# Two\n", "second")
    push = publish(work, remote, FEATURE)

    assert push.before == ZERO_SHA, "this case is about a push with no before-SHA"

    at = checkout(remote, push.ref, tmp_path / "checkout")
    assert_covers(pushed_range(push, at, tmp_path / "scratch"), push.published, at)


def test_a_push_with_no_resolvable_baseline_refuses_rather_than_scanning_nothing(
    tmp_path: Path, remote: Path, work: Path
) -> None:
    """A gate that cannot determine its scope must not report clean.

    A new branch, a zero before-SHA, and no default branch on the remote to fall
    back to: there is no baseline anywhere. The step has to fail the job rather
    than emit a range, because every value it could emit here is a guess.
    """
    git(work, "checkout", "--quiet", "-b", "feature")
    committing(work, "README.md", "# Title\n", "docs: readme")
    push = publish(work, remote, FEATURE)

    at = checkout(remote, push.ref, tmp_path / "checkout")
    result = pushed_range(push, at, tmp_path / "scratch")

    assert result.exit_code != 0, (
        f"the step resolved a baseline that does not exist: {result.range!r}"
    )
    assert result.range == "", "a step that fails must not also publish a range to scan"
    assert "::error::" in result.output, (
        f"the refusal has to reach the job's log as an error; got {result.output!r}"
    )


@pytest.mark.parametrize(
    "branch",
    [DEFAULT_BRANCH, "feature"],
    ids=["default-branch", "feature-branch"],
)
def test_a_force_push_covers_every_commit_it_publishes(
    tmp_path: Path, remote: Path, work: Path, branch: str
) -> None:
    """Case 2: the before-SHA is not an ancestor of the after-SHA.

    Both arms are exercised, because a force push of the default branch and of a
    feature branch take different branches of the step.

    ⚠️ **The superseded commit is genuinely absent from the checkout**, not
    hidden by this harness: a clone carries only reachable objects, and a
    force-pushed-over commit is reachable from nothing. That is what the
    checkout on GitHub sees too, and it is why the step cannot assume the value
    the event hands it can be resolved.
    """
    base = committing(work, "README.md", "# Title\n", "docs: readme")
    publish(work, remote, MAIN)

    if branch != DEFAULT_BRANCH:
        git(work, "checkout", "--quiet", "-b", branch)
    committing(work, "NOTES.md", "# Notes\n", "a note")
    superseded = publish(work, remote, f"refs/heads/{branch}")

    git(work, "reset", "--hard", "--quiet", base)
    committing(work, "NOTES.md", "# Notes, rewritten\n", "the note, rewritten")
    push = publish(work, remote, f"refs/heads/{branch}", force=True)

    assert push.before == superseded.after, "the event's before-SHA is the superseded tip"
    assert not is_ancestor(work, push.before, push.after), (
        "this case is about a before-SHA that is NOT an ancestor of the after-SHA"
    )

    at = checkout(remote, push.ref, tmp_path / "checkout")

    assert not holds_commit(at, push.before), (
        "the checkout can still resolve the superseded commit, so the step takes its "
        "first arm and this case never reaches the fallback it exists to exercise"
    )

    assert_covers(pushed_range(push, at, tmp_path / "scratch"), push.published, at)


def test_a_push_that_adds_and_removes_a_tree_is_scanned_over_the_commit_that_held_it(
    tmp_path: Path, remote: Path, work: Path
) -> None:
    """Case 3: several commits, and the content is in neither end of them.

    Driven all the way to a verdict rather than stopping at the range, because
    the range is only interesting for what the guard then does with it. The tip
    is asserted clean on purpose: that it is clean is what makes the second
    assertion mean anything.
    """
    push = a_push_that_hides_a_tree(work, remote)

    at = checkout(remote, push.ref, tmp_path / "checkout")
    result = pushed_range(push, at, tmp_path / "scratch")
    assert_covers(result, push.published, at)

    assert main([str(at)]) == 0, "the tip really is clean, so this proves something"
    assert main(["--range", result.range, str(at)]) == 1, (
        "the family tree this push published is still reachable, and the range the "
        "workflow computed for the push is what has to find it"
    )


def test_a_push_containing_a_merge_covers_both_parents(
    tmp_path: Path, remote: Path, work: Path
) -> None:
    """Case 4: the range walked has more than one parent.

    The tree is added and removed on the SIDE branch, which is never pushed on
    its own -- so the merge is the event that publishes it, and a walk that
    followed first parents alone would report clean over it.
    """
    base = committing(work, "README.md", "# Title\n", "docs: readme")
    publish(work, remote, MAIN)

    git(work, "checkout", "--quiet", "-b", "side")
    aside = committing(work, "family.ged", gedcom_document(), "add a tree on the side")
    (work / "family.ged").unlink()
    removed = committing(work, "SIDE.md", "# Side\n", "remove it again")

    git(work, "checkout", "--quiet", DEFAULT_BRANCH)
    trunk = committing(work, "NOTES.md", "# Notes\n", "meanwhile, on the trunk")
    git(work, "merge", "--quiet", "--no-ff", "-m", "merge the side branch", "side")
    push = publish(work, remote, MAIN)

    at = checkout(remote, push.ref, tmp_path / "checkout")
    result = pushed_range(push, at, tmp_path / "scratch")
    scanned = assert_covers(result, push.published, at)

    parents = git(at, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
    assert len(parents) == 2, f"this case is about a merge commit; got {len(parents)} parent(s)"
    assert {aside, removed, trunk} <= scanned, "both sides of the merge are published by it"
    assert base not in scanned, "and the baseline was already published, so it is not in the range"

    assert main([str(at)]) == 0, "the tip really is clean, so this proves something"
    assert main(["--range", result.range, str(at)]) == 1, (
        "content merged in from a branch nobody pushed is published by the merge"
    )


def test_a_pull_request_covers_every_commit_the_branch_adds(
    tmp_path: Path, remote: Path, work: Path
) -> None:
    """Case 5, the arithmetic half: a pull request takes the other range step.

    The tip of a pull request is a GENERATED MERGE COMMIT, so content added and
    later removed on the branch is absent from it. That is the defect this arm
    was rewritten for, reproduced here over a real ``refs/pull/N/merge``.

    The oracle is the commits the BRANCH published, which is what the pull
    request proposes -- not what pushing the generated merge ref added, which is
    a different question and would be satisfied by scanning the merge alone.
    """
    base = committing(work, "README.md", "# Title\n", "docs: readme")
    publish(work, remote, MAIN)

    git(work, "checkout", "--quiet", "-b", "feature")
    committing(work, "family.ged", gedcom_document(), "add a tree")
    (work / "family.ged").unlink()
    committing(work, "NOTES.md", "# Notes\n", "remove the tree and add a note")
    branch = publish(work, remote, FEATURE)

    git(work, "checkout", "--quiet", "-b", "pr-merge", base)
    git(work, "merge", "--quiet", "--no-ff", "-m", "Merge feature", "feature")
    merge = publish(work, remote, "refs/pull/1/merge", source="pr-merge")

    at = checkout(remote, merge.ref, tmp_path / "checkout")
    result = run_step(
        named_step(PULL_REQUEST_RANGE_STEP),
        pull_request_event(base, merge.after),
        checkout_dir=at,
        scratch=tmp_path / "scratch",
    )
    assert_covers(result, branch.published, at)

    assert main([str(at)]) == 0, "the generated merge tip really is clean"
    assert main(["--range", result.range, str(at)]) == 1, (
        "a branch that added a family tree in one commit and removed it in a later "
        "one is what the merge tip no longer holds, and the range is what finds it"
    )


# ---------------------------------------------------------------------------
# The routing half: which step an event reaches, and where its range comes from.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [PUSHED_RANGE_STEP, PULL_REQUEST_RANGE_STEP],
    ids=["the pushed range", "the pull request range"],
)
def test_the_script_driven_here_is_the_script_the_workflow_runs(name: str) -> None:
    """The anti-transcription guarantee, asserted rather than trusted.

    Every case in this file rests on the extracted body being the workflow's
    own. A reader that dropped, reordered or reflowed a line would be a second
    copy of the arithmetic with a straight face -- and it would keep passing
    while the workflow drifted, which is the failure the whole file exists to
    catch, one level up.

    Asserted by putting the indentation back and looking for the result in the
    file, so nothing about the script is restated here.
    """
    body = step_shell_body(named_step(name))
    indented = "\n".join(f"          {line}" if line else "" for line in body.splitlines())

    assert indented in workflow_text(), (
        f"the script driven for {name!r} is not the one in the workflow; the reader "
        "has dropped or altered a line, so these cases exercise a transcription"
    )


def range_steps_for(event: dict[str, str]) -> list[str]:
    return [
        step_name(block)
        for block in (named_step(PUSHED_RANGE_STEP), named_step(PULL_REQUEST_RANGE_STEP))
        if runs_for(step_condition(block), event)
    ]


def test_a_push_and_a_pull_request_take_different_steps() -> None:
    """Case 5, the routing half: the two events take different branches."""
    assert range_steps_for(EVENTS["a branch push"]) == [PUSHED_RANGE_STEP]
    assert range_steps_for(EVENTS["a pull request"]) == [PULL_REQUEST_RANGE_STEP]


def test_a_tag_push_takes_neither_range_step() -> None:
    """Case 6: regression cover for the tag that was routed to a range.

    A tag at the default-branch commit carries an all-zero before-SHA and a tag
    ref name. Routed to the pushed-range step it resolved a range of NO commits,
    the guard refused it, and the job failed on every ordinary tag push.
    """
    assert range_steps_for(EVENTS["a tag push"]) == [], (
        "a tag push has no baseline that can be trusted, so it must take neither range"
    )


def test_every_event_reaches_exactly_one_scan_step() -> None:
    """No event scans nothing, none scans twice, and no scan reads a range nobody wrote.

    The last clause is the tag defect stated as a rule rather than as a routing
    description: a scan whose RANGE comes from a step that did not run for this
    event receives the empty string, which is a scan of nothing wearing a
    successful step's clothes.
    """
    produced = re.compile(r"steps\.(\w+)\.outputs\.range")

    for description, event in EVENTS.items():
        running = [block for block in scan_steps() if runs_for(step_condition(block), event)]

        assert len(running) == 1, (
            f"{description} reaches {[step_name(block) for block in running]}, and exactly "
            "one scan must cover it -- none means the event publishes unscanned, two means "
            "the coverage depends on which of them ran"
        )

        source = produced.search(step_environment(running[0]).get("RANGE", ""))
        if not source:
            continue

        writers = [block for block in step_blocks() if f"id: {source.group(1)}" in block]
        assert len(writers) == 1, f"{description}: no single step writes {source.group(1)}"
        assert runs_for(step_condition(writers[0]), event), (
            f"for {description} the scan reads its range from {step_name(writers[0])!r}, "
            "which does not run for this event, so it scans the empty string"
        )


# ---------------------------------------------------------------------------
# Negative controls. The workflow is correct at this commit, so no case above
# arrives red -- and an assertion nobody has seen fail is not an assertion.
# ---------------------------------------------------------------------------

NARROWED = "${HEAD_SHA}~1..${HEAD_SHA}"


def a_narrowed_body() -> str:
    """The step's own script with the range narrowed to the last commit alone.

    Constructed IN MEMORY from the real body rather than by editing the
    workflow: there is then nothing on disk to restore, the control runs on
    every CI run rather than once as build evidence, and it cannot leave a
    mutant behind if the run is killed.
    """
    body = step_shell_body(named_step(PUSHED_RANGE_STEP))
    narrowed = body.replace("${BEFORE}..${HEAD_SHA}", NARROWED)
    assert narrowed != body, (
        "the narrowing matched nothing in the step's script, so this control would "
        "run the unmodified body and pass while proving nothing"
    )
    return narrowed


def test_a_range_narrowed_to_one_commit_is_caught(tmp_path: Path, remote: Path, work: Path) -> None:
    """The defect B7 names, injected, and shown to be caught and to be dangerous.

    A range covering some of what the push publishes resolves, covers commits,
    and reports clean -- so the guard-side refusals (B6) and every structural
    assertion pass. Only the coverage relation above sees it.
    """
    push = a_push_that_hides_a_tree(work, remote)
    at = checkout(remote, push.ref, tmp_path / "checkout")

    honest = pushed_range(push, at, tmp_path / "scratch")
    assert_covers(honest, push.published, at)

    narrowed = pushed_range(push, at, tmp_path / "narrowed", body=a_narrowed_body())

    assert narrowed.exit_code == 0 and narrowed.range, (
        "the narrowed range has to be a range the job would happily use; a step that "
        "failed would be caught by the job itself and prove nothing"
    )
    missing = push.published - rev_list(at, narrowed.range)
    assert missing, (
        "the narrowing covered the whole push after all, so this control is not "
        "watching the assertion it was written for"
    )
    with pytest.raises(AssertionError):
        assert_covers(narrowed, push.published, at)

    assert main(["--range", narrowed.range, str(at)]) == 0, (
        "and this is why it matters: the too-narrow range resolves, covers commits, "
        "scans content and reports CLEAN over a family tree the push published"
    )


@pytest.mark.parametrize(
    "condition",
    [
        "!github.event_name",
        "contains(github.ref, 'v')",
        "github.event.action == 'opened'",
        "github.event_name",
    ],
    ids=["negation", "a function call", "an undefined reference", "a bare reference"],
)
def test_a_condition_the_evaluator_cannot_read_is_refused(condition: str) -> None:
    """The routing assertions rest on this evaluator, so it must not guess.

    An evaluator that answered *true* to a construct it does not implement would
    make every routing assertion above vacuously green -- the same shape as a
    check written as a list of the known-bad answers, which admits every answer
    nobody has thought of yet. The bare reference is here for its own reason:
    the truthiness of a string is not an answer this may give.
    """
    with pytest.raises(UnreadableCondition):
        runs_for(condition, EVENTS["a branch push"])
