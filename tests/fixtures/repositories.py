"""Build throwaway Git repositories for tests that must talk to Git itself.

The guard's scope is what Git contains, not what the working tree happens to
show, so several properties can only be tested against a real repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *arguments: str) -> str:
    """Run a Git command in ``root`` and return its stdout."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def init_repository(root: Path) -> Path:
    """An empty repository with an identity, so commits can be made."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "--quiet", "--initial-branch=main")
    git(root, "config", "user.name", "Test Harness")
    git(root, "config", "user.email", "harness@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    return root


def commit_index(root: Path, message: str) -> str:
    """Commit exactly what is staged; returns the commit sha.

    Used where ``git add --all`` would undo the staging: an index entry with no
    file behind it, such as a symlink written through ``update-index``, reads
    as a deletion to ``add --all``.
    """
    git(root, "commit", "--quiet", "--no-verify", "-m", message)
    return git(root, "rev-parse", "HEAD")


def commit_all(root: Path, message: str) -> str:
    """Stage everything and commit; returns the commit sha."""
    git(root, "add", "--all")
    return commit_index(root, message)


def add_symlink_bytes(root: Path, name: str, payload: bytes) -> None:
    """Stage a symlink-mode entry over arbitrary bytes.

    Git stores whatever it is given under mode 120000; nothing checks that the
    blob is really a path. That is the hiding place this exercises.
    """
    blob = (
        subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=root,
            input=payload,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    git(root, "update-index", "--add", "--cacheinfo", "120000", blob, name)


def add_symlink(root: Path, name: str, target: str) -> None:
    """Stage a symlink whose committed blob content is ``target``.

    Written through the index rather than the filesystem: creating a real
    symlink needs privileges Windows does not grant by default, and it is the
    *committed blob* -- which is simply the target string -- that the guard has
    to read.
    """
    blob = (
        subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=root,
            input=target.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    git(root, "update-index", "--add", "--cacheinfo", "120000", blob, name)
