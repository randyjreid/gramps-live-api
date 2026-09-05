"""The one command the owner types: ``check``, the install doctor.

⛔ **The write commands are gone.** ``preview``, ``apply`` and the ``approve``
console read an operation file and wrote a note into the blessed copy without
the document route; R9 retires all three with the note flow, leaving the
document route as the only write path an agent can reach.

⚠️ **What ``check`` reports on is a SETUP, not a write.** It stats directories
and never opens a database, so it can say the runtime is missing, the plugin is
not registered, the copy is not blessed or the tree is locked without touching
anything. The rail that decides a write still lives inside Gramps, against the
database Gramps has already opened.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from gramps_live_api import config
from gramps_live_api.core import apply

LOCK_FILE = "lock"
"""What Gramps drops in a tree directory it has open, per ``cli/clidbman.py``."""

_PLUGIN_GLOB = "gramps*/plugins/**/gramps_live_api_host.gpr.py"
"""Where a registered plugin would be found under Gramps' user data directory.

⛔ **Keyed on the HOST registration, and R9's measured checklist is why.** It
used to name ``gramps_live_api_apply.gpr.py`` -- the registration the retirement
deletes -- and ``_plugin_check`` is the only thing that locates the plugin
directory at all. Left pointing there, ``check`` would report the plugin absent
on every invocation whatever else was present, and ``_source_check`` would then
have no directory to compare ``PLUGIN_FILES`` against.

⭐ **The host registration is the right one on its own terms, not merely the
surviving one.** It is what makes Gramps start the document route, which is now
the only write path there is."""


@dataclass(frozen=True, slots=True)
class Check:
    """One line of the doctor's report."""

    label: str
    ok: bool
    detail: str


