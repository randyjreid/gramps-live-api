"""Three MCP tools in front of the write path, and nothing else on the wire.

⚠️ **Two things an agent may not do, and they are the whole design.**

1. **It may not supply an operation.** ``propose_note`` builds the ``AddNote``
   here, validates it here, and files it in the proposal store here. What comes
   back is an id, the sentence a person will read, and a digest. ``approve``
   takes an id and a digest and **has no operation parameter**, so the agent can
   only name a stored proposal -- and name it wrongly, which every refusal in
   ``core.proposals`` is about.
2. **It may not type ``y``.** ``approve`` opens a **new console window** running
   ``python -m gramps_live_api approve <id>``. That process reads the operation
   off the disk, prints it in full, and reads a real console stdin. The agent
   owns the transcript; it does not own that window.

⭐ **And it may not LEARN what the window decided.** ``approve`` starts the
console and returns; there is no outcome in the reply, no second tool to ask,
and no file to read. The only route from that window to the transcript is the
owner typing what he saw. The layer that used to carry it drew a finding in four
consecutive review rounds -- polling, timeouts, ``still_open``, ``unknown``, a
cross-process report -- and was deleted rather than hardened, because it existed
to tell an agent something a human was watching happen.

Binding and approval are different questions and both are needed. Binding --
*is the thing written the thing that was approved?* -- is answered by the
operation never travelling through the agent. Approval -- *did a human say yes?*
-- is answered by the console. Binding alone would leave the human's yes as
something the agent asserts, which is the auto-approving path the brief forbids.

⚠️ **What this does NOT defend against.** The agent can misrepresent the
proposal in its transcript, propose repeatedly hoping for a tired ``y``, and
nothing authenticates the caller at all -- the agent host launches this as the
owner, so it is one trust domain by construction. **A human who approves without
reading the window is not protected by any of it.** See ``docs/slice2-mcp.md``.

⚠️ **The adapter stays thin, deliberately.** The reading is
``gramps_live_api.core.people``, the store is ``core.proposals``, the write is
``cli``'s console, and the rails are ``core.apply``'s. What is here is the shape
of three tools, and everything below is unit-tested with the console injected --
on a runner that has never seen Gramps or an MCP client.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, Protocol

from mcp.server import MCPServer

from gramps_live_api import config
from gramps_live_api.core import apply, people, proposals, schema

TOOL_NAMES = frozenset({"list_people", "propose_note", "approve"})
"""Exactly three, and criterion 1 asserts the server's own answer equals this."""

SERVER_NAME = "gramps-live-api"

CREATE_NEW_CONSOLE = 0x00000010
"""``subprocess.CREATE_NEW_CONSOLE``, spelled out rather than imported.

The constant exists only on Windows, so reading it off ``subprocess`` makes this
module's import depend on the platform -- and this module is imported by tests
on every platform in the matrix. Its value is part of the published Win32 API.
"""


class ToolRefusal(Exception):
    """This call is refused. Nothing has been written."""


class TargetIsPrivate(ToolRefusal):
    """The person carries Gramps' own ``priv`` flag, so they cannot be a target.

    ⚠️ **Refused BY NAME rather than reported absent, which is ruling 1's own
    wording.** Silence would leave the caller unable to tell *no such person*
    from *that person is private* -- the same defect class as a lock refusal
    that names no remedy. A test asserts the two messages differ.
    """


class TargetNotInExport(ToolRefusal):
    """The export holds no person with that Gramps ID.

    Also where a **stale export** lands: a person added to the copy since the
    export was taken is not in it, so this message is the only place that fact
    can reach the caller, and it says so. That is fail-closed and it has to be
    -- a person the export does not hold is a person whose ``priv`` flag cannot
    be read, and ruling 1 bounds this feature by that flag.
    """


class OperationNotWellFormed(ToolRefusal):
    """``schema.validate`` refuses the operation these arguments describe."""


class ConsoleUnavailable(ToolRefusal):
    """A separate console cannot be opened on this platform, so nothing runs."""


class ExportNotConfigured(ToolRefusal):
    """No export is configured, so there is nobody to look up."""


# ---------------------------------------------------------------------------
# The descriptions, generated from the frozensets
#
# ⚠️ **In a server the description is the ONLY documentation the caller ever
# sees.** Today the only way to learn that ``note_type`` is closed is to guess
# wrong and read ``NOTE_TYPE_UNKNOWN``, which is issue #64's second half. A set
# spelled out beside the frozenset goes stale the first time somebody adds a
# member, silently, so these are interpolated from the frozensets themselves and
# asserted to agree with them in both directions.
# ---------------------------------------------------------------------------

