"""The commands the owner types: ``preview``, ``apply``, ``check``, ``approve``.

⚠️ **``approve`` is a console window, and it is slice 2's whole trust model.**
The MCP server can spawn it; it cannot type in it. What that window prints comes
off the disk -- the operation stored in the proposal, re-rendered here by the
same ``full_display`` the digest covers -- never off anything an agent sent. If
the window disagrees with what the transcript claimed, the window is right, and
that is the point of the design rather than a caveat on it.

⚠️ **``apply`` exits 0 only when the note was written AND read back.** Every
other outcome -- a declined prompt, a run with no result marker, a read-back
that disagrees, a result record that could not be written -- is non-zero. That
is the one invariant worth having here, because it is the one anything
scripting this can rely on: zero means the note is in the tree.

The read-back runs in a **second, fresh process**. That is what makes it
evidence rather than a restatement: the assertion crosses the database file
instead of a live object graph.

⚠️ **The blessed-copy check run here is ADVISORY.** It exists so a wrong path
meets a clear message at the owner's own terminal instead of a refusal from
inside a Gramps subprocess. The load-bearing check runs in ``core.apply``,
inside Gramps, against ``Tree.save_path()`` -- the database Gramps has already
opened -- because that is the only place the answer cannot be about a different
tree than the one being written.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from gramps_live_api import config, invocation
from gramps_live_api.core import apply, proposals, schema

LOCK_FILE = "lock"
"""What Gramps drops in a tree directory it has open, per ``cli/clidbman.py``."""

_PLUGIN_GLOB = "gramps*/plugins/**/gramps_live_api_apply.gpr.py"
"""Where a registered plugin would be found under Gramps' user data directory."""

_SOURCE_DIRECTORY = str(Path(__file__).resolve().parent.parent)
"""The directory the shim must put on ``sys.path`` to import this package.

Gramps runs on its own frozen interpreter with its own ``sys.path``; nothing
this project installs is on it. The shim prepends this, which is why the tool
works from a checkout with no installation step.
"""


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
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    runner: invocation.Runner | None = None,
) -> int:
    """Run one command and return its exit code.

    Every stream, the environment and the runner are arguments with real
    defaults, so the whole front end is exercised by unit tests without a
    process, a terminal or a tree.
    """
    settings = argparse.ArgumentParser(prog="gramps_live_api", description=__doc__)
    commands = settings.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("preview", "read an operation, validate it, and print the sentence"),
        ("apply", "preview, ask, write into the blessed copy, and read it back"),
    ):
        parser = commands.add_parser(name, help=help_text)
        parser.add_argument("operation", help="the operation file")
    doctor = commands.add_parser("check", help="report on the runtime, the copy and the plugin")
    doctor.add_argument("tree", nargs="?", help="a tree to report on; defaults to the copy")
    console = commands.add_parser(
        "approve", help="show a proposal in full, ask, and write it into the blessed copy"
    )
    console.add_argument("proposal", help="the proposal id the server claimed")

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    settings_environ = os.environ if environ is None else environ
    arguments = settings.parse_args(list(argv))

    try:
        if arguments.command == "preview":
            return _preview(arguments.operation, out=out, err=err)
        if arguments.command == "check":
            return _check(arguments.tree, settings_environ, out=out, err=err)
        if arguments.command == "approve":
            return _approve(
                arguments.proposal,
                settings_environ,
                stdin=sys.stdin if stdin is None else stdin,
                out=out,
                err=err,
                runner=_with_subprocess if runner is None else runner,
            )
        return _apply(
            arguments.operation,
            settings_environ,
            stdin=sys.stdin if stdin is None else stdin,
            out=out,
            err=err,
            runner=_with_subprocess if runner is None else runner,
        )
    except (
        config.ConfigError,
        apply.ApplyError,
        invocation.NoResultMarker,
        proposals.ProposalError,
        schema.SchemaError,
        OSError,
    ) as failure:
        print(failure, file=err)
        return 1


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------


def _preview(path: str, *, out: TextIO, err: TextIO) -> int:
    operation = _operation_at(path)
    result = schema.validate(operation)
    if not result.well_formed:
        for violation in result.violations:
            print(f"{violation.rule.value} {violation.field_path}: {violation.message}", file=err)
        return 1
    print(schema.preview(operation), file=out)
    return 0


def _operation_at(path: str) -> schema.Operation:
    # ⚠️ **``utf-8-sig``, and that was found by using it.** Windows PowerShell
    # 5.1 writes a byte order mark with `-Encoding utf8`, which is exactly how
    # the owner produces this file following docs/using.md on the machine this
    # slice targets -- and a plain utf-8 read refuses perfectly good JSON with a
    # decoder message on his first run. utf-8-sig reads both spellings.
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as failure:
        raise schema.SchemaError(f"{path}: {failure}") from failure
    if not isinstance(payload, Mapping):
        raise schema.SchemaError(f"{path}: an operation is an object")
    return schema.from_dict(payload)


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
    checks = [_runtime_check(environ), plugin, _source_check(plugin, environ)]
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
    checks.append(_export_check(settings, environ))
    return checks


