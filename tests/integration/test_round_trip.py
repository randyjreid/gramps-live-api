"""The whole thing: a proposed note becomes a note on a person in a real tree.

⚠️ **THIS TEST RUNS ON ONE MACHINE AND SKIPS ON CI, BY NAME, AND THAT IS NOT A
GAP THAT SNUCK IN -- IT IS THE COST OF THE ROUTE, STATED.** CI is
``ubuntu-latest`` with no Gramps, no ``gi`` and no GTK, so ``DbTxn``, the plugin
registration and the read-back are unobservable there. ``pytest -rs`` names this
skip in the log, which is the most that can be done. **Green CI is not evidence
this slice works.**

What it does when it CAN run is the demo, driven by ``cli.main``: it builds a
throwaway Gramps home on ``tmp_path``, creates a tree, imports one invented
person, blesses the copy by hand exactly as the owner does, installs the plugin,
and then runs ``apply`` -- write, then read back in a second, fresh process.

**Nothing real is touched.** ``GRAMPSHOME`` redirects Gramps' entire user
directory into ``tmp_path``, so the tree, the plugin registry and the
configuration are all throwaway: the owner's trees are not on the same
filesystem path, not in the same tree list, and never opened.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gramps_live_api import cli, config, invocation
from gramps_live_api.core import apply, schema
from tests.fixtures.synthetic import (
    SEED_PERSON_GRAMPS_ID,
    SEED_PERSON_HANDLE,
    importable_tree_document,
)
from tests.fixtures.workflow import REPOSITORY_ROOT

OPERATION = {
    "type": "add_note",
    "target": {
        "object_type": "person",
        "handle": SEED_PERSON_HANDLE,
        "gramps_id": SEED_PERSON_GRAMPS_ID,
    },
    "note_type": "research",
    "text": "Ashenmoor deed",
}


def runtime_or_skip() -> str:
    found = os.environ.get(config.ENV_RUNTIME) or config.discover_runtime(os.environ)
    if found is None or not os.path.isfile(found):
        pytest.skip(
            "no Gramps runtime on this machine, so the write itself cannot be "
            "observed here -- this is EXPECTED on CI and is the stated cost of "
            "the route, not a gap: green CI is not evidence this slice works. "
            "What is still covered is the APPROACH to the write, by the seam twins "
            "test_the_command_opens_the_copy_through_the_tool_door"
            " and "
            "test_a_refusal_and_a_success_are_told_apart"
            " -- the argv that asks Gramps to run our code, and the reading of "
            "what it answers. Neither covers the write itself, and nothing can "
            "on a runner with no Gramps on it."
        )
    return found


def gramps(runtime: str, environ: dict[str, str], *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [runtime, *arguments], env=environ, capture_output=True, text=True, check=False
    )


def a_throwaway_tree(tmp_path: Path, runtime: str) -> tuple[Path, dict[str, str]]:
    """A Gramps home, a tree with one invented person in it, and the plugin.

    Setup, not the subject: it runs Gramps directly rather than through anything
    of ours, so a failure here reads as "the fixture could not be built" rather
    than as a failing assertion about the tool.
    """
    home = tmp_path / "gramps-home"
    home.mkdir()
    environ = dict(os.environ)
    environ["GRAMPSHOME"] = str(home)

    seed = tmp_path / "seed.gramps"
    seed.write_text(importable_tree_document(), encoding="utf-8")
    created = gramps(runtime, environ, "-C", "SliceOneThrowaway", "-i", str(seed))

    trees = [path.parent for path in (home / "gramps" / "grampsdb").glob("*/name.txt")]
    assert trees, f"Gramps created no tree: {created.stdout}\n{created.stderr}"
    tree = trees[0]
    (tree / apply.SENTINEL_NAME).write_text("", encoding="utf-8")

    # The version directory is whatever Gramps just made, so the install needs
    # no knowledge of the version -- which is the same reason the plugin derives
    # gramps_target_version rather than pinning it.
    version_directories = sorted((home / "gramps").glob("gramps*"))
    assert version_directories, f"Gramps made no user directory under {home}"
    plugins = version_directories[0] / "plugins" / "gramps-live-api"
    plugins.mkdir(parents=True)
    for name in ("gramps_live_api_apply.py", "gramps_live_api_apply.gpr.py"):
        shutil.copy(REPOSITORY_ROOT / "gramps_plugin" / name, plugins / name)

    environ[config.ENV_COPY] = str(tree)
    environ[config.ENV_RUNTIME] = runtime
    return tree, environ


def test_a_proposed_note_becomes_a_note_on_a_person(tmp_path: Path) -> None:
    """The demo, run by a machine. The owner then runs it by hand on his copy.

    Everything below the ``cli.main`` call is real: a real Gramps process, a
    real ``DbTxn``, a real note, and a second real process that goes looking for
    it. The only thing invented is the tree.
    """
    runtime = runtime_or_skip()
    tree, environ = a_throwaway_tree(tmp_path, runtime)
    operation = tmp_path / "op.json"
    operation.write_text(json.dumps(OPERATION), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()

    code = cli.main(
        ["apply", str(operation)],
        environ=environ,
        stdin=io.StringIO("y\n"),
        stdout=out,
        stderr=err,
    )

    assert code == 0, f"the round trip failed\nSTDOUT\n{out.getvalue()}\nSTDERR\n{err.getvalue()}"
    assert schema.preview(schema.from_dict(OPERATION)) in out.getvalue()
    assert "read back from a fresh process: 'Ashenmoor deed'" in out.getvalue(), (
        "the second process did not find the text it was sent to find, which is "
        f"the whole difference between writing it and it being there; got {out.getvalue()}"
    )

    records = sorted((tree / apply.UNDO_DIRECTORY).glob("*.json"))
    assert len(records) == 2, f"the undo record pair is not on disk; got {records}"
    recorded = json.loads(records[0].read_text(encoding="utf-8"))
    assert recorded["approved_preview"] == schema.preview(schema.from_dict(OPERATION))
    assert recorded["operation"] == OPERATION


def test_the_live_tree_refuses_the_write_it_was_never_blessed_for(tmp_path: Path) -> None:
    """The rail, against a real Gramps holding a real database.

    ⚠️ **The refusal comes from INSIDE Gramps**, not from the front end: the
    sentinel is removed after the copy is built, and the environment still names
    it, so the advisory check would pass on a copy that has since stopped being
    one. What refuses is the check that reads ``db.get_save_path()`` on the
    database Gramps has already opened, which is the load-bearing one.
    """
    runtime = runtime_or_skip()
    tree, environ = a_throwaway_tree(tmp_path, runtime)
    (tree / apply.SENTINEL_NAME).unlink()

    completed = subprocess.run(
        invocation.command_line(runtime, str(tree)),
        env=invocation.environment(
            environ,
            mode=invocation.MODE_APPLY,
            operation=json.dumps(OPERATION),
            approved_preview=schema.preview(schema.from_dict(OPERATION)),
            approved_digest=apply.approval_digest(schema.from_dict(OPERATION)),
            source=str(REPOSITORY_ROOT / "src"),
        ),
        capture_output=True,
        text=True,
        check=False,
    )

    payload = invocation.result_of(completed.stdout)
    assert payload["ok"] is False
    assert apply.SENTINEL_NAME in str(payload["error"])
    assert not (tree / apply.UNDO_DIRECTORY).exists(), (
        "a refused write left a record behind, so the refusal happened after "
        "something had already touched the copy"
    )
