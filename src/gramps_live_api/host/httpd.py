"""The listener: two routes, four refusals, and nothing that touches the database.

⚠️ **Every handler method here runs on the HTTP thread.** It reaches the tree
through ``Context.snapshot``, which is a ``Marshal.call`` -- so the database is
read on the GTK main thread and only the finished answer comes back. Nothing in
this file spells the database, and ``tests/unit/test_host_thread_boundary.py``
refuses it if anything ever does.

**The order of the checks is deliberate.**

1. ``Origin`` present -> **403**, before anything else. R8 accepts a listening
   socket on the grounds that this rule defeats DNS-rebinding and CSRF from a
   page the owner has open, and a rule that ran after authentication would let a
   browser-driven request with a stolen token through the door it exists to
   shut.
2. no token, or the wrong one -> **401**. Before the route check, so an
   unauthenticated caller learns nothing about which routes exist.
3. neither route -> **404**.
4. the main thread did not answer in time -> **503**, never a hung socket.

⛔ **Two routes are the whole surface.** No listing, no writes. ``/health``
carries a tree's own name and a count of people; ``/person`` carries two booleans
about one Gramps ID the caller already holds. **No other text at all**, which is
what keeps this slice unblocked by R3.

⭐ **``/person`` answers 200 in all three of its states**, and that is a decision
rather than laziness. *Does this ID name a person, and may I use them* is
answered **successfully** whether the answer is yes, no, or *they exist and are
private* -- and a 404 for "no such person" would collide with refusal 3 above,
which means *no such route*. Not-found and private are payload states.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from gramps_live_api.host import auth, document, log, mainthread, reads, status

LOOPBACK = "127.0.0.1"
"""⛔ The only address this ever binds. The wildcard would put the owner's tree
on every interface of the machine, including whatever network they are on."""

EPHEMERAL_PORT = 0
"""Let the operating system choose. The chosen port is written to the ``port``
file, so nothing has to agree on a number in advance and nothing collides with
whatever else the owner is running."""

HEALTH_ROUTE = "/health"

TOTALS_ROUTE = "/totals"
"""How many of each kind the tree holds. ⛔ An aggregate, never a listing --
every count is O(1) and no record is named."""

PERSON_ROUTE = "/person"
"""One person, named by the ID the caller already holds. ⛔ Not a listing."""

GRAMPS_ID_PARAMETER = "gramps_id"
"""⚠️ A query parameter and not a path segment, deliberately. ``urlsplit`` is
already here and already separates the query from the path, so the ID arrives
parsed; a path segment would mean this file grew path parsing -- surface the
route does not need and the one place a traversal-shaped input could matter."""

RESOLVE_ROUTE = "/resolve"
"""⭐ A KEYED lookup of every ``gramps_id`` a graph names, before anything else.

⚠️ **Added because validating ids through the name searches was unreliable, and
unreliable in the direction that matters.** ``/find/place`` matches on a place's
name, so a perfectly valid ``P0123`` did not match and was reported missing;
``/find/events`` answers the same empty result for *no such person* and for *a
person with no events*, so a nonexistent person passed. A search is not an
existence check, and using one as though it were made the attach-to-existing
flow fail in both directions at once."""

DOCUMENT_ROUTE = "/document"
"""⭐ The only route that writes, and it does not write on this thread.

It hands the graph to the GTK main thread and answers **202 immediately**. ⛔ It
does NOT hold the connection while a human reads a dialog: ``Marshal`` has a
five-second timeout, so waiting for an answer would 503 in the middle of the
owner deciding. **The agent therefore learns no outcome**, which is the existing
trust model rather than a limitation -- the owner finds out by looking at Gramps,
which is open in front of him."""

MAX_BODY_BYTES = document.MAX_GRAPH_BYTES

READ_ROUTES = {
    "/find/people": ("people", ("q",)),
    "/find/place": ("place", ("q",)),
    "/find/source": ("source", ("q",)),
    "/find/citation": ("citation", ("source", "page")),
    "/find/events": ("events", ("gramps_id",)),
    "/find/families": ("families", ("gramps_id",)),
    "/find/family-events": ("family_events", ("gramps_id",)),
    "/find/notes": ("notes", ("gramps_id", "kind")),
    "/find/associations": ("associations", ("gramps_id",)),
    "/find/citations": ("citations", ("gramps_id", "kind")),
    "/find/orphans": ("orphans", ("kind",)),
    "/find/changed": ("changed", ("since", "kind")),
}
"""⭐ The live reads, and every one of them carries R3's precondition P2.