LIST_PEOPLE_DESCRIPTION = f"""\
Find people in the owner's family tree by name. Reads a Gramps XML export; \
writes nothing and opens no database.

Returns, for each person: their name, their birth year where the record gives \
one, a birth label carrying the record's own shape (a range stays a range), \
their Gramps ID and their handle. Both identifiers are needed by propose_note \
and must be passed on exactly as they come back.

A search term is required -- there is no way to list everybody -- and at most \
{people.RESULT_CAP} people are returned. The reply says how many matched, so \
narrow the term if it was capped.

People the tree marks private are not returned and are not counted.\
"""

PROPOSE_NOTE_DESCRIPTION = f"""\
Propose a note for a person. **Nothing is written by this call.**

note_type must be one of: {schema._one_of(schema.NOTE_TYPES)}

gramps_id and handle must both come from list_people, unedited: they are two \
halves of one reference and are checked against each other at the write.

The tree's schema lets a reference point at any of these nine object types: \
{schema._one_of(schema.OBJECT_TYPES)}. This server attaches a note to a \
{apply.TARGET_OBJECT_TYPE} only and refuses the other eight by name. A person \
the tree marks private is refused, with a message that says so rather than \
reporting them absent.

Returns a proposal id, the exact sentence that will be shown for approval, and \
an approval digest. It does NOT return the operation: the operation stays on \
this server, which is what makes the thing written the thing that was approved.

Then call approve. **A console window opens on the owner's own machine and he \
types y there.** Tell him that plainly: agreement in this conversation is not \
the approval, and this server cannot type in that window -- and this server will \
not learn what he typed, so you must ask him.\
"""

APPROVE_DESCRIPTION = """\
Open the approval console for one proposal. Pass the proposal id and the \
approval digest exactly as propose_note returned them.

**This opens a console window on the owner's machine and returns immediately.** \
He reads the whole note there and types y or n. Nothing this conversation says \
is the approval.

**This call cannot see what he decides, and neither can you.** It returns as \
soon as the window is open. There is nothing in the reply that says what \
happened and no way to ask for one.

So: tell him plainly that a console window has opened, ask him to approve \
there, and ask him what it said. Relay his words. **Do not say the note was \
written, declined or refused unless he has told you so** -- you have not been \
told and you cannot find out. If he has not said, say you do not know.

**Never call approve again for this id.** One proposal is consumed by one \
approve whatever he answers. To write a second note, call propose_note again -- \
which asks him a second time, and is the only way a second note can happen.

A refusal from this call means **nothing was written**. Some refusals also \
consume the proposal and say so. All of them name the remedy -- relay the \
message verbatim.\
"""
"""⚠️ **The last paragraph is deliberately not the stronger sentence.**

*A refusal means nothing was consumed* is what the rollback in
``Store.claim_then`` tempts you to write here, and it is **false** for
``ApprovalMismatch``, ``ProposalExpired``, ``ProposalCorrupt``,
``ApprovalRulesChanged`` and ``ProposalFromAnotherSession``, every one of which
consumes the proposal by design. A fix may not widen the claim it fixes, and a
test asserts that sentence is absent.
"""


def require_console(platform: str = sys.platform) -> None:
    """Refuse a platform with no separate console. **It reads nothing else.**

    ⚠️ **A separate function because it NEEDS NOTHING FROM THE CLAIM, and that
    is L2.** ``approve`` used to claim the proposal -- an irreversible rename,
    deliberately -- and only then reach the check inside ``new_console``. On a
    host where a console cannot be opened, every proposal was therefore consumed
    and orphaned as ``.pending.json``, while the refusal advised proposing
    again; proposing again reached the same place. Propose, approve, burn,
    forever. A question answerable from a string alone belongs before the
    irreversible step, not after it.

    The refusal itself is unchanged and is the design: the whole thing rests on
    a window the agent cannot write to, and running in ours would keep the shape
    of the mechanism while losing the property it exists for. This project's
    write path is Windows-only already -- ``config.discover_runtime`` says
    nothing off it -- so it costs nothing that worked before.
    """
    if platform != "win32":
        raise ConsoleUnavailable(
            f"{platform}: a separate console window cannot be opened here, and this "
            "server will not ask for approval in a window it can write to itself"
        )


def new_console(
    argv: Sequence[str],
    *,
    platform: str = sys.platform,
    popen: Callable[..., Any] = subprocess.Popen,
) -> None:
    """Start ``argv`` in a console window this process cannot type into.

    ⭐ **It returns nothing, and that is a strengthening rather than an
    omission.** The handle it used to hand back existed so the server could ask
    whether the console was still alive, which was one stage of the outcome
    layer that is now deleted. Without it this server holds **no object at all**
    that refers to that window: it can start it and nothing else, which is the
    module docstring's second property with one fewer exception to it.

    ⚠️ **The refusal is checked here TOO, not only in ``Tools.approve``.** The
    two are not redundant: this one is the guarantee that no caller anywhere
    spawns an approval window into a shared console, and the earlier one is the
    guarantee that the proposal is not burnt reaching it. Dropping this one
    would leave the property resting on a caller remembering to ask first.

    ``platform`` and ``popen`` are arguments for ``config.py``'s reason: a
    branch only its own operating system can reach is a branch CI proves
    nothing about, and the whole matrix runs on Linux.
    """
    require_console(platform)
    popen(list(argv), creationflags=CREATE_NEW_CONSOLE, close_fds=True)


