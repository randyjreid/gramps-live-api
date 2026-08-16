"""How Gramps is asked to run our code, and how its answer is read.

⚠️ **THE EXIT CODE IS NOT A SIGNAL HERE, AND THAT IS MEASURED RATHER THAN
ASSUMED.** Two observations on Gramps AIO 6.0.8, this machine:

* ``gramps.exe`` refused to start at all while another Gramps was open --
  ``src/grampsaioc.py`` takes a named mutex, prints *Gramps is already running!*
  to **stderr**, and calls ``sys.exit()``, which exits **0**;
* ``gramps/gui/plug/tool.py:316-325`` wraps the whole tool invocation in a bare
  ``try: ... except: log.error(...)``, so a crash inside our tool is swallowed
  and the process still exits normally.

A refusal that exits 0 and a crash that exits 0 leave the exit code saying
nothing at all. So the front end reads a single-line marker on **stdout** and
treats its ABSENCE as failure -- which is the one reading that is right in every
one of those cases.
"""

from __future__ import annotations

import json

import pytest

from gramps_live_api import invocation

TREE = "a-copy-directory"
RUNTIME = "grampsd.exe"


def test_the_command_opens_the_copy_through_the_tool_door() -> None:
    argv = invocation.command_line(RUNTIME, TREE)

    assert argv[0] == RUNTIME
    assert "-O" in argv and argv[argv.index("-O") + 1] == TREE
    assert argv[argv.index("-a") + 1] == "tool"
    assert argv[argv.index("-p") + 1] == f"name={invocation.TOOL_ID}"


def test_the_command_never_asks_gramps_to_break_a_lock() -> None:
    """One rail comes free from Gramps, and giving it away would be silent.

    ``gramps/cli/arghandler.py`` refuses a tree that is locked -- a copy
    currently open in the GUI cannot be written by us. That is the "one writer"
    invariant, enforced by Gramps rather than by anything here, and passing
    ``-u`` would hand it back.
    """
    argv = invocation.command_line(RUNTIME, TREE)

    assert "-u" not in argv and "--force-unlock" not in argv, (
        "the invocation offers to break Gramps' own tree lock, which is the one "
        f"writer invariant this project gets for free; got {argv}"
    )


def test_nothing_but_the_tool_name_rides_in_the_options_string() -> None:
    """``-p`` is parsed by splitting on commas and then on equals signs.

    ``arghandler.py:686`` builds it as ``dict(tuple(chunk.split("=")) for chunk
    in options_str.split(","))`` -- no quoting and no escaping, and a value
    containing a comma or a second equals sign silently discards the whole
    options string. So nothing that could contain either goes near it.
    """
    options = invocation.command_line(RUNTIME, TREE)[-1]

    assert options.count("=") == 1, f"a second equals sign breaks the parse; got {options!r}"
    assert "," not in options, f"a comma discards the whole options string; got {options!r}"


def test_the_operation_travels_through_the_environment_and_not_through_argv() -> None:
    # Note text and paths have no safe spelling in `-p`. The environment has no
    # such parsing, which is the whole reason they go there.
    payload = '{"type": "add_note", "text": "a, b = c"}'
    argv = invocation.command_line(RUNTIME, TREE)
    environment = invocation.environment(
        {"PATH": "somewhere"},
        mode=invocation.MODE_APPLY,
        operation=payload,
        approved_preview="add a research note to person I0044",
        approved_digest="a" * 64,
        source="a-source-directory",
    )

    assert not any(payload in argument for argument in argv)
    assert environment[invocation.ENV_OPERATION] == payload
    assert environment[invocation.ENV_MODE] == invocation.MODE_APPLY
    assert environment["PATH"] == "somewhere", (
        "the child needs the environment it would otherwise have had; replacing "
        "it rather than adding to it leaves Gramps without its own settings"
    )


def test_verify_mode_carries_the_handles_the_write_produced() -> None:
    environment = invocation.environment(
        {},
        mode=invocation.MODE_VERIFY,
        operation="{}",
        approved_preview="",
        approved_digest="a" * 64,
        source="a-source-directory",
        handles={"note_handle": "f00d1e5f00d1e5", "person_handle": "a1b2c3d4e5f607"},
    )

    assert json.loads(environment[invocation.ENV_HANDLES])["note_handle"] == "f00d1e5f00d1e5"


