"""The demo, run end to end over a real socket -- with everything Gramps owns faked.

⭐ **This is the closest CI can get to the demo, and the gap is stated rather
than glossed.** What runs here is the real listener on a real loopback socket,
the real token, the real auth check, the real marshalling, and a request made
from a thread that is not the main one while the main thread drains the queue.
What is fake is Gramps: the ``dbstate``, the database behind it, and
``GLib.idle_add``.

**So a green run here proves the four demo steps against a stand-in, and proves
nothing about:**

- whether ``GLib.idle_add`` drains while a Gramps modal dialog holds a nested
  main loop (R8's first open falsifier);
- whether Gramps' real ``DbState`` answers ``is_open`` the way ``DummyDb`` is
  believed to;
- whether the plugin is reachable at all inside the frozen 3.14 interpreter.

Those are the owner's machine. ``docs/slice-a-demo.md`` says what to run there.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from gramps_live_api.host import httpd, log, paths, service
from tests.fixtures.host import (
    AngryDatabase,
    AngryPersonDatabase,
    ConnectedDatabase,
    DummyDatabase,
    FakeDatabase,
    FakeDbState,
    FakePerson,
    ask,
    running_host,
)

A_TREE = "an-invented-tree"
"""Invented, like every fixture here. CONTRIBUTING's fixture rule."""

A_PERSON = "I0042"
A_PRIVATE_PERSON = "I0043"
NOBODY_AT_ALL = "I9999"
"""Three invented Gramps IDs. **No real ID and no name anywhere in this file** --
the person route answers about an ID the caller already holds and returns no name
at all, so a fixture never needs one."""


def person_route(gramps_id: str) -> str:
    """``/person?gramps_id=<id>``, with the id escaped the way a client would."""
    return f"{httpd.PERSON_ROUTE}?{urlencode({httpd.GRAMPS_ID_PARAMETER: gramps_id})}"


def test_step_one_a_valid_token_gets_the_open_trees_name_and_person_count(
    tmp_path: Path,
) -> None:
    """Demo step 1, and the only step that returns anything at all."""
    dbstate = FakeDbState(db=FakeDatabase(A_TREE, people=17))

    with running_host(tmp_path, dbstate) as (host, loop):
        answer = ask(host, loop)

    assert answer.status == 200
    assert answer.body == {"ok": True, "tree": {"open": True, "name": A_TREE, "people": 17}}


def test_step_two_a_closed_tree_answers_cleanly_instead_of_crashing(tmp_path: Path) -> None:
    """Demo step 2. ``load_on_reg`` fires in this state, so it is the ORDINARY one.

    The stand-in raises if anything asks a closed tree for its name, so a 200
    here is evidence the closed check ran rather than evidence the reads happened
    to return nothing.
    """
    dbstate = FakeDbState(db=FakeDatabase(A_TREE, people=17))

    with running_host(tmp_path, dbstate) as (host, loop):
        assert ask(host, loop).body["tree"]["open"] is True

        dbstate.db = DummyDatabase()
        answer = ask(host, loop)

    assert answer.status == 200
    assert answer.body == {"ok": True, "tree": {"open": False}}


def test_step_three_a_wrong_token_is_refused(tmp_path: Path) -> None:
    """Demo step 3."""
    with running_host(tmp_path, FakeDbState(db=FakeDatabase(A_TREE, 1))) as (host, loop):
        wrong = ask(host, loop, token="not-the-token")
        absent = ask(host, loop, token="")

    assert wrong.status == 401
    assert wrong.body == {"ok": False, "error": httpd.UNAUTHORISED}
    assert wrong.headers.get("WWW-Authenticate") == "Bearer"
    assert absent.status == 401, "a request with no Authorization header at all was let through"


