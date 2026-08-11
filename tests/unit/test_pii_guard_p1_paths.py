"""P1 -- no path that identifies a person or a machine.

Amended in fix round 2. "No absolute filesystem path" was the wrong property:
``/people`` is an absolute path by that definition and leaks nothing, and this
repository is about to grow an HTTP server full of such strings. Three
detectors now, each precise on its own:

* drive-letter and UNC paths, which no route can collide with;
* a leading-slash path rooted at a real filesystem root, with two or more
  components;
* any leading-slash string at all when it sits in a path-bearing position.
"""

from __future__ import annotations

from gramps_live_api.core.pii_guard import scan_text
from tests.fixtures.expectations import rules
from tests.fixtures.synthetic import (
    extended_unc_path,
    extended_windows_path,
    gedcom_x_json,
    json_escaped,
    named_home_path,
    posix_path,
    unc_path,
    unicode_escaped_key,
    windows_path,
    windows_path_forward_slashes,
)


def test_drive_letter_path_is_a_finding() -> None:
    findings = scan_text(f"the tree lives at {windows_path('Data', 'Trees', 'export.txt')}")
    assert rules(findings) == ["P1"], f"expected one P1 finding, got {findings}"


def test_drive_letter_path_with_forward_slashes_is_a_finding() -> None:
    findings = scan_text(windows_path_forward_slashes("Data", "Trees", "export.txt"))
    assert rules(findings) == ["P1"], f"expected one P1 finding, got {findings}"


def test_unc_path_is_a_finding() -> None:
    findings = scan_text(unc_path("fileserver", "shared", "trees", "export.txt"))
    assert rules(findings) == ["P1"], f"expected one P1 finding, got {findings}"


def test_posix_absolute_path_is_a_finding() -> None:
    findings = scan_text(posix_path("srv", "backups", "export.txt"))
    assert rules(findings) == ["P1"], f"expected one P1 finding, got {findings}"


def test_finding_reports_source_and_line() -> None:
    text = "\n".join(
        [
            "# Notes",
            "",
            f"The export was written to {posix_path('srv', 'backups', 'export.txt')}.",
            "Nothing else here.",
        ]
    )

    findings = scan_text(text, source="notes.md")

    assert len(findings) == 1, f"expected exactly one finding, got {findings}"
    assert findings[0].source == "notes.md"
    assert findings[0].line == 3, f"expected line 3, got line {findings[0].line}"


def test_relative_paths_are_not_findings() -> None:
    text = "see docs/example.md and src/gramps_live_api/core/pii_guard.py"
    assert scan_text(text) == [], "relative paths must not be P1 findings"


def test_urls_are_not_findings() -> None:
    text = "documented at https://example.invalid/projects/one/two.html"
    assert scan_text(text) == [], "URL paths must not be P1 findings"


def test_prose_containing_slashes_is_not_a_finding() -> None:
    text = "read and/or write, a 3/4 majority, release 1.2/beta"
    assert scan_text(text) == [], "prose slashes must not be P1 findings"


def test_portable_posix_locations_are_allowlisted() -> None:
    shebang = "#!" + posix_path("usr", "bin", "env") + " python3"
    devnull = "redirect output to " + posix_path("dev", "null")

    assert scan_text(shebang) == [], "a shebang must be allowlisted"
    assert scan_text(devnull) == [], "the POSIX null device must be allowlisted"


def test_a_single_component_absolute_path_is_a_finding() -> None:
    findings = scan_text("home=" + posix_path("private-user"))

    assert rules(findings) == ["P1"], (
        "the property is *absolute path*, not a minimum number of components; "
        f"one component can carry a username on its own, got {findings}"
    )


def test_a_non_ascii_absolute_path_is_a_finding() -> None:
    path = posix_path("home", "用户", "tree")

    findings = scan_text("home=" + path)

    assert rules(findings) == ["P1"], (
        f"a path is a path in every script, not only in ASCII, got {findings}"
    )
    # Asserting the whole match, not merely that something was found: an
    # ASCII-only component class still matches the leading ASCII component and
    # reports a P1, while skipping the one that carries the username. That is a
    # pass for the wrong reason, and a mutation run caught it.
    assert findings[0].match == path, (
        "recognising only the ASCII prefix is not recognising the path; the "
        f"username is in the part that was skipped, got {findings[0].match!r}"
    )


