"""Root cause F -- what the guard prints, and where.

Two destinations, two threat models:

* A public Actions log is world-readable and retained. Printing the matched
  path there republishes the very thing the guard exists to contain, so the
  guard becomes the leak.
* A contributor's terminal is not a new exposure -- the value is already in a
  file on their disk. Hiding it there protects nothing and costs them the
  ability to act, and **a finding nobody can act on is a finding they route
  around**.

So redaction follows the destination, and the default is closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gramps_live_api.core.pii_guard import (
    _HOW_TO_ALLOW_A_TYPE,
    HISTORY_SOURCE,
    Finding,
    SourcePath,
    main,
    scan_blob,
    scan_text,
    show_matches_by_default,
)
from tests.fixtures.expectations import rules
from tests.fixtures.synthetic import posix_path


class Stream:
    def __init__(self, interactive: bool) -> None:
        self.interactive = interactive

    def isatty(self) -> bool:
        return self.interactive


SECRET_PATH = posix_path(  # pii-guard: not-a-secret -- a path fixture, not a credential
    "home", "private-user", "trees"
)


def test_a_finding_is_redacted_by_default() -> None:
    """Round 7 changed what survives here, deliberately.

    The source used to be printed in clear whatever the destination. It now
    follows the destination like the matched value, so a redacted finding
    keeps its shape and its line and nothing a person could be named by.
    """
    finding = scan_text(f"stored in {SECRET_PATH}", source="notes.md")[0]

    rendered = str(finding)

    assert SECRET_PATH not in rendered, "the default must be the safe one"
    assert "notes.md" not in rendered, "a filename is data too; the destination decides"
    assert ":1:" in rendered and "redacted" in rendered, (
        f"the line and the shape must survive or the finding is useless: {rendered!r}"
    )
    assert "notes.md" in finding.render(redact=False), "a local run still locates it"


def test_the_generated_representation_is_redacted() -> None:
    finding = scan_text(f"stored in {SECRET_PATH}", source="notes.md")[0]

    assert SECRET_PATH not in repr(finding), (
        "redaction must not depend on which method renders the object; a "
        "dataclass generates a repr that puts the value straight back"
    )


def test_a_collection_of_findings_is_redacted() -> None:
    findings = scan_text(f"stored in {SECRET_PATH}", source="notes.md")

    # The form that actually bites: a container formats its elements with
    # repr, and this is exactly how an assertion message reaches a build log.
    assert SECRET_PATH not in f"{findings}"
    assert SECRET_PATH not in f"{findings[0]!r}"


def test_a_finding_can_be_rendered_in_full() -> None:
    finding = scan_text(f"stored in {SECRET_PATH}", source="notes.md")[0]

    assert SECRET_PATH in finding.render(redact=False)


def test_an_interactive_terminal_shows_matches() -> None:
    assert show_matches_by_default(Stream(interactive=True), {}) is True


def test_a_pipe_or_a_file_does_not() -> None:
    assert show_matches_by_default(Stream(interactive=False), {}) is False


def test_continuous_integration_never_shows_matches() -> None:
    assert show_matches_by_default(Stream(interactive=True), {"CI": "true"}) is False, (
        "a build log is as public as the repository, whatever it looks like"
    )


def test_the_command_line_redacts_when_not_interactive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "notes.md").write_text(f"stored in {SECRET_PATH}\n", encoding="utf-8")

    assert main([str(tmp_path)]) == 1
    assert SECRET_PATH not in capsys.readouterr().out


def test_the_command_line_can_be_asked_for_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "notes.md").write_text(f"stored in {SECRET_PATH}\n", encoding="utf-8")

    assert main(["--show-matches", str(tmp_path)]) == 1
    assert SECRET_PATH in capsys.readouterr().out


def test_redaction_can_be_forced(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "notes.md").write_text(f"stored in {SECRET_PATH}\n", encoding="utf-8")

    assert main(["--redact", "--show-matches", str(tmp_path)]) == 1
    assert SECRET_PATH not in capsys.readouterr().out, "the safe flag must win"


# ---------------------------------------------------------------------------
# Round 5, finding 2: a directory is likelier to be a surname than a file is.
# ---------------------------------------------------------------------------


def test_every_component_of_a_matched_path_is_redacted() -> None:
    finding = Finding(
        rule="LOCAL",
        message="matches an entry in the local deny-list",
        source="Ashenmoor-family/records/notes.md",
        line=1,
        match="Ashenmoor",
    )

    rendered = str(finding)

    assert "Ashenmoor" not in rendered, (
        "redacting only the basename leaves the personal literal in the "
        f"directory, which is exactly where names live here; got {rendered}"
    )


def test_a_redacted_path_stays_usable() -> None:
    finding = Finding(
        rule="LOCAL",
        message="matches an entry in the local deny-list",
        source="Ashenmoor-family/records/notes.md",
        line=1,
        match="Ashenmoor",
    )

    rendered = str(finding)

    assert rendered.count("/") == 2, "the depth distinguishes one finding from another"
    assert "Ashenmoor" in finding.render(redact=False), "a local run still locates it"


# ---------------------------------------------------------------------------
# Round 7: the source becomes unprintable, the way the matched value already is.
#
# Five rounds of redaction findings were each fixed where they leaked. The
# matched value stopped leaking when it became a type that cannot be printed
# raw; the source never got the same treatment, so it leaked through a branch
# that forgot a flag, through every finding that never set one, and through a
# message that interpolated a filename.
# ---------------------------------------------------------------------------

PERSONAL_PATH = "Ashenmoor-family/records/notes.md"


def test_a_finding_that_does_not_match_the_path_still_redacts_it() -> None:
    """The flag was set on one kind of finding and nothing else.

    A personally named file draws findings that have nothing to do with its
    name -- its type is unprovable, its content is unclassifiable -- and each
    of those printed the path in clear while a finding about the *name*
    redacted the identical string, often on the adjacent line.
    """
    finding = Finding(
        rule="P2",
        message="content is not UTF-8 (12 bytes); refusing what cannot be proved safe",
        source=PERSONAL_PATH,
        line=1,
    )

    assert "Ashenmoor" not in str(finding), (
        f"the path is data whatever the finding is about; got {finding}"
    )


def test_no_route_off_a_finding_prints_its_source_raw() -> None:
    """Every way Python has of turning these objects into text.

    The matched value has this test already. The source did not, which is the
    whole of this round: safety that depends on the rendering path being the
    expected one is not safety.
    """
    finding = Finding(rule="P2", message="unprovable", source=PERSONAL_PATH, line=1)

    routes = {
        "str(finding)": str(finding),
        "repr(finding)": repr(finding),
        "f-string of finding": f"{finding}",
        "str(source)": str(finding.source),
        "repr(source)": repr(finding.source),
        "f-string of source": f"{finding.source}",
        "formatted source": format(finding.source, ">10"),
        "container repr": repr([finding.source]),
    }

    leaks = sorted(name for name, text in routes.items() if "Ashenmoor" in text)
    assert leaks == [], f"these routes print the source in clear: {leaks}"


def test_a_trailing_run_that_looks_like_an_extension_is_redacted() -> None:
    """An arbitrary run after a dot is not a file type.

    Keeping the suffix in clear was the round-5 answer to staying locatable.
    It was wrong: nothing constrains what follows the last dot in a name, so
    the exemption was a hole shaped like a surname.
    """
    finding = Finding(
        rule="LOCAL",
        message="matches an entry in the local deny-list",
        source="docs/tree.Ashenmoor",
        line=1,
        match="Ashenmoor",
    )

    assert "Ashenmoor" not in str(finding), f"a suffix is not a type; got {finding}"


def test_a_history_finding_says_so_while_redacting_its_path() -> None:
    """The scope is the guard's own word, not data.

    Redacting it along with the path made a redacted history finding
    indistinguishable from a redacted tip finding, which is the one thing the
    prefix exists to tell you.
    """
    tip = Finding(rule="P2", message="unprovable", source=PERSONAL_PATH, line=1)
    history = Finding(
        rule="P2",
        message="unprovable",
        source=SourcePath(PERSONAL_PATH, scope=HISTORY_SOURCE),
        line=1,
    )

    assert str(history).startswith(f"{HISTORY_SOURCE}/"), (
        f"a historical blob must still say it is historical; got {history}"
    )
    assert str(tip) != str(history), "the two scopes must not render identically"
    assert "Ashenmoor" not in str(history)


def test_the_unprovable_type_is_not_printed_in_the_message() -> None:
    """The second channel, and the one the source type cannot close.

    A message is text by the time it exists, so a value interpolated into one
    is redacted nowhere and revealed nowhere. The type belongs in the field
    the destination rule already governs.
    """
    findings = scan_blob(b"nothing\n", "Ashenmoor")

    assert rules(findings) == ["P2"], f"a file with no extension is unprovable, got {findings}"
    assert "Ashenmoor" not in str(findings[0]), (
        f"the filename stood in for the file type and was printed twice; got {findings[0]}"
    )
    assert "Ashenmoor" in findings[0].render(redact=False), (
        "the operator still needs to know which type to allow"
    )
    assert _HOW_TO_ALLOW_A_TYPE in findings[0].message, "the message still says how to allow it"