def main(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run one command and return its exit code.

    Both streams and the environment are arguments with real defaults, so the
    whole front end is exercised by unit tests without a process, a terminal or
    a tree.

    ⚠️ **``stdin`` and ``runner`` are gone with the write commands.** They were
    injected so a console prompt and a Gramps launch could be driven from a
    test; nothing here reads a person's answer or starts a process any more.
    """
    settings = argparse.ArgumentParser(prog="gramps_live_api", description=__doc__)
    commands = settings.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("check", help="report on the runtime, the copy and the plugin")
    doctor.add_argument("tree", nargs="?", help="a tree to report on; defaults to the copy")

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    settings_environ = os.environ if environ is None else environ
    arguments = settings.parse_args(list(argv))

    try:
        return _check(arguments.tree, settings_environ, out=out, err=err)
    except (config.ConfigError, apply.ApplyError, OSError) as failure:
        print(failure, file=err)
        return 1


# ---------------------------------------------------------------------------
# check -- read-only, and it never opens a database
# ---------------------------------------------------------------------------


def _check(tree: str | None, environ: Mapping[str, str], *, out: TextIO, err: TextIO) -> int:
    checks = inspect(tree, environ)
    for check in checks:
        print(f"  {'ok' if check.ok else 'NO'}   {check.label}: {check.detail}", file=out)
    failing = [check.label for check in checks if not check.ok]
    if failing:
        print(f"\nnot ready: {', '.join(failing)}", file=out)
        return 1
    print("\nready", file=out)
    return 0


def inspect(tree: str | None, environ: Mapping[str, str]) -> list[Check]:
    """The doctor's whole report. **Stats directories; opens nothing.**

    With a tree argument it reports on any tree, so the owner can point it at
    the live one and watch the refusal happen. That is the advisory copy of the
    rail, and the report says so.
    """
    plugin = _plugin_check(environ)
    checks = [
        _runtime_check(environ),
        plugin,
        _source_check(plugin, environ),
        _push_gate_check(),
    ]
    settings = config.load(environ)
    target = tree or settings.copy_path
    if target is None:
        checks.append(
            Check(
                "copy",
                False,
                f"no copy is configured -- set copy_path in {config.user_config_path(environ)} "
                f"or {config.ENV_COPY}, or name a tree on the command line",
            )
        )
        return checks

    resolved = os.path.realpath(target)
    checks.append(Check("copy", True, resolved))
    for required, why in (
        (apply.NAME_FILE, "a Gramps family tree directory"),
        (apply.SENTINEL_NAME, "blessed for writing by hand"),
    ):
        there = os.path.isfile(os.path.join(resolved, required))
        checks.append(Check(required, there, f"{'is' if there else 'is NOT'} {why}"))
    locked = os.path.isfile(os.path.join(resolved, LOCK_FILE))
    checks.append(
        Check(
            "lock",
            not locked,
            # ⛔ **The remedy, not just the condition.** The bare word "locked"
            # was what the owner met on demo day: true, and it does not say what
            # to do. A refusal that names a condition and stops makes the reader
            # go and find the document that explains it -- which is the moment a
            # setup gets abandoned.
            #
            # ⚠️ It deliberately does NOT offer to remove the lock. Breaking a
            # lock Gramps is holding is how a tree gets corrupted, and naming the
            # remedy is not the same as offering to perform it.
            "locked -- Gramps has this tree open, and we never break its lock. "
            "Close the tree in Gramps (Family Trees, then Close) and run this "
            "again. If Gramps is not running, the lock is stale and Gramps "
            "itself will offer to clear it next time you open that tree."
            if locked
            else "not locked",
        )
    )
    return checks


def _runtime_check(environ: Mapping[str, str]) -> Check:
    settings = config.load(environ)
    runtime = settings.runtime or config.discover_runtime(environ)
    if runtime is None:
        return Check("runtime", False, f"no {config.RUNTIME_NAME} found; set gramps_runtime")
    return Check("runtime", os.path.isfile(runtime), runtime)


CHECKOUT_ROOT = Path(__file__).resolve().parents[2]
"""The checkout this module was loaded from.

⚠️ Derived from ``__file__`` rather than from the working directory, because
``check`` is run from anywhere and the question *is the push gate installed* is
about **this checkout**, not about wherever the shell happens to be."""

HOOK_MARKER = "gramps_live_api.core.pii_guard"
"""What makes an installed ``pre-push`` OURS rather than merely present.

⚠️ Someone else's hook at that path is not this gate, and reporting it as one
would be worse than reporting nothing."""


def _push_gate_check() -> Check:
    """⛔ Is the personal-data guard actually wired to anything?

    ⚠️ **It was not, and that is why this exists.** No hook, no
    ``.pre-commit-config.yaml``, no ``core.hooksPath``, and ``CONTRIBUTING``
    asking a contributor to remember. CI runs ``on: push``, so by the time its
    guard job starts GitHub already holds the objects -- on a public repository
    that is publication. **CI detects; it cannot prevent.** Issue #171.

    ⭐ Git never installs a hook from a clone, by design, so this cannot install
    itself. **What it can do is refuse to let the installation go unverified** --
    a gate whose wiring nothing reports is the same convention one level down.

    ⛔ It does not claim the hook is unbypassable. ``git push --no-verify`` skips
    it and always will.
    """
    try:
        hooks = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=CHECKOUT_ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return Check("push gate", False, "not a git checkout, so no hook can be installed here")

    installed = CHECKOUT_ROOT / hooks / "pre-push"
    if not installed.is_file():
        return Check(
            "push gate",
            False,
            f"NOT installed -- nothing runs pii_guard before a push, and CI only "
            f"finds it after GitHub already has the objects. Install it: "
            f"cp scripts/hooks/pre-push {hooks}/pre-push && chmod +x {hooks}/pre-push",
        )
    try:
        body = installed.read_text(encoding="utf-8", errors="replace")
    except OSError as failure:
        return Check("push gate", False, f"a pre-push hook is present but unreadable: {failure}")

    if HOOK_MARKER not in body:
        return Check(
            "push gate",
            False,
            "a pre-push hook is installed but it is not this one -- it does not run "
            "pii_guard. Whatever it does, the personal-data gate is not wired up",
        )

    # ⛔ **Executable, not merely present.** Git 2.43 reports that it ignored a
    # non-executable hook and PROCEEDS WITH THE PUSH. Reporting ok here would be
    # false assurance in exactly the state this check exists to detect -- and the
    # mode is easy to lose: this repository's own hook reached the index as
    # 100644, because Windows git does not track the file mode by default.
    if os.name != "nt" and not os.access(installed, os.X_OK):
        return Check(
            "push gate",
            False,
            f"{installed} is installed but NOT EXECUTABLE, so git ignores it and "
            f"pushes anyway. chmod +x it",
        )

    # ⛔ **The same hook, or a STALE COPY of it?**
    #
    # ⚠️ Installation is a `cp`, and git does not refresh what was copied. Pull a
    # fixed `scripts/hooks/pre-push` and the installed one keeps every defect it
    # had -- while carrying the same marker, so a substring check called it
    # installed. **That is false assurance in the shape this check exists to
    # prevent**: it reported a gate that was running last month's rules.
    #
    # ⭐ Content, not a version string. A version has to be remembered on every
    # change; the bytes cannot fall out of step with themselves.
    canonical = CHECKOUT_ROOT / "scripts" / "hooks" / "pre-push"
    try:
        # ⚠️ Compared as TEXT with newlines normalised, because the canonical file
        # is stored `eol=lf` and a Windows working tree legitimately holds CRLF.
        # A byte comparison would report every Windows install as stale.
        wanted = canonical.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as failure:
        # ⛔ **Unreadable is REFUSED, not skipped.** Swallowing this left `wanted`
        # empty and the `if wanted and ...` guard then disabled the whole
        # staleness comparison -- so a sparse checkout or a deleted canonical
        # file turned the check back into "any executable hook counts", which is
        # the assurance it was added to remove. A check that cannot answer must
        # not answer yes.
        return Check(
            "push gate",
            False,
            f"cannot read {canonical} to compare against the installed hook "
            f"({failure}), so whether the gate is current cannot be established",
        )
    if body.splitlines() != wanted:
        return Check(
            "push gate",
            False,
            f"{installed} is a STALE copy -- it differs from "
            f"scripts/hooks/pre-push, so it is running an older version of the "
            f"gate. Installation is a copy and git does not refresh it. Re-copy "
            f"it: cp scripts/hooks/pre-push {installed}",
        )
    return Check("push gate", True, f"{installed} (bypassable with --no-verify)")


def _plugin_check(environ: Mapping[str, str]) -> Check:
    root = _gramps_user_data(environ)
    found = sorted(root.glob(_PLUGIN_GLOB)) if root.is_dir() else []
    if not found:
        return Check("plugin", False, f"not installed under {root}")
    return Check("plugin", True, str(found[0].parent))


# ⛔ The candidates the HOST plugin prepends to ``sys.path``, in its order.
#
# ⚠️ **Transcribed, not imported, and that is a duplication with a guard.**
# ``gramps_live_api_host`` imports Gramps at module scope, so this half of the
# project cannot import it -- the same reason ``_gramps_user_data`` transcribes
# Gramps' own rule. ``test_the_source_check_matches_what_the_host_actually_does``
# reads the plugin's source and fails if the two lists stop agreeing, because two
# spellings of one rule is this project's most-recorded defect class.
_HOST_SRC_ENV = "GRAMPS_LIVE_API_SRC"


def _host_source_candidates(plugin_dir: str, environ: Mapping[str, str]) -> list[str]:
    """Where the host plugin will look for ``gramps_live_api``, in its order."""
    here = os.path.realpath(plugin_dir)
    return [
        environ.get(_HOST_SRC_ENV, ""),
        os.path.join(os.path.dirname(here), "src"),
        here,
    ]


PLUGIN_FILES = (
    "gramps_live_api_host.gpr.py",
    "gramps_live_api_host.py",
    "gramps_live_api_writer.py",
)
"""Every file the plugin directory must hold for the document route to start.

⛔ **The two apply plugin files are gone with the note flow**, and so is the
reason this tuple used to be longer than what ``_PLUGIN_GLOB`` finds: discovery
was keyed on the apply registration, so finding it proved only that something was
installed and this listed the host's files to catch a directory that registered
no host at all. Discovery is now keyed on the host registration itself.

⚠️ **It is still not one file, and the writer is why.** Gramps ``exec``s a plugin
rather than importing it, so the plugin folder is not on ``sys.path``, and the
host adds its own directory precisely so the writer can be imported by name. A
directory carrying the registration and not the writer registers a host that dies
on the first document."""

HOST_MODULES = (
    "config",
    # ⚠️ **Not under ``host/``, and that is the point of computing the closure
    # rather than listing the directory.** ``host.document`` imports the frozen
    # note-type table, which lives in ``core/`` because it is the vocabulary both
    # routes validate against. A package missing it starts no host.
    "core._note_types",
    "host.accessor",
    "host.auth",
    "host.backup",
    "host.document",
    "host.httpd",
    "host.log",
    "host.mainthread",
    "host.paths",
    "host.reads",
    "host.service",
    "host.status",
    "host.tokens",
)
"""⛔ The modules the host plugin imports from ``gramps_live_api.host``.

⚠️ **A directory named ``gramps_live_api`` is not the package.** An empty or
partial one satisfied ``isdir`` and this check reported ready, while host
startup then died on ``from gramps_live_api.host import accessor, service`` --
the same defect this check exists to catch, one level down. **The test fixture
that exercised the check created exactly such a directory**, which is how it was
found.

⚠️ **The shim's own five were not enough, and the gap was silent.** ``service``
imports ``httpd``, ``log``, ``mainthread``, ``reads``, ``status`` and ``tokens``
at module scope, and ``accessor`` reaches several of them too. A tree holding the
five and missing ``httpd.py`` satisfied the check and then failed inside Gramps
while importing ``service`` -- so ``check`` said ready for a route that could not
start. This is the TRANSITIVE closure.

⭐ **Derived, not enumerated.** A test walks the plugin's imports through every
module they reach and fails if this tuple and that closure disagree in either
direction. Measured, the closure is every module in ``host/`` -- which is the
answer a hand-written list would have been least likely to reach.
"""


def _has_the_package(candidate: str) -> bool:
    """Does a ``gramps_live_api`` directory live here at all?

    ⛔ This is where Python BINDS the package, complete or not. Once a directory
    of that name is found on ``sys.path`` there is no falling through to a later
    entry, so the first one found is the one that has to be whole.
    """
    return bool(candidate) and os.path.isdir(os.path.join(candidate, "gramps_live_api"))


def _missing_from(candidate: str) -> list[str]:
    """Which startup modules this candidate does not carry."""
    package = os.path.join(candidate, "gramps_live_api")
    return [
        module
        for module in HOST_MODULES
        if not os.path.isfile(os.path.join(package, *module.split(".")) + ".py")
    ]


def _source_check(plugin: Check, environ: Mapping[str, str]) -> Check:
    """⛔ Can the host plugin reach ``gramps_live_api`` from where it is installed?

    ⚠️ **``plugin: ok`` does not answer this, and used to be read as if it did.**
    The plugin check finds a ``.gpr.py``; the host then has to import the package
    from the checkout, which it reaches by ``realpath``-ing its own directory and
    stepping up one level. **That works because the plugin directory is a
    junction into the checkout.** Copy the files instead -- a setup ``using.md``
    explicitly supports -- and ``realpath`` lands in Gramps' plugin folder, where
    there is no ``src``, so every document route fails on import while the check
    reports the setup ready.

    ⭐ Stated as the outcome rather than as the mechanism: *is there a directory
    on that list holding the package?* A junction, an explicit
    ``GRAMPS_LIVE_API_SRC``, and a checkout laid out some third way all pass it
    for the same reason the host would.
    """
    if not plugin.ok:
        return Check("source", False, "no plugin to resolve from")
    absent = [
        name for name in PLUGIN_FILES if not os.path.isfile(os.path.join(plugin.detail, name))
    ]
    if absent:
        return Check(
            "source",
            False,
            f"the plugin directory is incomplete -- it is missing "
            f"{', '.join(absent)}. Finding the registration proves Gramps will "
            f"load the host, not that the host can write: without the writer "
            f"beside it every document fails on import",
        )
    # ⛔ **RUN the resolution. Do not replay it.**
    #
    # ⚠️ Five defects came out of re-implementing Python's import resolution here,
    # each a layer deeper than the last: an empty ``gramps_live_api`` directory
    # counted as the package, then the transitive closure and ``config``, then the
    # loop order, then the de-duplication that interacts with that order, then the
    # namespace-package portion. **Every one was a place the replay and the real
    # thing disagreed** -- and #174 was filed unreproduced precisely because the
    # sixth would be too.
    #
    # ⭐ So the answer is not a sixth patch. **The child runs the host's OWN
    # ``_put_the_package_on_the_path`` and then imports**, which is the resolution
    # rather than a model of it. Order, de-duplication, namespace packages and
    # ``__init__`` semantics all come from Python, because Python is doing them.
    outcome = _import_as_the_host_would(plugin.detail, environ)
    if outcome.ok:
        return Check("source", True, outcome.detail)
    return Check("source", False, outcome.detail)


@dataclass(frozen=True)
class _Imported:
    """What a child process found when it imported the way the host does."""

    ok: bool
    detail: str


def _import_as_the_host_would(plugin_directory: str, environ: Mapping[str, str]) -> _Imported:
    """Ask a CHILD process to do exactly what the host does, and report.

    ⛔ **A subprocess, and that is the whole answer to "does this pollute
    ``check``?"** The path manipulation, the imports and any module-level code all
    happen in a process that exits immediately afterwards. ``check``'s own
    ``sys.path`` and ``sys.modules`` are untouched, so a later check cannot be
    influenced by what this one imported -- and importantly, a **broken** copy
    cannot be half-imported into the process that is diagnosing it.

    ⚠️ **The child loads the real plugin file by path and calls its real
    function.** Not a copy of the loop, not a re-derived candidate list: if the
    host's path rule changes, this changes with it, because it is the same code.

    ⚠️ **The environment is passed through**, so ``GRAMPS_LIVE_API_SRC`` means in
    the child exactly what it means in Gramps.

    ⛔ **``-E -S``, and BOTH are needed.** ``check`` runs on the owner's
    interpreter, where this package is installed; Gramps runs on its own, where
    it is not. Without isolation the child imports through a route Gramps does
    not have and reports ready for a setup that cannot start.

    * ``-S`` drops ``site``, so the venv's own install is not visible.
    * ``-E`` drops ``PYTHONPATH``. ⚠️ **``-S`` alone does not** -- and
      ``docs/using.md`` tells the owner to set ``PYTHONPATH=src``, so the
      documented setup was exactly the one that defeated it. **Measured: with
      ``-S`` alone the package imports through ``PYTHONPATH``; with ``-E -S`` it
      does not.**

    ⭐ ``GRAMPS_LIVE_API_SRC`` still reaches the child -- ``-E`` drops only the
    ``PYTHON*`` variables -- so the host's first candidate works as it does in
    Gramps.

    ⭐ The modules imported are the host's own, and ``src/`` imports neither
    ``gramps`` nor ``gi`` -- which is why a child on an ordinary interpreter can
    answer a question about a Gramps plugin at all.
    """
    program = (
        "import importlib, importlib.util, json, os, sys\n"
        # ⛔ **The WORKING DIRECTORY: the third route in, and the one ``-E`` does
        # not close.** ``python -c`` prepends the current directory to
        # ``sys.path``, so running ``check`` from the checkout's ``src`` -- or any
        # directory holding ``gramps_live_api`` -- let the child import it with no
        # usable candidate from the host at all.
        #
        # ⚠️ ``-P`` does exactly this and arrived in 3.11; this repository's floor
        # is 3.10, so it is done in the program and works on every version.
        "sys.path[:] = [p for p in sys.path if p not in ('', '.', os.getcwd())]\n"
        "plugin = sys.argv[1]\n"
        "wanted = json.loads(sys.argv[2])\n"
        "host = os.path.join(plugin, 'gramps_live_api_host.py')\n"
        "report = {}\n"
        "try:\n"
        "    spec = importlib.util.spec_from_file_location('_check_host', host)\n"
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    module._put_the_package_on_the_path()\n"
        "except Exception as failure:\n"
        "    report['setup'] = f'{type(failure).__name__}: {failure}'\n"
        "    print(json.dumps(report))\n"
        "    raise SystemExit(0)\n"
        "failed = {}\n"
        "try:\n"
        "    package = importlib.import_module('gramps_live_api')\n"
        "    report['origin'] = getattr(package, '__file__', None) or '(namespace package)'\n"
        "except Exception as failure:\n"
        "    failed['gramps_live_api'] = f'{type(failure).__name__}: {failure}'\n"
        "for name in wanted:\n"
        "    try:\n"
        "        importlib.import_module('gramps_live_api.' + name)\n"
        "    except Exception as failure:\n"
        "        failed[name] = f'{type(failure).__name__}: {failure}'\n"
        "report['failed'] = failed\n"
        "print(json.dumps(report))\n"
    )
    try:
        finished = subprocess.run(
            [
                sys.executable,
                "-E",
                "-S",
                "-c",
                program,
                plugin_directory,
                json.dumps(list(HOST_MODULES)),
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env={**environ},
            timeout=60,
            check=False,
        )
    except Exception as failure:  # noqa: BLE001 - any failure means "cannot say yes"
        return _Imported(False, f"the import could not be attempted: {failure}")
    # ⛔ Its OUTPUT, not its exit code. A traceback on stderr with a zero exit is
    # the shape this has to survive, and an unparseable answer is not a pass.
    try:
        report = json.loads((finished.stdout or "").strip().splitlines()[-1])
    except Exception:
        detail = (finished.stderr or finished.stdout or "").strip()[-400:]
        return _Imported(False, f"the import attempt returned nothing usable: {detail!r}")

    if "setup" in report:
        return _Imported(
            False,
            f"the host's own path setup did not run from {plugin_directory} -- "
            f"{report['setup']}. That is the code Gramps executes, so the document "
            f"route would fail the same way.",
        )
    failed = report.get("failed") or {}
    if not failed:
        # ⛔ The DIRECTORY, which is what this check has always reported and what
        # a reader can act on -- but **derived from the file Python actually
        # bound**, not from a candidate this process guessed at.
        origin = str(report.get("origin") or "")
        directory = os.path.dirname(os.path.dirname(origin)) if origin.endswith(".py") else ""
        return _Imported(True, directory or origin or plugin_directory)
    named = ", ".join(f"{name} ({why})" for name, why in sorted(failed.items()))
    origin = report.get("origin")
    where = f" It resolved gramps_live_api from {origin}." if origin else ""
    return _Imported(
        False,
        f"the host plugin cannot import {named} from {plugin_directory}.{where} "
        f"The plugin directory is meant to be a junction into the checkout, and a "
        f"copied installation is not one. Re-make it as a junction, or set "
        f"{_HOST_SRC_ENV} to the checkout's src directory. Until then the document "
        f"route fails on import while everything else here passes.",
    )


def _gramps_user_data(environ: Mapping[str, str]) -> Path:
    """Gramps' own user-data rule, transcribed from ``gramps/gen/const.py``.

    Transcribed rather than imported, because importing it would mean importing
    Gramps -- which this half of the project may not do, and which the doctor
    must work without in order to report that Gramps is missing.
    """
    if "GRAMPSHOME" in environ:
        return Path(environ["GRAMPSHOME"]) / "gramps"
    if "APPDATA" in environ:
        return Path(environ["APPDATA"]) / "gramps"
    if "XDG_DATA_HOME" in environ:
        return Path(environ["XDG_DATA_HOME"]) / "gramps"
    return Path(environ.get("HOME", "")) / ".local" / "share" / "gramps"
