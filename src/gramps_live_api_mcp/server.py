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

import contextlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, Protocol

from mcp.server import MCPServer

from gramps_live_api import config
from gramps_live_api.core import apply, people, proposals, schema
from gramps_live_api.host import document, paths

TOOL_NAMES = frozenset(
    {
        "list_people",
        "propose_note",
        "approve",
        "propose_document",
        "approve_document",
        "find_people",
        "find_place",
        "find_source",
        "find_citation",
        "list_events",
        "find_families",
        "list_family_events",
        "list_notes",
        "list_associations",
        "list_citations",
        "find_orphans",
        "tree_totals",
        "changed_since",
    }
)
"""The whole surface, and the tests assert the server's own answer equals this.

⚠️ **Three became five when the document flow arrived**, and the number is not
the invariant. What criterion 1 is actually about survives unchanged: the surface
is asserted against what the server exposes rather than against a comment, and
⛔ **none of these tools reports what the owner decided.** ``approve_document``
answers *shown*, not *written* -- the outcome is learned by looking at Gramps."""

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

DESCRIPTION_BUDGET = 2048
"""⛔ **How much of a tool description actually reaches the model.** MEASURED.

⚠️ A description longer than this is **delivered cut, mid-sentence**, and the
model is never told anything past the cut. ``propose_document`` ran to 5618
characters and arrived at 2048 -- **63% lost**, and what fell past the cut was
every *look it up before you create it* rule. A model received the exact shape of
a graph and no instruction to look anything up, so it would duplicate a person or
an event and hit no refusal doing it, because creating is the default and is
legitimate.

⭐ **Per tool, not shared across the schema.** Established by loading
``propose_document`` alone: it was still cut at 2048, where a shared budget would
have given it the whole allowance. A second tool at 1190 characters arrived
complete. **So shortening one description is a real fix, not a proxy** -- which
was the open question, and the answer decided the shape of the repair.

⚠️ **Characters, and bytes are indistinguishable on this evidence**, because every
description is pure ASCII (5618 characters == 5618 bytes). If one ever gains a
non-ASCII character the two stop agreeing, and this constant should be re-measured
rather than trusted.

⛔ **Enforced by test, not by reading.** Judging a docstring short enough by eye is
the check class that has failed repeatedly here -- the answer comes from the
reader instead of from the thing being checked.
"""


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

gramps_id is all you need. The handle is resolved here, from the same lookup \
that reads the person's privacy flag -- so a Gramps ID from any read is enough \
to propose a note, and there is nothing to hunt for.

handle is optional, for a caller that already holds one. Supply it and it is \
used as given and still checked against the Gramps ID at the write; if you pass \
one it must come from list_people, unedited.

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

FIND_PEOPLE_DESCRIPTION = (
    "Search people in the OPEN Gramps tree by name, and get their Gramps IDs. "
    "Searches alternate name spellings as well as the primary name, and ignores "
    "accents. USE THIS BEFORE PROPOSING ANYBODY, so you attach to the person who "
    "is already there instead of creating a duplicate. A search term is required. "
    "Private people are never returned and are not counted in any total."
)

FIND_PLACE_DESCRIPTION = (
    "Search places in the OPEN tree and get their Gramps IDs. Use it before "
    "naming a place: a tree often holds several spellings of one village, and "
    "picking blind makes another. A search term is required."
)

FIND_SOURCE_DESCRIPTION = (
    "Search sources in the OPEN tree by title or author, and get their Gramps "
    "IDs. Use it before proposing a source: the same parish register should be "
    "cited across many documents, not copied per document. A term is required."
)

FIND_CITATION_DESCRIPTION = (
    "ASK THIS FIRST: has this document already been entered? Lists the citations "
    "of one source, optionally narrowed by page. If a citation already names the "
    "page you are about to enter, the document is probably already in the tree -- "
    "say so to the owner instead of proposing it again."
)

LIST_EVENTS_DESCRIPTION = (
    "The events already recorded on one person, by Gramps ID. Use it before "
    "proposing an event, so citing what is already there stops meaning "
    "duplicating it. Refused by name if that person is marked private."
)

