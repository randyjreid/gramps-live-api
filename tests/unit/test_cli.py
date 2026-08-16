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
    """
    program_files = tmp_path / "program-files"
    install = program_files / "GrampsAIO64-6.0.8"
    install.mkdir(parents=True)
    runtime = install / config.RUNTIME_NAME
    runtime.write_text("", encoding="utf-8")
    plugins = tmp_path / "roaming" / "gramps" / "gramps60" / "plugins" / "gramps-live-api"
    plugins.mkdir(parents=True)
    (plugins / "gramps_live_api_apply.gpr.py").write_text("", encoding="utf-8")
    return {
        "ProgramFiles": str(program_files),
        "APPDATA": str(tmp_path / "roaming"),
        config.ENV_RUNTIME: str(runtime),
        **extra,
    }


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
