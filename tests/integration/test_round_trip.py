"""The whole thing: a proposed document becomes records in a real Gramps tree.

⚠️ **THIS TEST RUNS ON ONE MACHINE AND SKIPS ON CI, BY NAME, AND THAT IS NOT A
GAP THAT SNUCK IN -- IT IS THE COST OF THE ROUTE, STATED.** CI is
``ubuntu-latest`` with no Gramps, no ``gi`` and no GTK, so ``DbTxn``, the plugin
registration and the read-back are unobservable there. ``pytest -rs`` names this
skip in the log, which is the most that can be done. **Green CI is not evidence
this route works.**

⛔ **PORTED, not rewritten from nothing.** R9's fourth carve out: this file was
the only automated coverage against a real Gramps database, it drove the note
flow through ``cli apply``, and the retirement moves it to the document route
rather than deleting it and porting it next. What it still is: a throwaway
database, a real ``DbTxn``, a real write, verified from a second fresh process.

⛔ **WHAT IT CANNOT DRIVE, AND WHY, BECAUSE THE HALF THAT IS MISSING IS THE HALF
A READER WOULD ASSUME.** R9 asks for a round trip through ``propose_document``
and ``approve_document``. The first runs here for real. The second **cannot**:
``approve_document`` POSTs the stored graph to a loopback host that only exists
inside a running Gramps GUI, which then opens a **modal dialog** and writes only
if a person clicks. There is no way for a test to click it, and building one
would mean designing an auto-approving path into the product -- which is the one
thing the whole design exists to forbid. So this file drives:

* ``Tools.propose_document`` -- the real one, parsing and storing the graph;
* ``proposals.claim_document`` -- the same call ``approve_document`` makes, and
  the only irreversible step in it;
* ``gramps_live_api_writer.write`` -- inside a real Gramps, on the graph read
  back off the disk, in a real ``DbTxn``.

**What is NOT covered here is the loopback hop, the backup, the journal and the
dialog.** Those are the host's, and they are covered against fakes in
``tests/integration/test_host_over_loopback.py``. Saying so is the point: a
reader who takes this for the whole route would believe the approval surface is
tested, and it is not testable.

⚠️ **The tool plugin below is a FIXTURE, invented here.** Gramps runs
third-party code against an open tree through one sanctioned door, the CLI tool
plugin, and the retirement deletes the only registration this project shipped
for it. Rather than keeping a product plugin nothing uses, the door is built in
the throwaway Gramps home, beside the real writer, and it does nothing but call
the writer and print what it saw.

**Nothing real is touched.** ``GRAMPSHOME`` redirects Gramps' entire user
directory into ``tmp_path``, so the tree, the plugin registry and the
configuration are all throwaway: the owner's trees are not on the same
filesystem path, not in the same tree list, and never opened.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gramps_live_api import config
from gramps_live_api.core import apply, proposals
from tests.fixtures.synthetic import empty_tree_document
from tests.fixtures.workflow import REPOSITORY_ROOT

MARKER = "GRAMPS-LIVE-API-ROUND-TRIP"
"""What the fixture tool prints, and the only thing this file reads from a run.

⚠️ **The exit code is not a signal, and that is measured rather than assumed.**
``gramps/gui/plug/tool.py`` wraps the whole tool invocation in a bare ``except``
that logs and returns, so a crash inside our code exits normally; and the
launcher refuses a second instance by exiting zero. A single line on stdout whose
ABSENCE is failure is the one reading correct in every case.
"""

MODE = "GLAPI_ROUND_TRIP_MODE"
PAYLOAD = "GLAPI_ROUND_TRIP_PAYLOAD"

A_PERSON = "p1"
A_SOURCE = "s1"
A_CITATION = "c1"

GIVEN = "Quorvane"
SURNAME = "Ashenmoor"
"""Invented, from the register the other fixtures use. CONTRIBUTING's rule."""

