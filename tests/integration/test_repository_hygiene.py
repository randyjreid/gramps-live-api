"""The repository must contain what it appears to contain.

The .gitignore deliberately hides anything named like a credential or a family
tree. Those patterns are broad on purpose, and a broad pattern can swallow a
source file: a test module named after the property it tests is exactly the
shape of filename the credential patterns match. Nothing warns you -- the file
is simply absent from the clone CI builds, and the suite is quietly smaller
than the one that passed locally.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from gramps_live_api.core.pii_guard import main
from tests.fixtures.repositories import commit_all, git, init_repository
from tests.fixtures.synthetic import gedcom_document

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

GUARD_MODULE = "gramps_live_api.core.pii_guard"

# The workflow's steps are indented by six spaces, so this is where one begins.
# Both range tests below already split the file this way.
STEP_SEPARATOR = "      - name: "


def tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            "not a git checkout, so there is no history to read; nothing to cover -- "
            "this skip has no seam twin because the subject itself is absent, not the "
            "platform capability to observe it"
        )
    return set(result.stdout.splitlines())


def test_every_python_source_file_is_tracked() -> None:
    on_disk = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for directory in ("src", "tests")
        for path in (REPOSITORY_ROOT / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    }

    untracked = sorted(on_disk - tracked_files())

    assert untracked == [], (
        "these source files exist locally but are not in the repository, most "
        f"likely swallowed by a .gitignore pattern: {untracked}"
    )


def is_ignored(pathname: str) -> bool:
    """Whether Git ignores this path, read from the EXIT CODE and nothing else.

    ``check-ignore -v`` prints the matching line even when that line is a
    negation, so its output says a path is ignored in the very case where it
    is not. The .gitignore records this in the block that must stay last, and
    CONTRIBUTING repeats it. Only the exit code answers the question.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", pathname],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        pytest.skip(
            "not a git checkout, so there are no ignore rules to consult; "
            "nothing to cover -- this skip has no seam twin because the subject "
            "itself is absent, not the platform capability to observe it"
        )
    return result.returncode == 0


def test_the_workflow_directory_is_ignored() -> None:
    """.claude/ holds prompt files, and a prompt file is where local paths end up.

    Issue #27: the directory was neither tracked nor ignored, which is one
    ordinary ``git add`` away from publishing it. The contents were harmless;
    the state was not, and it is the same state issue #11 recorded for the
    lock file.

    Both spellings are asserted because they answer different questions, and
    the difference is not the one a reader expects. A bare ``.claude`` is
    reported as ignored only when the directory EXISTS on disk -- measured:
    exit 1 when absent, exit 0 when present -- because a trailing-slash rule
    matches directories and Git cannot know a nonexistent path is one. A fresh
    CI clone has no .claude/ at all, so the bare spelling would fail there for
    a reason that has nothing to do with the rule. The trailing slash and any
    path beneath it are answered from the rule alone, on disk or not.

    The markdown path is the one that matters. ``!*.md`` in .gitignore is
    unanchored, and this directory holds only markdown, so the file is exactly
    the shape that negation re-admits. It does not, because a negation cannot
    re-include a file whose parent directory is excluded -- but that is a claim
    about Git's behaviour, and the .gitignore records four deny-list variants
    that were silently re-admitted by a reading just as confident.
    """
    assert is_ignored(".claude/"), (
        "the .claude/ workflow directory is not ignored, so its prompt files are "
        "stageable by an ordinary git add into a public repository"
    )
    assert is_ignored(".claude/prompts/any-prompt.md"), (
        "markdown under .claude/ is not ignored -- the unanchored !*.md negation in "
        ".gitignore has re-admitted it, which is the interaction issue #27 warned "
        "would not be visible by reading the pattern"
    )


def test_no_path_is_both_untracked_and_unignored() -> None:
    """The state issues #11 and #27 both describe, asserted rather than noticed.

    A path that is neither tracked nor ignored is governed by nothing: it does
    not appear in the repository, so nobody reviews it, and it is not excluded,
    so any ``git add -A`` sweeps it in. Both issues were found by a person
    looking at the working tree at the right moment. This is that look, run
    every time.

    ⚠️ **This test can only ever fire LOCALLY.** A fresh CI clone contains
    exactly what the repository tracks and nothing else, so there is no
    untracked path for it to find and it passes vacuously on every single CI
    run. Green here is evidence of nothing in CI, and a later reader must not
    read it as evidence the property holds -- that is the structurally-cannot-
    fail defect issue #8 records. Its seam twin is
    test_the_workflow_directory_is_ignored, which asserts a rule rather than a
    tree state and therefore does fire in CI. That asymmetry is why both exist:
    one proves the rule shipped, the other catches the next directory nobody
    has written a rule for yet, and only on the machine where it appears.
    """
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            "not a git checkout, so there is no tree state to read; nothing to cover -- "
            "this skip has no seam twin because the subject itself is absent, not the "
            "platform capability to observe it"
        )

    ungoverned = sorted(line[3:] for line in result.stdout.splitlines() if line.startswith("??"))

    assert ungoverned == [], (
        "these paths are neither tracked nor ignored, so nothing governs them and an "
        "ordinary git add -A would commit them unexamined -- track each one or add a "
        f".gitignore rule for it, then confirm with the exit code of check-ignore: {ungoverned}"
    )


