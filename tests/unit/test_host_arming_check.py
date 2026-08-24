"""⛔ R4's precondition 3: the arming check refuses an unblessed tree, IN THE HOST.

**R4 named this its largest gap** -- *"the arming check refuses a tree with no
sentinel, under test, in the host -- and that check does not exist in
``src/gramps_live_api/host/`` at all today."* The check now exists. This file is
the *under test* half, and it did not exist either.

⚠️ **Why it is a separate file.** ``tests/unit/test_host_plugin.py`` stubs
``accessor.blessing`` **thirteen times** with ``monkeypatch.setattr``. That is
legitimate there -- those tests are about backups, discards, journals and
re-entrancy, and they need a blessing that simply says yes. But it means the
suite for the write path never once ran the check that stands between the API and
the owner's real tree. **A suite passing for a reason unrelated to the property it
names**, in the tests for the safety check itself.

⛔ **Nothing here stubs ``blessing`` or ``blessing_of``.** What is faked is the
DATABASE -- Gramps' own object, which cannot exist on a test machine -- and only
so far as ``get_save_path`` returning a real directory. Every file the check reads
is a real file on disk, and every answer comes from the code that runs in Gramps.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from gramps_live_api.host import accessor, document
from tests.fixtures.host_sources import PLUGIN_DIRECTORY

NAME_FILE = "name.txt"
PLUGIN_FILE = PLUGIN_DIRECTORY / "gramps_live_api_host.py"


def load_the_plugin() -> ModuleType:
    """Load the plugin file as a module without putting it on anyone's import path.

    ⚠️ Spelled out here rather than imported from ``test_host_plugin`` -- one test
    module importing another couples them, and this file exists precisely because
    that one's habits (stubbing the blessing) must not reach it.
    """
    specification = importlib.util.spec_from_file_location("a_host_plugin_under_test", PLUGIN_FILE)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class _FakeDatabase:
    """Gramps' database, only as far as the arming check touches it.

    ⛔ **This is the seam.** The database is Gramps' object and cannot exist here;
    the *check* is ours and must not be faked. ``get_save_path`` is the only thing
    ``blessing()`` asks it for.
    """

    def __init__(self, save_path: str | None, open_: bool = True) -> None:
        self._save_path = save_path
        self._open = open_

    def is_open(self) -> bool:
        return self._open

    def get_save_path(self) -> str | None:
        return self._save_path


class _FakeDbState:
    def __init__(self, db: Any) -> None:
        self.db = db


def _a_gramps_tree(path: Path, *, blessed: bool) -> Path:
    """A real directory on disk, with the real files the check looks for."""
    path.mkdir(parents=True, exist_ok=True)
    (path / NAME_FILE).write_text("Invented Testing Tree", encoding="utf-8")
    if blessed:
        (path / document.SENTINEL).write_text("", encoding="utf-8")
    return path


@pytest.fixture
def bound() -> Iterator[None]:
    """Unbind the accessor after each test, so none of them leaks state."""
    yield
    accessor.forget()


# ---------------------------------------------------------------------------
# The check itself, on real files.
# ---------------------------------------------------------------------------


def test_a_blessed_tree_is_blessed(tmp_path: Path) -> None:
    tree = _a_gramps_tree(tmp_path / "copy", blessed=True)

    outcome = document.blessing_of(str(tree))

    assert outcome.blessed, outcome.message
    assert outcome.message == str(tree), (
        "a blessing must carry the tree it blessed, because the caller compares it"
    )


def test_a_tree_WITHOUT_the_sentinel_is_REFUSED_and_named(tmp_path: Path) -> None:
    """⛔ The refusal R4 rests on, and the one nothing was asserting.

    ⚠️ It must NAME the tree. A refusal that says only *"not blessed"* leaves the
    owner unable to tell which of three trees was open -- and the whole reason the
    path comes from the open database rather than from an argument is so that the
    refusal names what is actually open.
    """
    tree = _a_gramps_tree(tmp_path / "live", blessed=False)

    outcome = document.blessing_of(str(tree))

    assert not outcome.blessed, "an unblessed tree was accepted for writing"
    assert str(tree) in outcome.message, (
        f"the refusal does not name the tree it refused: {outcome.message}"
    )
    assert document.SENTINEL in outcome.message, (
        "the refusal does not say what to create, so it is not actionable"
    )


def test_a_directory_that_is_not_a_TREE_is_refused_DISTINGUISHABLY(tmp_path: Path) -> None:
    """⛔ Two limbs, two reasons, and the difference between them matters.

    Both limbs fired on the one production observation R4 records -- a missing
    sentinel AND a parent directory that was not a tree. If they collapsed into
    one message the owner could not tell *"you pointed at the wrong folder"* from
    *"this folder is right and you have not blessed it"*, and only the second has
    an action attached to it.
    """
    not_a_tree = tmp_path / "documents"
    not_a_tree.mkdir()
    (not_a_tree / document.SENTINEL).write_text("", encoding="utf-8")

    outcome = document.blessing_of(str(not_a_tree))

    assert not outcome.blessed, (
        "a sentinel in a directory that is not a Gramps tree blessed it anyway -- "
        "so dropping that file anywhere would arm the write path"
    )
    assert "not a Gramps family tree" in outcome.message, (
        f"refused for the wrong reason, so the owner cannot act: {outcome.message}"
    )


def test_no_save_path_is_refused(tmp_path: Path) -> None:
    """⚠️ The empty answers, which are the ones that fail open when they fail."""
    assert not document.blessing_of(None).blessed
    assert not document.blessing_of("").blessed


# ---------------------------------------------------------------------------
# The same check, reached the way the host reaches it.
# ---------------------------------------------------------------------------


def test_the_ACCESSOR_asks_the_open_database_and_refuses(tmp_path: Path, bound: None) -> None:
    """⛔ ``accessor.blessing()`` for real -- never stubbed, which is the point.

    The path comes from the open database, so this is where *"the refusal names
    the tree that is actually open"* is either true or it is not.
    """
    unblessed = _a_gramps_tree(tmp_path / "live", blessed=False)
    accessor.bind(_FakeDbState(_FakeDatabase(str(unblessed))))

    outcome = accessor.blessing()

    assert not outcome.blessed
    assert str(unblessed) in outcome.message

    blessed = _a_gramps_tree(tmp_path / "copy", blessed=True)
    accessor.bind(_FakeDbState(_FakeDatabase(str(blessed))))
    assert accessor.blessing().blessed


def test_a_closed_or_absent_database_is_refused_not_assumed(tmp_path: Path, bound: None) -> None:
    """⚠️ ``no tree is open`` must refuse, not fall through to a stale answer."""
    accessor.forget()
    assert not accessor.blessing().blessed

    accessor.bind(_FakeDbState(_FakeDatabase(str(tmp_path), open_=False)))
    assert not accessor.blessing().blessed, "a CLOSED database was treated as open"

    accessor.bind(_FakeDbState(None))
    assert not accessor.blessing().blessed, "a missing database was treated as open"


# ---------------------------------------------------------------------------
# And through the plugin, which is what Gramps actually calls.
# ---------------------------------------------------------------------------


class _Writer:
    """Records what the host asked the UI to do, and says yes to everything."""

    def __init__(self) -> None:
        self.confirmed: list[str] = []
        self.told: list[tuple[str, str]] = []
        self.wrote: list[Any] = []

    def confirm(self, uistate: Any, text: str) -> bool:
        self.confirmed.append(text)
        return True

    def tell(self, uistate: Any, title: str, body: str) -> None:
        self.told.append((title, body))

    def write(self, dbstate: Any, graph: Any) -> dict[str, Any]:
        self.wrote.append(graph)
        return {"created": {"people": ["I9001"]}, "attached": {}}


def test_the_HOST_refuses_an_unblessed_tree_with_the_REAL_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: None
) -> None:
    """⛔ R4's precondition 3, end to end, with nothing about the check faked.

    ⚠️ **``accessor.blessing`` is deliberately NOT monkeypatched here.** The
    thirteen stubs elsewhere are what left this untested; this runs the real thing
    through the layer R8 rules is the only write path there is.

    ⭐ And the assertions are about what the owner experiences: **no dialog**, no
    write, and a refusal that names the tree.
    """
    plugin: ModuleType = load_the_plugin()
    writer = _Writer()
    monkeypatch.setitem(sys.modules, "gramps_live_api_writer", writer)

    unblessed = _a_gramps_tree(tmp_path / "live", blessed=False)
    accessor.bind(_FakeDbState(_FakeDatabase(str(unblessed))))

    from gramps_live_api.host import backup

    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    result = plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=backup.Outcome(ok=True, path=None, message="ok"),
        totals={},
        note=lambda level, message: None,
        backed_up_tree=None,
    )

    assert result is False
    assert writer.wrote == [], "an UNBLESSED tree was written to"
    assert writer.confirmed == [], (
        "the owner was shown an approval dialog for a tree that may not be "
        "written -- the refusal must come before the dialog, not after it"
    )
    assert writer.told, "the refusal was silent"
    assert str(unblessed) in " ".join(body for _title, body in writer.told), (
        f"the owner is not told which tree was refused: {writer.told}"
    )


def test_the_HOST_proceeds_when_the_tree_IS_blessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: None
) -> None:
    """⚠️ A refusal that also refuses correct trees is worse than the defect.

    Without this, the test above passes just as well against a check that refuses
    everything -- which is the shape this project keeps paying for.
    """
    plugin: ModuleType = load_the_plugin()
    writer = _Writer()
    monkeypatch.setitem(sys.modules, "gramps_live_api_writer", writer)

    blessed = _a_gramps_tree(tmp_path / "copy", blessed=True)
    accessor.bind(_FakeDbState(_FakeDatabase(str(blessed))))

    from gramps_live_api.host import backup

    copy = blessed / "a-backup.sqlite"
    copy.write_text("a backup", encoding="utf-8")

    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=backup.Outcome(ok=True, path=str(copy), message="ok"),
        totals={},
        note=lambda level, message: None,
        backed_up_tree=str(blessed),
    )

    assert writer.wrote, (
        "a BLESSED tree was refused, so the test above proves nothing -- a check "
        "that refuses everything passes it too"
    )
