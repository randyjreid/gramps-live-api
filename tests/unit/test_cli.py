"""``check``, the one command the owner types, and what each line of it refuses.

⚠️ **``check`` is covered end to end here because it never opens a database** --
it stats a directory and reports. What it cannot report on is a write, and after
R9 there is no write on this side of the process boundary at all: the document
route writes inside Gramps, and ``tests/integration/test_round_trip.py`` is what
observes that.

⛔ **``preview``, ``apply`` and the console ``approve`` are retired**, and so are
the tests that covered them: the injected runner, the two-run write and
read-back, the digest beside the sentence, and the operation file reader. What
survives from that half of the file is nothing, which is why it starts at the
doctor.

The one assertion in this file that carries the safety rail is
``test_check_refuses_an_unblessed_tree_by_name``: it is the refusal the owner
can watch happen by pointing ``check`` at his live tree.
"""

from __future__ import annotations

import io
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from gramps_live_api import cli, config
from gramps_live_api.core import apply
from tests.fixtures.trees import blessed


def run(*argv: str, environ: Mapping[str, str] | None = None) -> tuple[int, str, str]:
    """``cli.main`` with both streams captured and nothing real touched."""
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), environ={} if environ is None else environ, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def equipped(tmp_path: Path, **extra: str) -> dict[str, str]:
    """An environment where a runtime and a registered plugin are both present.

    The doctor reports on the whole picture, so a test about the *copy* has to
    supply the rest of it -- otherwise it asserts the exit code of a machine
    with no Gramps on it, which is a different question and one CI would answer
    the same way every time.

    ⚠️ **The runtime is supplied through ``GRAMPS_LIVE_API_RUNTIME``, not left to
    be discovered from the fake ``ProgramFiles`` tree below.** ``discover_runtime``
    returns ``None`` before it looks at anything when ``sys.platform`` is not
    ``win32`` -- correctly, because the all-in-one layout is a Windows fact -- so
    on the Linux matrix the fake install was ignored and this helper did not
    equip anything. Two tests asserting ``code == 0`` failed there while passing
    on Windows, and three more passed on Linux for the wrong reason: they assert
    a non-zero exit or a substring, which a missing runtime satisfies just as
    well as the condition under test.

    So the override is what makes the docstring's promise true on every platform,
    and the ``ProgramFiles`` tree stays because ``discover_runtime`` itself is
    tested through it elsewhere -- this helper is about the doctor's other
    checks, not about discovery.

    ⛔ **The export is gone with R9**, and so is the paragraph that used to be
    here about writing one after the copy so the doctor did not call it stale.
    ``check`` no longer reports on an export, because there is no longer anything
    that reads one.
    """
    program_files = tmp_path / "program-files"
    install = program_files / "GrampsAIO64-6.0.8"
    install.mkdir(parents=True, exist_ok=True)
    runtime = install / config.RUNTIME_NAME
    runtime.write_text("", encoding="utf-8")
    plugins = tmp_path / "roaming" / "gramps" / "gramps60" / "plugins" / "gramps-live-api"
    plugins.mkdir(parents=True, exist_ok=True)
    # ⛔ Every file the plugin directory must hold, from cli.PLUGIN_FILES rather
    # than from a name written here. It used to be possible to lay down only the
    # apply registration and equip "a registered plugin" that registered no HOST,
    # so the document route could not start while every caller asserted the exit
    # code of a setup that half works. Discovery is keyed on the host
    # registration now, and reading the tuple keeps this fixture honest anyway.
    for name in cli.PLUGIN_FILES:
        (plugins / name).write_text("", encoding="utf-8")
    # ⛔ **The host registration is laid down for REAL, not as an empty file.**
    #
    # ⚠️ ``_source_check`` no longer models Python's import resolution -- it runs
    # the host's own ``_put_the_package_on_the_path`` in a child process and
    # imports. An empty stub has no such function, so every caller would be
    # asserting the exit code of a plugin directory that cannot set up a path at
    # all, which is a different question from the one each test is asking.
    #
    # ⭐ Copying the real file makes these fixtures MORE faithful, not less: the
    # candidate order, the de-duplication and the ``realpath`` step are now the
    # ones Gramps executes, and a change to that rule reaches these tests by
    # itself.
    _lay_the_real_host_registration(plugins)
    # ⛔ **The host has to reach the package, and finding the .gpr.py does not
    # prove it can.** ``check`` reports that separately now, so a helper that
    # equips "a registered plugin" and stops leaves every caller asserting the
    # exit code of a setup the document route would fail on. This is the
    # explicit-directory route the host looks at first, which is also what a
    # copied installation is told to set.
    source = tmp_path / "checkout" / "src"
    _lay_out_the_host_package(source)
    return {
        "ProgramFiles": str(program_files),
        "APPDATA": str(tmp_path / "roaming"),
        config.ENV_RUNTIME: str(runtime),
        "GRAMPS_LIVE_API_SRC": str(source),
        **extra,
    }