def test_markup_closing_tags_are_not_findings() -> None:
    """A closing tag carries a slash and is still markup.

    The sample used to be a Gramps name block, which made this file score
    against the content property once elements were weighted -- the same
    literal-in-a-tracked-file problem the fixtures had. Neutral markup makes
    the same point about slashes without carrying a person.
    """
    text = "<section><title>Chapter One</title><body>Some prose.</body></section>"

    assert scan_text(text) == [], "a closing tag is markup, not a path"


# ---------------------------------------------------------------------------
# The amendment: routes are not paths, positions still are.
# ---------------------------------------------------------------------------


def test_an_http_route_is_not_a_finding() -> None:
    text = "\n".join(
        [
            '@app.get("/people")',
            '@app.get("/health")',
            '@app.post("/apply")',
            'router.add("/query", handler)',
        ]
    )

    assert scan_text(text) == [], (
        "a server-relative route carries no identity, and this repository is "
        "about to be full of them; a guard that must be overridden per route "
        "is a guard that gets switched off"
    )


def test_a_markdown_link_is_not_a_finding() -> None:
    assert scan_text("see [the guide](/docs/guide) for details") == []


def test_a_route_shaped_string_in_a_path_position_is_still_a_finding() -> None:
    findings = scan_text('backup_dir = "' + posix_path("people") + '"')

    assert rules(findings) == ["P1"], (
        "position is what distinguishes a path from a route; the same string "
        f"assigned to a path-named identifier is a path, got {findings}"
    )


def test_a_filesystem_call_is_a_path_position() -> None:
    for call in ("open(", "Path(", "os.path.join("):
        findings = scan_text(f'{call}"' + posix_path("data", "x") + '")')
        assert rules(findings) == ["P1"], f"{call} takes a path, got {findings}"


def test_a_file_url_is_a_finding() -> None:
    # file: addresses the local filesystem; http(s) does not. One scheme with
    # a defined meaning, not a list of syntax forms.
    text = "see file://" + posix_path("home", "private-user", "tree.ged") + " for the export"

    findings = scan_text(text)

    assert rules(findings) == ["P1"], (
        "a file URL defeated every detector, including a rooted personal path "
        f"in plain prose, because the lookbehind rejects a slash after a slash; got {findings}"
    )


def test_an_http_url_is_still_not_a_finding() -> None:
    assert scan_text("documented at https://example.invalid/home/private-user/tree") == [], (
        "an http path is served, not stored; only file: addresses a filesystem"
    )


def test_an_unrooted_single_component_outside_a_path_position_is_accepted() -> None:
    # The documented residual of the amendment. Recorded as a test so the
    # decision is visible where somebody would otherwise "fix" it.
    assert scan_text("the endpoint is " + posix_path("preview")) == []


def test_allowlist_is_by_exact_string_never_by_prefix() -> None:
    text = "the tree lives at " + posix_path("dev", "nullify", "trees", "export.txt")

    findings = scan_text(text)

    assert rules(findings) == ["P1"], (
        "a path that merely starts with an allowlisted string must still be a "
        f"P1 finding, got {findings}"
    )


def test_an_extended_unc_volume_path_is_a_finding() -> None:
    # The extended DRIVE spelling was already caught, by the drive-letter
    # detector matching inside it. This sibling has no drive letter, so nothing
    # was left to find it. Both are the same paths carrying a prefix, so the
    # fix completes the existing patterns rather than adding a detector.
    findings = scan_text("copied to " + extended_unc_path("fileserver", "shared", "trees"))

    assert rules(findings) == ["P1"], f"an extended UNC path names a machine, got {findings}"


def test_an_extended_drive_path_is_still_a_finding() -> None:
    findings = scan_text("copied to " + extended_windows_path("Users", "private-user"))

    assert rules(findings) == ["P1"], f"already caught, and must stay caught; got {findings}"


