"""The live reads and the document write path, and nothing else on the wire.

⚠️ **Two things an agent may not do, and they are the whole design.**

1. **It may not supply what is written.** ``propose_document`` parses the graph
   here, checks every Gramps ID against the open tree here, and stores it here.
   What comes back is an id and a preview. ``approve_document`` takes an id and
   **has no graph parameter**, so the agent can only name a stored proposal --
   and name it wrongly, which every refusal in ``core.proposals`` is about.
2. **It may not say yes.** ``approve_document`` puts the stored graph in front of
   the owner in a modal dialog **inside Gramps**, rendered from the stored record.
   The agent owns the transcript; it does not own that dialog.

⭐ **And it may not LEARN what the dialog decided.** ``approve_document`` answers
*shown*, not *written*: it returns as soon as the dialog is up, because holding a
connection while a human reads would time out mid-decision. The only route from
that dialog to the transcript is the owner saying what he saw.

Binding and approval are different questions and both are needed. Binding --
*is the thing written the thing that was approved?* -- is answered by the graph
never travelling through the agent at approval time. Approval -- *did a human say
yes?* -- is answered by the dialog. Binding alone would leave the human's yes as
something the agent asserts, which is the auto-approving path the brief forbids.

⛔ **The note flow is gone, and with it the console.** ``propose_note``,
``approve``, ``list_people`` and the export they read are retired by R9. The
dialog inside Gramps is now the only approval surface there is: it is a weaker
trust argument than a console this process held no handle on, and that cost is
recorded rather than glossed. See ``docs/slice2-mcp.md``.

⚠️ **What this does NOT defend against.** The agent can misrepresent the proposal
in its transcript, propose repeatedly hoping for a tired click, and nothing
authenticates the caller at all -- the agent host launches this as the owner, so
it is one trust domain by construction. **A human who approves without reading
the dialog is not protected by any of it.**

⚠️ **The adapter stays thin, deliberately.** The reads go to the host over
loopback, the graph is parsed by ``host.document``, the store is
``core.proposals``, and the blessing is ``core.apply``'s. Everything below is
unit-tested on a runner that has never seen Gramps or an MCP client.
"""

from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Literal, Protocol

from mcp.server import MCPServer

from gramps_live_api import config
from gramps_live_api.core import apply, proposals
from gramps_live_api.host import document, paths

TOOL_NAMES = frozenset(
    {
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
        "tree_name",
        "changed_since",
    }
)
"""The whole surface, and the tests assert the server's own answer equals this.

⚠️ **It has been three, then five, and it is now sixteen**, and the number was
never the invariant. What criterion 1 is actually about survives the note flow's
retirement unchanged: the surface is asserted against what the server exposes
rather than against a comment, and
⛔ **none of these tools reports what the owner decided.** ``approve_document``
answers *shown*, not *written* -- the outcome is learned by looking at Gramps."""

SERVER_NAME = "gramps-live-api"

GETTING_STARTED_PROMPT = "getting_started"
"""The name of the prompt below, used by the test that asserts it is listed."""

