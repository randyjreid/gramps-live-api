"""Asking Gramps to run our code, and reading the one line that says it did.

Gramps has exactly one sanctioned door for running third-party code against an
open tree, and it is the CLI tool plugin: ``-O <tree> -a tool -p name=<id>``
(``gramps/cli/arghandler.py``). This module builds that invocation and parses
its answer. It runs no subprocess itself -- everything here is pure, so the
argv, the environment and the parse are all covered by ordinary unit tests on a
runner with no Gramps.

⚠️ **THE EXIT CODE IS NOT A SIGNAL, AND THAT IS MEASURED.** Two observations on
Gramps AIO 6.0.8:

* ``src/grampsaioc.py`` takes a named mutex and, when another Gramps is already
  running, prints to **stderr** and calls ``sys.exit()`` -- which exits **0**.
  That is why the invocation uses ``grampsd.exe``, which has no mutex at all.
* ``gramps/gui/plug/tool.py:316-325`` wraps the entire tool invocation in a bare
  ``try: ... except: log.error(...)``. **A crash inside our tool is swallowed
  and the process still exits normally.**

So a refusal exits 0, a crash exits 0, and a success may exit anything. The one
reading that is correct in all three cases is a single-line marker on stdout
whose ABSENCE is failure, and that is what ``result_of`` implements.

⚠️ **Nothing but ``name=`` may travel through ``-p``.** The tool branch parses
options as ``dict(tuple(chunk.split("=")) for chunk in options_str.split(","))``
-- no quoting and no escaping -- so a value containing a comma or a second
equals sign silently discards the whole options string. Note text and paths go
through the **environment**, which has no such parsing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

TOOL_ID = "gramps_live_api_apply"
"""The plugin id registered in ``gramps_plugin/gramps_live_api_apply.gpr.py``.

The only value that rides in ``-p``, and it is a fixed identifier: no comma, one
equals sign, nothing a payload could influence.
"""

MARKER = "GRAMPS-LIVE-API-RESULT"
"""What a result line starts with, so it can be found among Gramps' own output."""

MODE_APPLY = "apply"
MODE_VERIFY = "verify"

ENV_MODE = "GRAMPS_LIVE_API_MODE"
ENV_OPERATION = "GRAMPS_LIVE_API_OP"
ENV_APPROVED = "GRAMPS_LIVE_API_APPROVED"
ENV_SOURCE = "GRAMPS_LIVE_API_SRC"
ENV_HANDLES = "GRAMPS_LIVE_API_HANDLES"


class NoResultMarker(Exception):
    """The run produced no readable result, whatever its exit code said.

    ⚠️ **An exception rather than a falsy return, deliberately.** A caller can
    forget to check a return value; it cannot forget to handle the one thing
    this function does when the run failed. Every measured failure mode --
    the mutex refusal, the swallowed crash, a truncated run -- arrives here.
    """


def command_line(runtime: str, tree_dir: str) -> list[str]:
    """The argv that runs our tool against the tree at ``tree_dir``.

    ⚠️ **No ``-u`` and no ``--force-unlock``, ever.** Gramps refuses a locked
    tree, so a copy currently open in the GUI cannot be written by us. That is
    the "one writer" invariant, enforced by Gramps rather than by anything here,
    and passing either flag would hand it back. Asserted by test.
    """
    return [runtime, "-O", tree_dir, "-a", "tool", "-p", f"name={TOOL_ID}"]


def environment(
    base: Mapping[str, str],
    *,
    mode: str,
    operation: str,
    approved_preview: str,
    source: str,
    handles: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """``base`` plus everything the shim needs, none of which fits in ``-p``.

    ``base`` is added to rather than replaced: the child is a Gramps process and
    needs the environment it would otherwise have had.
    """
    settings = dict(base)
    settings[ENV_MODE] = mode
    settings[ENV_OPERATION] = operation
    settings[ENV_APPROVED] = approved_preview
    settings[ENV_SOURCE] = source
    if handles is not None:
        settings[ENV_HANDLES] = json.dumps(handles)
    return settings


def emit_marker(payload: Mapping[str, object]) -> str:
    """The one line the shim prints, and the only thing the front end reads.

    ⚠️ **One LINE.** ``json.dumps`` escapes a newline inside a value, so a note
    whose text carries one cannot break the marker it is being reported through
    -- which would look to the front end exactly like a crash.
    """
    return f"{MARKER} {json.dumps(payload, ensure_ascii=False)}"


def result_of(stdout: str) -> Mapping[str, object]:
    """The payload the run reported, or refuse: absence is failure.

    ⚠️ **Two markers are refused rather than one of them chosen.** Nothing in a
    correct run emits two, so a second one means something this design has no
    reading for -- and preferring the first or the last would be a reading
    invented on the spot, over a tree.
    """
    lines = [line for line in stdout.splitlines() if line.startswith(MARKER)]
    if not lines:
        raise NoResultMarker(
            f"the run printed no {MARKER} line, so it did not complete -- the exit "
            "code says nothing here, because Gramps swallows a tool's exception "
            "and its launcher refuses by exiting zero"
        )
    if len(lines) > 1:
        raise NoResultMarker(f"the run printed {len(lines)} {MARKER} lines; refusing to pick one")
    try:
        payload = json.loads(lines[0][len(MARKER) :])
    except json.JSONDecodeError as failure:
        raise NoResultMarker(f"the {MARKER} line is not readable: {failure}") from failure
    if not isinstance(payload, dict):
        raise NoResultMarker(f"the {MARKER} line does not carry an object")
    return payload