def _export_check(settings: config.Settings, environ: Mapping[str, str]) -> Check:
    """The export ``list_people`` reads, and whether it still speaks for the copy.

    ⚠️ **The copy is read from the SETTINGS here, not passed in, and that is
    L4.** This used to take ``inspect``'s ``resolved`` -- which is the tree
    NAMED ON THE COMMAND LINE whenever there is one -- through a parameter
    called ``copy``. ``docs/using.md`` documents ``check <live tree>`` and tells
    the owner to run it, so the wrong tree was not a corner: pointing it at a
    tree touched since the export reported a false staleness, and pointing it at
    an old scratch tree reported a genuinely stale export as current. **The
    second direction is the fail-open this whole check exists to forbid.**

    The question is not *is this export newer than whatever you typed*. It is
    *does this export still speak for the copy ``list_people`` will answer
    about*, and the copy is a configured value. Taking it as an argument made
    that a fact about a call site.

    ⚠️ **The staleness comparison is a PRIVACY check, and that is why it fails
    the doctor rather than warning inside a passing report.** The two kinds of
    staleness fail in opposite directions. A stale *handle* fails closed at the
    write -- ``TargetNotFound`` or ``TargetDisagrees`` -- and costs the owner a
    confusing refusal. A stale ``priv`` **flag fails open**: a person marked
    private in the copy after the export was taken is still listed by
    ``list_people`` and still accepted as a target, and nothing anywhere says so.
    Ruling 1 bounds this feature by the tree's own mechanism, and a mechanism
    read out of a snapshot older than the tree is not the tree's mechanism.

    ⚠️ **It compares against files directly INSIDE the tree directory only**,
    which is what keeps our own writes out of the comparison: the undo records
    and the proposal store are subdirectories, so minting a proposal cannot make
    the doctor report its own side effect. What it does over-report is a copy
    Gramps merely opened -- the lock file is touched either way. That direction
    is deliberate: this answer has to be wrong toward *this snapshot may not
    speak for the copy*, never toward *the flag you are reading is current*.

    ⚠️ **So freshness that cannot be READ fails too**, and it says so in
    different words from a genuinely stale export. An ACL can permit access to
    known files while denying the listing; the comparison then has no left-hand
    side, and reporting *ready* over it is the sentence above being false in the
    forbidden direction. Two states, two messages, because the remedies differ:
    one is *re-stamp it once Gramps is closed*, the other is *this cannot be
    checked at all*.

    ⚠️ **And that remedy is NOT "export the tree again", which is #77.** You can
    only export from inside Gramps, and Gramps writes ``sqlite.db`` and
    ``meta_data.db`` when it CLOSES -- 46 seconds after the export, measured on
    the owner's box -- so every export is older than the copy by the time the
    application has exited, and a second one reproduces the ordering one cycle
    later. ``Copy-Item`` does not help either: it preserves ``LastWriteTime``, so
    the copy arrives stale with content identical to the fresh export. What works
    is re-stamping the export after Gramps has closed, and the message says both
    what that asserts and what it does not -- the comparison reads two timestamps
    and never opens the file, so a stamp on a genuinely old export defeats it.
    **A refusal naming a remedy that cannot work is the refusal lying**, which is
    a worse failure than the staleness it reports.

    ⚠️ **An export that is NOT CONFIGURED is a different state from all three of
    those, and it does not fail the doctor.** Slice 1's ``preview``, ``apply``
    and ``check`` read no export; only slice 2's tools do. ``docs/using.md``
    shows a config file holding one key -- ``copy_path`` -- and a report ending
    *ready*, which is the setup the owner actually performed, so failing it
    regresses a demo that passed in order to report a feature nobody has set up.
    What the line does instead is name the two tools that cannot run, because a
    passing report that stayed silent about it would be the other half of the
    same defect.

    **Absence and staleness are not one state, and only one of them is a
    privacy question.** There is no fail-open here to protect against: with no
    export configured there is nothing for ``list_people`` to read a stale
    ``priv`` flag out of. ``docs/slice2-mcp.md``'s ruling -- that a stale export
    fails the doctor rather than warning inside a passing report -- is about a
    snapshot that is lying, and it is unchanged below.
    """
    if settings.export_path is None:
        return Check(
            "export",
            True,
            "not configured, and nothing in slice 1 needs one -- list_people and "
            "propose_note are what cannot run. Set export_path in "
            f"{config.user_config_path(environ)} or {config.ENV_EXPORT} to use them",
        )
    export = os.path.realpath(settings.export_path)
    if not os.path.isfile(export):
        return Check("export", False, f"{export} is not a file")
    taken = os.path.getmtime(export)
    if settings.copy_path is None:
        # ⚠️ **Nothing to be stale AGAINST, and that is not the same as being
        # fresh.** ``list_people`` reads the export and needs no copy at all --
        # a test asserts that -- so this is a real configuration rather than a
        # half-finished one. What cannot be answered here is the staleness
        # question, and saying so is the honest report. It is not the forbidden
        # direction: the fail-open being guarded against is a ``priv`` flag read
        # out of a snapshot older than the copy, and there is no copy.
        return Check(
            "export",
            True,
            f"{export} -- no copy is configured, so whether it still speaks for one "
            "was not compared",
        )
    copy = os.path.realpath(settings.copy_path)
    try:
        changed = _copy_touched(copy)
    except OSError as failure:
        return Check(
            "export",
            False,
            f"whether {export} still speaks for the copy could not be established: "
            f"{copy} could not be read -- {failure.strerror or failure}. The privacy "
            "flag the export carries may already be stale and nothing here can tell, "
            "so this fails rather than call an export current that it did not check. "
            "Make the copy's own files readable",
        )
    if changed is not None and changed > taken:
        quoted = export.replace("'", "''")
        return Check(
            "export",
            False,
            f"{export} is older than the copy, so the privacy flag it carries may be "
            "stale -- a person marked private since it was taken would still be listed. "
            "Exporting again will not clear this: you can only export from inside Gramps, "
            "and Gramps writes the tree's own files when it CLOSES, after your export, so "
            "the next one lands stale the same way. What is out of date here is the "
            "timestamp; the contents may be perfectly current. So close Gramps, and if "
            "nothing has changed the tree since you took this file, re-stamp it: "
            f"(Get-Item '{quoted}').LastWriteTime = Get-Date. That claims only that the "
            "export is at least as new as the tree -- nothing here reads what is inside "
            "it, so stamping one the tree really has moved past defeats the check",
        )
    return Check("export", True, export)


