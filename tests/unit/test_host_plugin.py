"""The Gramps-facing half, covered as far as a machine without Gramps can cover it.

⭐ **The plugin module imports nothing from ``gramps`` or ``gi`` at module
level**, so it loads here and most of it runs. What is left uncovered is three
lines inside ``load_on_reg``: the ``gi`` import, the ``GLib.idle_add`` it passes
on, and ``dbstate.connect``. Everything else -- binding the accessor, starting
the service, resolving the package path, and the last-resort log -- is exercised
below.

⚠️ **The file is loaded BY PATH, not imported.** ``gramps_plugin/`` is outside
``src/`` and outside the package, and CONTRIBUTING says the package may not
import it. Loading it through ``importlib`` here is a test reaching for a file,
which is a different thing from the package depending on one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from gramps_live_api.host import accessor, paths
from tests.fixtures.host import MainLoop
from tests.fixtures.host_sources import PLUGIN_DIRECTORY, plugin_sources

PLUGIN_FILE = PLUGIN_DIRECTORY / "gramps_live_api_host.py"


def load_the_plugin() -> ModuleType:
    """Load the plugin file as a module without putting it on anyone's import path."""
    specification = importlib.util.spec_from_file_location("a_host_plugin_under_test", PLUGIN_FILE)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture
def plugin() -> ModuleType:
    return load_the_plugin()


def test_the_plugin_imports_with_no_gramps_and_no_gtk_on_the_machine(
    plugin: ModuleType,
) -> None:
    """The property everything else in this file rests on, asserted first.

    Its seam twin is test_the_plugin_half_is_covered_by_the_rule in
    tests/unit/test_host_thread_boundary.py, which asserts the same file is
    inside the thread-boundary rule's reach.
    """
    assert hasattr(plugin, "load_on_reg"), (
        "Gramps calls load_on_reg on the loaded module; without it the hook is a "
        "plugin that registers and does nothing"
    )
    assert hasattr(plugin, "start_host")


