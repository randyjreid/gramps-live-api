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

from pathlib import Path

from gramps_live_api.host import httpd, log, paths, service
from tests.fixtures.host import (
    AngryDatabase,
    DummyDatabase,
    FakeDatabase,
    FakeDbState,
    ask,
    running_host,
)

A_TREE = "an-invented-tree"
"""Invented, like every fixture here. CONTRIBUTING's fixture rule."""


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
