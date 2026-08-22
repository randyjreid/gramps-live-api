"""What a write reports must be what a write did.

⚠️ **A source was written and the log line said zero sources.** Not a dedup and
not a drop — a counter bug. The writer kept a hand-maintained ``counts`` dict of
six keys beside a ``created`` record of seven, and nothing made them agree.

⛔ **Worse than cosmetic: that line had already been used as evidence** for what a
write did, including to establish that ``gramps_id`` was honoured. **A diagnostic
that under-reports reads as evidence of absence.**

⭐ The fix deletes the second tally rather than adding the missing key, and these
tests exist so it cannot come back: one asserts the summary reports every kind,
and one **reads the writer's source** to assert it creates no kind the summary
does not know about.
"""

from __future__ import annotations

import ast
import pathlib
import re

from gramps_live_api.host import document

WRITER = pathlib.Path(__file__).resolve().parents[2] / "gramps_plugin" / "gramps_live_api_writer.py"


def test_a_write_of_one_of_each_reports_one_of_each() -> None:
    """§2's criterion, stated as it was asked for."""
    created = {kind: [f"X{index:04d}"] for index, kind in enumerate(document.CREATABLE)}

    reported = document.summarise_created(created)

    for kind in document.CREATABLE:
        assert f"1 {kind}" in reported, (
            f"a write created one {kind} and the summary does not say so: {reported!r}"
        )


def test_the_source_case_that_started_this() -> None:
    """⭐ The exact shape of the observed bug: a source written, reported as none."""
    reported = document.summarise_created({"sources": ["S0013"], "citations": ["C0001"]})

    assert "1 sources" in reported, (
        "a source was written and the summary omitted it -- the original defect"
    )
    assert "1 citations" in reported


def test_nothing_created_says_nothing() -> None:
    assert document.summarise_created({}) == "nothing"
    assert document.summarise_created({kind: [] for kind in document.CREATABLE}) == "nothing"


def test_the_writer_creates_no_kind_the_summary_cannot_report() -> None:
    """⛔ The anti-drift assertion, read from the writer's own source.

    ⚠️ **Two tallies drift silently and one cannot.** The previous pair
    disagreed by one key and nothing said so until a real write was compared
    against a real log line. This reads every ``note_created("<kind>", ...)`` in
    the writer and requires the kind to be one the summary knows -- so a new
    object type added to the writer fails here rather than going unreported.
    """
    tree = ast.parse(WRITER.read_text(encoding="utf-8"), filename=str(WRITER))

    recorded = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "note_created"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }

    assert recorded, "found no note_created calls -- has the writer been renamed?"
    unreportable = sorted(recorded - set(document.CREATABLE))
    assert unreportable == [], (
        "the writer creates these kinds and the summary cannot report them, so a "
        f"write of one would be logged as though it had not happened: {unreportable}"
    )


def test_the_writer_no_longer_keeps_a_second_tally() -> None:
    """⭐ The structural half: the thing that could disagree is gone.

    Adding the missing key would have fixed the symptom and left the mechanism.
    """
    body = WRITER.read_text(encoding="utf-8")
    assert not re.search(r"counts\s*\[", body), (
        "a second hand-maintained tally is back in the writer; the summary must "
        "derive from what was actually created"
    )