FIND_FAMILIES_DESCRIPTION = (
    "The families one person belongs to, as spouse or as child, with their "
    "Gramps IDs. ASK THIS BEFORE PROPOSING A FAMILY: a tree holds one family per "
    "couple, and creating a second splits their children across two households. "
    "Pass the family Gramps ID as gramps_id on a families node to add to the one "
    "that already exists."
)

LIST_FAMILY_EVENTS_DESCRIPTION = (
    "The events recorded on a FAMILY rather than on a person -- a marriage is "
    "one of these. Asking a person for their events and concluding there is no "
    "marriage is how a second marriage record gets entered for a couple who "
    "already have one. Use find_families first to get the family Gramps ID. "
    "If it shows no marriage and a document says there was one, you can now "
    "propose it: put the family local id in the event's family field and it is "
    "written onto the family, so this lookup reports it afterwards."
)

LIST_NOTES_DESCRIPTION = (
    "The notes attached to one record, with their Gramps IDs, so they can be "
    "named for a manual cleanup. kind is person, place, source or family."
)

LIST_ASSOCIATIONS_DESCRIPTION = (
    "A person's recorded associations -- godparents and similar -- with the "
    "relationship as the tree spells it. READ ONLY: associations cannot be "
    "proposed. Use it to avoid proposing somebody who is already recorded."
)

LIST_CITATIONS_DESCRIPTION = (
    "What cites one record, and from which source. ASK THIS BEFORE ADDING A "
    "CITATION: a record already carrying one does not need a second copy of "
    "the same claim. It also answers the opposite question -- a record with "
    "NO citation is a fact in the tree with nothing standing behind it. kind "
    "is person, event, family, place or citation."
)

FIND_ORPHANS_DESCRIPTION = (
    "Records of one kind that nothing in the tree references. A citation "
    "attached to nothing still exists and still looks correct, and does no "
    "work -- it cites nothing. Use it to find cleanup the owner should do by "
    "hand. kind is citation, source, note, place or repository. READ ONLY: it "
    "reports, it never deletes, and deletion is the owner's."
)

TREE_TOTALS_DESCRIPTION = (
    "How many people, families, events, places, sources, citations, notes, "
    "repositories and media the open tree holds. Every other read needs a "
    "search term, so this is the only way to ask how big the tree is -- "
    "useful for confirming an import landed. Counts include private records, "
    "because an aggregate over the whole tree names nobody."
)

CHANGED_SINCE_DESCRIPTION = (
    "What changed in the tree on or after a date, one collection at a time. "
    "ASK THIS BEFORE CONCLUDING SOMETHING IS ALREADY ENTERED: the alternative "
    "is diffing a stale export by hand, which is how a record gets entered "
    "twice. since is a date like 2026-08-01; kind is people, families, "
    "events, places, sources, citations or notes. One collection per call, "
    "because a single sweep of all of them costs about three quarters of a "
    "second inside the Gramps main loop."
)

PROPOSE_DOCUMENT_DESCRIPTION = """\
One document's findings as ONE graph. Writes nothing; returns a proposal id and a
preview. Then approve_document.

*** LOOK IT UP BEFORE YOU CREATE. An id you did not look up is a duplicate you
will make. person -> find_people. place -> find_place. source -> find_source.
family -> find_families. A person's OWN events (birth, death, census) -> list_events. A
COUPLE's events (MARRIAGE, divorce) sit on the FAMILY, on neither spouse ->
find_families then list_family_events. list_events never returns one. ***

*** A MARRIAGE GOES ON THE FAMILY: give the event "family". An event with only
"people" lands on them -- wrong for a marriage. A family with gramps_id
is ADDED TO: children join it, its parents are left alone. ***

*** THE SHAPE BELOW IS EXACT. Any other key, or a top-level key that is not a
group, is REFUSED by name. "events" belongs on an event, not a person: write
events[].people, never people[].events. A note has no "id". ***

*** ONE LOCAL ID PER RECORD. Two local ids carrying one "gramps_id" are REFUSED.
A document naming one person twice -- head of household, then a relationship
column -- is ONE person, one local id. Listing one local id twice in a list is
fine. ***

A node with "gramps_id" is ATTACHED TO, never modified; its other fields are
dropped and shown as dropped -- except a family's "children", which JOIN it. On
an attached EVENT, sending "people", "family" or
"role" is REFUSED. A gramps_id NOT IN THE TREE refuses the batch;
omitting it is how you create a new record.

"source" is one object; other groups are lists. "id" is yours to invent.

 people: "id","gramps_id?","given","surname","gender"
 places: "id","gramps_id?","title"
 events: "id","gramps_id?","type","date","role","place"(1 id),"people"(ids),
         "family"(1 id),"description"(free text: occupation, relation to head)
 source: "id","gramps_id?","title","author","pubinfo"
 citations: "id","source"(1 id),"page","attach_to"(ids)
 families: "id","gramps_id?","parents"(ids),"children"(ids)
 notes: "text","attach_to"(ids)
"""