GETTING_STARTED = """Read this before proposing anything into a Gramps tree through this server.

SAY WHICH TREE YOU ARE IN, FIRST. Call tree_name before anything else and say
the name back to the person you are working with. More than one tree on a
machine can be writable, so counts alone never identified one, and a proposal
aimed at the wrong tree is a write somebody has to undo. If the name is not the
tree you were told to work in, STOP AND ASK.

*** LOOK IT UP BEFORE YOU CREATE. An id you did not look up is a duplicate you
will make. person -> find_people. place -> find_place. source -> find_source.
family -> find_families. A person's OWN events (birth, death, census) ->
list_events. A COUPLE's events (MARRIAGE, divorce) sit on the FAMILY, on neither
spouse -> find_families then list_family_events. list_events never returns
one. ***

A CITATION IS ALWAYS CREATED, NEVER ATTACHED TO. Citations cannot carry a
gramps_id, and every citation you send is written as a new one. So before
proposing a document whose source already exists, call find_citation with the
source and the page: if that page is already cited on that source, the document
has been entered before -- do not propose it again.

AN EMPTY RESULT IS NOT PROOF OF ABSENCE. A search that returns nothing may mean
the spelling differs, or the record is marked private and deliberately out of
reach. Say what you searched for and what came back; do not conclude the person
is not there.

*** ONE LOCAL ID PER RECORD. Two local ids carrying one "gramps_id" are REFUSED.
A document naming one person twice -- head of household, then a relationship
column -- is ONE person, one local id. Listing one local id twice in a list is
fine. ***

ONE CENSUS EVENT PER PERSON. A census page lists a household; each person in it
gets their own Census event, not one event shared between them.

BEFORE PROPOSING AN EVENT, CALL list_events ON THAT PERSON. Almost everyone
already has a Birth event, and a second one is not a correction -- attach the
citation to the one that is there. Create a Birth event only for a person who
has none.

EVERY LOOKUP THAT RETURNS ROWS IS CAPPED AT 25, WITH NO PAGING. list_events,
find_people, find_source and find_citation all answer with "capped" and
"withheld", and list_events has no type filter either. IF "capped" IS TRUE, WHAT
YOU ARE LOOKING FOR MAY BE AMONG THE WITHHELD ROWS, AND AN ANSWER THAT DOES NOT
CONTAIN IT PROVES NOTHING. Narrow the search and look again, or stop and ask.
Never conclude a record is absent from a capped answer.

Two places that bites hardest. The Birth you did not see may be withheld, so a
capped list_events is not a reason to create a second one. And find_citation
matches a page by TERM rather than exactly -- a page of "1" can fill all 25 rows
with other pages while the exact one is withheld -- so a capped find_citation is
not evidence the document has not been entered before.

The approval dialog also shows what each attached person already
holds, on an "already has:" line, but that is the reader's last check and not
your first: they are reading a whole household at once, and you are looking at
one person before the proposal exists.

IF THE DOCUMENT DISAGREES WITH WHAT THE TREE RECORDS, that is two sources
disagreeing. Say so and stop. It is research, not a fix, and a second event is
not how it gets resolved.

ASK BEFORE USING AN EVENT TYPE YOU HAVE NOT SEEN IN THIS TREE. An unrecognised
type does not fail -- it silently creates a NEW CUSTOM TYPE carrying whatever
word you sent, and nothing reports that it is new. Use the types the tree
already uses, and ask about anything else.

ALWAYS SUPPLY A SOURCE. A fact with no citation is a fact nobody can check
later. The graph takes one "source" object and citations that attach to what it
supports.

A MARRIAGE GOES ON THE FAMILY: give the event "family", and give it a LOCAL id
-- the id you invented in this graph, not a Gramps ID. An event with only
"people" lands on them, which is wrong for a marriage.

DATES: write "abt 1877" for an approximate year. Do NOT write "1877?" -- "?" is
not in Gramps' vocabulary and the date will not parse.

The graph's groups are exactly: people, places, events, source, citations,
families, notes. Any other top-level key is refused by name.
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


class OperationNotWellFormed(ToolRefusal):
    """``schema.validate`` refuses the operation these arguments describe."""


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

TREE_NAME_DESCRIPTION = (
    "Which tree is open, by name, plus how many people it holds. ASK THIS "
    "FIRST, BEFORE ANY PROPOSAL, AND SAY THE NAME BACK: more than one tree on "
    "this machine can be writable, so counts alone do not tell you which one "
    "you are looking at, and a proposal aimed at the wrong tree is a write the "
    "owner has to undo. If the name is not the tree you were told to work in, "
    "STOP AND ASK. A closed tree answers open false and nothing else, which is "
    "the ordinary state before a tree is loaded, not an error."
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
 events: "id","gramps_id?","type","date","role","place"(1 id),"people"(ids or objects),
         "family"(1 id),"description"(free text: occupation, relation to head)
 source: "id","gramps_id?","title","author","pubinfo"
 citations: "id","source"(1 id),"page","attach_to"(ids)
 families: "id","gramps_id?","parents"(ids),"children"(ids)
 notes: "text","type","attach_to"(ids)
"""

