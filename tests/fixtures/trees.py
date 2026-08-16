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


class _Transaction:
    """What ``Tree.transaction`` hands back, and when it observes the records.

    ⚠️ **The observation happens on ENTRY, deliberately.** "The record exists
    by the time the apply returns" is a much weaker claim than "the record
    exists before the transaction opens", and only the second one is the
    property. Reading the undo directory here is a direct observation of the
    ordering rather than a proxy for it.
    """

    def __init__(self, tree: FakeTree) -> None:
        self._tree = tree

    def __enter__(self) -> object:
        self._tree.records_when_the_transaction_opened = self._tree.records_on_disk()
        self._tree.events.append("transaction opened")
        return self

    def __exit__(self, *_: object) -> bool:
        self._tree.events.append("transaction closed")
        return False


class FakeTree:
    """A tree that answers ``core.apply``'s four questions and remembers them.

    ⚠️ **Not a Gramps database and not a stand-in for one.** It proves the
    ordering and the refusals; it proves nothing about ``DbTxn``, about the
    note surviving to disk, or about the backlink Gramps maintains. Only the
    demo proves those, which is why the integration test that runs the real
    thing skips by name rather than being quietly absent.
    """

    def __init__(
        self,
        tree_dir: Path,
        *,
        people: dict[str, str] | None = None,
        note_handle: str = "f00d1e5f00d1e5",
        note_gramps_id: str = "N0021",
        text_read_back: str | None = None,
        attached: bool = True,
        refuse_the_write: bool = False,
    ) -> None:
        self._tree_dir = tree_dir
        self._people = {"I0044": "a1b2c3d4e5f607"} if people is None else people
        self._note_handle = note_handle
        self._note_gramps_id = note_gramps_id
        self._text_read_back = text_read_back
        self._attached = attached
        self._refuse_the_write = refuse_the_write
        self.events: list[str] = []
        self.written: list[tuple[str, str, str]] = []
        self.records_when_the_transaction_opened: list[str] = []

    def records_on_disk(self) -> list[str]:
        undo = self._tree_dir / apply.UNDO_DIRECTORY
        return sorted(path.name for path in undo.glob("*.json")) if undo.is_dir() else []

    # The protocol core.apply talks to.

    def save_path(self) -> str:
        return str(self._tree_dir)

    def person_handle_of(self, gramps_id: str) -> str | None:
        self.events.append(f"resolved {gramps_id}")
        return self._people.get(gramps_id)

    def transaction(self, message: str) -> _Transaction:
        return _Transaction(self)

    def add_note_to_person(
        self, *, person_handle: str, note_type: str, text: str, transaction: object
    ) -> apply.NoteIdentity:
        self.events.append("note written")
        if self._refuse_the_write:
            raise RuntimeError("the tree refused the write")
        self.written.append((person_handle, note_type, text))
        return apply.NoteIdentity(handle=self._note_handle, gramps_id=self._note_gramps_id)

    def note_on_person(self, *, note_handle: str, person_handle: str) -> apply.NoteSighting:
        self.events.append("note read back")
        return apply.NoteSighting(
            text="" if self._text_read_back is None else self._text_read_back,
            attached=self._attached,
        )