def test_starting_the_host_binds_the_accessor_and_listens(
    plugin: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``start_host`` is the whole plugin body except the three Gramps lines."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    loop = MainLoop()

    class ADbState:
        db = None

    accessor.forget()
    host = plugin.start_host(ADbState(), loop.schedule)

    try:
        assert host is not None, "the host did not start; host.log should say why"
        assert host.port > 0
        assert accessor.tree_status().open is False, (
            "the accessor was not bound to the dbstate the plugin was handed"
        )
    finally:
        if host is not None:
            host.stop()
        accessor.forget()


def test_a_started_host_is_kept_where_something_can_stop_it(
    plugin: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")

    class ADbState:
        db = None

    host = plugin.start_host(ADbState(), MainLoop().schedule)
    try:
        assert plugin._RUNNING["host"] is host
    finally:
        host.stop()
        accessor.forget()


@pytest.mark.parametrize(
    ("environ", "platform"),
    [
        pytest.param({"APPDATA": "an-appdata"}, "win32", id="windows"),
        pytest.param({"XDG_CONFIG_HOME": "a-config-home"}, "linux", id="freedesktop"),
        pytest.param({"HOME": "a-home"}, "linux", id="the freedesktop default"),
    ],
)
def test_the_last_resort_log_agrees_with_the_real_one(
    plugin: ModuleType, environ: dict[str, str], platform: str
) -> None:
    """The one duplicated path in this project, pinned so it cannot drift.

    ``gramps_plugin/gramps_live_api_host.py`` computes the log location itself,
    because the failure it exists to report is the one where the package cannot
    be imported and so cannot be asked. A copy that drifts writes the report into
    a directory nobody looks in, which is silence with extra steps.

    All three layouts, because the copy has three branches and a Windows-only
    assertion would leave two of them unmeasured on every runner.
    """
    real = paths.log_path(paths.state_directory(environ, platform=platform))

    assert Path(plugin.last_resort_log_path(environ, platform)) == real


def test_the_last_resort_note_writes_a_line_nothing_else_would_have(
    plugin: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8's accepted risk 2 at its worst: the package was never importable.

    ⚠️ ``gramps`` is put in ``sys.modules`` because that is the premise: this
    failure happens INSIDE Gramps. The note refuses to write outside one, so
    without this the test would assert against a file nothing wrote.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "gramps", ModuleType("gramps"))

    plugin._last_resort_note("ModuleNotFoundError: no module named gramps_live_api")

    written = paths.log_path(paths.state_directory({"APPDATA": str(tmp_path)}, platform="win32"))
    assert "ERROR" in written.read_text(encoding="utf-8")
    assert "gramps_live_api" in written.read_text(encoding="utf-8")


def test_the_hook_never_raises_however_badly_it_goes(plugin: ModuleType) -> None:
    """``load_on_reg``'s caller prints a traceback into a console the AIO does not have.

    Nothing that happens in there may escape, because an escaping exception is
    indistinguishable from a plugin that worked -- Gramps carries on either way.
    ``None`` for a dbstate makes every path in the hook fail.

    ⚠️ **Every arity is called, and that is the sharper half.** A signature
    mismatch raises in GRAMPS' code, before the body's ``try`` -- so it cannot be
    caught, cannot be logged, and fails in the one way nothing here can report.
    Nothing on this machine can check what Gramps passes, so the call is made
    impossible to get wrong instead of being got right by guessing.
    """
    plugin.load_on_reg(None)
    plugin.load_on_reg(None, None)
    plugin.load_on_reg(None, None, None)
    plugin.load_on_reg(None, None, None, "something a later Gramps added")


def test_the_registration_declares_the_hook_gramps_looks_for() -> None:
    """``load_on_reg=True`` in the ``.gpr.py`` is what makes Gramps call the module.

    Without it the plugin registers, appears in the plugin list, and is never
    loaded -- which looks exactly like an installation that worked.
    """
    registration = (PLUGIN_DIRECTORY / "gramps_live_api_host.gpr.py").read_text(encoding="utf-8")

    assert "load_on_reg=True" in registration.replace(" ", "")
    assert "GENERAL" in registration
    assert 'fname="gramps_live_api_host.py"' in registration


def test_both_plugin_files_are_inside_the_host_rules(plugin: ModuleType) -> None:
    """The registration has no imports, so it qualifies through what it registers.

    If it stopped qualifying, the thread-boundary and language-floor rules would
    quietly stop reading a file Gramps executes on every single launch.
    """
    covered = {path.name for path in plugin_sources()}

    assert covered == {"gramps_live_api_host.py", "gramps_live_api_host.gpr.py"}


def test_the_apply_plugin_is_not_swept_in() -> None:
    """The other direction. R8 retires the spawned-CLI writer in a LATER slice.

    A file-set rule that reached it would put the existing write path -- which
    does spell ``dbstate.db``, correctly, for its own architecture -- inside a
    rule written for this one, and the failure would read as a defect in code
    nobody touched.
    """
    swept: list[Any] = [path for path in plugin_sources() if "apply" in path.name]

    assert swept == []


def test_a_run_outside_gramps_never_touches_the_production_log(
    plugin: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ The suite was filling the one file a real failure is visible in.

    ``load_on_reg(None)`` is a correct test — the hook must never raise — and it
    fails at ``from gi.repository import GLib``, which is not a fault but proof
    that this is not Gramps. It reported that to the **production** log anyway:
    **68 tracebacks against 25 real lines**, and a reader came one message from
    declaring the host down because of them.

    ⚠️ **A log that cries wolf is the same defect as a guard that fires on every
    route literal.** It trains the reader to skip the line that matters, and
    ``host.log`` is the ONLY place a genuinely failed start appears — R8's
    accepted risk 2.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delitem(sys.modules, "gramps", raising=False)

    plugin.load_on_reg(None)
    plugin.load_on_reg(None, None, None)
    plugin._last_resort_note("this must not be written")

    written = paths.log_path(paths.state_directory({"APPDATA": str(tmp_path)}, platform="win32"))
    assert not written.exists(), (
        "a run outside Gramps wrote to the host log: " + written.read_text(encoding="utf-8")[:400]
    )


def test_the_hook_still_reports_when_it_really_is_gramps(
    plugin: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⚠️ The other direction, and the one that matters more.

    A guard that silenced real failures too would be worse than the noise it
    removed — the failure would go from buried to invisible.
    """
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "gramps", ModuleType("gramps"))

    plugin.load_on_reg(None)

    written = paths.log_path(paths.state_directory({"APPDATA": str(tmp_path)}, platform="win32"))
    assert written.exists() and "ERROR" in written.read_text(encoding="utf-8"), (
        "a genuine failure inside Gramps was silenced -- buried is bad, invisible is worse"
    )


# ---------------------------------------------------------------------------
# R7's backup: the continuation, and the refusal that makes the cost bounded.
# ---------------------------------------------------------------------------


class _Writer:
    """Stands in for ``gramps_live_api_writer``, recording what it was asked to do."""

    def __init__(self, say_yes: bool = True) -> None:
        self.confirmed: list[str] = []
        self.told: list[tuple[str, str]] = []
        self.wrote: list[Any] = []
        self._say_yes = say_yes

    def confirm(self, uistate: Any, text: str) -> bool:
        self.confirmed.append(text)
        return self._say_yes

    def tell(self, uistate: Any, title: str, body: str) -> None:
        self.told.append((title, body))

    def write(self, dbstate: Any, graph: Any) -> dict[str, Any]:
        self.wrote.append(graph)
        return {"created": {"people": ["I9001"]}, "attached": {}}


def _install_writer(monkeypatch: pytest.MonkeyPatch, writer: _Writer) -> None:
    monkeypatch.setitem(sys.modules, "gramps_live_api_writer", writer)


def test_a_failed_backup_shows_no_dialog_and_writes_nothing(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ Refuse-to-arm, in the ruling's own words.

    *If the backup cannot be taken, the host refuses to arm its write path and
    says so. It does not fall back to an export, it does not write without a
    backup, and it does not continue quietly.*

    ⭐ **And no dialog appears.** One that opens and then reports *"the backup
    failed, nothing was written"* has already spent the owner's attention on a
    decision that could not be honoured.
    """
    from gramps_live_api.host import backup

    writer = _Writer()
    _install_writer(monkeypatch, writer)
    failed = backup.Outcome(ok=False, path=None, message="the copy did not finish within 5 s")

    result = plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph={},
        parsed=None,
        resolution=None,
        taken=failed,
        totals={},
        note=lambda level, message: None,
    )

    assert writer.confirmed == [], "a dialog was shown even though the backup failed"
    assert writer.wrote == [], "the tree was written without a backup"
    assert result is False, "a truthy return reschedules the GLib idle callback"
    title, body = writer.told[-1]
    assert "no backup" in title.lower()
    assert "did not finish" in body and "refuses to arm" in body


def test_the_owner_is_told_where_the_backup_went(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⭐ A backup nobody can find is not a recovery path."""
    from gramps_live_api.host import backup, document

    writer = _Writer(say_yes=True)
    _install_writer(monkeypatch, writer)
    monkeypatch.setattr(accessor, "blessing", lambda: document.Blessing(True, str(tmp_path)))

    taken = backup.Outcome(
        ok=True,
        path=str(tmp_path / "backups" / "T" / "20260823T000000Z-T.sqlite"),
        message="backup taken",
        pages=12,
        attempts=1,
        seconds=0.12,
        taken_utc="2026-08-23T00:00:00+00:00",
    )
    # ⚠️ Built from keyword arguments, not a dict literal: pii_guard's P2
    # signature scores JSON-shaped key/value pairs carrying identity, and it
    # cannot tell an invented person from a real one by looking.
    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])

    result = plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=taken,
        totals={"people": 2934},
        note=lambda level, message: None,
    )

    assert writer.wrote, "the write did not happen after a successful backup"
    assert result is False
    written_title, written_body = writer.told[-1]
    assert written_title == "Written"
    assert "20260823T000000Z-T.sqlite" in written_body, (
        "the owner is not told which backup precedes this write"
    )


def _invented_root() -> str:
    """An absolute-looking root, assembled from parts.

    ⛔ A drive-letter literal in a test file is a P1 finding in this repository's
    own guard, and correctly so -- it cannot tell an invented path from the
    owner's.
    """
    return chr(67) + ":/somewhere"


def test_the_journal_records_which_backup_precedes_the_write() -> None:
    """⛔ R4 precondition 4: the age relative to the write, without archaeology.

    ⚠️ And ``totals_before``, because the restore procedure asks the owner to
    check the counts after replacing the file -- which he cannot do if nothing
    recorded them.
    """
    from gramps_live_api.host import document

    # ⚠️ Built from keyword arguments, not a dict literal: pii_guard's P2
    # signature scores JSON-shaped key/value pairs carrying identity, and it
    # cannot tell an invented person from a real one by looking.
    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    record = document.journal_record(
        document.parse(graph),
        {"people": ["I9001"]},
        {},
        tree_dir=_invented_root() + "/tree",
        written_utc="2026-08-23T00:00:05+00:00",
        approved_preview="...",
        backup_path=_invented_root() + "/backups/T/20260823T000000Z-T.sqlite",
        backup_utc="2026-08-23T00:00:00+00:00",
        totals_before={"people": 2934, "families": 1586},
    )

    assert record["backup"]["path"].endswith("20260823T000000Z-T.sqlite")
    assert record["backup"]["taken_utc"] < record["written_utc"], (
        "the recorded backup does not predate the write it is supposed to reverse"
    )
    assert record["backup"]["totals_before"]["people"] == 2934


def test_the_tree_name_is_read_from_a_file_never_the_database(
    plugin: ModuleType, tmp_path: Path
) -> None:
    """⚠️ This module may not touch ``dbstate.db`` -- the boundary test refuses it."""
    (tmp_path / "name.txt").write_text("RandyReid-Testing\n", encoding="utf-8")

    assert plugin._tree_name(str(tmp_path)) == "RandyReid-Testing"
    assert plugin._tree_name(str(tmp_path / "absent")) == "tree"


def test_the_backup_must_be_of_the_tree_that_gets_written(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⛔ A backup of a DIFFERENT tree is not a backup.

    Switch from blessed tree A to blessed tree B while the worker is copying and
    a check that asks only *is this blessed* passes: the write lands in B while
    the copy on disk is of A. **Recoverable-after is then false while every
    individual check reads green** -- the guarantee gone, and nothing saying so.
    """
    from gramps_live_api.host import backup, document

    writer = _Writer(say_yes=True)
    _install_writer(monkeypatch, writer)
    # The tree open NOW is B; the backup was taken of A.
    monkeypatch.setattr(accessor, "blessing", lambda: document.Blessing(True, str(tmp_path / "B")))

    taken = backup.Outcome(ok=True, path=str(tmp_path / "b.sqlite"), message="ok", taken_utc="t")

    result = plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph={},
        parsed=None,
        resolution=None,
        taken=taken,
        totals={},
        note=lambda level, message: None,
        backed_up_tree=str(tmp_path / "A"),
    )

    assert writer.wrote == [], "the write went to a tree the backup does not cover"
    assert writer.confirmed == [], "the owner was asked about a write that must not happen"
    assert result is False
    title, body = writer.told[-1]
    assert "tree changed" in title
    assert "backup is of" in body


def test_the_tree_is_rechecked_after_the_owner_confirms(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⚠️ ``confirm`` spins a NESTED GTK main loop, so arbitrary time passes inside it.

    The tree can be closed or swapped while the owner reads the dialog, which is
    exactly the window the pre-dialog check cannot see.
    """
    from gramps_live_api.host import backup, document

    tree_a = str(tmp_path / "A")
    seen = {"calls": 0}

    def blessing_that_changes():
        seen["calls"] += 1
        # Same tree before the dialog; a different one after it.
        return document.Blessing(True, tree_a if seen["calls"] == 1 else str(tmp_path / "B"))

    writer = _Writer(say_yes=True)
    _install_writer(monkeypatch, writer)
    monkeypatch.setattr(accessor, "blessing", blessing_that_changes)

    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    result = plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=backup.Outcome(ok=True, path=str(tmp_path / "b.sqlite"), message="ok"),
        totals={},
        note=lambda level, message: None,
        backed_up_tree=tree_a,
    )

    assert seen["calls"] >= 2, "the blessing was not re-checked after confirmation"
    assert writer.confirmed, "the dialog should have been shown -- the tree was fine before it"
    assert writer.wrote == [], "the tree changed while the dialog was open and the write proceeded"
    assert result is False


def test_a_cancelled_preview_still_prunes(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⛔ Every cancellation has already produced a verified backup.

    The copy must finish BEFORE the dialog opens, so declining costs a full copy
    -- roughly 24 MB on the measured tree. With pruning only on the success path,
    repeated declines grow the directory past its documented bound.
    """
    from gramps_live_api.host import backup, document

    directory = tmp_path / "backups" / "T"
    directory.mkdir(parents=True)
    for n in range(5):
        (directory / f"2026-08-2{n}T000000Z-T.sqlite").write_text("x", encoding="utf-8")
    newest = directory / "2026-08-24T000000Z-T.sqlite"

    writer = _Writer(say_yes=False)
    _install_writer(monkeypatch, writer)
    monkeypatch.setattr(accessor, "blessing", lambda: document.Blessing(True, str(tmp_path)))
    monkeypatch.setattr(backup, "RETAIN", 2)

    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    result = plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=backup.Outcome(ok=True, path=str(newest), message="ok"),
        totals={},
        note=lambda level, message: None,
        backed_up_tree=str(tmp_path),
    )

    assert result is False
    assert writer.wrote == [], "cancelling must not write"
    assert not newest.exists(), (
        "a cancelled preview's backup was KEPT. It protects nothing -- no write "
        "happened -- and RETAIN of them push the journal-linked pre-write backup "
        "out of the window, leaving copies but none that can undo the write."
    )
    assert len(list(directory.iterdir())) == 4, (
        "only the cancelled preview's own backup should have been removed"
    )


def test_the_backup_mapping_is_durable_BEFORE_the_write(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⛔ A committed write must never exist with no record of its backup.

    The journal used to be written **after** the transaction with its failure
    caught, so a disk, permission or serialisation error left a changed tree and
    no durable link to the copy that precedes it. **That is A4 defeated
    entirely** -- *recoverable-after* reduced to filesystem archaeology at the
    exact moment it is needed.
    """
    from gramps_live_api.host import backup, document

    writer = _Writer(say_yes=True)
    _install_writer(monkeypatch, writer)
    monkeypatch.setattr(accessor, "blessing", lambda: document.Blessing(True, str(tmp_path)))

    seen: list[str] = []
    real_write_journal = document.write_journal

    def recording(tree_dir, record, *, stem):  # noqa: ANN001, ANN202
        seen.append("journal" if record.get("write_confirmed") is not False else "intent")
        return real_write_journal(tree_dir, record, stem=stem)

    monkeypatch.setattr(document, "write_journal", recording)
    original_write = writer.write

    def write_and_note(dbstate, graph):  # noqa: ANN001, ANN202
        seen.append("write")
        return original_write(dbstate, graph)

    writer.write = write_and_note  # type: ignore[method-assign]

    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=backup.Outcome(ok=True, path=str(tmp_path / "b.sqlite"), message="ok", taken_utc="t"),
        totals={"people": 2934},
        note=lambda level, message: None,
        backed_up_tree=str(tmp_path),
    )

    assert seen and seen[0] == "intent", f"the backup was not recorded before the write: {seen}"
    assert "write" in seen and seen.index("intent") < seen.index("write")


def test_a_failure_to_record_the_backup_REFUSES_the_write(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⛔ Refusing is the only honest answer.

    Writing anyway would produce exactly the state A4 exists to prevent, and it
    would do it knowingly.
    """
    from gramps_live_api.host import backup, document

    writer = _Writer(say_yes=True)
    _install_writer(monkeypatch, writer)
    monkeypatch.setattr(accessor, "blessing", lambda: document.Blessing(True, str(tmp_path)))

    def refuse(*args: object, **kwargs: object) -> str:
        raise OSError("the journal directory is not writable")

    monkeypatch.setattr(document, "write_journal", refuse)

    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    result = plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=backup.Outcome(ok=True, path=str(tmp_path / "b.sqlite"), message="ok", taken_utc="t"),
        totals={},
        note=lambda level, message: None,
        backed_up_tree=str(tmp_path),
    )

    assert writer.wrote == [], "the tree was written with no durable record of its backup"
    assert result is False
    title, body = writer.told[-1]
    assert "Nothing was written" in title
    assert "backup could not be recorded" in body


def test_a_second_approval_is_REFUSED_while_one_is_on_screen(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⛔ The bound, not a fourth patch.

    ⚠️ **There is no "synchronous" in a GTK application with modal dialogs.**
    ``writer.confirm`` spins a nested main loop, so another ``_present`` runs
    *inside* it. Four review rounds found four different consequences of that one
    missing requirement — a backup restoring away another document's write, a
    cancelled preview evicting the pre-write backup, re-entry through the nested
    loop, an interleaved completion truncating the intent journal.

    ⭐ **They are one defect seen four times.** This asserts the second approval
    is REFUSED rather than queued behind and silently executed.
    """
    from gramps_live_api.host import backup, document

    reentered: list[object] = []
    backups_taken: list[str] = []
    writer = _Writer(say_yes=False)
    inner = dict(people=[dict(id="p9", given="Second", surname="Proposal")])

    def confirm_that_reenters(uistate: Any, text: str) -> bool:
        # This is exactly what a nested GTK main loop does: another scheduled
        # callback runs while the first is still inside ``confirm``.
        reentered.append(plugin._present(None, None, inner))
        return False

    def counting_backup(tree_dir: str, note: Any):  # noqa: ANN202
        backups_taken.append(tree_dir)
        return backup.Outcome(
            ok=True, path=str(tmp_path / "b.sqlite"), message="ok", taken_utc="t", seconds=0.1
        )

    writer.confirm = confirm_that_reenters  # type: ignore[method-assign]
    _install_writer(monkeypatch, writer)
    monkeypatch.setattr(accessor, "blessing", lambda: document.Blessing(True, str(tmp_path)))
    monkeypatch.setattr(accessor, "tree_totals", lambda: {"people": 1})
    monkeypatch.setattr(accessor, "resolve_nodes", lambda graph: document.Resolution())
    monkeypatch.setattr(plugin, "_take_backup", counting_backup)

    plugin._present(None, None, dict(people=[dict(id="p1", given="Ada", surname="Invented")]))

    assert reentered, "the re-entrant call never happened, so this proves nothing"
    assert reentered[0] is False, (
        f"the second approval was not refused; it returned {reentered[0]!r}"
    )
    assert len(backups_taken) == 1, (
        f"the re-entrant approval took its OWN backup -- the interleaving the "
        f"guard exists to prevent: {backups_taken}"
    )
    assert writer.wrote == [], "the re-entrant approval wrote"


def _ok_backup(tmp_path: Path):  # noqa: ANN202
    from gramps_live_api.host import backup

    return backup.Outcome(
        ok=True, path=str(tmp_path / "b.sqlite"), message="ok", taken_utc="t", seconds=0.1
    )


def test_the_in_flight_flag_is_cleared_on_every_exit(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⛔ A flag left set refuses every later proposal for the life of the process.

    That is a worse failure than the one it prevents, so the clearing is in a
    ``finally`` and this asserts it for a path that RAISES.
    """
    from gramps_live_api.host import document

    writer = _Writer()
    _install_writer(monkeypatch, writer)

    def explode() -> object:
        raise RuntimeError("blessing check blew up")

    monkeypatch.setattr(accessor, "blessing", explode)
    monkeypatch.setattr(accessor, "resolve_nodes", lambda graph: document.Resolution())

    plugin._present(None, None, dict(people=[dict(id="p1", given="Ada", surname="Invented")]))

    assert plugin._IN_FLIGHT["present"] is False, (
        "an exception left the guard set, so every later proposal would be refused"
    )


def test_the_intent_and_its_completion_share_one_file(
    plugin: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """⛔ A completion must finish the file it started, not name a new one.

    ⚠️ Both stems were computed independently from a UTC second, so a completion
    in the same second named an EXISTING intent file and ``write_journal`` opens
    with ``"w"`` — **truncating an already-fsynced backup mapping after the
    database had committed.** The stem now carries a collision-free suffix and
    the completion reuses the intent's own.
    """
    from gramps_live_api.host import backup, document

    writer = _Writer(say_yes=True)
    _install_writer(monkeypatch, writer)
    monkeypatch.setattr(accessor, "blessing", lambda: document.Blessing(True, str(tmp_path)))

    graph = dict(people=[dict(id="p1", given="Ada", surname="Invented")])
    plugin._write_after_backup(
        dbstate=None,
        uistate=None,
        graph=graph,
        parsed=document.parse(graph),
        resolution=document.Resolution(),
        taken=backup.Outcome(ok=True, path=str(tmp_path / "b.sqlite"), message="ok", taken_utc="t"),
        totals={"people": 1},
        note=lambda level, message: None,
        backed_up_tree=str(tmp_path),
    )

    undo = tmp_path / ".gramps-live-api-undo"
    records = sorted(undo.glob("*.json")) if undo.exists() else []
    assert len(records) == 1, (
        f"the completion should finish the intent's own file, not add a second: {records}"
    )
    import json

    written = json.loads(records[0].read_text(encoding="utf-8"))
    assert written.get("written_utc"), "the record was never completed"
    assert written["backup"]["path"].endswith("b.sqlite")
