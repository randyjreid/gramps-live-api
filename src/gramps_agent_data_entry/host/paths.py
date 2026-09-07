"""Where the host's three files live: one directory, resolved one way.

⚠️ **Deliberately derived from ``config.user_config_path`` rather than spelled
again.** Two answers to "where does this project keep things" is how the front
end and the host end up looking in different directories on the same machine,
and the failure would be silent -- a client reading a ``port`` file that nothing
writes looks exactly like a host that is not running.

``config.py``'s rule about arguments applies here for its reason: ``environ`` and
``platform`` are passed in, so both layouts are exercised on whichever platform
is running.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from gramps_live_api import config

TOKEN_FILE = "token"
PORT_FILE = "port"
LOG_FILE = "host.log"


def state_directory(environ: Mapping[str, str], *, platform: str = sys.platform) -> Path:
    """The per-user directory this project already owns -- on Windows, under APPDATA."""
    return config.user_config_path(environ, platform=platform).parent


def token_path(directory: Path) -> Path:
    return directory / TOKEN_FILE


def port_path(directory: Path) -> Path:
    """Written only after a successful bind, so its presence means something."""
    return directory / PORT_FILE


def log_path(directory: Path) -> Path:
    return directory / LOG_FILE


SYNCED = "synced"
UNSUPPORTED = "unsupported"
FAILED = "failed"
"""⛔ Three answers, because two of them are not the same thing.

⚠️ **A directory that CANNOT be flushed and one that FAILED to flush are
different facts**, and collapsing them is how a durability guarantee becomes
unverifiable. Windows cannot open a directory as a file descriptor at all, so it
always takes the first path -- meaning a boolean would report *not durable* on
every single write on the only platform this actually runs on, and the caller
would have to ignore it to function. **An ignored signal is not a signal.**"""


def create_directory(directory: str) -> list[str]:
    """Create ``directory`` and return every level a flush must then cover.

    ⛔ **The levels THIS RUN created -- discovered before creating them, because
    afterwards there is no way to tell.**

    ⚠️ The previous version walked a fixed **eight** levels toward the root, which
    was an enumeration wearing a bound's clothes and wrong in both directions.
    Walking too far fsynced ``grampsdb``, ``$HOME``, ``/home`` and ``/`` -- none of
    them created here -- so **one quirky ancestor on an NFS or FUSE mount turned
    into FAILED and refused every approved write**. Walking only eight left the
    ninth created level unflushed while reporting SYNCED, which is the same class
    of lie in the other direction.

    ⭐ The returned list is the directory itself, every level that had to be
    created, and **the first pre-existing ancestor** -- that last one because its
    own entry gained the topmost new level, and an unflushed parent entry loses
    the whole created path exactly as an unflushed leaf loses the file.
    """
    absolute = os.path.abspath(directory)
    missing = []
    current = absolute
    while not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    os.makedirs(absolute, exist_ok=True)

    # ⛔ **Owner-only, and ONLY on the levels this run created.**
    #
    # ⚠️ A tree copy is the whole database -- including every record the API's
    # privacy filtering hides. Under the common 022 umask these directories are
    # created 0755, so on any shared POSIX machine another local account can walk
    # in and read what the API refuses to show. ⭐ Narrowing a directory this run
    # did NOT create would change permissions the owner chose, so the same list
    # that bounds the flush bounds this.
    for level in missing:
        owner_only(level)

    levels = [absolute, *missing]
    if missing and os.path.isdir(current):
        levels.append(current)
    # ⛔ Deduplicated, order preserved: when the directory already existed,
    # ``missing`` is empty and the only level is the directory itself -- its entry
    # in its parent is already durable, so the parent is not flushed again.
    return list(dict.fromkeys(levels))


def owner_only(path: str) -> None:
    """Restrict ``path`` to its owner. ⛔ Never fatal -- and a no-op on Windows.

    ⚠️ **Windows does not have POSIX modes**, and `os.chmod` there controls only
    the read-only flag; access is governed by inherited ACLs instead. Calling it
    would do nothing useful and would make this read as a guarantee on a platform
    where it is not one. **Saying which platforms a protection covers is part of
    the protection.**
    """
    if os.name == "nt":
        return
    mode = 0o700 if os.path.isdir(path) else 0o600
    # A permission we could not narrow is not a reason to abandon a backup that is
    # otherwise sound; the caller has no better answer available than this one.
    with contextlib.suppress(OSError):
        os.chmod(path, mode)


def create_file_owner_only(path: str) -> None:
    """Create ``path`` empty and owner-readable BEFORE anything else opens it.

    ⛔ **Before, not after.** SQLite creates its destination with the process
    umask, so narrowing the file afterwards leaves a window in which the whole
    tree -- privacy-filtered records included -- is world-readable on disk. The
    window is small and its contents are the entire database.

    ⭐ Pre-creating means SQLite opens a file that already exists and leaves its
    mode alone, and ``os.replace`` carries that mode to the final name.
    """
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    handle = os.open(path, flags, 0o600)
    os.close(handle)
    owner_only(path)


def durable_directory(levels: list[str]) -> str:
    """Flush the levels ``create_directory`` said this run is responsible for.

    Returns ``SYNCED``, ``UNSUPPORTED`` or ``FAILED``. ⛔ ``FAILED`` anywhere is
    ``FAILED`` overall -- a partially durable path is not a durable path.
    """
    verdict = SYNCED
    for level in levels:
        outcome = _flush_one(level)
        if outcome == FAILED:
            return FAILED
        if outcome == UNSUPPORTED:
            verdict = UNSUPPORTED
    return verdict


def _flush_one(directory: str) -> str:
    """One directory. ⛔ ``UNSUPPORTED`` is a PLATFORM LIMIT, not an error.

    ⚠️ **Every ``OSError`` used to be called a platform limit**, which made the
    label mean *the open did not work* rather than *this platform cannot do this*.
    On POSIX, opening a directory read-only is always supported, so ``EMFILE``,
    ``EACCES`` and ``ENOENT`` there are genuine failures -- and reporting them as
    ``UNSUPPORTED`` walked them straight past the guard that refuses a write when
    the entry cannot be made durable. **A check answering for a reason unrelated
    to the property it names, in the code written to fix exactly that.**
    """
    if not hasattr(os, "fsync"):
        return UNSUPPORTED
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        # ⛔ Windows CANNOT open a directory as a descriptor -- a known limit of
        # the platform, true of every directory, always. Anywhere else the open
        # is supported and a refusal is a real failure.
        return UNSUPPORTED if os.name == "nt" else FAILED
    try:
        os.fsync(handle)
        return SYNCED
    except OSError:
        return FAILED
    finally:
        os.close(handle)
