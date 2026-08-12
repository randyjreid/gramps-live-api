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

from gramps_live_api.core.pii_guard import PORTABLE_PATHS, scan_text
from tests.fixtures.expectations import rules
from tests.fixtures.synthetic import (
    bare_named_home_path,
    every_separator_run_spelling,
    extended_unc_path,
    extended_windows_path,
    gedcom_x_json,
    json_escaped,
    named_home_path,
    posix_path,
    prose_describing_json_keys_with_escaped_quotes,
    repeated_separators,
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


def test_a_bare_named_home_directory_is_a_finding_where_a_path_belongs() -> None:
    """``~login`` is a whole home path; the account name IS the payload.

    The tilde detector requires a separator and a component under it, so the
    shortest spelling -- the one carrying nothing BUT the account name -- was
    the one it could not see. Every construction here puts it somewhere that
    already means "what follows is a filesystem path", which is where the
    corroboration comes from.
    """
    account = bare_named_home_path("private-user")
    constructions = (f"cd {account}", f"home = {account}", f'expanduser("{account}")')

    missed = [line for line in constructions if not scan_text(line, source="notes.md")]

    assert missed == [], f"a bare home path publishes an account name; missed {missed}"


def test_a_tilde_in_ordinary_prose_is_not_a_home_directory() -> None:
    """Why the fix went through POSITION and not through shape.

    The obvious repair is to make the trailing component optional in the tilde
    pattern. That pattern is shape alone, with nothing to corroborate it, so
    the repair reports every approximation, version constraint and duration in
    the repository -- a fail-open traded for a false positive on ordinary
    prose. The position is what supplies the corroboration the shape lacks, so
    the shape detector is left exactly as it was and this asserts that.
    """
    prose = "The scan takes ~30 seconds over ~2.5 MB, on ~1.0 of overhead."

    assert scan_text(prose, source="notes.md") == [], "an approximation is not an account name"


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


def test_an_escape_cannot_manufacture_structure_the_document_does_not_have() -> None:
    """Decoding must read a document, never rewrite it into a different one.

    ⚠️ **The test above does not cover this and never did.** Its payload names
    escapes in ENGLISH -- "backslash-solidus" -- so it contains no escape
    sequence at all and has never once exercised the decoder. A test whose name
    promises a guarantee its body does not check is why this arrived as a
    review finding rather than as a red suite.

    An escape can only occur INSIDE a string literal, so a delimiter it decodes
    to is content of that string and can never be a delimiter of the document
    around it. Producing one is not decoding; it is manufacturing structure the
    source does not contain -- here, four apparent structural keys out of prose
    that merely describes the format the guard looks for.
    """
    findings = scan_text(prose_describing_json_keys_with_escaped_quotes(), source="docs/notes.md")

    assert findings == [], (
        f"a document describing the format was read as a document in it, got {findings}"
    )


def test_a_repeated_separator_is_the_same_separator() -> None:
    """A path written with a doubled separator is the path it denotes.

    Issue #3 item 2. The rooted detector's stated property is a leading
    separator under a real filesystem root with two or more components, and a
    doubled separator satisfies every one of those terms: the empty string
    between two separators is not a component. It matched nothing, because the
    pattern could not cross the gap and its lookbehind refused to restart at
    the second one.

    Asserted as AGREEMENT between the two spellings rather than as "the doubled
    one is caught". The second is satisfied by a special case for two
    separators, which is the enumeration this module has now paid for twenty
    times over; the first is only satisfied by stating the rule.
    """
    path = posix_path("home", "private-user", "tree.ged")
    written = "the export lives at {}."

    assert rules(scan_text(written.format(path))) == ["P1"], "the premise: one separator is caught"

    findings = scan_text(written.format(repeated_separators(path)))

    assert rules(findings) == rules(scan_text(written.format(path))), (
        f"the same path, written with a repeated separator, got {findings}"
    )


def test_every_path_spelling_agrees_with_itself_however_its_separators_repeat() -> None:
    """Where else the rule holds -- which is everywhere a separator joins.

    The measured miss was never one detector. A repeated separator defeated the
    rooted shape and the named home directory outright, and degraded the
    drive-letter match to a single character -- a finding whose evidence names
    nothing an operator can act on. One cause, three constructions, which is
    this module's recurring defect: a rule agreed, then applied in only some of
    the places it holds.

    The VALUE is asserted, not merely the rule. Agreement on the rule alone
    passes on the drive-letter row, because that row was already reporting a
    finding -- just not one that says which path it found.

    The path-bearing position is deliberately absent, and the test below says
    why: a run of separators where that detector's value begins is a URL
    authority rather than a repeated separator, and its tail has tolerated
    repeats all along.
    """
    constructions = (
        ("rooted in prose", "the export lives at {}.", posix_path("home", "private-user", "tree")),
        ("a named home directory", "stored under {} today", named_home_path("private-user", "t")),
        ("a drive-letter path", "the tree lives at {}", windows_path_forward_slashes("Data")),
    )

    disagreed: list[str] = []
    for name, written, path in constructions:
        single = scan_text(written.format(path))
        doubled = scan_text(written.format(repeated_separators(path)))

        if rules(single) != ["P1"]:
            disagreed.append(f"{name}: the premise fails -- one separator gives {single}")
        elif rules(doubled) != ["P1"]:
            disagreed.append(f"{name}: a repeated separator gives {doubled}")
        elif single[0].match != path:
            disagreed.append(f"{name}: one separator reports {single[0].match!r}, not the path")
        elif doubled[0].match != repeated_separators(path):
            disagreed.append(f"{name}: a repeated separator reports {doubled[0].match!r}")

    assert disagreed == [], f"a spelling of the separator changed the verdict: {disagreed}"


def test_a_url_authority_is_not_a_repeated_separator() -> None:
    """The false-positive side of the separator rule, asserted rather than hoped for.

    ``file`` is one of the identifiers that make a path-bearing position, so
    the pair opening a file URL's authority sits exactly where that detector
    reads its value. Treating it as a repeated separator -- which the first
    draft of the fix did -- puts the authority INSIDE the reported value, and
    a value carrying it is no longer the exact string the portable allowlist
    holds. Measured across nine constructions: every file URL was renamed from
    the detector that understands the scheme to the one that does not, and two
    locations that identify nobody became findings.

    Both directions are asserted here, because either alone passes on a fix
    that breaks the other.
    """
    portable = ["usr" + chr(47) + "bin" + chr(47) + "env", "dev" + chr(47) + "null"]
    for location in portable:
        text = "written to file:" + chr(47) * 3 + location
        assert scan_text(text) == [], f"a portable location identifies nobody, got {text!r}"

    personal = posix_path("home", "private-user", "tree.ged")
    findings = scan_text("copied from file:" + chr(47) * 2 + personal)

    assert rules(findings) == ["P1"], f"a personal path in a file URL is a finding, got {findings}"
    assert findings[0].match == personal, (
        "the value must be the path the URL names, not the path with the "
        f"authority in front of it, got {findings[0].match!r}"
    )


def _every_context(value: str) -> dict[str, str]:
    """The value written into each surrounding that a detector reads it from.

    The allowlist is compared in one place, but the value reaching that place
    comes from four different patterns, and a repair proved in one surrounding
    is proved for one pattern. Assembled rather than written, like every path
    in this file.
    """
    return {
        "bare": value,
        "in prose": f"the script at {value} is used",
        "in a path-bearing position": 'path = "' + value + '"',
        "in a file URL": "written to file:" + chr(47) * 2 + "host" + value,
    }


def test_every_portable_path_is_allowlisted_however_its_separators_repeat() -> None:
    """The allowlist reads a path the way the detectors that matched it do.

    A regression, and one that could not have been measured over tracked
    content: ``1aafc1d`` taught four patterns that a run of separators is one
    separator, and left the allowlist comparing the spelling. The comparison
    then disagreed with the patterns about which path it had been given, and
    locations that identify nobody became findings.

    **Walked over ``PORTABLE_PATHS`` itself**, in every surrounding a detector
    reads a value from. A test naming three examples is satisfied by three
    special cases; the allowlist's own entries are what the code holds, and
    covering the values the code holds is the thing the original measurement
    could not do by scanning real content.
    """
    reported: list[str] = []
    for location in sorted(PORTABLE_PATHS):
        for spelling in every_separator_run_spelling(location):
            for surrounding, text in _every_context(spelling).items():
                findings = scan_text(text)
                if findings:
                    reported.append(f"{spelling!r} {surrounding}: {findings}")

    assert reported == [], (
        f"a location the allowlist holds became a finding by repeating its separators: {reported}"
    )


def test_a_repeated_separator_does_not_allowlist_a_path_that_identifies_somebody() -> None:
    """The other direction: reading runs as joins must not admit anything else.

    The values whose verdict the fix changes are exactly the respellings of
    what the allowlist already holds. A path that is not one of them is still a
    finding under every spelling, and still reports the whole path as its
    evidence rather than a fragment of it.
    """
    personal = posix_path("home", "private-user", "tree.ged")

    for spelling in every_separator_run_spelling(personal):
        findings = scan_text(f"the export lives at {spelling}.")

        assert rules(findings) == ["P1"], f"{spelling!r} identifies somebody, got {findings}"
        assert findings[0].match == spelling, (
            f"the evidence must be the path as written, got {findings[0].match!r}"
        )


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