def _lay_the_real_host_registration(plugin_directory: Path) -> None:
    """Copy the REAL ``gramps_live_api_host.py`` into a fake plugin directory.

    ⛔ ``_source_check`` runs that file's own ``_put_the_package_on_the_path`` in
    a child process and then imports. An empty stub has no such function, so a
    fixture leaving one behind makes every caller assert the exit code of a
    plugin directory that cannot set up a path at all.

    ⭐ Spelled once, because two fixtures lay plugin files down and **one of them
    overwrote the other's real copy** with an empty stub.
    """
    source = Path(__file__).resolve().parents[2] / "gramps_plugin" / "gramps_live_api_host.py"
    (plugin_directory / "gramps_live_api_host.py").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _lay_out_the_host_package(source: Path) -> Path:
    """A ``src`` directory holding what the host plugin actually imports.

    ⛔ **An empty directory named ``gramps_live_api`` is not the package**, and
    this helper used to make one. ``check`` reported the source ready, and host
    startup would then have died on ``from gramps_live_api.host import accessor,
    service`` -- so the fixture was asserting the exit code of a setup that does
    not work, which is the same defect the check exists to catch.

    ⭐ Built from ``cli.HOST_MODULES`` rather than from a list written here, so
    the fixture cannot fall behind the requirement it is meant to satisfy.
    """
    package = source / "gramps_live_api"
    for module in cli.HOST_MODULES:
        target = package.joinpath(*module.split("."))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.with_suffix(".py").write_text("", encoding="utf-8")
    # ⛔ **``__init__.py`` at every level, because that is what makes it a
    # PACKAGE rather than a namespace portion** -- and the difference decides
    # which directory wins.
    #
    # ⚠️ This fixture used to omit them, and nothing noticed while the check
    # modelled resolution by looking for a directory of the right name. **The
    # real import does not agree**: a directory with no ``__init__.py`` is a
    # namespace portion, the search CONTINUES past it, and a regular package
    # further down the path wins. That is #174's fifth defect, and it surfaced
    # the moment the check started importing instead of inferring.
    #
    # ⭐ The shipped package has them, so writing them here makes the fixture
    # faithful rather than lenient.
    for directory in {package, *(package.joinpath(*m.split(".")).parent for m in cli.HOST_MODULES)}:
        (directory / "__init__.py").write_text("", encoding="utf-8")
    return source


# ⛔ Captured BEFORE the autouse fixture below can replace it, so the three tests
# that are about the gate itself call the real thing rather than the stub.
THE_REAL_PUSH_GATE_CHECK = cli._push_gate_check


@pytest.fixture(autouse=True)
def _the_push_gate_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """⛔ Every test in this file is about the TREE, not about this clone's hooks.

    ⚠️ ``check`` reports the push gate, and the gate is a property of **the
    checkout the code was loaded from** -- not of ``environ``, so ``equipped``
    cannot supply it. On a fresh clone, and on every CI runner, no hook is
    installed, so a test asserting ``code == 0`` about a blessed copy was
    asserting the exit code of a machine that simply had not run the one-line
    install. **Four of them went red on the Linux matrix for exactly that.**

    ⭐ Same argument ``equipped`` already makes about the runtime: a test about
    the copy has to supply the rest of the picture, or it measures something else
    entirely. The three tests that are genuinely about the gate call
    ``_push_gate_check`` directly and are untouched by this.
    """
    monkeypatch.setattr(
        cli,
        "_push_gate_check",
        lambda: cli.Check("push gate", True, "installed (stubbed for tree tests)"),
    )


# ---------------------------------------------------------------------------
# check -- the doctor, read-only, and the refusal the owner can watch happen
# ---------------------------------------------------------------------------