def test_a_removed_line_in_a_quoted_diff_is_a_finding() -> None:
    # Round 5, finding 6: the lookbehind carried an undocumented hyphen, so a
    # removed line was skipped while the added line beside it was caught.
    # Pasting a diff into a Markdown file is an ordinary thing to do.
    removed = "-" + posix_path("home", "quorvane", "trees")
    added = "+" + posix_path("srv", "data", "trees")

    assert rules(scan_text(removed)) == ["P1"], "a removed line is still a line"
    assert rules(scan_text(added)) == ["P1"], "and the added line was already caught"


# ---------------------------------------------------------------------------
# Spellings that reach the scanner undecoded: judged as written, not as read.
# ---------------------------------------------------------------------------


def test_a_named_home_directory_is_a_finding() -> None:
    """An account name identifies a person as directly as their home does.

    P1 requires a leading slash, and the tilde spelling has none -- so the one
    form that carries an account name in plain sight was the one form the rule
    could not see. It is not an escaping problem: it is a spelling of a home
    path that the pattern was never taught.
    """
    findings = scan_text(f'path = "{named_home_path("private-user", "trees")}"')

    assert rules(findings) == ["P1"], f"a named home directory publishes an account, got {findings}"


def test_expanding_a_named_home_directory_is_a_finding() -> None:
    """The same name, inside the call that turns it into a real path."""
    findings = scan_text(f'expanduser("{named_home_path("private-user", "trees")}")')

    assert rules(findings) == ["P1"], f"the account name is in the source, got {findings}"


def test_a_json_escaped_path_is_the_path_it_decodes_to() -> None:
    """Escaped separators are a spelling, not a different string.

    The pattern wants a literal separator, so writing each one as JSON's
    escaped solidus hid an ordinary absolute path from every detector. The
    document means the same thing to anything that parses it.
    """
    plain = posix_path("home", "private-user", "tree")

    assert rules(scan_text(f'{{"home":"{plain}"}}')) == ["P1"], "the premise: unescaped is caught"

    findings = scan_text(f'{{"home":"{json_escaped(plain)}"}}')

    assert rules(findings) == ["P1"], f"the same path, one spelling along, got {findings}"


def test_a_unicode_escaped_key_is_the_key_it_decodes_to() -> None:
    """A GEDCOM X member name spelled with escapes parses to the same object."""
    plain = gedcom_x_json()

    assert rules(scan_text(plain, source="notes.md")) == ["P2"], (
        "the premise: plain keys are caught"
    )

    findings = scan_text(unicode_escaped_key(plain, "fullText"), source="notes.md")

    assert rules(findings) == ["P2"], f"an escaped key is the same key, got {findings}"


def test_a_document_describing_an_escape_is_not_a_finding() -> None:
    """The false-positive side, asserted rather than hoped for.

    Decoding changes what ordinary documents look like to the scanner, and
    this repository is full of prose about escape sequences. A sentence naming
    one must not become a path.
    """
    prose = "JSON writes a solidus as backslash-solidus, and a letter as backslash-u-hex."

    assert scan_text(prose, source="docs/notes.md") == [], "prose about escapes is prose"


def test_an_escape_cannot_renumber_the_findings_below_it() -> None:
    """Decoding must not move a line, only read it.

    Line numbers are computed from the decoded text, so an escape that decoded
    to a line break would insert a line and shift every finding after it -- an
    operator opening the file at the reported number finds the wrong line, and
    nothing announces that. Measured: the path below moves from line 2 to line
    3 without this.

    Added because the mutant removing the guard survived. The limit was
    written on principle and asserted by nothing, which makes it a comment
    rather than a rule.
    """
    escape = chr(92) + "u000a"
    document = f'label = "{escape}"\n{{"home":"{posix_path("home", "private-user", "tree")}"}}\n'

    findings = scan_text(document, source="notes.md")

    assert [finding.line for finding in findings] == [2], (
        f"an escape decoding to a line break renumbered what follows it, got {findings}"
    )
