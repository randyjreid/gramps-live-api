"""The listener: one route, four refusals, and nothing that touches the database.

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
3. not ``/health`` -> **404**.
4. the main thread did not answer in time -> **503**, never a hung socket.

⛔ **``/health`` is the whole surface.** No ``/people``, no writes. The response
carries a tree's own name and a count of people and no other text at all, which
is what keeps this slice unblocked by R3.
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
from urllib.parse import urlsplit

from gramps_live_api.host import auth, log, mainthread, status

LOOPBACK = "127.0.0.1"
"""⛔ The only address this ever binds. The wildcard would put the owner's tree
on every interface of the machine, including whatever network they are on."""

EPHEMERAL_PORT = 0
"""Let the operating system choose. The chosen port is written to the ``port``
file, so nothing has to agree on a number in advance and nothing collides with
whatever else the owner is running."""

HEALTH_ROUTE = "/health"

ORIGIN_REJECTED = "origin-rejected"
UNAUTHORISED = "unauthorised"
NO_SUCH_ROUTE = "no-such-route"
MAIN_THREAD_TIMEOUT = "main-thread-timeout"
TREE_READ_FAILED = "tree-read-failed"


@dataclass(frozen=True)
class Context:
    """Everything the handler is allowed to know. Notably not the database."""

    token: str
    snapshot: Callable[[], status.TreeStatus]
    note: Callable[[str, str], None]


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
        super().__init__(address, HealthHandler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        failure = sys.exc_info()[1]
        self.context.note(log.ERROR, f"the request handler raised {failure!r}")


class HealthHandler(http.server.BaseHTTPRequestHandler):
    """One ``GET``, and refusals for everything else.

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

        if urlsplit(self.path).path != HEALTH_ROUTE:
            self._respond(HTTPStatus.NOT_FOUND, {"ok": False, "error": NO_SUCH_ROUTE})
            return

        try:
            tree = self.context.snapshot()
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
            self.context.note(log.ERROR, f"{HEALTH_ROUTE} failed: {failure!r}")
            self._respond(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": TREE_READ_FAILED},
            )
            return

        self._respond(HTTPStatus.OK, {"ok": True, "tree": _wire(tree)})

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


def build(context: Context, *, port: int = EPHEMERAL_PORT) -> HostServer:
    """A server bound to loopback, not yet serving. The caller owns the thread."""
    return HostServer((LOOPBACK, port), context)


def bound_port(server: socketserver.BaseServer) -> int:
    """The port the operating system actually gave us."""
    return int(cast("tuple[str, int]", server.server_address)[1])