def test_check_reports_a_blessed_copy_as_writable(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")

    code, out, _ = run("check", copy.tree_dir, environ=equipped(tmp_path))

    assert code == 0, f"a blessed copy was not reported writable; got {out}"
    assert apply.SENTINEL_NAME in out


def test_check_refuses_an_unblessed_tree_by_name(tmp_path: Path) -> None:
    """The rail, demonstrated: point it at the live tree and watch the refusal.

    ⚠️ **This is the advisory copy of the check, and the report says so.** The
    load-bearing one runs inside Gramps against the database it has already
    opened, because that is the only place the answer cannot be about a
    different tree than the one being written.
    """
    live = tmp_path / "tree"
    live.mkdir()
    (live / apply.NAME_FILE).write_text("Invented Tree\n", encoding="utf-8")

    code, out, _ = run("check", str(live), environ=equipped(tmp_path))

    assert code != 0
    assert apply.SENTINEL_NAME in out, (
        "a refusal that does not name the missing file leaves the owner with "
        f"nothing to do about it; got {out}"
    )


def test_check_reports_a_locked_tree(tmp_path: Path) -> None:
    # Gramps refuses a locked tree and we never pass -u, so a copy open in the
    # GUI cannot be written. Reporting it is how that reads as an explanation
    # rather than as a mystery failure.
    copy = blessed(tmp_path / "tree")
    (Path(copy.tree_dir) / cli.LOCK_FILE).write_text("", encoding="utf-8")

    _, out, _ = run("check", copy.tree_dir, environ=equipped(tmp_path))

    assert "locked" in out.lower()


def test_check_falls_back_to_the_configured_copy(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")

    code, out, _ = run("check", environ=equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir}))

    assert code == 0
    assert copy.tree_dir in out


def test_check_says_so_when_no_copy_is_configured(tmp_path: Path) -> None:
    code, out, _ = run("check", environ=equipped(tmp_path))

    assert code != 0
    assert config.CONFIG_FILE in out, (
        "the owner has to be told where to configure a copy, or the first run "
        f"of the doctor is a dead end; got {out}"
    )


# ---------------------------------------------------------------------------
# ⛔ ``plugin: ok`` does not mean the document route can start
# ---------------------------------------------------------------------------


def _plugin_dir(environ: Mapping[str, str]) -> Path:
    checks = {check.label: check for check in cli.inspect(None, environ)}
    return Path(checks["plugin"].detail)


def test_a_COPIED_installation_passes_plugin_and_FAILS_source(tmp_path: Path) -> None:
    """⛔ The setup ``using.md`` supports, and the promise it used to make.

    ⚠️ The host reaches the package by ``realpath``-ing its own directory and
    stepping up one level, which works **because the plugin directory is a
    junction into the checkout**. Copy the files instead and ``realpath`` lands
    in Gramps' plugin folder, where there is no ``src`` -- so every document
    route fails on import.

    ⭐ Before this check existed, that setup produced a report with no ``NO`` on
    it, under a page saying *"if `check` passes, this route has what it needs."*
    """
    environ = dict(equipped(tmp_path))
    del environ["GRAMPS_LIVE_API_SRC"]  # a copy sets nothing
    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert checks["plugin"].ok, "the .gpr.py is there -- a copy does install it"
    assert not checks["source"].ok, (
        "a copied installation cannot reach gramps_live_api, and the report said nothing about it"
    )
    assert "junction" in checks["source"].detail, (
        f"the refusal must name the remedy, not just the condition: {checks['source'].detail}"
    )


def test_an_explicit_SRC_directory_satisfies_the_source_check(tmp_path: Path) -> None:
    """⭐ The first candidate: the owner who put the checkout somewhere else."""
    environ = equipped(tmp_path)
    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert checks["source"].ok, checks["source"].detail
    assert checks["source"].detail == environ["GRAMPS_LIVE_API_SRC"]


def test_a_checkout_BESIDE_the_plugin_satisfies_it_with_no_environment(
    tmp_path: Path,
) -> None:
    """⭐ The second candidate, and the one a junction actually produces.

    ⚠️ Asserted without ``GRAMPS_LIVE_API_SRC``, because that variable would
    satisfy the check for a different reason and the test would pass against a
    resolver that had lost this branch entirely.
    """
    environ = dict(equipped(tmp_path))
    del environ["GRAMPS_LIVE_API_SRC"]
    _lay_out_the_host_package(_plugin_dir(environ).parent / "src")

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert checks["source"].ok, checks["source"].detail


def test_the_source_check_matches_what_the_host_actually_does() -> None:
    """⛔ **Two spellings of one rule, pinned to each other.**

    ``cli`` cannot import ``gramps_live_api_host`` -- it imports Gramps at module
    scope -- so the candidate list is transcribed, the same way
    ``_gramps_user_data`` transcribes Gramps' own rule. A transcription that
    nothing checks is how the two ends stop agreeing, which is this project's
    most-recorded defect class.

    ⭐ So this reads the plugin's source and asserts the three candidates are
    still the three candidates, in order.
    """
    source = (
        Path(__file__).resolve().parents[2] / "gramps_plugin" / "gramps_live_api_host.py"
    ).read_text(encoding="utf-8")

    assert 'named = os.environ.get("GRAMPS_LIVE_API_SRC")' in source, (
        "the host no longer reads GRAMPS_LIVE_API_SRC first"
    )
    assert "here = os.path.dirname(os.path.realpath(__file__))" in source, (
        "the host no longer resolves its own directory through the junction"
    )
    assert (
        'for candidate in (named, os.path.join(os.path.dirname(here), "src"), here):' in source
    ), (
        "the host's candidate list changed; cli._host_source_candidates must "
        "change with it or check will report on a rule the host no longer uses"
    )


