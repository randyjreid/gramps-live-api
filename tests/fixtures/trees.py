"""A blessed copy on ``tmp_path``, and a tree that is not Gramps.

⚠️ **Everything here is invented, and none of it is a Gramps database.** The
directory is three files the check looks at; the tree object below answers the
four questions ``core.apply`` asks and records what it was asked. That is enough
to exercise the ORDERING -- authorise, record, write -- on a runner with no
Gramps on it, and it is not evidence that a note reaches a real tree. Only the
demo is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gramps_live_api.core import apply

MOMENT = datetime(2026, 8, 16, 12, 34, 56, tzinfo=timezone.utc)
"""One fixed instant, so a record's stem and contents are assertable."""


def blessed(directory: Path) -> apply.WritableCopy:
    """``directory`` made into a copy the owner has blessed, and its token."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / apply.NAME_FILE).write_text("Invented Copy\n", encoding="utf-8")
    (directory / apply.SENTINEL_NAME).write_text("", encoding="utf-8")
    return apply.authorise(str(directory))
