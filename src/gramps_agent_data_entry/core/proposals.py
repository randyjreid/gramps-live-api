"""Where a proposal waits, and the one way to take it exactly once.

⚠️ **The graph never leaves the server, and that is the whole binding.**
``propose_document`` parses the document's findings, checks every Gramps ID
against the open tree, and files the result here; it returns the proposal's id
and a preview. ``approve_document`` takes an id and **no graph parameter**, so an
agent can only say *which stored proposal* to act on. It cannot supply a
different one; it can only name one wrongly, and every way of naming it wrongly
has its own type and its own message below.

**Where the store lives, and why it is not a temp directory.** Inside the
blessed copy, on the precedent ``.gramps-live-api-undo`` already set: it is
derived from the one path the tool was given, it needs no second configuration
key, it travels with the copy, the blessing that authorised writing there covers
it -- and it keeps a document's findings, which are personal data, out of a temp
directory that survives a crash and that nothing in this project blessed.

⛔ **The note flow's ``Store`` is gone with R9, and with it the digest, the
session check, the TTL and the six refusals a claim ran through.** Those bound a
proposal to the console that would display it: an operation rendered into a
sentence, a digest over that operation, and a rename per state. The document
route's proposal is claimed once and shown in a dialog that renders from the
stored record, so what survives here is the naming rule, the location, and the
claim itself.

⚠️ **What this does NOT defend against**, stated here because the next reader
will otherwise take the refusals below for a security model. The store sits
inside the copy and the agent runs as the same user, so nothing here is a
cryptographic boundary: a file rewritten in place is a file this reads back. The
dialog rendering is a UI defence. What it does buy is bounded and closable:
*one claimed proposal produces at most one dialog, showing exactly what was
stored.*
"""

from __future__ import annotations

import json
import os
import re
import secrets
from contextlib import suppress
from typing import Any

PROPOSAL_DIRECTORY = ".gramps-live-api-proposals"
"""Where proposals live, inside the tree directory. See the module docstring."""

_ID_LENGTH = 8
_ID = re.compile(r"[0-9a-f]{16}")
"""What a proposal id may be, and it is checked by SHAPE.

⚠️ **The id is agent-supplied text that becomes part of a filename.** Refusing
by shape cannot be defeated by a link, a normalisation or a drive-relative
spelling, and there is no legitimate id it rejects -- ``new_session`` produces
exactly this alphabet. Resolving the path and comparing it to the directory is
the alternative, and it answers a question about the filesystem where this
answers a question about the value.
"""


class ProposalError(Exception):
    """This proposal cannot be approved. Nothing has been written."""


class ProposalNotFound(ProposalError):
    """No proposal by that name is awaiting approval.

    Also what an id that could not name one of ours gets: a value that is not
    the shape ``new_session`` produces names nothing, and saying so is the whole
    answer.
    """


def claim_document(path: str, claimed: str, proposal_id: str) -> dict[str, Any]:
    """Take a document proposal exactly once, and return what it held.

    ⭐ **It lives HERE rather than beside the store**, and that is the point of
    moving it. The document flow was written *next to* the note flow's ``Store``
    rather than *through* it, and inherited the location and none of the rails --
    the missing id validation was the same omission. It is also why the test
    covering it could not run on CI's core legs at all: reaching it meant
    importing the MCP server, and ``mcp`` is an optional extra. **The fix for a
    rail being left off is to put the code where the rails are.**

    ⛔ **``O_CREAT | O_EXCL`` is the lock, and it fails on an existing target on
    EVERY platform.** That matters for what the test proves rather than for what
    the host does -- the host is Windows-only, CI is Linux on three interpreters,
    and a fix whose test passes for a different reason than the fix works is a
    fix with no coverage.

    ⚠️ **The previous spelling was ``os.rename`` and its comment was wrong.** It
    said the rename fails because the destination exists, which is true on
    Windows and false on POSIX. What actually refused the second call on both was
    that the SOURCE had been consumed -- so the protection was real and the
    stated reason was not, and under two genuinely concurrent calls POSIX would
    have silently replaced the claim and opened two dialogs.

    Raises ``ProposalNotFound`` if there is nothing to claim and
    ``ProposalError`` if somebody already claimed it.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
    except OSError:
        if os.path.exists(claimed):
            raise ProposalError(
                f"document proposal {proposal_id!r} has already been dispatched. "
                "Propose it again if you need to show it once more."
            ) from None
        raise ProposalNotFound(f"no document proposal called {proposal_id!r}") from None

    try:
        descriptor = os.open(claimed, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ProposalError(
            f"document proposal {proposal_id!r} has already been dispatched. "
            "Propose it again if you need to show it once more."
        ) from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(body)

    # ⚠️ The original goes only AFTER the claim exists. A crash between the two
    # leaves both, and the claim is what a second call trips over -- which is the
    # safe direction: refusing a proposal twice costs a re-propose, dispatching
    # one twice writes the graph twice.
    with suppress(OSError):
        os.unlink(path)

    return dict(json.loads(body))


def store_directory(tree_dir: str) -> str:
    """Where proposals live for the copy at ``tree_dir``."""
    return os.path.join(tree_dir, PROPOSAL_DIRECTORY)


def new_session() -> str:
    """A fresh identifier, minted at server start and again per proposal.

    ⚠️ **The name is about the first use and it has two**, which is a seam rather
    than a tidy fact: the server mints one to say *this run*, and
    ``propose_document`` mints one to name a proposal. Both want the same thing --
    sixteen hex characters ``_ID`` accepts -- and one generator is why a stored
    proposal's name cannot fail the rule that reads it back.
    """
    return secrets.token_hex(_ID_LENGTH)