def test_an_EMPTY_gramps_live_api_directory_does_not_satisfy_the_source_check(
    tmp_path: Path,
) -> None:
    """⛔ A directory with the right name is not the package.

    ⚠️ The first version of this check asked ``isdir(candidate/"gramps_live_api")``
    and stopped. An empty or partial directory satisfied it, ``check`` printed
    **ready**, and host startup would then have died on ``from
    gramps_live_api.host import accessor, service`` — reporting the setup sound
    for the one route that could not run.

    ⭐ **This test's own fixture is how it was found.** ``equipped`` created
    exactly such an empty directory, so every case exercising the check was
    asserting the exit code of a setup that does not work.
    """
    environ = dict(equipped(tmp_path))
    hollow = tmp_path / "hollow" / "src"
    (hollow / "gramps_live_api").mkdir(parents=True, exist_ok=True)
    environ["GRAMPS_LIVE_API_SRC"] = str(hollow)

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert not checks["source"].ok, (
        "an empty directory named gramps_live_api was accepted as the package"
    )
    for module in cli.HOST_MODULES:
        assert module in checks["source"].detail, (
            f"the refusal does not say that {module} is what is missing: {checks['source'].detail}"
        )


def test_a_PARTIAL_package_does_not_satisfy_it_either(tmp_path: Path) -> None:
    """⚠️ Half the modules is the likelier real failure than none of them.

    A copy that ran out of disk, an interrupted sync, a checkout of an older
    revision — each leaves some of them. ⭐ Every module is required
    individually rather than any-of, so this asserts each one's absence in turn
    rather than one representative.
    """
    for missing in cli.HOST_MODULES:
        environ = dict(equipped(tmp_path))
        partial = tmp_path / f"partial-{missing}" / "src"
        # ⛔ Laid out through the SAME helper, then one module removed.
        #
        # ⚠️ This loop used to write its own files as `host / f"{module}.py"`,
        # which with dotted names produced `host/host.service.py` and
        # `host/config.py` -- so EVERY module read as absent and the assertion
        # below passed for a reason that had nothing to do with the one removed.
        # Building the complete package and deleting one is the only version that
        # can tell "this module is missing" from "none of them are there".
        _lay_out_the_host_package(partial)
        (partial / "gramps_live_api").joinpath(*missing.split(".")).with_suffix(".py").unlink()
        environ["GRAMPS_LIVE_API_SRC"] = str(partial)

        checks = {check.label: check for check in cli.inspect(None, environ)}

        assert not checks["source"].ok, (
            f"a package missing {missing}.py was accepted; host startup imports it"
        )
        # ⛔ **ONLY the removed module, and this is the assertion that
        # discriminates.** "Some module is missing" is satisfied by a fixture
        # that laid none of them down correctly -- which is what the previous
        # version did, and why it passed either way. Naming exactly one is the
        # only claim a broken layout cannot satisfy.
        named = [o for o in cli.HOST_MODULES if o in checks["source"].detail]
        assert named == [missing], (
            f"expected the refusal to name only {missing}; it named {named}. If it "
            f"names all of them the fixture laid down no module correctly, and this "
            f"test would pass for a reason unrelated to the one removed"
        )


def test_HOST_MODULES_is_the_TRANSITIVE_closure_of_what_the_host_imports() -> None:
    """⛔ **Two spellings of one rule, pinned to each other.**

    ``cli`` cannot import ``gramps_live_api_host`` -- it imports Gramps at module
    scope -- so the requirement is transcribed, the same way ``_gramps_user_data``
    transcribes Gramps' own rule. A transcription that nothing checks is how the
    two ends stop agreeing.

    ⚠️ **The first version walked only the plugin shim's own imports, and that
    was not enough.** ``service`` imports ``httpd``, ``log``, ``mainthread``,
    ``reads``, ``status`` and ``tokens`` at module scope; a tree holding the
    shim's five and missing ``httpd.py`` passed the check and then failed inside
    Gramps. **A closure is what the runtime needs; the first level is what is
    easy to read.**

    ⭐ So this walks the imports through every module they reach, and fails in
    **either** direction -- a module added to the host's startup that is not in
    the tuple, or one left in the tuple after the host stopped reaching it.
    """
    import ast

    root = Path(__file__).resolve().parents[2]

    def imported_by(source: str) -> set[str]:
        """Every ``gramps_live_api`` module this source names, dotted."""
        found: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                found.update(
                    alias.name for alias in node.names if alias.name.startswith("gramps_live_api")
                )
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("gramps_live_api"):
                continue
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        return {name[len("gramps_live_api.") :] for name in found if "." in name}

    plugin = (root / "gramps_plugin" / "gramps_live_api_host.py").read_text(encoding="utf-8")
    closure = imported_by(plugin)
    assert closure, "no host imports were found at all; the pattern has stopped matching"

    package = root / "src" / "gramps_live_api"
    pending, closure = list(closure), set()
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        module = package.joinpath(*name.split(".")).with_suffix(".py")
        if not module.is_file():
            continue
        closure.add(name)
        pending.extend(imported_by(module.read_text(encoding="utf-8")))

    assert set(cli.HOST_MODULES) == closure, (
        f"cli.HOST_MODULES is {sorted(cli.HOST_MODULES)} but the host's import "
        f"closure is {sorted(closure)} -- check would report a setup ready that "
        f"cannot start"
    )