NOTE_TEXT = "Ashenmoor deed, entered by the round trip."
NOTE_TYPE = "research"
"""⛔ A CALLER CHOSEN note type, and it is the reason R9 has a precondition.

The one capability the note flow had that the document route lacked was a typed
note. Note types moved to the document route first, and this asserts the moved
capability against a real ``NoteType`` -- a ``research`` note, not the
``transcript`` every note used to be filed as.
"""

DOCUMENT: dict[str, Any] = {
    "people": [{"id": A_PERSON, "given": GIVEN, "surname": SURNAME, "gender": "female"}],
    "source": {"id": A_SOURCE, "title": "Larkspur Row parish register", "author": "Invented"},
    "citations": [
        {"id": A_CITATION, "source": A_SOURCE, "page": "folio 12", "attach_to": [A_PERSON]}
    ],
    "notes": [{"text": NOTE_TEXT, "type": NOTE_TYPE, "attach_to": [A_PERSON]}],
}
"""One document's findings, creating everything and attaching to nothing existing.

⚠️ **No ``gramps_id`` anywhere, deliberately.** ``propose_document`` checks every
supplied Gramps ID against the OPEN tree over the loopback host, and there is no
host here -- ``document.requested`` is what decides whether it asks. A graph that
attaches to an existing record is therefore out of this file's reach, and that is
recorded rather than worked around.
"""


def runtime_or_skip() -> str:
    found = os.environ.get(config.ENV_RUNTIME) or config.discover_runtime(os.environ)
    if found is None or not os.path.isfile(found):
        pytest.skip(
            "no Gramps runtime on this machine, so the write itself cannot be "
            "observed here -- this is EXPECTED on CI and is the stated cost of "
            "the route, not a gap: green CI is not evidence this route works. "
            "What is still covered is everything up to the Gramps boundary, by "
            "the seam twins "
            "test_the_first_claim_returns_the_record"
            " and "
            "test_a_write_of_one_of_each_reports_one_of_each"
            " -- the claim that dispatches a stored proposal exactly once, and "
            "the writer's own account of what it created. Neither covers a "
            "DbTxn, and nothing can on a runner with no Gramps on it."
        )
    return found


def mcp_or_skip() -> Any:
    """``Tools``, or a skip. The MCP server is an optional extra.

    ⚠️ **Imported inside the function rather than at module scope**, so this file
    stays collectable where the extra is absent. ``find_spec`` rather than
    ``importorskip`` for ``test_mcp_server.py``'s reason: the second would
    swallow an ImportError raised by our own module and report a skip.
    """
    if importlib.util.find_spec("mcp") is None:  # pragma: no cover - installed in dev
        pytest.skip(
            "the MCP server is an optional extra and it is not installed, so "
            "propose_document cannot be reached at all -- there is nothing to cover "
            "here. CI's mcp leg installs '.[mcp]'.",
        )
    from gramps_live_api_mcp.server import Tools

    return Tools