def test_step_four_an_origin_header_is_rejected_even_with_the_right_token(
    tmp_path: Path,
) -> None:
    """Demo step 4, and the ordering matters as much as the refusal.

    A valid token is presented here on purpose: this is what a page the owner has
    open in a browser would look like if it had somehow read the token file. The
    ``Origin`` rule has to shut that door before the token opens it, which is why
    the check runs first in the handler.
    """
    with running_host(tmp_path, FakeDbState(db=FakeDatabase(A_TREE, 1))) as (host, loop):
        answer = ask(host, loop, origin="https://a-page-the-owner-has-open.example")

    assert answer.status == 403
    assert answer.body == {"ok": False, "error": httpd.ORIGIN_REJECTED}


def test_an_origin_header_is_rejected_before_the_token_is_even_read(tmp_path: Path) -> None:
    """The seam twin of the step above: wrong token AND an Origin gives 403, not 401.

    The two orderings are indistinguishable when the token is right. This is the
    input that tells them apart, and it is the one that says the browser rule is
    not sitting behind the thing it exists to protect.
    """
    with running_host(tmp_path, FakeDbState(db=FakeDatabase(A_TREE, 1))) as (host, loop):
        answer = ask(host, loop, token="not-the-token", origin="https://elsewhere.example")

    assert answer.status == 403


def test_a_blocked_main_thread_becomes_a_503_and_not_a_hung_socket(tmp_path: Path) -> None:
    """R8's accepted risk 4, reproduced by simply never draining the loop."""
    dbstate = FakeDbState(db=FakeDatabase(A_TREE, 1))

    with running_host(tmp_path, dbstate, timeout=0.2) as (host, loop):
        answer = ask(host, loop, drain=False)

    assert answer.status == 503
    assert answer.body == {"ok": False, "error": httpd.MAIN_THREAD_TIMEOUT}


def test_a_database_that_raises_is_a_500_carrying_no_tree_text(tmp_path: Path) -> None:
    """A failure inside the read must not put a database message on the wire.

    SQLite's cross-thread error is the one this is modelled on, and a real one can
    quote a value out of the tree. The response says only that the read failed;
    the detail goes to the log, on the owner's own machine.
    """
    dbstate = FakeDbState(db=AngryDatabase())

    with running_host(tmp_path, dbstate) as (host, loop):
        answer = ask(host, loop)
        written = paths.log_path(host.directory).read_text(encoding="utf-8")

    assert answer.status == 500
    assert answer.body == {"ok": False, "error": httpd.TREE_READ_FAILED}
    assert "SQLite objects" not in str(answer.body)
    assert log.ERROR in written, "nothing recorded the failure where the owner could find it"


def test_an_unknown_route_is_a_404_and_needs_the_token_first(tmp_path: Path) -> None:
    """No ``/people`` in this slice, and an unauthenticated caller learns no routes."""
    with running_host(tmp_path, FakeDbState(db=FakeDatabase(A_TREE, 1))) as (host, loop):
        known = ask(host, loop, route="/people")
        anonymous = ask(host, loop, route="/people", token="not-the-token")

    assert known.status == 404
    assert known.body == {"ok": False, "error": httpd.NO_SUCH_ROUTE}
    assert anonymous.status == 401, (
        "an unauthenticated caller was told whether a route exists, which is a "
        "map of the surface handed out for free"
    )


def test_a_query_string_does_not_hide_the_route(tmp_path: Path) -> None:
    """``/health?x=1`` is ``/health``. Matching the raw path would answer 404 here."""
    with running_host(tmp_path, FakeDbState(db=FakeDatabase(A_TREE, 3))) as (host, loop):
        answer = ask(host, loop, route=f"{httpd.HEALTH_ROUTE}?anything=1")

    assert answer.status == 200


# ---------------------------------------------------------------------------
# The person probe -- A2. Ruling 1's SECOND enforcement point, and the read F3
# is about. Three states, one status code, and no tree text in any of them.
# ---------------------------------------------------------------------------


