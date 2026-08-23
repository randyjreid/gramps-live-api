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


def durable_directory(directory: str) -> str:
    """Flush ``directory`` and every level this run may have created above it.

    Returns ``SYNCED``, ``UNSUPPORTED`` or ``FAILED``.

    ⛔ **The whole newly created path, not just the leaf.** A tree's first backup
    creates ``backups/`` and ``backups/<tree>/``; syncing only the leaf leaves the
    entry FOR that leaf unflushed in its own parent, so on POSIX a crash can lose
    the directory the file was durably written into. ⚠️ Syncing one level stood in
    for durability of the path -- an enumerated step where a bound was needed.
    """
    walked = []
    current = os.path.abspath(directory)
    for _ in range(8):
        walked.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    verdict = SYNCED
    for level in walked:
        outcome = _flush_one(level)
        if outcome == FAILED:
            return FAILED
        if outcome == UNSUPPORTED:
            verdict = UNSUPPORTED
    return verdict


def _flush_one(directory: str) -> str:
    """One directory. ⛔ ``UNSUPPORTED`` is a platform limit, not an error."""
    if not hasattr(os, "fsync"):
        return UNSUPPORTED
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        # ⚠️ Windows: a directory cannot be opened as a descriptor. A KNOWN LIMIT,
        # reported as one so a caller can tell it from an I/O failure.
        return UNSUPPORTED
    try:
        os.fsync(handle)
        return SYNCED
    except OSError:
        return FAILED
    finally:
        os.close(handle)