def test_PLUGIN_FILES_is_what_the_plugin_directory_actually_holds() -> None:
    """⛔ Derived from ``gramps_plugin/`` rather than written beside it."""
    root = Path(__file__).resolve().parents[2]
    on_disk = {path.name for path in (root / "gramps_plugin").glob("*.py")}

    assert set(cli.PLUGIN_FILES) == on_disk, (
        f"cli.PLUGIN_FILES is {sorted(cli.PLUGIN_FILES)} but gramps_plugin/ holds "
        f"{sorted(on_disk)} -- a file added there would never be checked for"
    )


def test_a_plugin_directory_without_the_WRITER_is_refused(tmp_path: Path) -> None:
    """⛔ Finding the registration proves Gramps will load the host, not that it can write.

    ⚠️ **This test used to remove ``gramps_live_api_host.gpr.py`` and assert
    ``plugin`` stayed ok.** That was true while ``_PLUGIN_GLOB`` matched the
    apply registration: a directory holding that and no host registration
    registered no host, Gramps never started the document route, and every line
    of the report read ``ok``. R9 repoints discovery at the host registration, so
    that hole is closed by construction -- removing it now fails ``plugin``
    itself, which is the honest answer and no longer this test's question.

    ⭐ **What is left of the question is the writer**, and it is the same shape
    one file along: Gramps ``exec``s a plugin rather than importing it, so a
    directory carrying the registration and not ``gramps_live_api_writer.py``
    loads a host that dies on the first document.
    """
    environ = equipped(tmp_path)
    checks = {check.label: check for check in cli.inspect(None, environ)}
    plugin_dir = Path(checks["plugin"].detail)
    for name in cli.PLUGIN_FILES:
        (plugin_dir / name).write_text("", encoding="utf-8")
    # ⛔ The loop above just overwrote the real registration with an empty stub.
    _lay_the_real_host_registration(plugin_dir)

    complete = {check.label: check for check in cli.inspect(None, environ)}
    assert complete["source"].ok, complete["source"].detail

    (plugin_dir / "gramps_live_api_writer.py").unlink()
    partial = {check.label: check for check in cli.inspect(None, environ)}

    assert partial["plugin"].ok, "the host registration is still there, so plugin stays ok"
    assert not partial["source"].ok, "a plugin directory with no writer was reported as ready"
    assert "gramps_live_api_writer.py" in partial["source"].detail, (
        f"the refusal does not name what is missing: {partial['source'].detail}"
    )


def test_discovery_is_keyed_on_the_HOST_registration(tmp_path: Path) -> None:
    """⛔ R9's first coupling, asserted rather than left to the glob's spelling.

    ⚠️ **This is the one that gates the other two.** ``_plugin_check`` is the only
    thing that locates the plugin directory, and ``_source_check`` reads its
    ``detail`` for that directory -- so a glob keyed on a registration that no
    longer exists reports the plugin absent on every invocation, whatever else is
    present, and ``PLUGIN_FILES`` is then never meaningfully compared against
    anything.
    """
    environ = equipped(tmp_path)
    plugin_dir = Path({c.label: c for c in cli.inspect(None, environ)}["plugin"].detail)

    (plugin_dir / "gramps_live_api_host.gpr.py").unlink()
    without = {check.label: check for check in cli.inspect(None, environ)}

    assert not without["plugin"].ok, (
        "removing the host registration left the plugin reported as installed, so "
        "discovery is keyed on something else again"
    )
    assert not without["source"].ok and "no plugin to resolve from" in without["source"].detail, (
        f"the source check answered about a directory it could not locate: {without['source']}"
    )