def test_a_person_who_is_not_private_is_found_and_usable(tmp_path: Path) -> None:
    """State one, and the state the F3 measurement is taken in.

    The assertion on ``person_lookups`` is the load-bearing half: it says the
    database was ASKED for the person, which is the difference between timing a
    read and timing the hop around one.
    """
    person = FakePerson(A_PERSON)
    database = FakeDatabase(A_TREE, people=2, persons=[person])

    with running_host(tmp_path, FakeDbState(db=database)) as (host, loop):
        answer = ask(host, loop, route=person_route(A_PERSON))

    assert answer.status == 200
    assert answer.body == {"ok": True, "person": {"found": True, "private": False}}
    assert database.person_lookups == [A_PERSON], (
        "the route answered without fetching the person, so it measures the hop "
        "and not the read -- which is the one defect A2 exists not to repeat"
    )
    assert person.privacy_reads >= 1, (
        "the privacy flag did not come off the fetched object, so the answer is "
        "not derived from the person at all"
    )


def test_a_private_person_is_refused_by_name_rather_than_reported_absent(
    tmp_path: Path,
) -> None:
    """State two -- ruling 1's second enforcement point, on the wire.

    ⭐ **The comparison is the test, not the payload.** *No such person* and
    *that person is private* have to be tellable apart, which is exactly what
    ``TargetIsPrivate`` refuses to collapse one level down; asserting the private
    payload alone would pass even if the two answers were identical.
    """
    database = FakeDatabase(A_TREE, people=2, persons=[FakePerson(A_PRIVATE_PERSON, private=True)])

    with running_host(tmp_path, FakeDbState(db=database)) as (host, loop):
        private = ask(host, loop, route=person_route(A_PRIVATE_PERSON))
        absent = ask(host, loop, route=person_route(NOBODY_AT_ALL))

    assert private.status == 200
    assert private.body == {"ok": True, "person": {"found": True, "private": True}}
    assert private.body != absent.body, (
        "a private person and a person who is not there gave the same answer, so "
        "the caller cannot tell 'no such person' from 'that person is private'"
    )


def test_an_id_that_names_nobody_is_an_ordinary_answer_and_not_an_error(
    tmp_path: Path,
) -> None:
    """State three. A 404 would collide with the listener's own 'no such route'."""
    database = FakeDatabase(A_TREE, people=2, persons=[FakePerson(A_PERSON)])

    with running_host(tmp_path, FakeDbState(db=database)) as (host, loop):
        answer = ask(host, loop, route=person_route(NOBODY_AT_ALL))

    assert answer.status == 200
    assert answer.body == {"ok": True, "person": {"found": False}}
    assert database.person_lookups == [NOBODY_AT_ALL]


def test_the_person_route_puts_no_tree_text_on_the_wire(tmp_path: Path) -> None:
    """⛔ The rule the whole slice is unblocked by: two booleans and nothing else.

    R3 -- the injection widening -- is still owed, so the response echoes neither
    the tree's name nor the Gramps ID it was asked about. The exact-equality
    assertions above already forbid a third key; this says the same thing about
    the values, and names the strings that would be the tempting ones to add.
    """
    database = FakeDatabase(A_TREE, people=2, persons=[FakePerson(A_PERSON)])

    with running_host(tmp_path, FakeDbState(db=database)) as (host, loop):
        answer = ask(host, loop, route=person_route(A_PERSON))

    written = json.dumps(answer.body)
    assert A_TREE not in written, "the tree's own name reached a route that may not carry it"
    assert A_PERSON not in written, "the Gramps ID was echoed back, which is free text on the wire"
    assert all(isinstance(value, bool) for value in answer.body["person"].values()), (
        "the person payload carries something that is not a boolean"
    )