def _copy_touched(copy: str) -> float | None:
    """When the copy's own files were last written, or ``None`` if it holds none.

    Non-recursive on purpose. See ``_export_check``.

    ⚠️ **A copy that cannot be READ raises rather than answering ``None``**, and
    the two were the same answer until C1-2. *Nothing in it was written* and *it
    could not be listed* are different facts with opposite consequences: the
    first is evidence the export is still current, the second is the absence of
    any evidence at all, and collapsing them let ``check`` print **ready** over
    a freshness comparison it had never made.
    """
    stamps = [
        entry.stat().st_mtime for entry in os.scandir(copy) if entry.is_file(follow_symlinks=False)
    ]
    return max(stamps) if stamps else None


def _runtime_check(environ: Mapping[str, str]) -> Check:
    settings = config.load(environ)
    runtime = settings.runtime or config.discover_runtime(environ)
    if runtime is None:
        return Check("runtime", False, f"no {config.RUNTIME_NAME} found; set gramps_runtime")
    return Check("runtime", os.path.isfile(runtime), runtime)


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
    "gramps_live_api_apply.gpr.py",
    "gramps_live_api_apply.py",
    "gramps_live_api_host.gpr.py",
    "gramps_live_api_host.py",
    "gramps_live_api_writer.py",
)
"""Every file the plugin directory must hold for BOTH routes to start.

⛔ ``_PLUGIN_GLOB`` finds one of these -- the apply registration -- and finding it
proved only that something was installed. **A directory holding that file and not
``gramps_live_api_host.gpr.py`` registers no host at all**, so Gramps never starts
the document route while every line of the report reads ok.

⚠️ The writer is here too and is not optional: Gramps ``exec``s a plugin rather
than importing it, so the plugin folder is not on ``sys.path``, and the host adds
its own directory precisely so the writer can be imported by name."""