def test_a_source_missing_config_py_is_refused(tmp_path: Path) -> None:
    """⛔ The startup closure reaches OUTSIDE ``host/``, by exactly one module.

    ⚠️ ``host/paths.py`` imports ``gramps_live_api.config`` at module scope, so a
    tree carrying all twelve ``host/`` modules and no ``config.py`` satisfied the
    old predicate and then died importing ``service`` -> ``paths`` -> ``config``.

    ⭐ **One module, and a hand-written list would not have found it** -- which is
    the argument for deriving the closure rather than enumerating it, made
    concrete.
    """
    environ = dict(equipped(tmp_path))
    source = tmp_path / "no-config" / "src"
    _lay_out_the_host_package(source)
    (source / "gramps_live_api" / "config.py").unlink()
    environ["GRAMPS_LIVE_API_SRC"] = str(source)

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert not checks["source"].ok, "a package with no config.py was accepted"
    assert "config" in checks["source"].detail, checks["source"].detail


def test_the_candidate_the_HOST_would_bind_is_the_one_checked(tmp_path: Path) -> None:
    """⛔ The host's effective order is the REVERSE of the loop that builds it.

    ⚠️ ``sys.path.insert(0, candidate)`` per candidate means the **last** one
    inserted ends up **first** on the path. Checking them in loop order answered
    about the lowest-precedence directory: a valid explicit source beside a
    partial junction-derived one reported **ready** from the explicit one while
    the host bound the partial one and failed on import.

    ⭐ And a REGULAR package does not fall through: once a directory named
    ``gramps_live_api`` **holding an ``__init__.py``** is found, the package is
    bound there, so a complete copy further down the path does not rescue it.

    ⛔ **The qualifier is load-bearing and this test used to omit it.** It said
    *"once a directory named gramps_live_api is found"*, full stop, and built its
    partial package with no ``__init__.py`` -- which makes it a **namespace
    portion**, and Python then CONTINUES the search and binds the complete copy
    further down. The assertion passed only because the check being tested held
    the same false belief. **Running the import instead of modelling it is what
    surfaced this**, which is #174's whole argument.
    """
    environ = dict(equipped(tmp_path))
    complete = tmp_path / "explicit" / "src"
    _lay_out_the_host_package(complete)
    environ["GRAMPS_LIVE_API_SRC"] = str(complete)

    # A partial package beside the plugin -- the candidate the host inserts LAST,
    # and therefore the one it actually binds.
    plugin_dir = _plugin_dir(environ)
    partial = plugin_dir / "gramps_live_api" / "host"
    partial.mkdir(parents=True, exist_ok=True)
    (partial / "accessor.py").write_text("", encoding="utf-8")
    # ⛔ A REGULAR package, so Python binds here and does not fall through.
    (plugin_dir / "gramps_live_api" / "__init__.py").write_text("", encoding="utf-8")
    (partial / "__init__.py").write_text("", encoding="utf-8")

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert not checks["source"].ok, (
        "check reported ready from the explicit source while the host would bind "
        "the partial package beside the plugin"
    )
    assert str(plugin_dir) in checks["source"].detail, (
        f"the refusal names the wrong directory: {checks['source'].detail}"
    )


# ⛔ Is the personal-data guard wired to anything?
# ---------------------------------------------------------------------------


def test_check_reports_the_push_gate_as_installed_when_our_hook_is_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⭐ Installed, and reported with its bypass named rather than hidden."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    # ⛔ The CANONICAL content, because the check now compares against it. A stub
    # carrying only the marker is exactly what "stale" means, and writing one
    # here would assert that a stale hook is reported as the gate.
    canonical_text = (
        Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "pre-push"
    ).read_text(encoding="utf-8")
    # ⛔ The fixture gets its OWN canonical copy, so CHECKOUT_ROOT stays tmp_path
    # and the check compares two files that both live inside the fixture.
    canonical = tmp_path / "scripts" / "hooks" / "pre-push"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(canonical_text, encoding="utf-8")
    hook = hooks / "pre-push"
    hook.write_text(canonical_text, encoding="utf-8")
    # ⛔ Executable, because the check now requires it. On Windows this line is
    # a no-op, which is exactly why the omission was invisible here and red on
    # every Linux runner.
    hook.chmod(0o755)
    monkeypatch.setattr(cli, "CHECKOUT_ROOT", tmp_path)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "hooks\n", ""),
    )

    check = THE_REAL_PUSH_GATE_CHECK()

    assert check.ok, check.detail
    assert "--no-verify" in check.detail, (
        "the gate must not be reported as though it were unbypassable"
    )


