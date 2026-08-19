"""A Gramps-shaped stand-in, and a main loop that behaves like the GTK one.

⚠️ **The point of this fixture is that the MAIN THREAD drains the queue.** The
accessor refuses any thread but that one, so a drainer running on a worker would
be testing nothing -- it would fail for the right reason and prove the wrong
thing. So the request goes out on a spawned thread, standing in for the HTTP
thread, and the queue is drained here, on the interpreter's main thread, exactly
where ``GLib.idle_add`` callbacks run inside Gramps.

Not drained, the same helper reproduces a blocked GTK loop -- which is how the
503 is tested without anything having to hang.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gramps_live_api.host import accessor, httpd, service, tokens


class FakeDatabase:
    """The three methods ``accessor.tree_status`` calls, and nothing else."""

    def __init__(self, name: str, people: int) -> None:
        self._name = name
        self._people = people

    def is_open(self) -> bool:
        return True

    def get_dbname(self) -> str:
        return self._name

    def get_number_of_people(self) -> int:
        return self._people


class DummyDatabase:
    """What Gramps leaves behind when no tree is open, and it is not merely empty.

    ⚠️ **The two readers raise on purpose.** Gramps' own ``DummyDb`` answers with
    empty values, which would let an accessor that forgot to check ``is_open``
    return a nameless tree of nobody and look correct. Raising here means the
    check is asserted rather than coincidentally satisfied.
    """

    def is_open(self) -> bool:
        return False

    def get_dbname(self) -> str:
        raise AssertionError("a closed tree was asked for its name")

    def get_number_of_people(self) -> int:
        raise AssertionError("a closed tree was asked how many people it holds")


class AngryDatabase:
    """A tree that is open and then fails to answer, the way a cross-thread call would."""

    def is_open(self) -> bool:
        return True

    def get_dbname(self) -> str:
        raise RuntimeError("SQLite objects created in a thread can only be used in that thread")

    def get_number_of_people(self) -> int:
        raise AssertionError("unreachable: the name is read first")


@dataclass
class FakeDbState:
    """Gramps' ``DbState``: an attribute holding the database, and a signal to connect to."""

    db: Any = None
    subscriptions: list[tuple[str, Callable[..., None]]] = field(default_factory=list)

    def connect(self, signal: str, handler: Callable[..., None]) -> None:
        self.subscriptions.append((signal, handler))

    def emit(self, signal: str) -> None:
        for name, handler in self.subscriptions:
            if name == signal:
                handler(self.db)


class MainLoop:
    """``GLib.idle_add`` and the drain that runs what it queued."""

    def __init__(self) -> None:
        self._queued: deque[Callable[[], bool]] = deque()

    def schedule(self, work: Callable[[], bool]) -> None:
        self._queued.append(work)

    def drain(self) -> int:
        """Run everything queued, here, on whichever thread called. Returns how many."""
        ran = 0
        while self._queued:
            self._queued.popleft()()
            ran += 1
        return ran


def no_command(argv: list[str]) -> tokens.CommandResult:
    """Stand in for ``icacls`` so the Windows layout is exercised on every platform."""
    return tokens.CommandResult(returncode=0, detail="")


@contextlib.contextmanager
def running_host(
    directory: Path,
    dbstate: FakeDbState,
    *,
    timeout: float = 5.0,
) -> Iterator[tuple[service.Host, MainLoop]]:
    """A real listener on a real loopback socket, with a fake tree behind it."""
    loop = MainLoop()
    accessor.forget()
    accessor.bind(dbstate)
    host = service.start(
        schedule=loop.schedule,
        environ={"APPDATA": str(directory)},
        platform="win32",
        timeout=timeout,
        run=no_command,
    )
    try:
        yield host, loop
    finally:
        host.stop()
        accessor.forget()


@dataclass
class Answer:
    """What came back, whether or not the status made urllib call it an error."""

    status: int
    body: dict[str, Any]
    headers: dict[str, str]


def ask(
    host: service.Host,
    loop: MainLoop,
    *,
    route: str = httpd.HEALTH_ROUTE,
    token: str | None = None,
    origin: str | None = None,
    drain: bool = True,
) -> Answer:
    """Make the request from a worker thread while the main thread runs the loop.

    ``drain=False`` is a GTK loop that is busy elsewhere: nothing scheduled ever
    runs, and the HTTP side has to answer anyway.
    """
    presented = host.token if token is None else token
    request = urllib.request.Request(f"http://{httpd.LOOPBACK}:{host.port}{route}")
    if presented:
        request.add_header("Authorization", f"Bearer {presented}")
    if origin is not None:
        request.add_header("Origin", origin)

    outcome: dict[str, Any] = {}

    def call() -> None:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                outcome["answer"] = Answer(
                    status=response.status,
                    body=json.loads(response.read().decode("utf-8")),
                    headers=dict(response.headers),
                )
        except urllib.error.HTTPError as refusal:
            outcome["answer"] = Answer(
                status=refusal.code,
                body=json.loads(refusal.read().decode("utf-8")),
                headers=dict(refusal.headers),
            )

    thread = threading.Thread(target=call, name="the-http-client")
    thread.start()
    while thread.is_alive():
        if drain:
            loop.drain()
        time.sleep(0.005)
    thread.join(timeout=30)

    assert "answer" in outcome, "the request produced no answer at all"
    return outcome["answer"]
