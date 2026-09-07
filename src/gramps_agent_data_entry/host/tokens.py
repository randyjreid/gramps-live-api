"""Minting the bearer token, and writing it down as privately as the platform allows.

⚠️ **The protection achieved is REPORTED, never assumed.** ``write_token``
returns which mechanism actually succeeded, and the caller logs it. A host that
prints "token written" and means "written world-readable, the ACL command was
not on this machine" is worse than one that says nothing, because the sentence
reads like a guarantee.

⚠️ **``0o600`` is not an ACL on Windows.** Python maps the mode of a file it
creates onto the read-only attribute and nothing else -- there is no owner-only
DACL in it. The AIO bundles no ``pywin32``, so the available mechanism is
``icacls``, which is a Windows built-in. Both halves of the command are
load-bearing and neither works alone:

``/inheritance:r``   stop inheriting the parent's list -- without it the grant is
                     added to whatever was already there, which is a no-op
                     wearing a protection's clothes.
``/grant:r``         replace, rather than add, the entry for this account --
                     without it, and with inheritance already removed, the file
                     is unreadable by everyone including the owner.

⚠️ **Failure is fail-open and says so.** The host still starts: on Windows the
per-user application-data directory is already owner-plus-administrators, and R8
accepts that any process running as the owner can read the token -- such a
process could read the tree directly. The residual this does NOT cover is a
machine whose profile directory has been widened by hand, and the log line is how
the owner would find out.
"""

from __future__ import annotations

import os
import secrets
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

TOKEN_BYTES = 32
"""256 bits before encoding. Not a tuned figure -- it is the point past which
guessing stops being the way in, and the token is written to a file rather than
typed, so length costs nobody anything."""

OWNER_ONLY_ACL = "acl"
OWNER_ONLY_MODE = "mode"
INHERITED_ONLY = "inherited"

_ACL_TIMEOUT_SECONDS = 10.0
"""``load_on_reg`` runs on the startup path, so this cannot wait indefinitely."""


@dataclass(frozen=True)
class CommandResult:
    """What running a command produced. ``detail`` never carries the account name."""

    returncode: int
    detail: str


@dataclass(frozen=True)
class Protection:
    """Which mechanism protected the token file, and anything the owner should know.

    ⛔ ``detail`` is written into ``host.log``. Nothing personal goes in it -- not
    the account name, not the domain -- because that file is the one the owner
    will paste into an issue.
    """

    kind: str
    detail: str


def new_token() -> str:
    """A fresh bearer token. Generated at every startup, never persisted between them."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def write_token(
    path: Path,
    token: str,
    *,
    platform: str,
    environ: Mapping[str, str],
    run: Callable[[list[str]], CommandResult] | None = None,
) -> Protection:
    """Write the token, protect it as far as the platform allows, and say which.

    ``run`` is a parameter so the Windows branch is exercised on every platform.
    A branch only its own operating system can reach is a branch CI proves
    nothing about -- ``config.py``'s rule, applied to a subprocess instead of to
    an environment variable.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # os.open with the mode, rather than write_text and a chmod afterwards: the
    # gap between the two is a window in which the token exists at the default
    # mode, and on the platform where the mode is the whole protection that
    # window is the whole exposure.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(token)

    if platform != "win32":
        return Protection(OWNER_ONLY_MODE, "created with mode 0600")

    return _restrict_on_windows(path, environ, run or _run)


def _restrict_on_windows(
    path: Path,
    environ: Mapping[str, str],
    run: Callable[[list[str]], CommandResult],
) -> Protection:
    account = environ.get("USERNAME")
    if not account:
        return Protection(
            INHERITED_ONLY,
            "no account name in the environment, so no access list was set; the file "
            "keeps whatever the application-data directory grants",
        )

    domain = environ.get("USERDOMAIN")
    principal = f"{domain}\\{account}" if domain else account

    result = run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{principal}:(F)",
        ]
    )
    if result.returncode != 0:
        return Protection(
            INHERITED_ONLY,
            f"the access list could not be set ({result.detail}); the file keeps "
            "whatever the application-data directory grants",
        )

    return Protection(OWNER_ONLY_ACL, "inheritance removed, full control granted to this account")


def _run(argv: list[str]) -> CommandResult:
    """Run it without a shell, and never let its failure escape as an exception.

    ⛔ **Neither the command line nor the command's own output goes into the
    detail, and the second one is the trap.** ``icacls`` names the file it could
    not process in its error text, and on Windows that path contains the account
    name -- so forwarding stderr into a line that gets logged would publish the
    owner's username in the file most likely to be pasted into an issue. What
    survives is the exit code, which is enough to tell "not installed" from
    "refused" and carries nothing about who the owner is.
    """
    # Fixed argv, no shell, and every element is either a literal or a path this
    # process chose -- there is no user input in this command line.
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_ACL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(returncode=-1, detail=f"{argv[0]} timed out")
    except OSError as failure:
        return CommandResult(
            returncode=-1, detail=f"{argv[0]} could not be run: {type(failure).__name__}"
        )

    return CommandResult(
        returncode=completed.returncode, detail=f"{argv[0]} exit {completed.returncode}"
    )
