"""The three commands the owner types, and what each of them refuses.

⚠️ **Only ``preview`` is covered end to end here.** ``check`` is covered because
it never opens a database -- it stats a directory and reports. ``apply`` is
covered up to the process boundary and no further: the runner is injected, so
what these tests prove is the *approach* to the write. Whether a note reaches a
tree is observable only where Gramps is, and the demo is what observes it.

The one assertion in this file that carries the safety rail is
``test_check_refuses_an_unblessed_tree_by_name``: it is the refusal the owner
can watch happen by pointing ``check`` at his live tree.
"""

from __future__ import annotations

import io
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from gramps_live_api import cli, config, invocation
from gramps_live_api.core import apply, schema
from tests.fixtures.trees import blessed

OPERATION = schema.AddNote(
    target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
    note_type="research",
    text="Ashenmoor deed",
)


class Recorder:
    """A runner that starts no process and remembers what it was asked to."""

    def __init__(self, *replies: invocation.Completed) -> None:
        self._replies = list(replies)
        self.runs: list[tuple[Sequence[str], Mapping[str, str]]] = []

    def __call__(self, argv: Sequence[str], environ: Mapping[str, str]) -> invocation.Completed:
        self.runs.append((argv, environ))
        return self._replies.pop(0)


def marker(**payload: object) -> invocation.Completed:
    return invocation.Completed(
        stdout=f"Gramps Settings:\n{invocation.emit_marker(payload)}\n", stderr="", returncode=255
    )


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

    ⚠️ **The export joined the picture in slice 2, and for the same reason the
    runtime override did.** ``check`` now reports on it, so a test about the
    *copy* that supplied no export would assert the exit code of a machine that
    has not finished its setup -- a different question, answered the same way
    every time. A caller that IS about the export passes ``GRAMPS_LIVE_API_EXPORT``
    itself; passing it empty is how a test says *no export configured*, because
    an empty value is not a value.

    ⚠️ **It is written AFTER the copy exists, deliberately.** The doctor reports
    an export older than the copy as stale, so a helper that made one first would
    hand every caller a stale setup.
    """
    program_files = tmp_path / "program-files"
    install = program_files / "GrampsAIO64-6.0.8"
    install.mkdir(parents=True, exist_ok=True)
    runtime = install / config.RUNTIME_NAME
    runtime.write_text("", encoding="utf-8")
    plugins = tmp_path / "roaming" / "gramps" / "gramps60" / "plugins" / "gramps-live-api"
    plugins.mkdir(parents=True, exist_ok=True)
    # ⛔ Every file the plugin directory must hold, from cli.PLUGIN_FILES rather
    # than from a name written here. Laying down only the apply registration
    # equipped "a registered plugin" that registers no HOST -- so the document
    # route could not start, and every caller was asserting the exit code of a
    # setup that half works.
    for name in cli.PLUGIN_FILES:
        (plugins / name).write_text("", encoding="utf-8")
    # ⛔ **The host has to reach the package, and finding the .gpr.py does not
    # prove it can.** ``check`` reports that separately now, so a helper that
    # equips "a registered plugin" and stops leaves every caller asserting the
    # exit code of a setup the document route would fail on. This is the
    # explicit-directory route the host looks at first, which is also what a
    # copied installation is told to set.
    source = tmp_path / "checkout" / "src"
    _lay_out_the_host_package(source)
    export = tmp_path / "equipped.gramps"
    export.write_text("<database/>", encoding="utf-8")
    return {
        "ProgramFiles": str(program_files),
        "APPDATA": str(tmp_path / "roaming"),
        config.ENV_RUNTIME: str(runtime),
        config.ENV_EXPORT: str(export),
        "GRAMPS_LIVE_API_SRC": str(source),
        **extra,
    }


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
    return source


def operation_file(directory: Path, payload: object) -> str:
    path = directory / "op.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def run(
    *arguments: str,
    environ: Mapping[str, str] | None = None,
    answer: str = "y",
    runner: Recorder | None = None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        arguments,
        environ={} if environ is None else environ,
        stdin=io.StringIO(answer),
        stdout=out,
        stderr=err,
        runner=runner,
    )
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# preview -- the only command CI covers from end to end
# ---------------------------------------------------------------------------


def test_preview_prints_the_sentence_and_touches_nothing(tmp_path: Path) -> None:
    runner = Recorder()

    code, out, _ = run(
        "preview", operation_file(tmp_path, schema.to_dict(OPERATION)), runner=runner
    )

    assert code == 0
    assert out.strip() == schema.preview(OPERATION)
    assert runner.runs == [], "preview started a process; it is meant to touch nothing"


def test_preview_reports_the_violations_and_no_sentence(tmp_path: Path) -> None:
    payload = schema.to_dict(OPERATION)
    payload["note_type"] = ""

    code, out, err = run("preview", operation_file(tmp_path, payload))

    assert code != 0
    assert schema.RuleId.FIELD_EMPTY.value in err
    assert "note_type" in err
    assert out.strip() == "", (
        "a sentence was printed for an operation validate rejected, and a "
        f"sentence on screen is the thing a person approves; got {out!r}"
    )


def test_preview_refuses_a_file_that_is_not_an_operation(tmp_path: Path) -> None:
    code, _, err = run("preview", operation_file(tmp_path, {"type": "add_furniture"}))

    assert code != 0
    assert "add_furniture" in err


def test_an_operation_file_carrying_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    """Found by using it: PowerShell 5.1 writes a BOM with ``-Encoding utf8``.

    That is exactly how the owner produces this file following ``docs/using.md``
    on the machine this slice targets, and a plain ``utf-8`` read refuses it with
    a decoder message about a byte order mark -- on his very first run, over a
    file that is perfectly good JSON. ``utf-8-sig`` reads both spellings, so
    tolerating it costs nothing and refusing it costs the first run.
    """
    path = tmp_path / "op.json"
    path.write_text(json.dumps(schema.to_dict(OPERATION)), encoding="utf-8-sig")

    code, out, err = run("preview", str(path))

    assert code == 0, err
    assert out.strip() == schema.preview(OPERATION)


def test_preview_refuses_a_file_that_is_not_json(tmp_path: Path) -> None:
    path = tmp_path / "op.json"
    path.write_text("{not json", encoding="utf-8")

    code, _, err = run("preview", str(path))

    assert code != 0
    assert err.strip()


def test_preview_refuses_a_file_that_is_not_there(tmp_path: Path) -> None:
    code, _, err = run("preview", str(tmp_path / "nowhere.json"))

    assert code != 0
    assert err.strip()


# ---------------------------------------------------------------------------
# check -- the doctor, read-only, and the refusal the owner can watch happen
# ---------------------------------------------------------------------------


def test_check_reports_a_blessed_copy_as_writable(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    runner = Recorder()

    code, out, _ = run("check", copy.tree_dir, environ=equipped(tmp_path), runner=runner)

    assert code == 0, f"a blessed copy was not reported writable; got {out}"
    assert apply.SENTINEL_NAME in out
    assert runner.runs == [], "check started a Gramps process; it only stats a directory"


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
# apply -- covered up to the process boundary, and no further
# ---------------------------------------------------------------------------


def blessed_environment(tmp_path: Path) -> tuple[apply.WritableCopy, dict[str, str]]:
    copy = blessed(tmp_path / "tree")
    return copy, {config.ENV_COPY: copy.tree_dir, config.ENV_RUNTIME: "a-runtime"}


def test_apply_writes_then_reads_back_in_a_second_process(tmp_path: Path) -> None:
    """Two runs, and the second one is what makes the first evidence.

    A fresh process means the assertion crosses the database file rather than a
    live object graph -- the difference between "we wrote it" and "it is there".
    """
    copy, environ = blessed_environment(tmp_path)
    runner = Recorder(
        marker(ok=True, note_gramps_id="N0021", note_handle="f00d", person_handle="a1b2"),
        marker(ok=True, text_matches=True, attached=True, text="Ashenmoor deed"),
    )

    code, out, _ = run(
        "apply",
        operation_file(tmp_path, schema.to_dict(OPERATION)),
        environ=environ,
        runner=runner,
    )

    assert code == 0
    assert len(runner.runs) == 2, f"the read-back did not run in its own process; {runner.runs}"
    assert runner.runs[0][1][invocation.ENV_MODE] == invocation.MODE_APPLY
    assert runner.runs[1][1][invocation.ENV_MODE] == invocation.MODE_VERIFY
    assert runner.runs[0][0] == invocation.command_line("a-runtime", copy.tree_dir)
    assert "N0021" in out and "Ashenmoor deed" in out


def test_apply_sends_the_sentence_that_was_approved(tmp_path: Path) -> None:
    # The binding between what was shown and what is written travels with the
    # operation, and the write refuses if the two do not agree.
    _, environ = blessed_environment(tmp_path)
    runner = Recorder(
        marker(ok=True, note_gramps_id="N0021", note_handle="f00d", person_handle="a1b2"),
        marker(ok=True, text_matches=True, attached=True, text="Ashenmoor deed"),
    )

    run(
        "apply", operation_file(tmp_path, schema.to_dict(OPERATION)), environ=environ, runner=runner
    )

    assert runner.runs[0][1][invocation.ENV_APPROVED] == schema.preview(OPERATION)


def test_declining_the_prompt_writes_nothing_at_all(tmp_path: Path) -> None:
    _, environ = blessed_environment(tmp_path)
    runner = Recorder()

    code, out, _ = run(
        "apply",
        operation_file(tmp_path, schema.to_dict(OPERATION)),
        environ=environ,
        answer="n",
        runner=runner,
    )

    assert runner.runs == [], "a declined operation started a Gramps process"
    assert code != 0, (
        "apply exits 0 only when the note was written AND read back, so a "
        "declined run must not look like a completed one to anything scripting it"
    )
    assert "nothing was written" in out.lower()


def test_a_run_that_produced_no_marker_is_a_failure(tmp_path: Path) -> None:
    # The measured case: Gramps swallows a tool's exception and exits normally,
    # so a front end reading the exit code would call this a success.
    _, environ = blessed_environment(tmp_path)
    runner = Recorder(invocation.Completed(stdout="Gramps Settings:\n", stderr="", returncode=0))

    code, _, err = run(
        "apply",
        operation_file(tmp_path, schema.to_dict(OPERATION)),
        environ=environ,
        runner=runner,
    )

    assert code != 0
    assert invocation.MARKER in err


def test_a_write_whose_record_failed_reports_the_handles_and_still_fails(tmp_path: Path) -> None:
    """The commit stands, the handles are printed, the exit is non-zero.

    An operator can reconstruct a record. They cannot reconstruct a handle they
    were never told -- so the handles reach stdout even on the failing path.
    """
    _, environ = blessed_environment(tmp_path)
    runner = Recorder(
        marker(
            ok=True,
            note_gramps_id="N0021",
            note_handle="f00d1e5f00d1e5",
            person_handle="a1b2",
            record_error="the result record could not be written",
        ),
        marker(ok=True, text_matches=True, attached=True, text="Ashenmoor deed"),
    )

    code, out, err = run(
        "apply",
        operation_file(tmp_path, schema.to_dict(OPERATION)),
        environ=environ,
        runner=runner,
    )

    assert code != 0
    assert "f00d1e5f00d1e5" in out
    assert "record" in err.lower()


def test_a_read_back_that_disagrees_fails_the_run(tmp_path: Path) -> None:
    _, environ = blessed_environment(tmp_path)
    runner = Recorder(
        marker(ok=True, note_gramps_id="N0021", note_handle="f00d", person_handle="a1b2"),
        marker(ok=True, text_matches=True, attached=False, text="Ashenmoor deed"),
    )

    code, _, err = run(
        "apply",
        operation_file(tmp_path, schema.to_dict(OPERATION)),
        environ=environ,
        runner=runner,
    )

    assert code != 0
    assert err.strip()


def test_apply_does_not_claim_a_consumed_proposal_it_never_had(tmp_path: Path) -> None:
    """L6, and the owner ruling is that it is fixed PATH-SPECIFIC.

    ``_write_and_verify`` serves two callers whose guarantees differ. On
    ``approve`` the proposal really is consumed before Gramps is launched, so
    *no second note can arrive this way* is true. On ``apply`` there is no
    proposal at all: this command re-reads ``op.json`` every run, and running it
    again on the same file can put a second note on the person. The shared
    post-commit message asserted the approve guarantee down both paths.

    ⚠️ **Not softened into a sentence vague enough to be true for both.** A
    message that said nothing either way would leave the seam papered over, and
    the seam is the point: the message says the true thing for the path it is
    on, which on this path is that a re-run CAN write a second note. That is
    #69's residual on the CLI path, open and unchanged -- and the design
    question of whether one function should serve both callers is issue #73,
    which is not this.
    """
    _, environ = blessed_environment(tmp_path)
    runner = Recorder(
        marker(ok=True, note_gramps_id="N0021", note_handle="f00d", person_handle="a1b2"),
        invocation.Completed(stdout="Gramps says nothing\n", stderr="", returncode=0),
    )

    code, _, err = run(
        "apply", operation_file(tmp_path, schema.to_dict(OPERATION)), environ=environ, runner=runner
    )

    assert code != 0
    assert "THE NOTE WAS WRITTEN" in err, "the post-commit handler is what ran"
    assert "proposal" not in err.lower(), (
        "the apply path has no proposal, and a message telling the owner one was "
        f"consumed tells him a duplicate is impossible when it is not; got {err!r}"
    )
    assert "SECOND note" in err, "what is true on this path is said, not merely not-said"


def test_apply_refuses_before_the_prompt_when_the_copy_is_not_blessed(tmp_path: Path) -> None:
    # The advisory check, which exists so the owner meets a clear message at his
    # own terminal rather than a refusal from inside a Gramps subprocess.
    live = tmp_path / "tree"
    live.mkdir()
    (live / apply.NAME_FILE).write_text("Invented Tree\n", encoding="utf-8")
    runner = Recorder()

    code, _, err = run(
        "apply",
        operation_file(tmp_path, schema.to_dict(OPERATION)),
        environ={config.ENV_COPY: str(live), config.ENV_RUNTIME: "a-runtime"},
        runner=runner,
    )

    assert code != 0
    assert runner.runs == []
    assert apply.SENTINEL_NAME in err


def test_an_invalid_operation_never_reaches_the_prompt(tmp_path: Path) -> None:
    _, environ = blessed_environment(tmp_path)
    payload = schema.to_dict(OPERATION)
    payload["note_type"] = "musing"
    runner = Recorder()

    code, out, err = run("apply", operation_file(tmp_path, payload), environ=environ, runner=runner)

    assert code != 0
    assert runner.runs == []
    assert schema.RuleId.NOTE_TYPE_UNKNOWN.value in err
    assert "?" not in out, f"an operation validate rejected was offered for approval; got {out!r}"


def test_the_real_runner_does_not_raise_on_output_that_is_not_utf8(tmp_path: Path) -> None:
    """A byte the codec cannot read must not become an exception. Ever.

    ⚠️ **The decode happens after the child has exited, which on an apply is
    after the note has COMMITTED.** An exception here escapes the
    ``NoResultMarker`` handler entirely: no read-back, no handles printed, and a
    traceback where the record needed to undo a real write should be.

    Strict decoding is wrong in both directions and each was measured. The
    locale's answer (cp1252) mangled correct UTF-8 into mojibake, so a fidelity
    check displayed false infidelity, and raised on its own undefined bytes.
    Then ``encoding="utf-8"`` alone fixed the mojibake and moved the raise onto a
    legacy-code-page banner from Gramps, which is not ours to constrain.

    ``errors="replace"`` is what closes it, and the guarantee is bounded and
    provable rather than argued: ``bytes.decode`` with ``replace`` is TOTAL --
    there is no byte sequence for which it raises. Verified by negative control:
    remove the argument and this test fails with ``UnicodeDecodeError`` raised
    inside subprocess's reader thread.

    The marker is unaffected either way, being ASCII by construction, so there is
    nothing in it for substitution to touch. Both halves are asserted.
    """
    text = "Иван — 🌳"
    marker_line = invocation.emit_marker({"ok": True, "text": text})
    # The bad bytes are built with ``bytes([...])`` rather than an escape, and
    # the child goes to a file rather than through ``-c``: a source string
    # carrying backslash escapes through two levels of quoting is its own source
    # of bugs and has nothing to do with what is under test.
    child = tmp_path / "noisy_child.py"
    child.write_text(
        "import sys\n"
        "sys.stdout.buffer.write(bytes([255, 254]) + b' not utf-8 at all')\n"
        "sys.stdout.buffer.write(bytes([10]))\n"
        f"sys.stdout.buffer.write({marker_line.encode()!r} + bytes([10]))\n"
        "sys.stderr.buffer.write(bytes([129, 141]) + b' undefined in cp1252 too')\n",
        encoding="utf-8",
    )

    completed = cli._with_subprocess([sys.executable, str(child)], dict(os.environ))

    assert completed.returncode == 0, f"the child itself failed: {completed.stderr}"
    assert "�" in completed.stdout, "undecodable bytes should be substituted, not raise"
    assert "�" in completed.stderr, "stderr takes the same path, and a failure prints it"
    # Substitution did not touch the marker, and it still round-trips.
    assert invocation.result_of(completed.stdout)["text"] == text


def test_apply_shows_the_whole_note_before_asking_for_approval(tmp_path: Path) -> None:
    """Nothing is written that the operator was not shown.

    The one-line sentence elides free text at 60 characters. When the approval
    was compared as that elided string, everything past the limit went into the
    tree without ever reaching a screen -- so the prompt authorised content it
    had never displayed.
    """
    copy, environ = blessed_environment(tmp_path)
    tail = "and the part that used to be invisible"
    long_note = schema.AddNote(
        target=OPERATION.target,
        note_type="research",
        text="x" * schema._PREVIEW_TEXT_LIMIT + " " + tail,
    )
    runner = Recorder(marker(ok=True, note_handle="n0", note_gramps_id="N0001", person_handle="p0"))

    _, out, _ = run(
        "apply",
        operation_file(tmp_path, schema.to_dict(long_note)),
        environ=environ,
        answer="n",
        runner=runner,
    )

    assert tail not in schema.preview(long_note), "meaningless unless preview really elides"
    assert tail in out, f"the operator was asked to approve text they were never shown; got {out!r}"
    assert runner.runs == [], "declining still started a process"


def test_apply_sends_a_digest_of_the_operation_beside_the_sentence(tmp_path: Path) -> None:
    # The sentence is what the operator read; the digest is what binds the
    # write, because a sentence is elided and a digest is not.
    copy, environ = blessed_environment(tmp_path)
    runner = Recorder(
        marker(ok=True, note_handle="n0", note_gramps_id="N0001", person_handle="p0"),
        marker(ok=True, text_matches=True, attached=True, text=OPERATION.text),
    )

    run(
        "apply",
        operation_file(tmp_path, schema.to_dict(OPERATION)),
        environ=environ,
        runner=runner,
    )

    _, child_env = runner.runs[0]
    assert child_env[invocation.ENV_APPROVED_DIGEST] == apply.approval_digest(OPERATION)
    assert child_env[invocation.ENV_APPROVED] == schema.preview(OPERATION)


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


def test_a_plugin_directory_without_the_HOST_registration_is_refused(tmp_path: Path) -> None:
    """⛔ Finding one ``.gpr.py`` proves something is installed, not both routes.

    ⚠️ ``_PLUGIN_GLOB`` matches ``gramps_live_api_apply.gpr.py`` alone. A
    directory holding that and **not** ``gramps_live_api_host.gpr.py`` registers
    no host, so Gramps never starts the document route -- and every line of the
    report read ``ok``.
    """
    environ = equipped(tmp_path)
    checks = {check.label: check for check in cli.inspect(None, environ)}
    plugin_dir = Path(checks["plugin"].detail)
    for name in cli.PLUGIN_FILES:
        (plugin_dir / name).write_text("", encoding="utf-8")

    complete = {check.label: check for check in cli.inspect(None, environ)}
    assert complete["source"].ok, complete["source"].detail

    (plugin_dir / "gramps_live_api_host.gpr.py").unlink()
    partial = {check.label: check for check in cli.inspect(None, environ)}

    assert partial["plugin"].ok, "the apply registration is still there, so plugin stays ok"
    assert not partial["source"].ok, "a plugin directory registering no host was reported as ready"
    assert "gramps_live_api_host.gpr.py" in partial["source"].detail, (
        f"the refusal does not name what is missing: {partial['source'].detail}"
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

    ⭐ And Python does not fall through: once a directory named
    ``gramps_live_api`` is found, the package is bound there, so a complete copy
    further down the path does not rescue a partial one above it.
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

    checks = {check.label: check for check in cli.inspect(None, environ)}

    assert not checks["source"].ok, (
        "check reported ready from the explicit source while the host would bind "
        "the partial package beside the plugin"
    )
    assert str(plugin_dir) in checks["source"].detail, (
        f"the refusal names the wrong directory: {checks['source'].detail}"
    )