def gramps(runtime: str, environ: dict[str, str], *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [runtime, *arguments],
        env=environ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


TOOL_REGISTRATION = '''\
"""A CLI tool door into a THROWAWAY Gramps, built by the round trip test."""

from gramps.gen.plug._pluginreg import STABLE, TOOL, TOOL_MODE_CLI, TOOL_UTILS, register
from gramps.version import VERSION_TUPLE

register(
    TOOL,
    id="glapi_round_trip",
    name="gramps-live-api: round trip fixture",
    description="Calls the document writer against an open throwaway tree.",
    version="0.0.0",
    gramps_target_version=f"{VERSION_TUPLE[0]}.{VERSION_TUPLE[1]}",
    status=STABLE,
    fname="glapi_round_trip.py",
    authors=["randyjreid"],
    authors_email=[],
    category=TOOL_UTILS,
    toolclass="RoundTripTool",
    optionclass="RoundTripToolOptions",
    tool_modes=[TOOL_MODE_CLI],
)
'''

TOOL_MODULE = '''\
"""Call the real writer against the open tree, and print one line about it.

⛔ **Nothing is decided here.** The blessing is ``gramps_live_api_writer``'s, the
write is ``gramps_live_api_writer.write``, and the graph comes off the disk. This
is the door and the reporting, which is what cannot be covered anywhere else.

Everything arrives through the ENVIRONMENT. Gramps parses its ``-p`` options by
splitting on commas and then on equals signs, with no quoting, so a payload
carrying either would silently discard the whole string.
"""

import json
import os
import sys
import traceback

from gramps.gui.plug import tool

MARKER = "GRAMPS-LIVE-API-ROUND-TRIP"


def _writer():
    """The real writer, imported by name from beside this file."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import gramps_live_api_writer

    return gramps_live_api_writer


class RoundTripTool(tool.Tool):
    """The work happens in ``__init__``, which is where ``cli_tool`` calls us."""

    def __init__(self, dbstate, user, options_class, name, callback=None):
        tool.Tool.__init__(self, dbstate, options_class, name)
        try:
            payload = self._decide(dbstate)
        except Exception as failure:
            traceback.print_exc()
            payload = {"ok": False, "error": "%s: %s" % (type(failure).__name__, failure)}
        try:
            print(MARKER + " " + json.dumps(payload), flush=True)
        except Exception:
            traceback.print_exc()

    def _decide(self, dbstate):
        writer = _writer()
        database = dbstate.db
        mode = os.environ.get("GLAPI_ROUND_TRIP_MODE")
        tree_dir = database.get_save_path()

        if mode == "blessing":
            blessed, message = writer.blessing(tree_dir)
            return {"ok": True, "blessed": blessed, "message": message}

        if mode == "read":
            wanted = json.loads(os.environ["GLAPI_ROUND_TRIP_PAYLOAD"])
            people = database.get_number_of_people()
            person = database.get_person_from_gramps_id(wanted["person"])
            if person is None:
                return {"ok": True, "found": False, "people": people}
            name = person.get_primary_name()
            notes = []
            for handle in person.get_note_list():
                note = database.get_note_from_handle(handle)
                notes.append({"text": note.get(), "type": str(note.get_type().xml_str())})
            citations = []
            for handle in person.get_citation_list():
                citation = database.get_citation_from_handle(handle)
                source = database.get_source_from_handle(citation.get_reference_handle())
                citations.append({"page": citation.get_page(), "source": source.get_title()})
            return {
                "ok": True,
                "found": True,
                "given": name.get_first_name(),
                "surname": name.get_surname(),
                "notes": notes,
                "citations": citations,
                "people": people,
            }

        blessed, message = writer.blessing(tree_dir)
        if not blessed:
            return {"ok": False, "error": message}
        graph = json.loads(os.environ["GLAPI_ROUND_TRIP_PAYLOAD"])
        return {"ok": True, "written": writer.write(dbstate, graph)}


class RoundTripToolOptions(tool.ToolOptions):
    """No options. Everything this tool needs arrives in the environment."""

    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
        self.options_dict = {}
        self.options_help = {}
'''


def a_throwaway_tree(tmp_path: Path, runtime: str) -> tuple[Path, dict[str, str]]:
    """A Gramps home, an empty tree, the real writer, and the fixture door.

    Setup, not the subject: it runs Gramps directly rather than through anything
    of ours, so a failure here reads as "the fixture could not be built" rather
    than as a failing assertion about the tool.

    ⚠️ **The tree is EMPTY**, where the note flow's version imported one invented
    person. The document creates everybody it names, so a seed would only be
    something else to tell apart in the read-back.
    """
    home = tmp_path / "gramps-home"
    home.mkdir()
    environ = dict(os.environ)
    environ["GRAMPSHOME"] = str(home)

    seed = tmp_path / "seed.gramps"
    seed.write_text(empty_tree_document(), encoding="utf-8")
    created = gramps(runtime, environ, "-C", "DocumentRoundTripThrowaway", "-i", str(seed))

    trees = [path.parent for path in (home / "gramps" / "grampsdb").glob("*/name.txt")]
    assert trees, f"Gramps created no tree: {created.stdout}\n{created.stderr}"
    tree = trees[0]
    (tree / apply.SENTINEL_NAME).write_text("", encoding="utf-8")

    # The version directory is whatever Gramps just made, so the install needs
    # no knowledge of the version -- which is the same reason the host plugin
    # derives gramps_target_version rather than pinning it.
    version_directories = sorted((home / "gramps").glob("gramps*"))
    assert version_directories, f"Gramps made no user directory under {home}"
    plugins = version_directories[0] / "plugins" / "gramps-live-api"
    plugins.mkdir(parents=True)
    # ⛔ The REAL writer, copied rather than stubbed. It is the subject.
    shutil.copy(
        REPOSITORY_ROOT / "gramps_plugin" / "gramps_live_api_writer.py",
        plugins / "gramps_live_api_writer.py",
    )
    (plugins / "glapi_round_trip.gpr.py").write_text(TOOL_REGISTRATION, encoding="utf-8")
    (plugins / "glapi_round_trip.py").write_text(TOOL_MODULE, encoding="utf-8")

    environ[config.ENV_COPY] = str(tree)
    environ[config.ENV_RUNTIME] = runtime
    return tree, environ


def in_gramps(
    runtime: str, environ: dict[str, str], tree: Path, mode: str, payload: object = None
) -> dict[str, Any]:
    """Run the fixture tool against ``tree`` and return what its marker carried."""
    child = dict(environ)
    child[MODE] = mode
    if payload is not None:
        child[PAYLOAD] = json.dumps(payload)
    completed = gramps(runtime, child, "-O", str(tree), "-a", "tool", "-p", "name=glapi_round_trip")
    lines = [line for line in completed.stdout.splitlines() if line.startswith(MARKER)]
    assert len(lines) == 1, (
        f"the run printed {len(lines)} {MARKER} lines, so it did not complete -- the "
        f"exit code says nothing here.\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}"
    )
    return dict(json.loads(lines[0][len(MARKER) :]))


def in_process(tmp_path: Path, environ: dict[str, str]) -> dict[str, str]:
    """``environ`` with the CONFIGURATION DIRECTORY redirected into ``tmp_path``.

    ⛔ **The owner's own ``config.json`` must not reach this test**, and it did:
    ``config.load`` resolves the user configuration directory, so a run on the
    machine this route targets read the real file -- and refused, correctly,
    because that file still carries the retired ``export_path``. A test that
    depends on what somebody has configured is a test that answers a different
    question on every box.

    ⚠️ **Only the in-process half is redirected.** ``GRAMPSHOME`` already puts
    Gramps' whole user directory under ``tmp_path``, and moving ``APPDATA`` out
    from under a Gramps subprocess on Windows is a bigger change than this needs.
    """
    settings = dict(environ)
    settings["APPDATA"] = str(tmp_path / "settings")
    settings["XDG_CONFIG_HOME"] = str(tmp_path / "settings")
    settings["HOME"] = str(tmp_path / "settings")
    return settings


def proposed(tmp_path: Path, environ: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """``propose_document``, for real, and the graph it stored, off the disk.

    ⭐ **The graph is read back the way ``approve_document`` reads it**, through
    ``proposals.claim_document`` -- the same call, on the same path, with the
    same id rule. What is skipped is the loopback POST that would hand it to a
    dialog, because there is no Gramps holding one open.
    """
    tools = mcp_or_skip()(in_process(tmp_path, environ), session="roundtripsession")
    reply = tools.propose_document(DOCUMENT)
    proposal_id = str(reply["proposal_id"])

    copy = apply.authorise(environ[config.ENV_COPY])
    directory = os.path.join(proposals.store_directory(copy.tree_dir), "documents")
    record = proposals.claim_document(
        os.path.join(directory, proposal_id + ".json"),
        os.path.join(directory, proposal_id + ".claimed.json"),
        proposal_id,
    )
    return proposal_id, dict(record["graph"])


def test_a_proposed_document_becomes_records_on_a_person(tmp_path: Path) -> None:
    """The route, run by a machine. The owner then runs the dialog by hand.

    Everything below ``propose_document`` is real: a real Gramps process, a real
    ``DbTxn``, real records, and a second real process that goes looking for
    them. The only thing invented is the tree.
    """
    runtime = runtime_or_skip()
    tree, environ = a_throwaway_tree(tmp_path, runtime)
    _, graph = proposed(tmp_path, environ)

    written = in_gramps(runtime, environ, tree, "write", graph)
    assert written["ok"], written.get("error")
    created = written["written"]["created"]
    assert len(created["people"]) == 1, f"one person was proposed; got {created}"
    assert len(created["notes"]) == 1 and len(created["citations"]) == 1, created
    assert len(created["sources"]) == 1, created

    # ⛔ A SECOND, FRESH PROCESS, and that is what makes this evidence rather
    # than a restatement: the assertion crosses the database file instead of a
    # live object graph. "We wrote it" and "it is there" are different claims.
    seen = in_gramps(runtime, environ, tree, "read", {"person": created["people"][0]})
    assert seen["found"], f"the person the write reported is not in the tree: {seen}"
    assert (seen["given"], seen["surname"]) == (GIVEN, SURNAME)
    assert seen["people"] == 1, f"the throwaway tree holds somebody else too: {seen}"
    assert [note["text"] for note in seen["notes"]] == [NOTE_TEXT], (
        f"the note is not on the person a fresh process reads: {seen['notes']}"
    )
    # ⛔ The note TYPE, which is the capability R9 made a precondition of the
    # retirement. A note filed as the default would pass every other assertion
    # here, which is the failure this one exists to catch.
    assert seen["notes"][0]["type"].lower() == NOTE_TYPE, (
        f"the note was not filed under the type the document asked for: {seen['notes']}"
    )
    assert [citation["page"] for citation in seen["citations"]] == ["folio 12"], seen["citations"]


def test_a_document_proposal_cannot_be_claimed_twice(tmp_path: Path) -> None:
    """One claimed proposal produces at most one write, against a real store.

    ⚠️ **The same property ``tests/unit/test_document_claim.py`` asserts on
    ``tmp_path``**, and it is here because this is the only place the store sits
    inside a tree Gramps itself created. The claim is the irreversible step in
    ``approve_document``; a second one that succeeded would write the document
    twice.
    """
    runtime = runtime_or_skip()
    _, environ = a_throwaway_tree(tmp_path, runtime)
    proposal_id, _ = proposed(tmp_path, environ)

    copy = apply.authorise(environ[config.ENV_COPY])
    directory = os.path.join(proposals.store_directory(copy.tree_dir), "documents")

    with pytest.raises(proposals.ProposalError) as refusal:
        proposals.claim_document(
            os.path.join(directory, proposal_id + ".json"),
            os.path.join(directory, proposal_id + ".claimed.json"),
            proposal_id,
        )

    assert "already been dispatched" in str(refusal.value)


def test_the_live_tree_refuses_the_write_it_was_never_blessed_for(tmp_path: Path) -> None:
    """The rail, against a real Gramps holding a real database.

    ⚠️ **The refusal comes from INSIDE Gramps**, not from the front end: the
    sentinel is removed after the proposal is stored, so anything that decided on
    the configured path would still say yes. What refuses is the writer's own
    ``blessing`` against ``db.get_save_path()`` -- the database Gramps has
    already opened -- which is the load-bearing one.
    """
    runtime = runtime_or_skip()
    tree, environ = a_throwaway_tree(tmp_path, runtime)
    _, graph = proposed(tmp_path, environ)
    (tree / apply.SENTINEL_NAME).unlink()

    refused = in_gramps(runtime, environ, tree, "write", graph)

    assert refused["ok"] is False
    assert apply.SENTINEL_NAME in str(refused["error"])
    seen = in_gramps(runtime, environ, tree, "read", {"person": "I0001"})
    assert seen["people"] == 0, (
        "a refused write left records behind, so the refusal happened after "
        f"something had already touched the copy: {seen}"
    )