def console_command(proposal_id: str) -> list[str]:
    """The argv that shows one proposal and asks. Absolute interpreter, see #60."""
    return [sys.executable, "-m", "gramps_live_api", "approve", proposal_id]


class Tools:
    """The three tools, with the console and the session injected.

    Everything the MCP layer above calls is a plain method here, so the whole
    surface is exercised without a client, a transport or an event loop.
    """

    def __init__(
        self,
        environ: Mapping[str, str],
        *,
        session: str | None = None,
        spawner: Callable[[Sequence[str]], None] = new_console,
        ttl_seconds: float = proposals.DEFAULT_TTL_SECONDS,
        platform: str = sys.platform,
    ) -> None:
        self._environ = environ
        self.session = proposals.new_session() if session is None else session
        self._spawn = spawner
        self._ttl = ttl_seconds
        self._platform = platform
        """⚠️ **Data rather than a second injected callable**, deliberately.

        ``approve`` has to answer *can a console be opened here?* before it
        claims anything, and the spawner is already injected for tests -- so a
        second callable beside it would be a second thing a test could set
        inconsistently with the first. A string is the same fact ``new_console``
        already takes, and the real spawner still checks it for itself.
        """

    # -- the tools ----------------------------------------------------------

    def list_people(self, name: str) -> dict[str, object]:
        """People whose name contains ``name``, minus the ones marked private.

        ⚠️ **Requires no blessed copy**, deliberately. It writes nothing, and a
        read-only tool that refused until the write path was configured would
        push the owner to configure the write path in order to look somebody up.
        """
        found = people.search(people.read_export(self._export()), name)
        return {
            "people": [
                {
                    "name": person.name,
                    "birth_year": person.birth_year,
                    "birth_display": person.birth_display,
                    "gramps_id": person.gramps_id,
                    "handle": person.handle,
                    "other_birth_events": person.other_birth_events,
                }
                for person in found.people
            ],
            "shown": len(found.people),
            "matched": found.matched,
            "capped": found.matched > len(found.people),
        }

    def propose_note(
        self, gramps_id: str, handle: str, note_type: str, text: str
    ) -> dict[str, object]:
        """File a note for approval and return what may be said about it.

        ⚠️ **The privacy flag is consulted HERE, not at the listing.** A handle
        can arrive from a stale export, from something somebody wrote down, or
        from a caller that never listed at all, so a private person has to be
        unreachable through this path independently of the other one.
        """
        person = people.find(people.read_export(self._export()), gramps_id)
        if person is None:
            raise TargetNotInExport(
                f"{gramps_id}: the export holds no {apply.TARGET_OBJECT_TYPE} with that "
                "Gramps ID. If this person was added to the tree after the export was "
                "taken, export it again -- until then nothing here can read their "
                "privacy flag, and this refuses rather than guess."
            )
        if person.private:
            raise TargetIsPrivate(
                f"{gramps_id}: this person is marked private in the tree, so they cannot "
                "be the target of a note from here. This is not 'no such person' -- they "
                "exist and are deliberately out of reach. Remove the privacy flag in "
                "Gramps and export again if that is what the owner wants."
            )

        operation = schema.AddNote(
            target=schema.ObjectRef(
                object_type=apply.TARGET_OBJECT_TYPE, handle=handle, gramps_id=gramps_id
            ),
            note_type=note_type,
            text=text,
        )
        result = schema.validate(operation)
        if not result.well_formed:
            raise OperationNotWellFormed(
                "; ".join(
                    f"{violation.rule.value} {violation.field_path}: {violation.message}"
                    for violation in result.violations
                )
            )

        store = self._store()
        proposal = store.mint(operation)
        return {
            "proposal_id": proposal.id,
            "sentence": proposal.full_display,
            "approval_digest": proposal.approval_digest,
            "expires_utc": (proposal.created_utc + store.ttl).isoformat(),
            "next": (
                "Show the owner this sentence and call approve with the id and the digest. "
                "A console window will open on his machine and he types y THERE. His "
                "agreement in this conversation is not the approval and cannot be."
            ),
        }

    def approve(self, proposal_id: str, approval_digest: str) -> dict[str, object]:
        """Claim the proposal and open the console. **Then return, knowing nothing.**

        ⚠️ **The claim happens before the console opens**, so by the time
        anything can crash or be retried the proposal is already consumed. That
        is #69's bounded claim held structurally rather than carefully: one
        approved proposal produces at most one write attempt, because a second
        ``approve`` meets ``ProposalNotFound``.

        ⚠️ **But the PLATFORM is asked first, and that is L2.** The claim is an
        irreversible rename and the question *can a console be opened here?*
        needs nothing from it. Asked afterwards, a host that cannot spawn one
        consumed every proposal and orphaned it as ``.pending.json``, while
        advising the agent to propose again -- into the same refusal. The
        ordering above buys a proposal that cannot be written twice; this one
        buys a proposal that is not destroyed before anybody could write it
        once, and they do not trade against each other.

        ⭐ **And the spawn is the CALLEE of the claim, which is D-1.** L2 closed
        *this host cannot spawn consoles* and left *the spawn itself failed*,
        which produces the identical burn loop -- so the question that cannot be
        asked in advance is answered inside ``claim_then``, and a claim that
        cannot be followed through is rolled back. That closes the class rather
        than the two instances.

        ⭐ **What comes back names no outcome, because there is none to name.**
        The window is open and the owner is reading it; nothing in this process
        will ever learn what he types. Three keys, frozen by test.
        """
        require_console(self._platform)
        store = self._store()
        store.claim_then(
            proposal_id,
            approval_digest,
            lambda: self._spawn(console_command(proposal_id)),
        )
        return {
            "proposal_id": proposal_id,
            "console": "opened",
            "next": (
                "A console window has opened on the owner's machine. Tell him so, ask "
                "him to approve there, and ask him what it said -- this call cannot see "
                "it and neither can you. Do not call approve again for this id."
            ),
        }

    # -- the machinery ------------------------------------------------------

    def _export(self) -> str:
        export = config.load(self._environ).export_path
        if export is None:
            raise ExportNotConfigured(
                "no export is configured -- set export_path in "
                f"{config.user_config_path(self._environ)} or {config.ENV_EXPORT}, and "
                "run `python -m gramps_live_api check`"
            )
        return export

    def _store(self) -> proposals.Store:
        """The store inside the blessed copy. **The blessing is the permission.**

        ``apply.authorise`` is the same constructor the write path uses, so a
        directory that is not a hand-blessed Gramps tree cannot receive a
        proposal file either -- there is no second, weaker check here.
        """
        settings = config.load(self._environ)
        if settings.copy_path is None:
            raise config.ConfigError(
                f"no copy is configured -- set copy_path in "
                f"{config.user_config_path(self._environ)} or {config.ENV_COPY}"
            )
        copy = apply.authorise(settings.copy_path)
        return proposals.Store(
            proposals.store_directory(copy.tree_dir),
            session=self.session,
            ttl_seconds=self._ttl,
        )


