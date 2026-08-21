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
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gramps_live_api.host import accessor, httpd, service, tokens


class FakePerson:
    """A Gramps ``Person`` as far as the person probe is concerned: an ID and a flag.

    ⚠️ **The flag is reachable ONLY through ``get_privacy()``, and that is what
    makes "derived from the returned object" checkable.** There is no ``private``
    attribute to read and no second place the answer lives, so an accessor that
    answered from an index -- or from anything but the object it fetched -- could
    not produce a ``True`` here, and the private case would fail rather than pass
    for the wrong reason.
    """

    def __init__(self, gramps_id: str, *, private: bool = False) -> None:
        self.gramps_id = gramps_id
        self._private = private
        self.privacy_reads = 0
        """How many times the flag was read off this object. A test reads it."""

    def get_privacy(self) -> bool:
        self.privacy_reads += 1
        return self._private


class FakeDatabase:
    """The three methods ``accessor.tree_status`` calls, and the one the person probe calls.

    ⚠️ **``person_lookups`` is what makes "it materialised the person" observable
    from outside.** A2 exists to time a real single-person read, and a probe that
    answered from an index would measure nothing -- so a test asserts the
    database was actually asked, by name, rather than trusting the payload.
    """

    def __init__(self, name: str, people: int, *, persons: Iterable[FakePerson] = ()) -> None:
        self._name = name
        self._people = people
        self._persons = {person.gramps_id: person for person in persons}
        self.person_lookups: list[str] = []

    def is_open(self) -> bool:
        return True

    def get_dbname(self) -> str:
        return self._name

    def get_number_of_people(self) -> int:
        return self._people

    def get_person_from_gramps_id(self, gramps_id: str) -> FakePerson | None:
        self.person_lookups.append(gramps_id)
        return self._persons.get(gramps_id)


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


class AngryPersonDatabase:
    """Open, and then fails the PERSON read, the way a cross-thread call would.

    Beside ``AngryDatabase`` rather than inside it. That fake asserts the tree
    NAME is read first and says so in its ``get_number_of_people``; teaching it a
    fourth method would edit an existing assertion instead of adding one.
    """

    def is_open(self) -> bool:
        return True

    def get_person_from_gramps_id(self, gramps_id: str) -> object:
        raise RuntimeError("SQLite objects created in a thread can only be used in that thread")


class _Backend:
    """Something between the database and its connection, the way Gramps' DB-API layer is."""

    def __init__(self, connection: object) -> None:
        self.connection = connection


class ConnectedDatabase(FakeDatabase):
    """A ``FakeDatabase`` with a connection-shaped object nested under it.

    ⚠️ **The attribute names here are arbitrary on purpose.** The real path into
    Gramps' DB-API backend is unknown from this repository, so the probe walks
    instance dictionaries rather than naming a path -- and a fixture that used
    the name the probe looks for would be testing our guess instead of the walk.
    """

    def __init__(self, name: str, people: int, *, connection: object) -> None:
        super().__init__(name, people)
        self.somewhere_underneath = _Backend(connection)


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