def test_a_closed_tree_answers_the_person_route_without_reaching_into_it(
    tmp_path: Path,
) -> None:
    """The state ``load_on_reg`` starts in, so it is ORDINARY rather than a fault.

    ⚠️ **The closed-database fake has no person reader at all**, so a 200 here is
    evidence the ``is_open`` check ran -- exactly as its raising name reader is
    evidence for ``/health``. Had the check been missing, this would be a 500.

    ⚠️ **What this ANSWERS is a decision the brief did not make**, and it is
    reported as such: a closed tree is answered ``found: false``, on the ground
    that no Gramps ID names a person in a tree that is not open, and that
    ``/health`` is the route that says whether one is. Nothing here claims the
    caller can tell the two apart from this payload alone.
    """
    dbstate = FakeDbState(db=FakeDatabase(A_TREE, people=2, persons=[FakePerson(A_PERSON)]))

    with running_host(tmp_path, dbstate) as (host, loop):
        assert ask(host, loop, route=person_route(A_PERSON)).body["person"]["found"] is True

        dbstate.db = DummyDatabase()
        answer = ask(host, loop, route=person_route(A_PERSON))

    assert answer.status == 200
    assert answer.body == {"ok": True, "person": {"found": False}}


def test_a_person_read_that_raises_is_a_500_carrying_no_tree_text(tmp_path: Path) -> None:
    """The same rule ``/health`` holds: a database message never reaches the wire."""
    with running_host(tmp_path, FakeDbState(db=AngryPersonDatabase())) as (host, loop):
        answer = ask(host, loop, route=person_route(A_PERSON))
        written = paths.log_path(host.directory).read_text(encoding="utf-8")

    assert answer.status == 500
    assert answer.body == {"ok": False, "error": httpd.TREE_READ_FAILED}
    assert "SQLite objects" not in json.dumps(answer.body)
    assert log.ERROR in written, "nothing recorded the failure where the owner could find it"
    assert httpd.PERSON_ROUTE in written, "the log line does not say which route failed"


def test_a_blocked_main_thread_makes_the_person_route_a_503_too(tmp_path: Path) -> None:
    """R8's accepted risk 4 reaches the new route as well, and by the same mechanism."""
    database = FakeDatabase(A_TREE, people=2, persons=[FakePerson(A_PERSON)])

    with running_host(tmp_path, FakeDbState(db=database), timeout=0.2) as (host, loop):
        answer = ask(host, loop, route=person_route(A_PERSON), drain=False)

    assert answer.status == 503
    assert answer.body == {"ok": False, "error": httpd.MAIN_THREAD_TIMEOUT}


def test_the_person_route_sits_behind_the_token_and_the_origin_rule(tmp_path: Path) -> None:
    """The new route adds no auth path, which is the reason A2 is a LIGHT-tier slice.

    Both refusals are checked on the NEW route rather than inferred from
    ``/health``: the ordering is what makes a stolen token useless to a page the
    owner has open, and a route that slotted in ahead of either check would be
    the one place it did not hold.
    """
    database = FakeDatabase(A_TREE, people=2, persons=[FakePerson(A_PERSON)])

    with running_host(tmp_path, FakeDbState(db=database)) as (host, loop):
        anonymous = ask(host, loop, route=person_route(A_PERSON), token="not-the-token")
        from_a_page = ask(
            host,
            loop,
            route=person_route(A_PERSON),
            origin="https://a-page-the-owner-has-open.example",
        )

    assert anonymous.status == 401
    assert from_a_page.status == 403
    assert database.person_lookups == [], (
        "a refused request still read a person out of the tree, so the refusal "
        "happened after the work rather than before it"
    )


def test_the_person_route_with_no_gramps_id_names_nobody(tmp_path: Path) -> None:
    """An absent parameter is an ID that names nobody, not a new refusal.

    Answering *"does this ID name a person"* with 200 ``found: false`` needs no
    fourth status code and no fourth payload state -- and the lookup still runs,
    so what is measured is still a read.
    """
    database = FakeDatabase(A_TREE, people=2, persons=[FakePerson(A_PERSON)])

    with running_host(tmp_path, FakeDbState(db=database)) as (host, loop):
        answer = ask(host, loop, route=httpd.PERSON_ROUTE)

    assert answer.status == 200
    assert answer.body == {"ok": True, "person": {"found": False}}
    assert database.person_lookups == [""]


# ---------------------------------------------------------------------------
# The fenced extra: R7's connection-reachability probe. REPORT ONLY.
# ---------------------------------------------------------------------------