⚠️ **No count here on purpose.** This said "five" while the table held nine, and
a number that once matched is the worst kind of stale because it reads as
considered. The table is the count.

⛔ **No route lists anything without a term.** ``reads.require_term`` refuses,
and the refusal is a 400 rather than an empty list, so a caller cannot mistake
*you may not* for *there are none*."""

SEARCH_TERM_REQUIRED = "search-term-required"
TARGET_IS_PRIVATE = "target-is-private"
UNKNOWN_KIND = "unknown-kind"

ORIGIN_REJECTED = "origin-rejected"
UNAUTHORISED = "unauthorised"
NO_SUCH_ROUTE = "no-such-route"
MAIN_THREAD_TIMEOUT = "main-thread-timeout"
TREE_READ_FAILED = "tree-read-failed"
GRAPH_INVALID = "graph-invalid"
TREE_NOT_BLESSED = "tree-not-blessed"
BODY_TOO_LARGE = "body-too-large"


@dataclass(frozen=True)
class Context:
    """Everything the handler is allowed to know. Notably not the database."""

    token: str
    snapshot: Callable[[], status.TreeStatus]
    person: Callable[[str], status.PersonStatus]
    """One Gramps ID in, three states out. Like ``snapshot`` it is a ``Marshal``
    call, so the fetch happens on the GTK main thread and only the two booleans
    come back -- **the handler never holds the Person object**, which is what
    keeps the boundary where the accessor's rules can see it."""

    note: Callable[[str, str], None]

    resolve: Callable[[dict[str, Any]], document.Resolution]
    """⛔ A keyed existence check, not a search. See ``RESOLVE_ROUTE``.

    ⚠️ **The display strings are deliberately NOT put on the wire here.** This
    answers *does this id exist*; who it names is the dialog's business, and a
    caller that could read the name would be a caller that could echo it back."""

    totals: Callable[[], dict[str, int]]
    """⛔ Counts only. An aggregate over the whole tree names nobody, which is
    why it is allowed to answer without a search term when nothing else is."""

    read: Callable[..., reads.Found]
    """One live read of the open tree, marshalled. ⛔ Returns plain data, never
    a Gramps object -- the handler is on the HTTP thread."""

    write_document: Callable[[dict[str, Any]], document.Blessing]
    """Blessing check, then schedule the dialog. ⛔ Fire and forget.

    Unlike ``snapshot`` and ``person`` this is **not** a ``Marshal.call`` all the
    way through: the blessing read is marshalled and waited for, because it is
    O(1) and the caller needs its answer; the dialog is merely *scheduled*, and
    nothing waits. That asymmetry is the whole reason this route can answer 202
    while a human takes as long as they like."""


