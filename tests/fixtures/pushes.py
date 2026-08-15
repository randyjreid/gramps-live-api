"""Real pushes into a scratch remote, and the range the workflow computes for them.

⚠️ **Everything here lives under pytest's ``tmp_path``, outside the project
working tree.** A scratch ``.git`` under the repository would be a nested
repository and untracked noise, which
``test_no_path_is_both_untracked_and_unignored`` refuses.

The oracle -- *what commits did this push publish?* -- is computed **in the bare
remote, from what the remote gained**:

    git rev-list <new> --not <every ref the remote held before the push>

That is what a receive hook would compute. It reads nothing the workflow's step
reads: not the before-SHA, not the default branch, not a remote-tracking ref. A
transcription of the step's own arithmetic would agree with the step by
construction and prove nothing.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tests.fixtures.repositories import git, init_repository
from tests.fixtures.shell import posix_shell
from tests.fixtures.workflow import step_environment, step_shell_body

ZERO_SHA = "0" * 40
"""The before-SHA a push carries when the ref is new to the remote."""


@dataclass(frozen=True)
class Push:
    """One push, and the commits the remote gained because of it."""

    ref: str
    ref_name: str
    ref_type: str
    before: str
    after: str
    published: frozenset[str]


@dataclass(frozen=True)
class StepResult:
    """What a workflow step did: its exit status and what it wrote as its range."""

    exit_code: int
    range: str
    output: str


def bare_remote(path: Path) -> Path:
    """A remote that can be pushed into on any branch, because nothing is checked out."""
    path.mkdir(parents=True, exist_ok=True)
    git(path.parent, "init", "--bare", "--quiet", "--initial-branch=main", str(path))
    return path


def working_clone(path: Path) -> Path:
    """A repository to build history in. Reuses the suite's identity-configured init."""
    return init_repository(path)


def remote_refs(remote: Path) -> dict[str, str]:
    listing = git(remote, "for-each-ref", "--format=%(refname) %(objectname)")
    return dict(line.split(" ", 1) for line in listing.splitlines() if line)


def rev_list(root: Path, expression: str, exclude: set[str] | None = None) -> frozenset[str]:
    """The commits ``expression`` covers, as a set of SHAs."""
    arguments = ["rev-list", expression]
    if exclude:
        arguments.append("--not")
        arguments.extend(sorted(exclude))
    return frozenset(git(root, *arguments).split())


def holds_commit(root: Path, sha: str) -> bool:
    """Whether ``root`` can resolve ``sha`` as a commit -- the step's own question."""
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Read from the exit code, which is the only thing this command answers with."""
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=root,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def publish(
    work: Path, remote: Path, ref: str, *, source: str = "HEAD", force: bool = False
) -> Push:
    """Push ``source`` to ``ref`` in ``remote``, and measure what the remote gained."""
    held = remote_refs(remote)
    before = held.get(ref, ZERO_SHA)

    arguments = ["push", "--quiet"]
    if force:
        arguments.append("--force")
    git(work, *arguments, str(remote), f"{source}:{ref}")

    after = remote_refs(remote)[ref]
    return Push(
        ref=ref,
        ref_name=ref.split("/", 2)[2],
        ref_type="tag" if ref.startswith("refs/tags/") else "branch",
        before=before,
        after=after,
        published=rev_list(remote, after, exclude=set(held.values())),
    )


def checkout(remote: Path, ref: str, into: Path) -> Path:
    """The stand-in for ``actions/checkout`` at ``fetch-depth: 0``.

    A full clone, so remote-tracking refs exist for every branch the remote
    holds -- which is what the step's ``origin/<default>`` fallback reads, and
    what the action's own whole-history fetch supplies.

    ⚠️ **``--no-local`` is load-bearing, not a tidiness flag.** Cloning from a
    path, Git takes a local shortcut and hardlinks the WHOLE object store --
    unreachable objects included. The superseded commit of a force push would
    then be resolvable in the checkout, the step would take its first arm, and
    the force-push case would pass without ever reaching the fallback it exists
    to exercise. The real transport transfers only what is reachable, which is
    what a checkout on GitHub gets.
    """
    git(into.parent, "clone", "--quiet", "--no-local", str(remote), str(into))
    if ref.startswith("refs/heads/"):
        git(into, "checkout", "--quiet", ref.split("/", 2)[2])
    elif ref.startswith("refs/tags/"):
        git(into, "checkout", "--quiet", "--detach", ref)
    else:
        git(into, "fetch", "--quiet", "origin", ref)
        git(into, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    return into


def resolve_environment(block: str, event: Mapping[str, str]) -> dict[str, str]:
    """The step's ``env:`` block with its expressions answered from ``event``.

    Read from the step's own block rather than written out here, so a step that
    starts reading a different field of the event gets that field -- or raises.
    A reference the event does not define is never silently empty: the shell
    would then take a branch nobody chose, and report a range for it.
    """
    resolved = {}
    for name, text in step_environment(block).items():
        if text.startswith("${{") and text.endswith("}}"):
            reference = text[3:-2].strip()
            if reference not in event:
                raise LookupError(f"the step reads {reference}, which this event does not define")
            resolved[name] = event[reference]
        else:
            resolved[name] = text
    return resolved


def run_step(
    block: str,
    event: Mapping[str, str],
    *,
    checkout_dir: Path,
    scratch: Path,
    body: str | None = None,
) -> StepResult:
    """Run a workflow step's own shell body over ``checkout_dir``.

    ``body`` overrides the extracted script, and exists only for the negative
    controls: a narrowed range has to be shown failing, or the coverage
    assertion is not watching anything.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    script = scratch / "step.sh"
    script.write_text(
        body if body is not None else step_shell_body(block), encoding="utf-8", newline="\n"
    )

    output_file = scratch / "step-output"
    output_file.write_text("", encoding="utf-8", newline="\n")

    environment = dict(os.environ)
    environment.update(resolve_environment(block, event))
    # Forward slashes: the shell is given this path inside its own script, and a
    # backslash inside double quotes is not a separator there.
    environment["GITHUB_OUTPUT"] = str(output_file).replace("\\", "/")

    completed = subprocess.run(
        [str(posix_shell()), str(script)],
        cwd=checkout_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    written = dict(
        line.split("=", 1)
        for line in output_file.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    return StepResult(
        exit_code=completed.returncode,
        range=written.get("range", ""),
        output=completed.stdout + completed.stderr,
    )