APPROVE_DOCUMENT_DESCRIPTION = (
    "Put a proposed document in front of the owner in Gramps. Loads the stored "
    "proposal -- nothing you pass here reaches the dialog except which proposal "
    "to show. Returns as soon as the dialog is up; it does NOT report what the "
    "owner decided. Gramps must be open. Ask the owner to look at Gramps."
)

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
        self, gramps_id: str, note_type: str, text: str, handle: str = ""
    ) -> dict[str, object]:
        """File a note for approval and return what may be said about it.

        ⚠️ **The privacy flag is consulted HERE, not at the listing.** A handle
        can arrive from a stale export, from something somebody wrote down, or
        from a caller that never listed at all, so a private person has to be
        unreachable through this path independently of the other one.

        ⭐ **The handle is optional because this function already knows it.**
        Issue #64: the one write verb predating the document route demanded a
        value no live read publishes, so reaching it meant going through the
        export-backed listing and carrying a handle by hand. The lookup below
        runs either way, to read the privacy flag, and the record it returns
        carries the handle -- **requiring the caller to supply what this was
        about to compute was the whole gap.**

        ⚠️ **A supplied handle is used as given, not overridden.** A caller
        holding one from elsewhere is asserting something, and gramps_id and
        handle are checked against each other at the write -- so quietly
        replacing it would discard that check rather than perform it.
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
                object_type=apply.TARGET_OBJECT_TYPE,
                handle=handle or person.handle,
                gramps_id=gramps_id,
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
        self._runtime()
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

    def _runtime(self) -> str:
        """The Gramps this host would launch. **Asked before the claim.**

        ⭐ **The one thing this change adds, and the invariant is what asks for
        it.** ``_approve`` asks the same question in the console, which is after
        the window has opened and therefore after the claim -- so on a host with
        no Gramps every ``approve`` consumed a proposal, showed a window that
        refused, and advised proposing again into the same place. A
        deterministic host precondition answered after the irreversible step is
        L2 and D-1's burn loop, whatever the precondition happens to be.

        ⚠️ **``os.path.isfile`` as well as *a runtime was named*, and that is
        ``check``'s own predicate rather than an invented one.** A configured
        ``gramps_runtime`` pointing at a path that an uninstall took away
        satisfies the first question and fails at the launch, which is the same
        loop -- and it is how the owner will actually meet this. The console
        does not ask the second question, so this is strictly the stricter of
        the two: it can refuse where the console would have opened and failed,
        never the reverse.
        """
        settings = config.load(self._environ)
        runtime = settings.runtime or config.discover_runtime(self._environ)
        if runtime is None:
            raise config.ConfigError(
                f"no {config.RUNTIME_NAME} found; set gramps_runtime in "
                f"{config.user_config_path(self._environ)} or {config.ENV_RUNTIME}, and run "
                "`python -m gramps_live_api check`. Nothing was consumed -- the same "
                "proposal can be approved once this host can launch Gramps."
            )
        if not os.path.isfile(runtime):
            raise config.ConfigError(
                f"{runtime}: gramps_runtime names a path that is not there, so no window "
                "is opened. Run `python -m gramps_live_api check`. Nothing was consumed -- "
                "the same proposal can be approved once the path is right."
            )
        return runtime

    # -- the document flow --------------------------------------------------

    def propose_document(self, graph: dict[str, object]) -> dict[str, object]:
        """Validate a document's findings and put them where approval can find them.

        ⭐ **The graph is STORED here and read back at approval time.** Nothing
        an agent says in the approve call reaches the dialog -- that is the whole
        binding, and it is what carries slice 2's guarantee across from a console
        this server held no handle on to a dialog inside Gramps.

        ⛔ **Nothing is written to the tree.** This returns a preview and an id.
        """
        parsed = document.parse(graph)

        # ⭐ Validate every gramps_id against the LIVE tree by KEYED lookup.
        # ⚠️ This used the name searches and that was wrong in both directions:
        # /find/place matches a place's NAME, so a valid P0123 did not match and
        # was reported missing, while /find/events answers the same empty result
        # for "no such person" and for "a person with no events", so a
        # nonexistent person passed. **A search is not an existence check.**
        missing = self._resolve_ids(parsed)
        if missing:
            # ⛔ The advice comes from ``document.how_to_resolve_them()`` rather
            # than being spelled again here. Two copies of one sentence is how
            # this message went stale: events became attachable and only the tool
            # description was updated.
            raise ToolRefusal(
                "these Gramps IDs are not in the open tree: "
                + ", ".join(missing)
                + ". "
                + document.how_to_resolve_them()
            )

        settings = config.load(self._environ)
        if settings.copy_path is None:
            raise config.ConfigError(
                f"no copy is configured -- set copy_path in "
                f"{config.user_config_path(self._environ)} or {config.ENV_COPY}"
            )
        copy = apply.authorise(settings.copy_path)

        directory = os.path.join(proposals.store_directory(copy.tree_dir), "documents")
        os.makedirs(directory, exist_ok=True)
        proposal_id = proposals.new_session()
        record = {
            "id": proposal_id,
            "session": self.session,
            "graph": parsed.as_dict(),
        }
        path = os.path.join(directory, proposal_id + ".json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)

        return {
            "proposal_id": proposal_id,
            "summary": document.summary(parsed),
            "preview": document.caller_preview(parsed),
        }

    def approve_document(self, proposal_id: str) -> dict[str, object]:
        """Load the STORED graph and put it in front of the owner in Gramps.

        ⚠️ **A separate verb from ``approve``, deliberately.** ``approve``
        carries the console-and-digest contract the note flow is built on; giving
        one name two meanings would put a second set of rules behind a word the
        owner already understands.

        ⚠️ **The answer is "shown", not an outcome.** The host returns 202 the
        moment the dialog is up, because holding an HTTP connection while a human
        reads would time out mid-decision. **What the owner does with the dialog
        is between him and Gramps**, and he learns the result by looking at it.
        """
        settings = config.load(self._environ)
        if settings.copy_path is None:
            raise config.ConfigError("no copy is configured")
        copy = apply.authorise(settings.copy_path)

        # ⛔ The id is CALLER-CONTROLLED and is joined into a path. Without this
        # an absolute or ``../``-shaped id let approve_document read, claim and
        # UNLINK an arbitrary reachable .json -- and dispatch it for approval if
        # it happened to hold a "graph", which is a write path opened by a file
        # this server never minted.
        #
        # ⚠️ The same rule ``proposals.Store`` already applies to its own ids.
        # It was not applied here because this store was written beside that one
        # rather than through it, which is exactly how a rail gets left off.
        if not proposals._ID.fullmatch(proposal_id):
            raise proposals.ProposalNotFound(
                f"{proposal_id!r} is not the name of a document proposal"
            )

        directory = os.path.join(proposals.store_directory(copy.tree_dir), "documents")
        path = os.path.join(directory, proposal_id + ".json")

        claimed = os.path.join(directory, proposal_id + ".claimed.json")
        record = proposals.claim_document(path, claimed, proposal_id)

        def unclaim() -> None:
            """Put it back. ⚠️ ONLY when the host never showed the dialog."""
            with contextlib.suppress(OSError):
                os.replace(claimed, path)

        # ⛔ From the stored record. The argument named WHICH proposal; it did
        # not supply any part of what the dialog will show.
        graph = record["graph"]

        # ⚠️ Host discovery is INSIDE the guarded section. It raises when Gramps
        # is closed or the port file is gone, and raising outside meant the claim
        # was consumed for ever with no dialog ever scheduled -- a proposal spent
        # on nothing.
        try:
            port, token = self._host_address()
        except ToolRefusal:
            unclaim()
            raise

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/document",
            data=json.dumps(graph).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                answer = json.loads(response.read().decode("utf-8"))
                status = response.status
        except urllib.error.HTTPError as refusal:
            # The host refused before showing anything, so the proposal is still
            # unspent and goes back.
            unclaim()
            detail = refusal.read().decode("utf-8", "replace")
            return {"shown": False, "status": refusal.code, "detail": detail}
        except OSError as failure:
            unclaim()
            return {
                "shown": False,
                "detail": f"the Gramps host is not answering -- is Gramps open? ({failure})",
            }

        if not answer.get("shown"):
            unclaim()
            return {"shown": False, "status": status}

        return {"shown": bool(answer.get("shown")), "status": status}

    # -- the live reads, served by the host from the OPEN tree -------------

    def _host(self, path: str, **query: str) -> dict[str, object]:
        """One live read through the host. **Not the export.**

        ⚠️ **The export is a snapshot and the tree is not.** Three documents in a
        row were entered that were already in the tree, and nothing in the tool
        could say so; these reads exist so that question has an answer.
        """
        port, token = self._host_address()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}?" + urllib.parse.urlencode(query),
            headers={"Authorization": "Bearer " + token},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return dict(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as refusal:
            body = refusal.read().decode("utf-8", "replace")
            detail = json.loads(body or "{}")
            raise ToolRefusal(str(detail.get("detail") or detail.get("error") or refusal)) from None
        except OSError as failure:
            raise ToolRefusal(f"the Gramps host is not answering: {failure}") from None

    def _resolve_ids(self, parsed: document.Graph) -> list[str]:
        """The Gramps IDs in ``parsed`` that the OPEN tree does not hold."""
        if not document.requested(parsed):
            return []
        answer = self._post("/resolve", parsed.as_dict())
        rows = answer.get("missing")
        return [str(x) for x in rows] if isinstance(rows, list) else []

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        """A POST to the host, answered as JSON."""
        port, token = self._host_address()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return dict(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as refusal:
            body = refusal.read().decode("utf-8", "replace")
            detail = json.loads(body or "{}")
            raise ToolRefusal(str(detail.get("detail") or detail.get("error") or refusal)) from None
        except OSError as failure:
            raise ToolRefusal(f"the Gramps host is not answering: {failure}") from None

    def _host_address(self) -> tuple[str, str]:
        """Where the host is listening, and the token it minted."""
        directory = paths.state_directory(self._environ)
        try:
            return (
                (directory / "port").read_text(encoding="utf-8").strip(),
                (directory / "token").read_text(encoding="utf-8").strip(),
            )
        except OSError:
            raise ToolRefusal(
                "the Gramps host is not running -- open Gramps on the blessed copy"
            ) from None

    def find_people(self, name: str) -> dict[str, object]:
        """People in the OPEN tree whose name contains ``name``, alternates included."""
        return self._host("/find/people", q=name)

    def find_place(self, text: str) -> dict[str, object]:
        return self._host("/find/place", q=text)

    def find_source(self, text: str) -> dict[str, object]:
        return self._host("/find/source", q=text)

    def find_citation(self, source: str, page: str = "") -> dict[str, object]:
        return self._host("/find/citation", source=source, page=page)

    def list_events(self, gramps_id: str) -> dict[str, object]:
        return self._host("/find/events", gramps_id=gramps_id)

    def find_families(self, gramps_id: str) -> dict[str, object]:
        return self._host("/find/families", gramps_id=gramps_id)

    def list_family_events(self, gramps_id: str) -> dict[str, object]:
        return self._host("/find/family-events", gramps_id=gramps_id)

    def list_notes(self, gramps_id: str, kind: str = "person") -> dict[str, object]:
        return self._host("/find/notes", gramps_id=gramps_id, kind=kind)

    def list_associations(self, gramps_id: str) -> dict[str, object]:
        return self._host("/find/associations", gramps_id=gramps_id)

    def list_citations(self, gramps_id: str, kind: str = "person") -> dict[str, object]:
        return self._host("/find/citations", gramps_id=gramps_id, kind=kind)

    def find_orphans(self, kind: str) -> dict[str, object]:
        return self._host("/find/orphans", kind=kind)

    def tree_totals(self) -> dict[str, object]:
        return self._host("/totals")

    def changed_since(self, since: str, kind: str = "people") -> dict[str, object]:
        return self._host("/find/changed", since=since, kind=kind)

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
    def propose_note(
        gramps_id: str, note_type: str, text: str, handle: str = ""
    ) -> dict[str, object]:
        return tools.propose_note(gramps_id, note_type, text, handle)

    @server.tool(name="find_people", description=FIND_PEOPLE_DESCRIPTION)
    def find_people(name: str) -> dict[str, object]:
        return tools.find_people(name)

    @server.tool(name="find_place", description=FIND_PLACE_DESCRIPTION)
    def find_place(text: str) -> dict[str, object]:
        return tools.find_place(text)

    @server.tool(name="find_source", description=FIND_SOURCE_DESCRIPTION)
    def find_source(text: str) -> dict[str, object]:
        return tools.find_source(text)

    @server.tool(name="find_citation", description=FIND_CITATION_DESCRIPTION)
    def find_citation(source: str, page: str = "") -> dict[str, object]:
        return tools.find_citation(source, page)

    @server.tool(name="list_events", description=LIST_EVENTS_DESCRIPTION)
    def list_events(gramps_id: str) -> dict[str, object]:
        return tools.list_events(gramps_id)

    @server.tool(name="find_families", description=FIND_FAMILIES_DESCRIPTION)
    def find_families(gramps_id: str) -> dict[str, object]:
        return tools.find_families(gramps_id)

    @server.tool(name="list_family_events", description=LIST_FAMILY_EVENTS_DESCRIPTION)
    def list_family_events(gramps_id: str) -> dict[str, object]:
        return tools.list_family_events(gramps_id)

    @server.tool(name="list_notes", description=LIST_NOTES_DESCRIPTION)
    def list_notes(gramps_id: str, kind: str = "person") -> dict[str, object]:
        return tools.list_notes(gramps_id, kind)

    @server.tool(name="list_associations", description=LIST_ASSOCIATIONS_DESCRIPTION)
    def list_associations(gramps_id: str) -> dict[str, object]:
        return tools.list_associations(gramps_id)

    @server.tool(name="list_citations", description=LIST_CITATIONS_DESCRIPTION)
    def list_citations(gramps_id: str, kind: str = "person") -> dict[str, object]:
        return tools.list_citations(gramps_id, kind)

    @server.tool(name="find_orphans", description=FIND_ORPHANS_DESCRIPTION)
    def find_orphans(kind: str) -> dict[str, object]:
        return tools.find_orphans(kind)

    @server.tool(name="tree_totals", description=TREE_TOTALS_DESCRIPTION)
    def tree_totals() -> dict[str, object]:
        return tools.tree_totals()

    @server.tool(name="changed_since", description=CHANGED_SINCE_DESCRIPTION)
    def changed_since(since: str, kind: str = "people") -> dict[str, object]:
        return tools.changed_since(since, kind)

    @server.tool(name="propose_document", description=PROPOSE_DOCUMENT_DESCRIPTION)
    def propose_document(graph: dict[str, object]) -> dict[str, object]:
        return tools.propose_document(graph)

    @server.tool(name="approve_document", description=APPROVE_DOCUMENT_DESCRIPTION)
    def approve_document(proposal_id: str) -> dict[str, object]:
        return tools.approve_document(proposal_id)

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
