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

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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


def test_a_tag_push_is_not_routed_to_a_range() -> None:
    """A tag at the default-branch commit resolves to a range of no commits.

    The before-SHA is all zeros and the ref name is the tag, so the fallback
    emits default..HEAD, which is empty; the guard rightly refuses an empty
    range and the job failed on every ordinary tag push. The workflow
    subscribes to tag pushes, so it was doing this to itself.

    A tag makes a commit's tree referenceable under a new public name. The tree
    is what the tag publishes, so the tip scan reads exactly that and is never
    empty -- which is why the range step must be branch-only.
    """
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    ranged = [
        block
        for block in workflow.split("      - name: ")
        if "--range" in block and "github.event_name == 'push'" in block
    ]

    assert ranged, "no push step computes a range at all"
    assert all("ref_type" in block for block in ranged), (
        "a push range step does not distinguish a branch from a tag, so a tag push "
        "resolves to a range covering no commits and the job fails"
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