def test_the_connection_probe_names_a_sqlite_connection_it_can_reach(tmp_path: Path) -> None:
    """R7 asks whether a process holding the tree can reach the connection. One line, no more.

    ⛔ **Nothing is written and nothing depends on the answer.** A real
    ``sqlite3.Connection`` is used rather than a stand-in because the whole
    question is whether the object at the end of the walk *is* one.
    """
    connection = sqlite3.connect(":memory:")
    try:
        database = ConnectedDatabase(A_TREE, people=1, connection=connection)
        with running_host(tmp_path, FakeDbState(db=database)) as (host, loop):
            service.database_changed(host)
            written = paths.log_path(host.directory).read_text(encoding="utf-8")
    finally:
        connection.close()

    assert "connection probe:" in written
    assert "sqlite3.Connection=True" in written


def test_the_connection_probe_reports_finding_nothing_rather_than_raising(
    tmp_path: Path,
) -> None:
    """Finding nothing is a valid result, and A2 ships either way."""
    with running_host(tmp_path, FakeDbState(db=FakeDatabase(A_TREE, 1))) as (host, loop):
        service.database_changed(host)
        written = paths.log_path(host.directory).read_text(encoding="utf-8")

    assert "connection probe:" in written
    assert "sqlite3.Connection=True" not in written


def test_the_listener_is_on_loopback_and_writes_its_port_beside_the_token(
    tmp_path: Path,
) -> None:
    """A client finds the host by reading two files in one directory."""
    with running_host(tmp_path, FakeDbState()) as (host, loop):
        directory = host.directory

        assert host.server.server_address[0] == httpd.LOOPBACK
        assert paths.port_path(directory).read_text(encoding="utf-8") == str(host.port)
        assert paths.token_path(directory).read_text(encoding="utf-8") == host.token

    assert not paths.port_path(directory).exists(), (
        "the port file outlived the listener, so a client will be sent to a socket "
        "that is not there and read it as a host that errored"
    )


def test_the_startup_line_says_what_protection_the_token_actually_got(
    tmp_path: Path,
) -> None:
    """R8's accepted risk 2 in its ordinary, successful form."""
    with running_host(tmp_path, FakeDbState()) as (host, loop):
        written = paths.log_path(host.directory).read_text(encoding="utf-8")

    assert log.INFO in written
    assert "listening" in written
    assert "token protection=" in written


def test_a_failed_start_leaves_an_error_line_rather_than_silence(tmp_path: Path) -> None:
    """The whole reason ``host.log`` exists: ``load_on_reg`` eats the exception.

    A directory where the token file belongs makes the write fail, which stands
    in for every startup fault the owner would otherwise never see.
    """
    directory = paths.state_directory({"APPDATA": str(tmp_path)}, platform="win32")
    paths.token_path(directory).mkdir(parents=True)

    host = service.start_and_report(
        schedule=lambda work: None,
        environ={"APPDATA": str(tmp_path)},
        platform="win32",
    )

    assert host is None
    written = paths.log_path(directory).read_text(encoding="utf-8")
    assert log.ERROR in written
    assert "startup failed" in written
    assert not paths.port_path(directory).exists(), (
        "a port file survives a failed start, so a client reads 'running' from a "
        "host that is not there"
    )


def test_the_database_changed_subscription_records_what_it_saw(tmp_path: Path) -> None:
    """Scope's ``database-changed`` tracking, wired the way the plugin wires it."""
    dbstate = FakeDbState(db=DummyDatabase())

    with running_host(tmp_path, dbstate) as (host, loop):
        dbstate.connect(
            "database-changed", lambda database: service.database_changed(host, database)
        )

        dbstate.db = FakeDatabase(A_TREE, 4)
        dbstate.emit("database-changed")
        dbstate.db = DummyDatabase()
        dbstate.emit("database-changed")

        written = paths.log_path(host.directory).read_text(encoding="utf-8")

    assert "database-changed: a tree is open" in written
    assert "database-changed: no tree open" in written
