"""A blessed copy on ``tmp_path``.

⚠️ **Nothing here is a Gramps database.** The directory is the two files
``core.apply``'s check looks at, which is enough to exercise the blessing on a
runner with no Gramps on it, and it is not evidence that anything reaches a real
tree. Only ``tests/integration/test_round_trip.py`` is.

⛔ **``FakeTree``, ``MOMENT`` and ``NOTE_TYPE_VALUES`` went with R9.** They stood
in for the Gramps database the note flow's ``apply_operation`` drove -- the
transaction, the note handle, the read-back and a ``NoteType`` with a row removed
so the drift refusal was reachable without Gramps. That write path is retired,
and the document route's write happens out in ``gramps_plugin/`` where a fake
would prove nothing.
"""

from __future__ import annotations

from pathlib import Path

from gramps_live_api.core import apply


def blessed(directory: Path) -> apply.WritableCopy:
    """``directory`` made into a copy the owner has blessed, and its token."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / apply.NAME_FILE).write_text("Invented Copy\n", encoding="utf-8")
    (directory / apply.SENTINEL_NAME).write_text("", encoding="utf-8")
    return apply.authorise(str(directory))