def test_check_reports_the_push_gate_as_MISSING_and_names_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ The state this project was actually in, and nothing said so."""
    (tmp_path / "hooks").mkdir()
    monkeypatch.setattr(cli, "CHECKOUT_ROOT", tmp_path)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "hooks\n", ""),
    )

    check = THE_REAL_PUSH_GATE_CHECK()

    assert not check.ok
    assert "NOT installed" in check.detail
    assert "cp scripts/hooks/pre-push" in check.detail, (
        "a refusal that names a condition and stops is where a setup gets abandoned"
    )


def test_SOMEONE_ELSES_pre_push_hook_is_not_reported_as_this_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ Present is not the same as ours.

    ⚠️ A hook at that path doing something else entirely would satisfy an
    existence check, and ``check`` would then report the personal-data gate as
    wired up when nothing runs the guard at all. **That is worse than reporting
    nothing**, because it is a false assurance about the one thing standing
    between this tree and a public repository.
    """
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text("#!/bin/sh\nexec npm test\n", encoding="utf-8")
    monkeypatch.setattr(cli, "CHECKOUT_ROOT", tmp_path)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "hooks\n", ""),
    )

    check = THE_REAL_PUSH_GATE_CHECK()

    assert not check.ok, "a foreign pre-push hook was reported as this project's gate"
    assert "not this one" in check.detail, check.detail


@pytest.mark.skipif(os.name == "nt", reason="Windows has no executable bit to withhold")
def test_a_NON_EXECUTABLE_hook_is_not_reported_as_a_working_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ Git ignores a hook it cannot execute, and pushes anyway.

    ⚠️ Git 2.43 says so explicitly and then proceeds, so reporting ``ok`` here is
    false assurance **in exactly the state this check exists to detect**.

    ⭐ And the mode is easy to lose rather than exotic: this repository's own hook
    reached the index as ``100644``, because Windows git does not track the file
    mode by default. CI caught it on the first Linux run.
    """
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-push"
    hook.write_text(f"#!/bin/sh\npython -m {cli.HOOK_MARKER} .\n", encoding="utf-8")
    hook.chmod(0o644)
    # ⛔ An IDENTICAL canonical file, so this test isolates the executable
    # bit and nothing else. Without it the staleness check answered first and
    # the test asserted a message about the canonical being unreadable -- green
    # on Windows, where the mode check is skipped, and red on every Linux leg.
    canonical = tmp_path / "scripts" / "hooks" / "pre-push"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(hook.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(cli, "CHECKOUT_ROOT", tmp_path)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "hooks\n", ""),
    )

    check = THE_REAL_PUSH_GATE_CHECK()

    assert not check.ok, "a hook git would ignore was reported as a working gate"
    assert "NOT EXECUTABLE" in check.detail, check.detail


def test_a_STALE_installed_hook_is_not_reported_as_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ Installation is a ``cp``, and git does not refresh what was copied.

    ⚠️ Pull a fixed ``scripts/hooks/pre-push`` and the installed one keeps every
    defect it had — while carrying the same marker, so a substring check called
    it installed. **That is false assurance in exactly the shape this check
    exists to prevent:** a gate reported as wired up while running last month's
    rules.

    ⭐ It caught a real one the moment it was written — the hook installed on
    this project's own machine predated three fixes to the ref-range logic.

    Content, not a version string: a version has to be remembered on every
    change, and the bytes cannot fall out of step with themselves.
    """
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    canonical = (Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "pre-push").read_text(
        encoding="utf-8"
    )
    hook = hooks / "pre-push"
    hook.write_text(canonical + "\n# an older copy, missing later fixes\n", encoding="utf-8")
    hook.chmod(0o755)
    monkeypatch.setattr(cli, "CHECKOUT_ROOT", Path(__file__).resolve().parents[2])
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, str(hooks) + "\n", ""),
    )

    check = THE_REAL_PUSH_GATE_CHECK()

    assert not check.ok, "a stale copy of the hook was reported as the gate"
    assert "STALE" in check.detail, check.detail


def test_an_IDENTICAL_installed_hook_is_reported_as_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⚠️ The other direction: the staleness check must not fail every install.

    ⭐ Compared as text with newlines normalised, because the canonical file is
    stored ``eol=lf`` and a Windows working tree legitimately holds CRLF — a byte
    comparison would report **every** Windows installation as stale.
    """
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    canonical_path = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "pre-push"
    hook = hooks / "pre-push"
    # ⛔ Written back with CRLF deliberately: that is what a Windows checkout has.
    hook.write_bytes(canonical_path.read_text(encoding="utf-8").replace("\n", "\r\n").encode())
    hook.chmod(0o755)
    monkeypatch.setattr(cli, "CHECKOUT_ROOT", Path(__file__).resolve().parents[2])
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, str(hooks) + "\n", ""),
    )

    check = THE_REAL_PUSH_GATE_CHECK()

    assert check.ok, f"an identical hook with CRLF was called stale: {check.detail}"


def test_an_UNREADABLE_canonical_hook_is_refused_rather_than_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ A check that cannot answer must not answer yes.

    ⚠️ Swallowing the read error left the wanted content empty, and the guard
    reading ``if wanted and ...`` then **disabled the staleness comparison
    entirely** — so a sparse checkout or a deleted canonical file turned this
    back into *any executable hook counts*, which is the assurance it was added
    to remove.

    ⭐ Same rule the hook itself already applies to a missing interpreter and to
    a ref it cannot scan: cannot answer means refuse.
    """
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-push"
    hook.write_text(f"#!/bin/sh\npython -m {cli.HOOK_MARKER} .\n", encoding="utf-8")
    hook.chmod(0o755)
    # ⛔ A checkout root with no scripts/hooks/pre-push in it at all.
    monkeypatch.setattr(cli, "CHECKOUT_ROOT", tmp_path / "no-such-checkout")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, str(hooks) + "\n", ""),
    )

    check = THE_REAL_PUSH_GATE_CHECK()

    assert not check.ok, "an unreadable canonical hook disabled the staleness check"
    assert "cannot read" in check.detail, check.detail


