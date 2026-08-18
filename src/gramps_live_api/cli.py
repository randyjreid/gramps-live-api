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
    checks.append(_export_check(settings, resolved, environ))
    return checks


def _export_check(settings: config.Settings, copy: str, environ: Mapping[str, str]) -> Check:
    """The export ``list_people`` reads, and whether it still speaks for the copy.

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
    is deliberate: this answer has to be wrong toward *re-export*, never toward
    *the flag you are reading is current*.

    ⚠️ **So freshness that cannot be READ fails too**, and it says so in
    different words from a genuinely stale export. An ACL can permit access to
    known files while denying the listing; the comparison then has no left-hand
    side, and reporting *ready* over it is the sentence above being false in the
    forbidden direction. Two states, two messages, because the remedies differ:
    one is *export again*, the other is *this cannot be checked at all*.
    """
    if settings.export_path is None:
        return Check(
            "export",
            False,
            "no export is configured -- set export_path in "
            f"{config.user_config_path(environ)} or {config.ENV_EXPORT}. "
            "list_people and propose_note cannot run without it",
        )
    export = os.path.realpath(settings.export_path)
    if not os.path.isfile(export):
        return Check("export", False, f"{export} is not a file")
    taken = os.path.getmtime(export)
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
        return Check(
            "export",
            False,
            f"{export} is older than the copy, so the privacy flag it carries may be "
            "stale -- a person marked private since it was taken would still be listed. "
            "Export the tree again",
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

    code, _ = _write_and_verify(
        operation, runtime, copy, environ, sentence=sentence, out=out, err=err, runner=runner
    )
    return code


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
    out: TextIO,
    err: TextIO,
    runner: invocation.Runner,
) -> tuple[int, dict[str, object]]:
    """Run the write, then the read-back, and say what happened in both places.

    Returns the exit code and a payload the console files as its report -- the
    same facts, once for a person at a terminal and once for an agent that will
    relay them. ``outcome`` is the word the agent reads, and it is deliberately
    not a boolean: *written*, *failed*, *unverified* and *unknown* are four
    different things to do next.

    ⚠️ **The APPLY RUN'S RESULT MARKER is the line this function is divided by,
    and that division is C1-1.** Two Gramps runs happen here. A failure before
    the marker is ``failed``, which ``APPROVE_DESCRIPTION`` tells the agent means
    the write was refused. A failure after it is ``unverified``: the note is in
    the tree and nothing has read it back. Reporting the second as the first is
    the input that makes an agent propose the same note again -- the duplicate
    path this slice exists to close -- so the two are separated structurally
    rather than by care, by putting everything past the marker inside one
    ``try`` whose handler cannot say *failed*.
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
        # ⚠️ **#69's vocabulary.** A run that printed no marker may or may not
        # have committed, and the exit code says nothing here by construction.
        # The honest report is that it is unknown and that retrying is not the
        # answer -- the proposal is already consumed, so a retry cannot write a
        # second note, and what settles it is the undo record on disk.
        print(failure, file=err)
        return 1, {
            "outcome": "unknown",
            "error": (
                f"{failure}\nThe write may have committed. The proposal is consumed and "
                "will not be retried, so no second note can arrive this way -- look in "
                f"{os.path.join(copy.tree_dir, apply.UNDO_DIRECTORY)} for what happened."
            ),
        }

    if not written.get("ok"):
        # ⚠️ Verbatim, never paraphrased. #62's refusal message now reaches an
        # AGENT, which will summarise it, and the remedy is inside the words.
        message = str(written.get("error", "the write failed and said nothing"))
        print(message, file=err)
        return 1, {"outcome": "failed", "error": message}

    # The marker said the write committed. Everything below this line is
    # therefore POST-COMMIT, which is why it is all inside one try: see the
    # docstring. The report is built first so the handles reach the operator
    # down every path out of here, including the failing ones -- they are what
    # an undo by hand needs and the only place they exist.
    report: dict[str, object] = {
        "outcome": "written",
        "note_gramps_id": written.get("note_gramps_id"),
        "note_handle": written.get("note_handle"),
        "person_handle": written.get("person_handle"),
        "record": written.get("record"),
        "record_error": written.get("record_error"),
    }
    try:
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
            operation=payload,
            approved_preview=sentence,
            approved_digest=digest,
            handles={
                "note_handle": str(written.get("note_handle")),
                "person_handle": str(written.get("person_handle")),
            },
        )
    except (invocation.NoResultMarker, apply.ApplyError, schema.SchemaError, OSError) as failure:
        # ⚠️ **Enumerated, not ``Exception``.** *No post-commit failure is
        # misreported* is a claim over an unbounded space; what is claimed here
        # is the bounded one -- these four, which are the set the callers of
        # this function already catch and turn into ``failed``. Anything else
        # still escapes to ``main``, and files no report, which is a residual
        # rather than a fix.
        unverified = (
            f"{failure}\n"
            "THE NOTE WAS WRITTEN AND THE READ-BACK DID NOT RUN. The write reported "
            "success before this failure, so the note is in the tree and nothing here "
            "has read it back -- this is not a refusal and the note must not be "
            "proposed again. The proposal is consumed, so no second note can arrive "
            f"this way. Look in {os.path.join(copy.tree_dir, apply.UNDO_DIRECTORY)}, and "
            "in the tree itself, for what happened."
        )
        print(unverified, file=err)
        report["outcome"] = "unverified"
        report["error"] = unverified
        return 1, report

    if not (seen.get("ok") and seen.get("text_matches") and seen.get("attached")):
        disagreement = (
            "the read-back disagrees with what was written: "
            f"text matches={seen.get('text_matches')}, on the person={seen.get('attached')}"
        )
        print(disagreement, file=err)
        report["outcome"] = "unverified"
        report["error"] = disagreement
        return 1, report
    print(f"read back from a fresh process: {seen.get('text')!r}", file=out)
    return code, report


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
    proposal = store.claimed(proposal_id)
    operation = proposal.operation

    sentence = schema.preview(operation)
    entire = schema.full_display(operation)
    print(entire, file=out)
    print(f"write this into {copy.tree_dir}? [y/N] ", end="", file=out)
    out.flush()

    if stdin.readline().strip().lower() not in {"y", "yes"}:
        store.consume(proposal_id, approved=False)
        store.write_report(proposal_id, {"outcome": "declined"})
        print("nothing was written", file=out)
        return _closed(stdin, out, 1)

    store.consume(proposal_id, approved=True)
    try:
        code, report = _write_and_verify(
            operation, runtime, copy, environ, sentence=sentence, out=out, err=err, runner=runner
        )
    except (apply.ApplyError, schema.SchemaError, OSError) as failure:
        # ⚠️ **A report is filed even here, and that is not tidiness.** The
        # server is blocked reading for one, and a failure that files none
        # leaves it waiting out its whole timeout for an answer that already
        # exists -- reporting *still open* over a run that ended.
        store.write_report(proposal_id, {"outcome": "failed", "error": str(failure)})
        print(failure, file=err)
        return _closed(stdin, out, 1)

    store.write_report(proposal_id, report)
    return _closed(stdin, out, code)


def _closed(stdin: TextIO, out: TextIO, code: int) -> int:
    """Hold the window open until the owner has read it, then return ``code``.

    A console the server spawned closes the instant its process exits, taking
    the note's identifiers and any refusal with it. The owner is the only reader
    this window has.
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