def test_the_marker_is_found_among_everything_else_gramps_prints() -> None:
    stdout = "\n".join(
        (
            "Gramps Settings:",
            "----------------",
            " gramps    : AIO64-6.0.8--1",
            invocation.emit_marker({"ok": True, "note_gramps_id": "N0021"}),
            "Cleaning up.",
        )
    )

    assert invocation.result_of(stdout)["note_gramps_id"] == "N0021"


def test_a_refusal_and_a_success_are_told_apart() -> None:
    """Ruling 3, asserted: the two outcomes the exit code cannot separate.

    The refusal reproduced here is the measured one -- the mutex message goes to
    **stderr** and stdout carries nothing, while the process exits 0. The
    success carries the marker. Only one of the two is read as a result, and it
    is not the exit code that decides.
    """
    refusal_stdout = ""
    refusal_stderr = "Gramps is already running!\n"
    success_stdout = invocation.emit_marker({"ok": True, "note_gramps_id": "N0021"})

    with pytest.raises(invocation.NoResultMarker) as refused:
        invocation.result_of(refusal_stdout)

    assert invocation.result_of(success_stdout)["ok"] is True
    assert invocation.MARKER in str(refused.value), (
        "a run that produced no result must say what was missing, or the owner "
        f"sees a bare failure over a tree; got {refused.value}"
    )
    assert "already running" not in refusal_stdout, (
        "the mutex refusal was measured on STDERR with an exit code of 0 -- a "
        "front end reading either would call this run a success"
    )
    assert refusal_stderr  # the message exists; it is simply not where a result is read


def test_a_crash_gramps_swallowed_is_read_as_a_failure() -> None:
    # gui/plug/tool.py logs the traceback and returns, so the process exits
    # normally with a partial, ordinary-looking stdout and no result.
    swallowed = "Gramps Settings:\n----------------\nDone.\n"

    with pytest.raises(invocation.NoResultMarker):
        invocation.result_of(swallowed)


def test_a_marker_that_is_not_json_is_a_failure_rather_than_a_shrug() -> None:
    with pytest.raises(invocation.NoResultMarker):
        invocation.result_of(f"{invocation.MARKER} not json at all\n")


def test_two_markers_are_refused_rather_than_one_of_them_chosen() -> None:
    """Fail closed. Choosing one means choosing which run the owner is told about.

    Nothing in a correct run emits two, so a second marker means something
    happened that this design has no reading for -- and picking the first or the
    last would be a reading invented on the spot.
    """
    doubled = "\n".join(
        (invocation.emit_marker({"ok": True}), invocation.emit_marker({"ok": False}))
    )

    with pytest.raises(invocation.NoResultMarker):
        invocation.result_of(doubled)


def test_the_marker_survives_a_payload_carrying_a_newline() -> None:
    # A note is free text and a person can put a newline in it. The marker is a
    # LINE, so a payload that broke it would be a payload that could not be read
    # back -- and the failure would look like a crash.
    emitted = invocation.emit_marker({"text": "first\nsecond"})

    assert "\n" not in emitted
    assert invocation.result_of(f"chatter\n{emitted}\nmore chatter")["text"] == "first\nsecond"


def test_the_marker_is_ascii_even_when_the_payload_is_not() -> None:
    """The protocol may not depend on what code page the pipe happens to use.

    ⚠️ **This is not a formatting preference.** The plugin emits this line by
    PRINTING it, inside a bare ``except`` that swallows whatever print raises.
    When the child's stdout is a redirected legacy code page -- which
    ``capture_output`` guarantees on Windows -- a payload carrying a character
    outside that page makes ``print`` raise ``UnicodeEncodeError``, the except
    eats it, and no marker is emitted at all. The front end then reports a
    failed run for a write that has ALREADY COMMITTED.

    So the assertion is that the line is encodable by the narrowest thing it
    could meet, not merely that it looks reasonable.
    """
    emitted = invocation.emit_marker({"text": "Иван — 🌳", "ok": True})

    assert emitted.isascii(), "a non-ASCII marker is unprintable on a legacy code page"
    # The narrowest code page this realistically meets, and one that cannot
    # represent any of the three characters above.
    emitted.encode("cp1252")


def test_an_ascii_marker_still_returns_the_original_text() -> None:
    # Escaping is only acceptable because it is lossless: the reader un-escapes
    # and the caller sees what was written. A marker that were ASCII by
    # TRUNCATION would pass the test above and be worthless.
    text = "Иван — 🌳"

    seen = invocation.result_of(f"chatter\n{invocation.emit_marker({'text': text})}\n")

    assert seen["text"] == text