def shell_bodies() -> list[tuple[int, str]]:
    """Every line belonging to a ``run:`` block, with its line number.

    Hand-parsed by indentation rather than with a YAML library, because the
    guard job deliberately installs nothing and this repository has no runtime
    dependencies to add one to.
    """
    lines = (
        (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    body: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip().startswith("run:"):
            index += 1
            continue
        indent = len(line) - len(line.lstrip())
        body.append((index + 1, line.strip()[len("run:") :]))
        index += 1
        while index < len(lines):
            following = lines[index]
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append((index + 1, following))
            index += 1
    return body


def test_no_workflow_expression_is_interpolated_into_a_shell_body() -> None:
    """A branch name is not trusted input, and a ref name is a branch name.

    GitHub substitutes an expression into the script text before Bash parses
    it, so a branch whose name contains an apostrophe -- which Git permits --
    ends the quoting and the rest of the line becomes code. This job's whole
    purpose is scanning for leaked data, in a public repository.

    Asserted as the ABSENCE of interpolation rather than the presence of an
    env block: the defect is the interpolation, and a presence test passes
    while both forms sit side by side.
    """
    interpolated = sorted(f"line {number}" for number, text in shell_bodies() if "${{" in text)

    assert interpolated == [], (
        "these shell bodies have a workflow expression substituted into them before "
        f"Bash sees the script; pass the value through env: and quote it instead: {interpolated}"
    )


def workflow_text() -> str:
    return (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def step_blocks() -> list[str]:
    """Every step of the workflow, as text. The first chunk is the file header."""
    return workflow_text().split(STEP_SEPARATOR)[1:]


def step_name(block: str) -> str:
    return block.splitlines()[0].strip()


def guard_invocation(block: str) -> str:
    """The block's ``run:`` line if it runs the guard, otherwise the empty string."""
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("run:") and GUARD_MODULE in stripped:
            return stripped
    return ""


def scan_steps() -> list[str]:
    return [block for block in step_blocks() if guard_invocation(block)]


def test_no_scan_step_reads_only_the_tip() -> None:
    """A scan must cover the history the event publishes, not the tree it ends on.

    This replaces test_a_tag_push_is_not_routed_to_a_range, which asserted that
    the push range step distinguishes a branch from a tag. That was a
    restatement of the implementation: it described the routing the code had
    rather than the guarantee the gate owes, it was equally true of a workflow
    that scanned a tag correctly, and it survived five review rounds while a
    tag push reported clean over every ancestor of its target. A test that
    passes on both the defect and the fix is not watching the defect.

    So the rule, not the routing: NO step may scan less than the history it
    publishes, which is mechanically "every step that runs the guard passes
    --range". It is false of the code that shipped the defect, true of the fix,
    and -- unlike its predecessor -- it also catches a step added later that
    forgets a range, because it names no event type and so cannot be satisfied
    by re-routing.

    A tag publishes its target commit AND every ancestor. Content added in A
    and deleted in B is absent from B's tree and still reachable through a tag
    on B; the tip scan read the tree and reported clean over the rest.
    """
    steps = scan_steps()
    assert steps, "no step runs the guard at all -- this test has stopped watching anything"

    tip_only = sorted(step_name(block) for block in scan_steps() if "--range" not in block)

    assert tip_only == [], (
        "these steps scan the tip alone, so content their event publishes but their "
        f"checkout no longer holds is never read: {tip_only}"
    )


def tag_push_scan_arguments(target: Path) -> list[str]:
    """The guard arguments CI runs on a tag push, read from the workflow itself.

    Read rather than restated, so the reproduction below exercises what CI will
    actually run. A copy of the arguments here would keep passing while the
    workflow drifted, which is the failure this whole test file exists to
    catch.
    """
    covering = [block for block in scan_steps() if "ref_type != 'branch'" in block]
    assert len(covering) == 1, (
        "expected exactly one guard step to cover a tag push, found "
        f"{[step_name(block) for block in covering]}"
    )

    block = covering[0]
    environment = dict(re.findall(r"^ +(\w+): +(\S+)$", block, re.MULTILINE))
    _, _, tail = guard_invocation(block).partition(GUARD_MODULE)

    arguments = []
    for token in tail.split():
        word = token.strip('"')
        if word.startswith("$"):
            name = word[1:]
            assert name in environment, (
                f"the step passes {word}, which its own env: block does not define"
            )
            word = environment[name]
        arguments.append(str(target) if word == "." else word)
    return arguments


def test_a_tag_push_does_not_report_clean_over_a_deleted_ancestor(tmp_path: Path) -> None:
    """The reviewer's scenario, run end to end through the workflow's own arguments.

    Commit A adds a family tree, commit B deletes it, the tag points at B. B's
    tree is clean and A's blob is publicly reachable through the tag, so a scan
    of the tip reports clean over content the tag publishes. The tip scan is
    asserted to pass here on purpose: that it passes IS the defect, and stating
    it is what makes the second assertion mean something.
    """
    root = init_repository(tmp_path / "repo")
    (root / "README.md").write_text("# Title\n", encoding="utf-8")
    (root / "family.ged").write_text(gedcom_document(), encoding="utf-8")
    commit_all(root, "A: a family tree arrives")
    (root / "family.ged").unlink()
    commit_all(root, "B: and is deleted again")
    git(root, "tag", "v1")

    assert main([str(root)]) == 0, "the tip is not clean, so this proves nothing about the range"

    assert main(tag_push_scan_arguments(root)) == 1, (
        "the scan CI runs on a tag push reports clean over a family tree that the "
        "tag publishes through its target's ancestor"
    )


def test_every_pull_request_gets_a_history_scan() -> None:
    """The defect was a condition, so this asserts the condition is gone.

    A same-repository pull request used to run the tip scan alone: both range
    steps carried a fork-only condition. A branch that added genealogy data in
    one commit and removed it in a later one came back clean, because the
    merge tip no longer held it -- and the tip is all that was scanned.

    A test that merely found the step would have passed throughout, which is
    why this looks for the condition rather than the step.
    """
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    ranged = [
        block
        for block in workflow.split("      - name: ")
        if "--range" in block and "pull_request" in block
    ]

    assert ranged, "no pull-request step computes a range at all"
    assert not any("fork" in block for block in ranged), (
        "a pull-request range step is still conditioned on the fork flag, so a "
        "same-repository pull request scans only the merge tip"
    )


def test_the_job_refuses_a_checkout_it_cannot_prove_is_complete() -> None:
    """Every range arm rests on the whole history being present. Nothing asserted it.

    ``fetch-depth: 0`` supplies it and a comment states it is required, but a
    comment is not a check. ``git rev-list`` on a shallow clone succeeds and
    returns only the commits that were fetched, so a checkout that quietly
    stopped being complete would make every range arm -- the branch push, the
    pull request, and the tag -- scan a truncated history and report clean over
    the rest. That is the same fail-open as the tag defect, one level down.

    Asserted as fail-closed on anything that is not exactly "false", not as
    "fail when the answer is true": the second is a known-safe list, and it
    admits every answer nobody has thought of yet -- an empty result, a failed
    invocation, a word from a future Git.

    The step is unconditional because the property it protects is, and the
    ordering is asserted because a check that runs after the scan protects
    nothing.
    """
    blocks = step_blocks()
    shallow = [block for block in blocks if "--is-shallow-repository" in block]

    assert len(shallow) == 1, (
        "expected exactly one step to establish that the checkout is complete, found "
        f"{[step_name(block) for block in shallow]}"
    )

    block = shallow[0]
    conditions = [line for line in block.splitlines() if line.strip().startswith("if:")]
    assert conditions == [], (
        "the completeness check is conditional, so some event reaches the scans "
        f"without it: {conditions}"
    )

    assert blocks.index(block) < min(blocks.index(scan) for scan in scan_steps()), (
        "the completeness check runs after a scan, which is after the answer stopped "
        "being able to change anything"
    )

    assert "exit 1" in block, "the completeness check reports without failing the job"
    assert '!= "false"' in block, (
        "the completeness check does not fail closed: it must abort on every answer "
        "that is not exactly false, not only on the one word that means shallow today"
    )
    assert '= "true"' not in block, (
        "the completeness check tests for the known-bad answer, so an empty result or "
        "an unrecognised word from a future Git passes it"
    )


def job_blocks() -> dict[str, str]:
    """Every job of the workflow, as text, keyed by its name.

    Hand-parsed by indentation for the reason shell_bodies() gives: the guard
    job deliberately installs nothing, so this repository has no dependency to
    add a YAML library to. A job header is the only key at two spaces -- the
    keys inside one sit at four, and its steps at six.
    """
    _, _, jobs = workflow_text().partition("\njobs:\n")

    blocks: dict[str, str] = {}
    name = ""
    for line in jobs.splitlines():
        header = re.match(r"^ {2}([\w-]+):\s*$", line)
        if header:
            name = header.group(1)
            blocks[name] = ""
        elif name:
            blocks[name] += line + "\n"
    return blocks


def job_steps(job: str) -> list[str]:
    """The job's steps, as text. Split on the list marker, not on ``- name:``.

    STEP_SEPARATOR would drop every unnamed step, and an unnamed ``- uses:`` is
    exactly what a checkout is: the shape this test exists to read.
    """
    return re.split(r"^ {6}- ", job, flags=re.MULTILINE)[1:]


def invokes_the_suite(step: str) -> bool:
    """Whether this step runs pytest, read from its ``run:`` block alone.

    Comments are excluded and so is everything ahead of ``run:``. This
    workflow explains itself at length, and a step whose commentary mentions
    the suite does not run it.
    """
    body = step.partition("run:")[2]
    return any("pytest" in line for line in body.splitlines() if not line.strip().startswith("#"))


def test_every_job_that_runs_the_suite_checks_out_whole_history() -> None:
    """B8's history assertion cannot run on a checkout that stops at one commit.

    ``test_every_commit_this_repository_publishes_is_clean`` scans the commits
    this repository publishes, and it refuses to do that over a truncated
    history -- correctly, because a range scan over commits that were never
    fetched reports clean over the part it cannot see. So on a shallow checkout
    it SKIPS. Nothing goes red: the job stays green while the property goes
    unmeasured on every ordinary run, which is issue #31, and it is why the
    workflow runs ``pytest -rs``. A skip named in the report is a skip somebody
    can notice; a skip folded into a count is what let this survive.

    ⚠️ **The rule, not the routing.** This names no job, so it is equally true
    of a job added later that runs the suite on a checkout nobody thought
    about -- the same reason test_no_scan_step_reads_only_the_tip asks whether
    every step running the guard passes --range, rather than asking about the
    tag arm it was written for.

    And every checkout in such a job, not merely one of them. A second checkout
    added later without ``fetch-depth: 0`` is the same defect with a second
    cause; failing closed on it costs a reviewer one look, and the other
    reading costs a property nobody measures.
    """
    jobs = {
        name: block
        for name, block in job_blocks().items()
        if any(invokes_the_suite(step) for step in job_steps(block))
    }

    assert jobs, "no job runs the suite at all -- this test has stopped watching anything"

    checkoutless = sorted(
        name
        for name, block in jobs.items()
        if not [step for step in job_steps(block) if "actions/checkout" in step]
    )
    assert checkoutless == [], (
        "these jobs run the suite without checking the repository out at all, so this "
        f"test would be asserting a property of a step that is not there: {checkoutless}"
    )

    truncated = sorted(
        name
        for name, block in jobs.items()
        for step in job_steps(block)
        if "actions/checkout" in step and "fetch-depth: 0" not in step
    )

    assert truncated == [], (
        "these jobs run the suite on a checkout they have not asked to be complete, so "
        "the history assertion skips there rather than failing -- the job stays green "
        f"and the property goes unmeasured: {truncated}"
    )


def test_every_skip_names_a_seam_twin_that_exists() -> None:
    """A cross-reference that rots is worse than none at all.

    Every platform skip states which seam test covers the property in its
    place, so a local run reporting five skips says what it still proves. That
    claim is a string, and a renamed twin would leave it confidently wrong --
    pointing a reader at a test that is not there and implying coverage that
    has moved. So the names are checked against the functions that exist.

    This also refuses a skip that explains itself without naming a twin: an
    uncovered skip is a real gap, and it should be argued for rather than
    arrive by omission. The one exemption is a skip whose SUBJECT is absent
    rather than whose observation is -- there is no seam twin for a repository
    that is not a checkout, because there is nothing there to cover. Such a
    skip has to say so in those words, so the exemption is claimed on purpose.
    """
    named = re.compile(r"seam twins? \"?\n?\s*\"?(test_\w+)(?:\s+and\s+\"?\n?\s*\"?(test_\w+))?")
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in (REPOSITORY_ROOT / "tests").rglob("test_*.py")
    }
    defined = {
        name
        for text in sources.values()
        for name in re.findall(r"^def (test_\w+)", text, re.MULTILINE)
    }

    skips = [
        (path, block)
        for path, text in sources.items()
        for block in re.findall(r"pytest\.skip\((.*?)\)", text, re.DOTALL)
    ]
    assert skips, "no skips found at all -- this test has stopped watching anything"

    for path, block in skips:
        if "nothing to cover" in block:
            continue
        twins = named.search(block)
        assert twins, f"a skip in {path.name} claims no seam twin: {block.strip()}"
        for twin in filter(None, twins.groups()):
            assert twin in defined, (
                f"the skip in {path.name} names {twin}, which no longer exists -- "
                "the twin was renamed and the coverage claim rotted with it"
            )
