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
    """R8's accepted risk 2 at its worst: the package was never importable."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "win32")

    plugin._last_resort_note("ModuleNotFoundError: no module named gramps_live_api")

    written = paths.log_path(paths.state_directory({"APPDATA": str(tmp_path)}, platform="win32"))
    assert "ERROR" in written.read_text(encoding="utf-8")
    assert "gramps_live_api" in written.read_text(encoding="utf-8")


def test_the_hook_never_raises_however_badly_it_goes(plugin: ModuleType) -> None:
    """``load_on_reg``'s caller prints a traceback into a console the AIO does not have.

    Nothing that happens in there may escape, because an escaping exception is
    indistinguishable from a plugin that worked -- Gramps carries on either way.
    ``None`` for a dbstate makes every path in the hook fail.
    """
    plugin.load_on_reg(None, None, None)


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