class HostServer(http.server.HTTPServer):
    """An ``HTTPServer`` that carries our context and reports its own failures.

    ``handle_error`` is overridden because the base class prints a traceback to
    stderr, and the all-in-one build has no console -- so a handler that blew up
    would do it silently, which is exactly the invisibility R8's accepted risk 2
    is about.
    """

    allow_reuse_address = False
    """⚠️ **Overridden from ``HTTPServer``'s default of 1, and on Windows that
    default is not the harmless thing it is elsewhere.**

    On POSIX ``SO_REUSEADDR`` only lets a new listener take a port still in
    ``TIME_WAIT``. On Windows it lets **any** process bind a port another process
    is already listening on, with the delivery of connections undefined between
    them -- so a listener that sets it can be displaced by something that binds
    the same port afterwards.

    Nothing is given up by refusing it here: the port is chosen by the operating
    system at every startup, so there is no fixed number to re-bind and no
    restart that could collide with its own previous socket.
    """

    def __init__(self, address: tuple[str, int], context: Context) -> None:
        self.context = context
        super().__init__(address, RequestHandler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        failure = sys.exc_info()[1]
        self.context.note(log.ERROR, f"the request handler raised {failure!r}")


class RequestHandler(http.server.BaseHTTPRequestHandler):
    """One ``GET``, and refusals for everything else.

    Named for what it is rather than for the first route it carried: it was
    ``HealthHandler`` while ``/health`` was the only route, and a second route
    made that name a claim about the surface that is no longer true.

    ``protocol_version`` is left at HTTP/1.0, so every response closes its
    connection. Keep-alive on a single-threaded listener means one client holding
    a socket open blocks the next, and there is no use-derived trigger for the
    threading that would fix it.
    """

    server_version = "gramps-live-api"
    sys_version = ""
    """The interpreter version is Gramps' business, not a caller's."""

    @property
    def context(self) -> Context:
        return cast(HostServer, self.server).context

    def log_message(self, format: str, *args: Any) -> None:
        """Silence. The base class writes to stderr, and the AIO has no console.

        Nothing is lost that anyone could have read. What is gained is that a
        request line -- which a caller controls -- cannot be written anywhere by
        a caller simply asking for it.
        """

    def do_GET(self) -> None:
        if self.headers.get("Origin") is not None:
            self._respond(HTTPStatus.FORBIDDEN, {"ok": False, "error": ORIGIN_REJECTED})
            return

        presented = auth.presented_token(self.headers.get("Authorization"))
        if presented is None or not auth.token_matches(presented, self.context.token):
            self._respond(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "error": UNAUTHORISED},
                headers=[("WWW-Authenticate", "Bearer")],
            )
            return

        target = urlsplit(self.path)

        if target.path == HEALTH_ROUTE:
            self._answer(HEALTH_ROUTE, "tree", self.context.snapshot, _wire)
            return

        if target.path == TOTALS_ROUTE:
            self._answer(TOTALS_ROUTE, "totals", self.context.totals, dict)
            return

        if target.path == PERSON_ROUTE:
            gramps_id = _requested_id(target.query)
            self._answer(
                PERSON_ROUTE,
                "person",
                lambda: self.context.person(gramps_id),
                _person_wire,
            )
            return

        if target.path in READ_ROUTES:
            self._read(target)
            return

        self._respond(HTTPStatus.NOT_FOUND, {"ok": False, "error": NO_SUCH_ROUTE})

    def _read(self, target: Any) -> None:
        """One live read, with P2's three bounds answered as status codes.

        ⛔ **A missing search term is a 400, not an empty list.** *You may not
        list everybody* and *there are none* are different answers, and
        collapsing them would let a caller conclude the tree is empty.

        ⛔ **A private target is a 403 naming the refusal**, not a 404 -- ruling
        1's second enforcement point: silence would leave the caller unable to
        tell *no such person* from *that person is private*.
        """
        which, parameters = READ_ROUTES[target.path]
        query = parse_qs(target.query)
        values = [(query.get(name) or [""])[0] for name in parameters]
        try:
            found = self.context.read(which, *values)
        except reads.SearchTermRequired as refusal:
            self._respond(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": SEARCH_TERM_REQUIRED, "detail": str(refusal)},
            )
            return
        except reads.UnknownKind as refusal:
            # ⛔ 400 and not an empty 200. The caller asked about a kind of record
            # this cannot look up, and answering "no notes" would be a wrong
            # answer to a question that was never understood.
            self._respond(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": UNKNOWN_KIND, "detail": str(refusal)},
            )
            return
        except reads.TargetIsPrivate as refusal:
            self._respond(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": TARGET_IS_PRIVATE, "detail": str(refusal)},
            )
            return
        except mainthread.MainThreadTimeout:
            self._respond(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": MAIN_THREAD_TIMEOUT},
            )
            return
        except Exception as failure:
            self.context.note(log.ERROR, f"{target.path} failed: {failure!r}")
            self._respond(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": TREE_READ_FAILED},
            )
            return

        self._respond(HTTPStatus.OK, {"ok": True, **_found_wire(found)})

    def do_POST(self) -> None:
        """One route, and the same three refusals in the same order as ``do_GET``.

        ⚠️ **The order is repeated rather than shared** because it is the thing a
        reader checks: ``Origin`` before authentication, authentication before
        the route. A helper would hide it at exactly the place it must be visible.
        """
        if self.headers.get("Origin") is not None:
            self._respond(HTTPStatus.FORBIDDEN, {"ok": False, "error": ORIGIN_REJECTED})
            return

        presented = auth.presented_token(self.headers.get("Authorization"))
        if presented is None or not auth.token_matches(presented, self.context.token):
            self._respond(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "error": UNAUTHORISED},
                headers=[("WWW-Authenticate", "Bearer")],
            )
            return

        route = urlsplit(self.path).path
        if route == RESOLVE_ROUTE:
            self._resolve()
            return

        if route != DOCUMENT_ROUTE:
            self._respond(HTTPStatus.NOT_FOUND, {"ok": False, "error": NO_SUCH_ROUTE})
            return

        body = self._body()
        if body is None:
            return

        try:
            graph = document.parse(body)
        except document.GraphInvalid as refusal:
            self._respond(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": GRAPH_INVALID, "detail": str(refusal)},
            )
            return

        try:
            outcome = self.context.write_document(graph.as_dict())
        except mainthread.MainThreadTimeout:
            self._respond(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": MAIN_THREAD_TIMEOUT},
            )
            return
        except Exception as failure:
            self.context.note(log.ERROR, f"{DOCUMENT_ROUTE} failed: {failure!r}")
            self._respond(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": TREE_READ_FAILED},
            )
            return

        if not outcome.blessed:
            self._respond(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": TREE_NOT_BLESSED, "detail": outcome.message},
            )
            return

        # ⭐ 202, not 200, and not a result. The dialog is up; what the human does
        # with it is between them and Gramps.
        self._respond(HTTPStatus.ACCEPTED, {"ok": True, "shown": True})

    def _resolve(self) -> None:
        """Look up every ``gramps_id`` in a graph. ⛔ Writes nothing, shows nothing."""
        body = self._body()
        if body is None:
            return
        try:
            graph = document.parse(body)
        except document.GraphInvalid as refusal:
            self._respond(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": GRAPH_INVALID, "detail": str(refusal)},
            )
            return
        try:
            resolution = self.context.resolve(graph.as_dict())
        except mainthread.MainThreadTimeout:
            self._respond(
                HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": MAIN_THREAD_TIMEOUT}
            )
            return
        except Exception as failure:
            self.context.note(log.ERROR, f"{RESOLVE_ROUTE} failed: {failure!r}")
            self._respond(
                HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": TREE_READ_FAILED}
            )
            return

        self._respond(
            HTTPStatus.OK,
            {
                "ok": True,
                "nodes": [
                    {
                        "id": node.local_id,
                        "gramps_id": node.gramps_id,
                        "kind": node.kind,
                        "found": node.found,
                    }
                    for node in resolution.nodes
                ],
                "missing": [node.gramps_id for node in resolution.missing],
            },
        )

    def _body(self) -> bytes | None:
        """The request body, or answer for the two ways reading it fails."""
        try:
            declared = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._respond(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": GRAPH_INVALID, "detail": "Content-Length is not a number"},
            )
            return None
        if declared > MAX_BODY_BYTES:
            # ⛔ Refused on the DECLARED length, before a byte is read. Reading it
            # first to find out how big it was is the denial of service.
            self._respond(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"ok": False, "error": BODY_TOO_LARGE},
            )
            return None
        return self.rfile.read(declared) if declared > 0 else b""

    def _answer(
        self,
        route: str,
        key: str,
        work: Callable[[], Any],
        wire: Callable[[Any], dict[str, Any]],
    ) -> None:
        """Cross to the main thread for ``work``, or answer for the two ways it fails.

        ⚠️ **Shared by both routes on purpose.** The two failures below are the
        ones R8 accepts rather than route-specific handling, so a second copy of
        them is a second place for one of them to be got wrong -- and the one
        that would be got wrong is the ``Exception`` arm, whose whole job is to
        keep a database message off the wire.
        """
        try:
            answer = work()
        except mainthread.MainThreadTimeout:
            self._respond(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": MAIN_THREAD_TIMEOUT},
            )
            return
        except Exception as failure:
            # ⛔ The detail goes to the log on the owner's own machine and NOT
            # into the response: a database error message can quote a value out
            # of the tree, and this slice puts no tree text on the wire.
            self.context.note(log.ERROR, f"{route} failed: {failure!r}")
            self._respond(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": TREE_READ_FAILED},
            )
            return

        self._respond(HTTPStatus.OK, {"ok": True, key: wire(answer)})

    def _respond(
        self,
        code: HTTPStatus,
        payload: dict[str, Any],
        *,
        headers: Iterable[tuple[str, str]] = (),
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def _wire(tree: status.TreeStatus) -> dict[str, Any]:
    """The tree, as the two facts this slice is allowed to publish.

    Closed is reported as an ordinary answer with ``open: false`` and no other
    keys -- not as an error. ``load_on_reg`` fires with no tree open, so that is
    the state the host STARTS in, and a client that treated it as a fault would
    be broken every single launch.
    """
    if not tree.open:
        return {"open": False}
    return {"open": True, "name": tree.name, "people": tree.people}


def _person_wire(person: status.PersonStatus) -> dict[str, Any]:
    """The three states, as the two booleans this slice is allowed to publish.

    ⛔ **No name, no date, no Gramps ID echoed back.** The caller supplied the
    key; what comes back is only what is true of it, which is what keeps this
    route inside the same rule ``/health`` sits in and unblocked by R3.

    ⚠️ **``private`` is ABSENT rather than ``false`` when nobody was found**, in
    the same shape ``_wire`` uses for a closed tree. A ``false`` there would be a
    claim about the privacy of somebody the tree does not hold -- and ruling 1's
    second enforcement point is precisely that *no such person* and *that person
    is private* must not be one answer.
    """
    if not person.found:
        return {"found": False}
    return {"found": True, "private": person.private}


def _found_wire(found: reads.Found) -> dict[str, Any]:
    """A read's answer on the wire.

    ⛔ **``matched`` counts only what could be shown.** Private records are gone
    before counting, so *42 matched, 25 shown* can never be run backwards to
    learn that seventeen private people exist -- ruling 1's first enforcement
    point, which is about arithmetic rather than about text.
    """
    return {
        "results": [
            {"gramps_id": match.gramps_id, "display": match.display, **match.detail}
            for match in found.matches
        ],
        "shown": found.shown,
        "matched": found.matched,
        "withheld": found.withheld,
        "capped": found.capped,
    }


def _requested_id(query: str) -> str:
    """The ``gramps_id`` the caller asked about, or the empty string.

    ⚠️ **An absent parameter is an ID that names nobody, not a fourth refusal.**
    *Does this ID name a person* is answered successfully by *no* when there is
    no ID, which needs no status code and no payload state this route does not
    already have -- and the lookup still runs, so what is measured is still a
    read. **A repeated parameter takes the first value**, so one request has one
    answer whatever a client sends.
    """
    values = parse_qs(query).get(GRAMPS_ID_PARAMETER, [])
    return values[0] if values else ""


def build(context: Context, *, port: int = EPHEMERAL_PORT) -> HostServer:
    """A server bound to loopback, not yet serving. The caller owns the thread."""
    return HostServer((LOOPBACK, port), context)


def bound_port(server: socketserver.BaseServer) -> int:
    """The port the operating system actually gave us."""
    return int(cast("tuple[str, int]", server.server_address)[1])