def test_a_NAMESPACE_portion_does_not_bind_and_python_falls_through(tmp_path: Path) -> None:
    """⭐ #174's fifth defect, asserted as the behaviour rather than the belief.

    ⛔ A directory named ``gramps_live_api`` with **no ``__init__.py``** is a
    namespace portion. Python records it and **continues the search**, so a
    complete regular package further down the path binds instead.

    ⚠️ The replaced check believed the opposite -- *"Python binds a package at the
    first directory of that name and does not fall through"* -- and refused a
    setup that in fact works. **Running the import is what settled it**, and this
    test exists so nobody reinstates the belief.
    """
    environ = dict(equipped(tmp_path))
    complete = tmp_path / "explicit" / "src"
    _lay_out_the_host_package(complete)
    environ["GRAMPS_LIVE_API_SRC"] = str(complete)

    # A bare directory of the right name beside the plugin: a namespace portion,
    # NOT a package, and therefore not what binds.
    (_plugin_dir(environ) / "gramps_live_api").mkdir(parents=True, exist_ok=True)

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert checks["source"].ok, (
        "an empty directory is a namespace portion, so the host falls through to "
        f"the complete package and the route works: {checks['source'].detail}"
    )


def test_the_check_runs_a_real_import_and_names_what_failed(tmp_path: Path) -> None:
    """⛔ The refusal quotes Python's own error, not a model's conclusion.

    ⭐ That is the whole point of #174: five defects came from re-deriving import
    resolution, so the check now reports what the interpreter said.
    """
    environ = dict(equipped(tmp_path))
    broken = tmp_path / "explicit" / "src" / "gramps_live_api"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "__init__.py").write_text(
        "raise RuntimeError('this package is broken')\n", encoding="utf-8"
    )
    environ["GRAMPS_LIVE_API_SRC"] = str(tmp_path / "explicit" / "src")

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert not checks["source"].ok
    assert "RuntimeError" in checks["source"].detail, checks["source"].detail
    assert "this package is broken" in checks["source"].detail, checks["source"].detail


def test_PYTHONPATH_cannot_satisfy_the_source_check(tmp_path: Path) -> None:
    """⛔ ``-S`` drops ``site``; it does NOT drop ``PYTHONPATH``.

    ⚠️ ``docs/using.md`` tells the owner to set ``PYTHONPATH=src``, so the
    documented setup was precisely the one that defeated the isolation: a copied
    plugin with no ``GRAMPS_LIVE_API_SRC`` would import the checkout through
    ``PYTHONPATH`` and report ready for a route Gramps cannot start.

    ⭐ Gramps' interpreter has neither, which is what ``-E -S`` reproduces.
    """
    environ = dict(equipped(tmp_path))
    del environ["GRAMPS_LIVE_API_SRC"]
    environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert not checks["source"].ok, (
        "PYTHONPATH satisfied the check for a route Gramps has no PYTHONPATH on: "
        f"{checks['source'].detail}"
    )


def test_the_WORKING_DIRECTORY_cannot_satisfy_the_source_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ The third route into the child, and the one ``-E`` does not close.

    ⚠️ ``python -c`` prepends the current directory to ``sys.path``. Running
    ``check`` from the checkout's ``src`` -- or any directory holding
    ``gramps_live_api`` -- let the child import it even when the copied plugin
    and ``GRAMPS_LIVE_API_SRC`` offered nothing.

    ⭐ Three routes in: ``site``, ``PYTHONPATH``, and the working directory. Each
    was found by review after the previous one was closed, which is what a
    mechanism reasoned about rather than measured looks like.
    """
    environ = dict(equipped(tmp_path))
    del environ["GRAMPS_LIVE_API_SRC"]
    monkeypatch.chdir(Path(__file__).resolve().parents[2] / "src")

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert not checks["source"].ok, (
        "the working directory satisfied the check for a route Gramps does not "
        f"run from: {checks['source'].detail}"
    )