HOST_MODULES = (
    "config",
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
            f"{', '.join(absent)}. Finding one .gpr.py proves something is "
            f"installed, not that both routes can start: without the host "
            f"registration Gramps never starts the document route at all",
        )
    # ⛔ **In the host's EFFECTIVE order, which is the REVERSE of its loop.**
    #
    # ⚠️ The host does ``sys.path.insert(0, candidate)`` for each in turn, so the
    # LAST one it inserts ends up FIRST on the path. Checking them in loop order
    # answered about the lowest-precedence directory: a valid explicit
    # ``GRAMPS_LIVE_API_SRC`` beside a partial junction-derived ``src`` reported
    # ready from the explicit one while the host bound the partial one and died
    # on import. Replayed, the host resolves the plugin directory and the check
    # named the explicit source.
    candidates = [c for c in _host_source_candidates(plugin.detail, environ) if c]
    effective = next((c for c in reversed(candidates) if _has_the_package(c)), None)

    if effective is not None:
        absent_modules = _missing_from(effective)
        if not absent_modules:
            return Check("source", True, effective)
        return Check(
            "source",
            False,
            f"the host resolves gramps_live_api from {effective} -- it is first on "
            f"the path the host builds -- and that copy is missing "
            f"{', '.join(absent_modules)}. Python binds a package at the first "
            f"directory of that name and does not fall through to a later one, so "
            f"a complete copy elsewhere does not rescue this",
        )
    return Check(
        "source",
        False,
        f"the host plugin cannot reach a COMPLETE gramps_live_api from "
        f"{plugin.detail} -- it needs gramps_live_api/host/ carrying "
        f"{', '.join(HOST_MODULES)}. The plugin directory is meant to be a "
        f"junction into the checkout, and a copied installation is not one. "
        f"Re-make it as a junction, or set {_HOST_SRC_ENV} to the checkout's src "
        f"directory. Until then the document route fails on import while "
        f"everything else here passes.",
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


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def _apply(
    path: str,
    environ: Mapping[str, str],
    *,
    stdin: TextIO,
    out: TextIO,
    err: TextIO,
    runner: invocation.Runner,
) -> int:
    settings = config.load(environ)
    if settings.copy_path is None:
        raise config.ConfigError(
            f"no copy is configured -- set copy_path in {config.user_config_path(environ)} "
            f"or {config.ENV_COPY}"
        )
    runtime = settings.runtime or config.discover_runtime(environ)
    if runtime is None:
        raise config.ConfigError(f"no {config.RUNTIME_NAME} found; set gramps_runtime")

    operation = _operation_at(path)
    result = schema.validate(operation)
    if not result.well_formed:
        for violation in result.violations:
            print(f"{violation.rule.value} {violation.field_path}: {violation.message}", file=err)
        return 1

    # Advisory, and early: a wrong path should meet a sentence at this terminal
    # rather than a refusal from inside a Gramps subprocess. The check that
    # decides runs in core.apply, against the database Gramps has opened.
    copy = apply.authorise(settings.copy_path)
    sentence = schema.preview(operation)
    print(sentence, file=out)
    # ⚠️ **Nothing is written that was not shown.** The sentence above elides
    # free text at 60 characters, and the approval used to be compared as that
    # elided string -- so everything past the limit went into the tree without
    # having been displayed or approved. The digest below now binds the whole
    # operation, and this prints the rest of what the digest covers, because a
    # binding the operator cannot read is not an approval.
    #
    # Printed only when it differs, so the ordinary short note still shows one
    # line and the prompt stays where the eye expects it.
    entire = schema.full_display(operation)
    if entire != sentence:
        print(f"  in full: {entire}", file=out)
    print(f"write this into {copy.tree_dir}? [y/N] ", end="", file=out)
    out.flush()
    if stdin.readline().strip().lower() not in {"y", "yes"}:
        print("nothing was written", file=out)
        return 1

    return _write_and_verify(
        operation,
        runtime,
        copy,
        environ,
        sentence=sentence,
        second_note=A_RE_RUN_OF_APPLY_CAN_WRITE_A_SECOND_NOTE,
        out=out,
        err=err,
        runner=runner,
    )


NO_SECOND_NOTE_FROM_A_PROPOSAL = (
    "The note must not be proposed again: the proposal is consumed and will not be "
    "retried, so no second note can arrive this way. Writing another one needs a fresh "
    "proposal, a fresh console and a second human yes."
)
"""What is true about a duplicate on the ``approve`` path.

``store.consume`` runs before Gramps is launched, so a retried ``approve`` meets
``ProposalNotFound``. This is the sentence the whole of #69's disposition for the
MCP route buys, and it is true only here.
"""

A_RE_RUN_OF_APPLY_CAN_WRITE_A_SECOND_NOTE = (
    "Nothing here was consumed. This command re-reads the operation file every time it "
    "runs, so running it again on the same file CAN put a SECOND note on the person. "
    "Look at the person in Gramps before you re-run."
)
"""What is true about a duplicate on the ``apply`` path, which is a different thing.

⚠️ **#69's residual, open and unchanged**, and it is closed for the MCP route
only. There is no proposal on this path to be consumed and nothing binds one run
to the next, so the strong sentence above is simply false here.

⚠️ **Path-specific rather than softened, which is the owner's ruling on L6.** A
sentence vague enough to be true for both callers would read as reassurance on
the path where a duplicate is possible, and would hide the seam instead of
showing it. The seam is that ``_write_and_verify`` serves two callers whose
guarantees differ -- **issue #73**, which is a design question and not this.
"""


# ---------------------------------------------------------------------------
# The write itself -- shared by ``apply`` and by ``approve``
#
# ⚠️ **Shared rather than reimplemented, and that is the load-bearing part.**
# Criterion 8 is that every slice 1 rail still holds with an agent standing in
# front of it: the sentinel, the token whose constructor performs the check, the
# lock Gramps owns, the undo record before the transaction, the read-back in a
# fresh process. A second copy of this body would be a second place for one of
# them to be quietly dropped. Only the SOURCE of the operation differs between
# the two commands -- a file the owner wrote, or a proposal the store holds.
# ---------------------------------------------------------------------------


def _write_and_verify(
    operation: schema.Operation,
    runtime: str,
    copy: apply.WritableCopy,
    environ: Mapping[str, str],
    *,
    sentence: str,
    second_note: str,
    out: TextIO,
    err: TextIO,
    runner: invocation.Runner,
) -> int:
    """Run the write, then the read-back, and say what happened in both places.

    Returns the exit code. **Everything else it has to say, it says to a
    person** -- there is no report and no agent reading one, so the words on
    these two streams are the whole of what anybody learns.

    ⚠️ **The APPLY RUN'S RESULT MARKER is the line this function is divided by,
    and that division is C1-1.** Two Gramps runs happen here. A failure before
    the marker is a refusal: nothing was written. A failure after it is not:
    the note is in the tree and nothing has read it back. Telling the owner the
    second as the first costs him his knowledge of what is in the tree, and
    loses the handles an undo by hand needs, so the two sides are separated
    structurally rather than by care: everything past the marker is ONE CALL,
    made inside one ``try`` whose handler cannot say *refused*.

    ⚠️ **The DISTINCTION survives the deletion of the vocabulary that named
    it.** The outcome words -- ``failed``, ``unverified``, ``unknown`` -- are
    gone with the report they travelled in. What C1-1 is about is not the word;
    it is that two different facts must not be told as one, and they are now
    told as two sentences on ``err``.

    ⚠️ **A call rather than a block, and that distinction is C2-1.** The first
    repair put the post-marker statements inside a ``try``, and the block then
    ended before the last two of them -- the disagreement message and the
    success line -- so a console that broke while printing either one reached
    the caller's pre-commit handler and was told as a refusal, for a note that
    was in the tree and confirmed. A block's boundary is *which statements happen to
    sit inside it*, which is a fact about where somebody stopped typing; a
    call's boundary is the callee. A statement appended to the end of the
    post-commit body next year is inside the handler by construction, which is
    the only sense in which *structurally* was ever true.

    ⚠️ **``second_note`` is a PARAMETER because the two callers' guarantees
    differ, and that is L6.** Both messages below tell the operator what a
    re-run does, and the answer is not the same one twice: ``approve`` consumed
    its proposal before Gramps was launched and ``apply`` consumed nothing. The
    sentence used to be written once, in ``approve``'s words, and printed down
    both paths -- so on ``apply`` it told the owner a duplicate was impossible
    where a duplicate is exactly what a re-run produces.

    ⚠️ **This is not the two callers being split**, which is issue #73 and is
    deliberately not answered here. It is one function saying the true thing for
    whichever of them called it, so the seam SHOWS rather than being papered
    over by a sentence weak enough to be true of both.
    """
    payload = json.dumps(schema.to_dict(operation))
    digest = apply.approval_digest(operation)
    try:
        written = _one_run(
            runner,
            runtime,
            copy,
            environ,
            mode=invocation.MODE_APPLY,
            operation=payload,
            approved_preview=sentence,
            approved_digest=digest,
        )
    except invocation.NoResultMarker as failure:
        # ⚠️ **A run that printed no marker may or may not have committed**, and
        # the exit code says nothing here by construction. The honest answer is
        # that nobody knows, that what a re-run would do is this caller's own,
        # and that what settles it is the undo record on disk.
        #
        # ⚠️ **All three sentences are PRINTED now.** Only the first used to
        # be: the other two went into the report, which is where the server read
        # them, and the person at the console was told less than the agent was.
        # There is no report and no agent, so this is the whole audience.
        print(
            f"{failure}\nThe write may have committed. {second_note}\nLook in "
            f"{os.path.join(copy.tree_dir, apply.UNDO_DIRECTORY)} for what happened.",
            file=err,
        )
        return 1

    if not written.get("ok"):
        # ⚠️ Verbatim, never paraphrased. #62's refusal message names the remedy
        # inside its own words, and the owner is the one who acts on it.
        print(str(written.get("error", "the write failed and said nothing")), file=err)
        return 1

    # The marker said the write committed. There is no region between this line
    # and the handler below: the whole post-commit body is the call, so nothing
    # can be added past the marker and outside the try without moving the call.
    try:
        return _after_commit(
            written,
            runner,
            runtime,
            copy,
            environ,
            payload=payload,
            sentence=sentence,
            digest=digest,
            out=out,
            err=err,
        )
    except (invocation.NoResultMarker, apply.ApplyError, schema.SchemaError, OSError) as failure:
        # ⚠️ **Enumerated, not ``Exception``.** *No post-commit failure is told
        # wrongly* is a claim over an unbounded space; what is claimed here is
        # the bounded one -- these four, which are the set the callers of this
        # function already catch and turn into a refusal. Anything else still
        # escapes to ``main``, which is a residual rather than a fix.
        #
        # ⚠️ **The telling is best-effort, because a console that broke is how
        # this handler gets reached in the first place**: a bare ``print`` would
        # raise inside the ``except`` and propagate exactly like the original,
        # so the machinery that exists to prevent a false refusal would produce
        # one. ⚠️ **And that is R4 in one line: if this stream is the broken
        # one, nobody is told at all.** The report used to catch part of it.
        # What is left is the exit code, the handles already on ``out``, and the
        # undo record on disk.
        _say(
            f"{failure}\n"
            "THE NOTE WAS WRITTEN AND THE READ-BACK DID NOT RUN. The write reported "
            "success before this failure, so the note is in the tree and nothing here "
            f"has read it back -- this is not a refusal. {second_note}\n"
            # ⚠️ **Repeated, and that repetition is load-bearing.** These are
            # printed to ``out`` the moment the marker says the note committed
            # -- and the failure that brings us here can BE that printing, in
            # which case this copy is the only one the owner gets. They are what
            # an undo by hand needs and the one thing he cannot reconstruct.
            f"{_handles(written)}\n"
            f"Look in {os.path.join(copy.tree_dir, apply.UNDO_DIRECTORY)}, and in the "
            "tree itself, for what happened.",
            err,
        )
        return 1


def _after_commit(
    written: Mapping[str, object],
    runner: invocation.Runner,
    runtime: str,
    copy: apply.WritableCopy,
    environ: Mapping[str, str],
    *,
    payload: str,
    sentence: str,
    digest: str,
    out: TextIO,
    err: TextIO,
) -> int:
    """Read the note back, and say what both runs found. **All of it post-commit.**

    ⚠️ **This is a function so that its caller's handler has a boundary nobody
    has to remember** -- see ``_write_and_verify``. Every statement here runs
    after the apply run's marker said the note committed, so every exception out
    of here means the same thing, whatever it was raised by and whenever it is
    added: the note is in the tree, and the read-back did not finish.

    ⚠️ **Which is why nothing PAST the read-back is allowed to raise.** Once
    ``_one_run`` returns, the caller's verdict -- *the read-back did not run* --
    has stopped being true, so a statement down there that could reach it would
    print a sentence contradicting itself. What is left past it is lookups on a
    ``dict`` (``result_of`` refuses a marker that is not an object) and
    best-effort ``_say``. **That is a claim about the statements written below,
    checkable by reading them -- not a claim that nothing here can fail**, and
    it is the obligation anything added after ``_one_run`` inherits.
    """
    code = 0
    print(_handles(written), file=out)
    if written.get("record_error"):
        # The commit stands. Rolling it back would be a second write nobody
        # approved, and the handles above are the part that cannot be
        # reconstructed -- which is why they are printed before this.
        print(
            f"THE WRITE SUCCEEDED AND ITS RESULT RECORD DID NOT: {written['record_error']}\n"
            "The note is in the tree. Write the handles above down: they are what "
            "an undo by hand needs, and nothing on disk now records them.",
            file=err,
        )
        code = 1

    # ⚠️ **The printing above is NOT best-effort, and the asymmetry is the
    # point.** A console that fails here leaves the read-back unlaunched, so the
    # handler's *the note is in the tree and nothing read it back* is literally
    # true and its words are the right ones. Below, they would be false.
    seen = _one_run(
        runner,
        runtime,
        copy,
        environ,
        mode=invocation.MODE_VERIFY,
        operation=payload,
        approved_preview=sentence,
        approved_digest=digest,
        handles={
            "note_handle": str(written.get("note_handle")),
            "person_handle": str(written.get("person_handle")),
        },
    )
    if not (seen.get("ok") and seen.get("text_matches") and seen.get("attached")):
        _say(
            "the read-back disagrees with what was written: "
            f"text matches={seen.get('text_matches')}, on the person={seen.get('attached')}",
            err,
        )
        return 1
    _say(f"read back from a fresh process: {seen.get('text')!r}", out)
    return code


def _handles(written: Mapping[str, object]) -> str:
    """What an operator needs about a note the marker said committed.

    ⚠️ **The only place these exist once the window is gone.** The note's
    Gramps ID and the two handles cannot be reconstructed from anything else in
    the room -- the undo record on disk is what remains, and this is what he
    reads off the screen while it is in front of him.

    Built once and printed down every path out of the post-commit body,
    including the failing ones, so no path can lose them by forgetting.
    """
    return (
        f"note {written.get('note_gramps_id')} written\n"
        f"  note handle   {written.get('note_handle')}\n"
        f"  person handle {written.get('person_handle')}"
    )


def _say(message: str, stream: TextIO) -> None:
    """Tell the operator something about an outcome that is already decided.

    ⚠️ **Post-commit diagnostics only, and the swallowing is the whole point.**
    An outcome describes what is in the tree; printing is how a person is told
    about it. A console that has gone away is a reason the telling fails, never
    a reason the note stopped being written -- and C2-1 is exactly what happens
    when the two are allowed to be the same exception. What survives it is the
    **exit code**, whose meaning ``docs/using.md`` documents, and the undo and
    result records on disk.

    ⚠️ **R4, said here rather than left to be discovered.** There used to be a
    report as well, so a broken stream lost the telling and not the account.
    There is no report now: **a console whose stream breaks while printing this
    tells nobody anything.** That is a real loss, accepted -- the human is the
    only reader, and a broken console has no reader.

    ⚠️ **``OSError`` only, which is the bounded set the post-commit handler
    already names.** A stream that is *closed* rather than broken raises
    ``ValueError``, and that is the recorded residual -- the four-exception
    enumeration -- unchanged here rather than quietly widened.
    """
    with contextlib.suppress(OSError):
        print(message, file=stream)


# ---------------------------------------------------------------------------
# approve -- the console window, and slice 2's whole trust model
# ---------------------------------------------------------------------------


def _approve(
    proposal_id: str,
    environ: Mapping[str, str],
    *,
    stdin: TextIO,
    out: TextIO,
    err: TextIO,
    runner: invocation.Runner,
) -> int:
    """Show one claimed proposal in full, ask, and write it if the answer is yes.

    ⚠️ **The operation comes off the disk and the sentence is RE-RENDERED from
    it**, never taken from the sentence stored beside it. ``ProposalCorrupt``
    binds the stored operation to the digest; nothing binds the stored sentence,
    so printing that one would show whatever last edited the file while writing
    what the operation says -- which is precisely the agreed-versus-written
    disagreement this window exists to make impossible.

    ⚠️ **The proposal is consumed BEFORE Gramps is launched**, and the ordering
    is #69's whole disposition. Everything after that point can crash, time out
    or be retried, and none of it can produce a second note: a retried
    ``approve`` meets ``ProposalNotFound``. A second note needs a second
    proposal, a second console and **a second human yes**.

    ⭐ **NOTHING LEAVES THIS PROCESS BUT AN EXIT CODE, and the window is the
    channel.** There is no report file and no server waiting on one: what the
    owner reads here is the only account of what happened, and the only route
    from it to the transcript is him saying so. Which is why every region below
    ends at ``_closed`` rather than letting an exception reach ``main`` -- a
    console that exits the instant it refuses takes the refusal off the screen
    with it. That was L7's second half, and the deletion promotes it from a
    courtesy to the whole mechanism.
    """
    settings = config.load(environ)
    if settings.copy_path is None:
        raise config.ConfigError(
            f"no copy is configured -- set copy_path in {config.user_config_path(environ)} "
            f"or {config.ENV_COPY}"
        )
    runtime = settings.runtime or config.discover_runtime(environ)
    if runtime is None:
        raise config.ConfigError(f"no {config.RUNTIME_NAME} found; set gramps_runtime")

    copy = apply.authorise(settings.copy_path)
    store = proposals.Store(proposals.store_directory(copy.tree_dir), session="")
    try:
        proposal = store.claimed(proposal_id)
        operation = proposal.operation
        sentence = schema.preview(operation)
        entire = schema.full_display(operation)
        print(entire, file=out)
        print(f"write this into {copy.tree_dir}? [y/N] ", end="", file=out)
        out.flush()
        answered = stdin.readline()
    except (proposals.ProposalError, schema.SchemaError, apply.ApplyError, OSError) as failure:
        # ⚠️ **A refusal is the true thing to say here, and the region is what
        # makes it true.** Nothing past this point has run, so nothing has been
        # written. It is the post-commit region where the same sentence would be
        # the lie, and that region is below and unchanged.
        _say(str(failure), err)
        return _closed(stdin, out, 1)

    if answered.strip().lower() not in {"y", "yes"}:
        store.consume(proposal_id, approved=False)
        print("nothing was written", file=out)
        return _closed(stdin, out, 1)

    store.consume(proposal_id, approved=True)
    try:
        code = _write_and_verify(
            operation,
            runtime,
            copy,
            environ,
            sentence=sentence,
            second_note=NO_SECOND_NOTE_FROM_A_PROPOSAL,
            out=out,
            err=err,
            runner=runner,
        )
    except (apply.ApplyError, schema.SchemaError, OSError) as failure:
        # ⚠️ **This handler is kept, and the plan proposed deleting it with the
        # report write it used to carry.** Without it a launch failure -- the
        # apply run's own ``OSError``, which ``_write_and_verify`` does not
        # catch -- escapes to ``main``, which prints and returns 1 without
        # reaching ``_closed``. The window would then vanish with the message
        # still on it, and there is no longer anywhere else the message exists.
        print(failure, file=err)
        return _closed(stdin, out, 1)

    return _closed(stdin, out, code)


def _closed(stdin: TextIO, out: TextIO, code: int) -> int:
    """Hold the window open until the owner has read it, then return ``code``.

    A console the server spawned closes the instant its process exits, taking
    the note's identifiers and any refusal with it. The owner is the only reader
    this window has.

    ⭐ **Promoted by the deletion.** It was a courtesy while a report carried
    the same facts to the server; it is now the only channel by which any of
    them reaches anybody at all.
    """
    print("\npress Enter to close this window ", end="", file=out)
    out.flush()
    stdin.readline()
    return code


def _one_run(
    runner: invocation.Runner,
    runtime: str,
    copy: apply.WritableCopy,
    environ: Mapping[str, str],
    *,
    mode: str,
    operation: str,
    approved_preview: str,
    approved_digest: str,
    handles: Mapping[str, str] | None = None,
) -> Mapping[str, object]:
    completed = runner(
        invocation.command_line(runtime, copy.tree_dir),
        invocation.environment(
            environ,
            mode=mode,
            operation=operation,
            approved_preview=approved_preview,
            approved_digest=approved_digest,
            source=_SOURCE_DIRECTORY,
            handles=handles,
        ),
    )
    try:
        return invocation.result_of(completed.stdout)
    except invocation.NoResultMarker as failure:
        raise invocation.NoResultMarker(
            f"{failure}\n"
            f"Gramps exited {completed.returncode}, which is not consulted and cannot be.\n"
            f"What it printed on stderr:\n{completed.stderr}"
        ) from failure


def _with_subprocess(argv: Sequence[str], environ: Mapping[str, str]) -> invocation.Completed:
    """The real runner. The only place in this package that starts a process."""
    # ⚠️ **The decode may not RAISE, and that -- not the choice of codec -- is
    # the property this line has to hold.** Decoding happens after the child has
    # exited, which on an apply is after the note has COMMITTED. An exception
    # here escapes the NoResultMarker handler entirely: no read-back, no
    # handles printed, a traceback instead of the record needed to undo a write
    # that did happen.
    #
    # Strict decoding is wrong in both directions and each was tried:
    #
    #   - ``text=True`` alone asks ``locale.getpreferredencoding(False)``, which
    #     is cp1252 on a Windows box while the child writes UTF-8. Measured: an
    #     em dash came back mojibake, so a fidelity check DISPLAYED false
    #     infidelity on a note that was correct in the tree -- and cp1252 has
    #     undefined bytes, so some input raised instead.
    #   - ``encoding="utf-8"`` alone fixes the mojibake and moves the raise: a
    #     Gramps banner or diagnostic emitted in a legacy code page is not valid
    #     UTF-8, and strict decoding of it raises just as surely.
    #
    # ``errors="replace"`` is what closes it, and its guarantee is bounded and
    # provable rather than argued: ``bytes.decode`` with ``replace`` is TOTAL --
    # there is no byte sequence for which it raises. A stray byte becomes U+FFFD
    # in a diagnostic a human reads, which is strictly better than an exception
    # that hides a committed write.
    #
    # ⚠️ **This is stderr's guard, not the marker's.** The marker is ASCII by
    # construction (see ``emit_marker``), so the protocol survives whatever the
    # pipe does; substitution cannot corrupt it, because there is nothing
    # non-ASCII in it to substitute. What is protected here is Gramps' own
    # output, which is not ours to constrain and which the failure handler
    # prints -- previously it could raise while trying to report.
    completed = subprocess.run(  # noqa: S603
        list(argv),
        env=dict(environ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return invocation.Completed(
        stdout=completed.stdout, stderr=completed.stderr, returncode=completed.returncode
    )