APPROVE_DOCUMENT_DESCRIPTION = (
    "Put a proposed document in front of the owner in Gramps. Loads the stored "
    "proposal -- nothing you pass here reaches the dialog except which proposal "
    "to show. Returns as soon as the dialog is up; it does NOT report what the "
    "owner decided. Gramps must be open. Ask the owner to look at Gramps."
)


class Tools:
    """Every tool, with the session injected.

    Everything the MCP layer above calls is a plain method here, so the whole
    surface is exercised without a client, a transport or an event loop.

    ⚠️ **``spawner``, ``ttl_seconds`` and ``platform`` are gone with the note
    flow.** They existed so a test could inject the console this server used to
    open, and so a proposal could expire before somebody typed into it. The
    document route holds no console handle and stores its proposal for a dialog
    inside Gramps, so there is nothing left for any of the three to configure.
    """

    def __init__(self, environ: Mapping[str, str], *, session: str | None = None) -> None:
        self._environ = environ
        self.session = proposals.new_session() if session is None else session

    # -- the document flow --------------------------------------------------

    def propose_document(self, graph: dict[str, object]) -> dict[str, object]:
        """Validate a document's findings and put them where approval can find them.

        ⭐ **The graph is STORED here and read back at approval time.** Nothing
        an agent says in the approve call reaches the dialog -- that is the whole
        binding, and it is the only place the binding lives now that the console
        the note flow approved at is retired.

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

        ⚠️ **Still spelled ``approve_document`` although ``approve`` is now
        free.** The note flow's ``approve`` carried a console-and-digest contract
        this verb does not have, and reusing the shorter name would quietly put a
        different set of rules behind a word a reader may remember. It is not
        renamed back.

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

    def tree_name(self) -> dict[str, object]:
        """The tree's identity, from the route that already published it.

        ⛔ **``/health`` is NOT widened for this.** It has reported ``name``
        since the slice that introduced it; nothing could ask it through MCP,
        which made this an exposure gap rather than a missing capability. Adding
        a field to ``tree_totals`` was the other option and was refused -- that
        tool's contract is counts.
        """
        return self._host("/health")

    def changed_since(self, since: str, kind: str = "people") -> dict[str, object]:
        return self._host("/find/changed", since=since, kind=kind)


def build_server(tools: Tools) -> MCPServer:
    """Every tool, registered. **Nothing decides anything here.**

    Every body below is one call into ``Tools``, so the transport is a
    transport: a bug in it cannot cause an unapproved write, because the write
    is gated by the dialog inside Gramps rather than by anything on this wire.
    """
    server = MCPServer(name=SERVER_NAME)

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

    @server.tool(name="tree_name", description=TREE_NAME_DESCRIPTION)
    def tree_name() -> dict[str, object]:
        return tools.tree_name()

    @server.tool(name="changed_since", description=CHANGED_SINCE_DESCRIPTION)
    def changed_since(since: str, kind: str = "people") -> dict[str, object]:
        return tools.changed_since(since, kind)

    @server.tool(name="propose_document", description=PROPOSE_DOCUMENT_DESCRIPTION)
    def propose_document(graph: dict[str, object]) -> dict[str, object]:
        return tools.propose_document(graph)

    @server.tool(name="approve_document", description=APPROVE_DOCUMENT_DESCRIPTION)
    def approve_document(proposal_id: str) -> dict[str, object]:
        return tools.approve_document(proposal_id)

    @server.prompt(
        name=GETTING_STARTED_PROMPT,
        description=(
            "Read this first. What a new caller needs to avoid creating duplicates "
            "in somebody's family tree: which tree you are in, what to look up "
            "before creating anything, and what not to propose twice."
        ),
    )
    def getting_started() -> str:
        return GETTING_STARTED

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