def build_server(tools: Tools) -> MCPServer:
    """The three tools, registered. **Nothing decides anything here.**

    Every body below is one call into ``Tools``, so the transport is a
    transport: a bug in it cannot cause an unapproved write, because the write
    is gated by the console rather than by anything on this wire.
    """
    server = MCPServer(name=SERVER_NAME)

    @server.tool(name="list_people", description=LIST_PEOPLE_DESCRIPTION)
    def list_people(name: str) -> dict[str, object]:
        return tools.list_people(name)

    @server.tool(name="propose_note", description=PROPOSE_NOTE_DESCRIPTION)
    def propose_note(gramps_id: str, handle: str, note_type: str, text: str) -> dict[str, object]:
        return tools.propose_note(gramps_id, handle, note_type, text)

    @server.tool(name="approve", description=APPROVE_DESCRIPTION)
    def approve(proposal_id: str, approval_digest: str) -> dict[str, object]:
        return tools.approve(proposal_id, approval_digest)

    return server


class Servable(Protocol):
    """Whatever ``serve`` runs. Injected so the transport choice is assertable.

    ``Literal["stdio"]`` rather than ``str``: the SDK's ``run`` is overloaded per
    transport, and a protocol widening it to any string would not be satisfied
    by the real server -- which is the type checker saying, correctly, that this
    server has one transport.
    """

    def run(self, transport: Literal["stdio"] = "stdio") -> None: ...


def _configured() -> Servable:
    """The real server, reading the owner's own environment.

    The session id is minted here and nowhere else: it is what binds a proposal
    to **this run** of this process, so a proposal minted before a restart is
    refused rather than approved against rules that may have moved with it.
    """
    return build_server(Tools(os.environ))


def serve(build: Callable[[], Servable] = _configured) -> None:
    """Run the server on stdio, and only on stdio.

    ⚠️ **Named rather than left to the SDK's default.** The brief says no HTTP
    endpoint, and the SDK ships -- and installs -- a whole HTTP stack this
    project uses none of. The one place that choice is made is here, and a test
    asserts the word.
    """
    build().run(transport="stdio")
