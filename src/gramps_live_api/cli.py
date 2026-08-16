"""The three commands the owner types: ``preview``, ``apply``, ``check``.

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
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from gramps_live_api import config, invocation
from gramps_live_api.core import apply, schema

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

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    settings_environ = os.environ if environ is None else environ
    arguments = settings.parse_args(list(argv))

    try:
        if arguments.command == "preview":
            return _preview(arguments.operation, out=out, err=err)
        if arguments.command == "check":
            return _check(arguments.tree, settings_environ, out=out, err=err)
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
    checks = [_runtime_check(environ), _plugin_check(environ)]
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
            "locked -- Gramps has this tree open, and we never break its lock"
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


def _plugin_check(environ: Mapping[str, str]) -> Check:
    root = _gramps_user_data(environ)
    found = sorted(root.glob(_PLUGIN_GLOB)) if root.is_dir() else []
    if not found:
        return Check("plugin", False, f"not installed under {root}")
    return Check("plugin", True, str(found[0].parent))


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
    print(f"write this into {copy.tree_dir}? [y/N] ", end="", file=out)
    out.flush()
    if stdin.readline().strip().lower() not in {"y", "yes"}:
        print("nothing was written", file=out)
        return 1

    written = _one_run(
        runner,
        runtime,
        copy,
        environ,
        mode=invocation.MODE_APPLY,
        operation=json.dumps(schema.to_dict(operation)),
        approved_preview=sentence,
    )
    if not written.get("ok"):
        print(written.get("error", "the write failed and said nothing"), file=err)
        return 1

    code = 0
    print(f"note {written.get('note_gramps_id')} written", file=out)
    print(f"  note handle   {written.get('note_handle')}", file=out)
    print(f"  person handle {written.get('person_handle')}", file=out)
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

    seen = _one_run(
        runner,
        runtime,
        copy,
        environ,
        mode=invocation.MODE_VERIFY,
        operation=json.dumps(schema.to_dict(operation)),
        approved_preview=sentence,
        handles={
            "note_handle": str(written.get("note_handle")),
            "person_handle": str(written.get("person_handle")),
        },
    )
    if not (seen.get("ok") and seen.get("text_matches") and seen.get("attached")):
        print(
            "the read-back disagrees with what was written: "
            f"text matches={seen.get('text_matches')}, on the person={seen.get('attached')}",
            file=err,
        )
        return 1
    print(f"read back from a fresh process: {seen.get('text')!r}", file=out)
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
    handles: Mapping[str, str] | None = None,
) -> Mapping[str, object]:
    completed = runner(
        invocation.command_line(runtime, copy.tree_dir),
        invocation.environment(
            environ,
            mode=mode,
            operation=operation,
            approved_preview=approved_preview,
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
    # ⚠️ ``encoding`` is explicit because ``text=True`` alone decodes with
    # ``locale.getpreferredencoding(False)`` -- cp1252 on a Windows box -- while
    # the child writes UTF-8. That is a check whose answer comes from the machine
    # rather than from the protocol, and it fails two ways: a correct note comes
    # back as mojibake in the read-back line, so a fidelity check DISPLAYS false
    # infidelity; and a byte cp1252 does not map raises UnicodeDecodeError on the
    # strict default, after the write has committed.
    #
    # The marker itself is ASCII by construction now (see ``emit_marker``), so
    # this is not the marker's guard -- it is stderr's. Gramps' own error output
    # is not ours to constrain, and it is what the NoResultMarker handler prints
    # when a run fails: without this, the reporting path can raise while trying
    # to report.
    completed = subprocess.run(  # noqa: S603
        list(argv),
        env=dict(environ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return invocation.Completed(
        stdout=completed.stdout, stderr=completed.stderr, returncode=completed.returncode
    )
