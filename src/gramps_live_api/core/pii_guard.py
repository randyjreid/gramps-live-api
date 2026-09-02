"""Refuse to let personal data reach a public repository.

This repository is public and its owner is not. The guard states *properties*
that committed content must satisfy, never a list of strings that must not
appear -- a committed deny-list of personal data would itself be the leak this
module exists to prevent.

P1
    No path that identifies a person or a machine may appear in committed
    content. Amended in fix round 2: "no absolute filesystem path" was the
    wrong property, because a server-relative route is an absolute path by that
    definition and identifies nobody. See CONTRIBUTING.md for the recorded
    decision and what it deliberately stops catching.
P2
    No genealogy data the guard has a property for may be committed, whatever
    it is named -- and no content it cannot prove safe. Content the guard
    cannot classify is a finding: refuse what cannot be proved safe rather than
    passing what the guard fails to recognise.

    The two halves do different work, and saying only the first overclaims. A
    format with a property is caught wherever it sits; an unrecognised format
    inside a safe file type rests on the type gate, which is the residual this
    project recorded first -- a family tree fits inside perfectly valid
    Markdown. GEDCOM X was the proof: refused as a text file because text is
    not a safe type, and clean as Markdown until it was given a property.
Credentials were a third property for four rounds and are no longer scanned
for at all. Four mechanisms failed, the last taking its own suppression channel
down with it, and this repository's risk is personal data rather than secrets.
See CONTRIBUTING.md; a dedicated scanner is the answer if a later phase ever
handles real credentials.

Anything narrower than a property -- a pattern written to catch one particular
string -- belongs in the local deny-list described at the foot of this module,
not here. If a property has to grow a special case to catch something, the
property is wrong and the right response is to say so, not to add the case.
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
import subprocess
import sys
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from weakref import WeakKeyDictionary

SOURCE_SHA256_AT_IMPORT = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
"""This module's own bytes, hashed **during the import that compiled it**.

⛔ **Read here rather than by whoever wants it, and the difference is a
fail-open.** ``history_anchor`` records a digest of the rules that proved a
prefix clean. Hashing this file *later* certifies whatever it says at that
moment -- but the scan runs the functions already compiled into memory. An edit
landing between this module's import and that hash would be recorded as the
rules in force while the OLD code did the scanning, and the anchor would then
license skipping commits nobody checked under the new rule.

⚠️ Rehashing at the end of the run does not catch it: the file is stable at both
reads, and both read the wrong thing.

⭐ Taken here, the value is fixed by the same module execution that produced the
functions, so it describes the code that will actually run.
"""

DENYLIST_FILENAME = ".pii-denylist"
DENYLIST_PREFIX = DENYLIST_FILENAME

UNDECODABLE_MARKER = "�"
"""What a byte that is not UTF-8 becomes when a committed name is decoded."""

HISTORY_SOURCE = "history"
"""How a finding from a historical blob names itself.

A revision expression is operator-supplied text of unknown content -- a
filesystem path has reached git through that argument -- so it is never echoed
back. A fixed marker says the same thing and says it more clearly."""


_SECRET_VALUES: MutableMapping[Secret, str] = WeakKeyDictionary()
"""Where the sensitive strings actually live, keyed weakly by their wrapper.

Module-private and keyed by object identity, so reaching this global yields
nothing without already holding the wrapper -- which is the same as holding the
Secret, and that route is `reveal`."""


class Secret:
    """A string that cannot be printed by accident.

    Three rounds of redaction leaks were each fixed at the call site that
    leaked -- a build log, a generated repr, a container f-string, a summary
    line, an exception message. There is always another call site, so this type
    removes the ability to make the mistake rather than the latest instance of
    it: every way Python has of turning an object into text is redacted, and
    the raw value comes out only through ``reveal``, which has exactly one
    caller (asserted by a test).
    """

    # The value is NOT stored on the instance. An attribute is a route: it was
    # publicly readable, and it came back out through __getstate__ and pickle,
    # so the "one audited route" guarantee was false while the test that was
    # meant to prove it merely listed the routes somebody had thought of.
    #
    # A weak-keyed side table leaves nothing to read. It must be weak-keyed:
    # an id()-keyed dict is a trap, because ids are reused after collection --
    # a new wrapper would inherit a dead one's value -- and entries that are
    # never freed accumulate through a long scan.
    __slots__ = ("__weakref__",)

    def __init__(self, value: str) -> None:
        _SECRET_VALUES[self] = value

    def reveal(self) -> str:
        """The raw value. One call site only -- see the test that enforces it."""
        return _SECRET_VALUES[self]

    def _length(self) -> int:
        return len(_SECRET_VALUES[self])

    def __len__(self) -> int:
        return self._length()

    def __bool__(self) -> bool:
        return bool(self._length())

    def __eq__(self, other: object) -> bool:
        # Two Secrets compare by IDENTITY, which is also what keeps the side
        # table working: a weak mapping compares referents when hashes collide,
        # so a content comparison here would re-enter the table and recurse.
        if isinstance(other, Secret):
            return self is other
        # Comparing to a plain string is allowed: a comparison reveals nothing
        # to anyone who does not already hold the value, and refusing it would
        # push callers towards reveal(), which is the thing being rationed.
        if isinstance(other, str):
            return _SECRET_VALUES[self] == other
        return NotImplemented

    def __hash__(self) -> int:
        # Identity, not content: a content hash of a weak key would defeat the
        # table, and equal-but-distinct secrets need not share a bucket.
        return object.__hash__(self)

    def __str__(self) -> str:
        return f"<{self._length()} characters, redacted>"

    # Every remaining route from object to text. __format__ matters as much as
    # the other two: an f-string with a format specifier does not call __str__.
    __repr__ = __str__

    def __format__(self, specification: str) -> str:
        return format(str(self), specification)

    def __reduce__(self) -> tuple[object, ...]:
        # Serialising would carry the value out of the process. There is no
        # use for a pickled Secret, so this is refused rather than redacted.
        raise TypeError("a Secret cannot be serialised")


def _reveal(value: Secret | str) -> str:
    """The one place a Secret is unwrapped.

    Deliberately the only caller of ``reveal``: a test asserts that, because a
    second one restores the regime where safety depended on remembering.
    """
    return value.reveal() if isinstance(value, Secret) else value


class SourcePath:
    """Where a finding was found. Unprintable in the raw, like the value.

    ``Secret`` stopped matched values leaking by removing the ability to print
    one, and the source was left as a plain string for five more rounds. It
    leaked the same way every time and was fixed the same way every time --
    at the site that leaked. The sites kept coming: a branch that forgot to
    set a flag, every finding that never set one, a filename interpolated into
    a message. This type ends that by construction.

    A path is stored as its components, each wrapped, so the redacted form is
    computed from lengths and never from the value: **redacting never
    reveals.** What survives redaction is the scope, the depth, and each
    component's length -- enough to tell two findings apart and to see that
    two lines concern one file. What does not survive is anything a person
    could be named by.

    The ``scope`` is the guard's own word for where it looked, never data, so
    it stays in clear: without it a redacted historical finding is
    indistinguishable from a redacted one at the tip.

    NOT a digest, and deliberately: a hash of a path is a confirmation oracle
    for anyone holding a guess, which in this archive means anyone with a
    surname to try. A per-run identifier was refused for a duller reason --
    the shape already distinguishes findings, and a counter is state to carry
    for a job that needs none.
    """

    __slots__ = ("_parts", "scope")

    def __init__(self, text: str, *, scope: str = "") -> None:
        self._parts = tuple(Secret(part) for part in text.split(_SEPARATOR))
        self.scope = scope

    def _scoped(self, body: str) -> str:
        return f"{self.scope}{_SEPARATOR}{body}" if self.scope else body

    def _shape(self) -> str:
        """Scope, depth and component lengths. Computed without the value."""
        return self._scoped(_SEPARATOR.join(str(part) for part in self._parts))

    def rendered(self, *, redact: bool) -> str:
        """The ONE place the cleartext path is produced, and a test says so.

        Everything else here works from lengths, so nothing but a deliberate
        unredacted render can put a path into text. That single call site is
        the whole guarantee: four earlier redaction fixes were true by
        inspection, and true by inspection is what they were when they broke.
        """
        if redact:
            return self._shape()
        return self._scoped(_SEPARATOR.join(_reveal(part) for part in self._parts))

    def __str__(self) -> str:
        return self._shape()

    # Every remaining route from object to text, for the same reason Secret
    # defines all three: an f-string with a specifier does not call __str__,
    # and a container formats its elements with repr.
    __repr__ = __str__

    def __format__(self, specification: str) -> str:
        return format(str(self), specification)

    def __eq__(self, other: object) -> bool:
        # Compared component by component, never by building the whole path:
        # producing the cleartext to answer a comparison would be a second way
        # to produce it, and there is exactly one.
        #
        # Two wrappers compare by IDENTITY, as two Secrets do. Comparison
        # against a plain string is allowed on the same reasoning Secret uses:
        # it tells nobody anything they did not already hold, and refusing it
        # pushes callers towards revealing instead.
        if isinstance(other, SourcePath):
            return self is other
        if isinstance(other, str):
            expected = other.split(_SEPARATOR)
            if self.scope:
                if not expected or expected[0] != self.scope:
                    return False
                expected = expected[1:]
            return len(expected) == len(self._parts) and all(
                part == component for part, component in zip(self._parts, expected, strict=True)
            )
        return NotImplemented

    def __hash__(self) -> int:
        # Consistent with the equality above without touching the value: equal
        # paths necessarily share a scope and the same component lengths.
        return hash((self.scope, tuple(len(part) for part in self._parts)))


@dataclass(frozen=True, repr=False)
class Finding:
    """One reason a piece of content must not be committed.

    ``match`` is the matched value itself and ``source`` is where it was
    found. Both are unprintable in the raw. Redaction is a property of where
    the finding is being *printed*, not of the finding, so it belongs to
    rendering -- see ``render`` and ``show_matches_by_default``.

    ``repr`` is suppressed and redefined deliberately. The generated one names
    every field, which put the matched value back into any output that formats
    the object with ``repr`` -- including a container f-string, which is how a
    failing assertion reaches a build log. Redaction must not depend on which
    method happens to render the object.
    """

    rule: str
    message: str
    source: SourcePath | str
    line: int
    match: Secret | str = ""

    def __post_init__(self) -> None:
        # Normalised on the way in, so no construction site can forget. From
        # here on the sensitive fields are unprintable by construction.
        #
        # There used to be a flag saying whether the source was safe to print.
        # It was set in one branch and omitted in every other, which is what a
        # flag does. Wrapping here needs nobody to remember anything.
        if not isinstance(self.match, Secret):
            object.__setattr__(self, "match", Secret(self.match))
        if not isinstance(self.source, SourcePath):
            object.__setattr__(self, "source", SourcePath(self.source))

    def render(self, *, redact: bool = True) -> str:
        """One line describing the finding, with or without the matched value.

        Redacted is the default, so every accidental path -- a log, an
        exception, an f-string somebody adds later -- fails safe. The values
        themselves are ``Secret``, so even this method cannot leak by mistake:
        showing them takes a deliberate ``reveal``.
        """
        located = f"{self._reported_source(redact=redact)}:{self.line}: {self.rule} {self.message}"
        if not self.match:
            return located
        if redact:
            return f"{located}: {self.match}"
        return f"{located}: {_reveal(self.match)}"

    def _reported_source(self, *, redact: bool) -> str:
        # The source follows the destination, exactly as the matched value
        # does. One rule for both, rather than a rule for values and an
        # exemption for the field that names the file.
        #
        # The extension used to survive redaction, on the reasoning that it
        # said what kind of thing was hit. It does not: nothing constrains what
        # follows the last dot in a name, so the exemption was a hole shaped
        # like a surname.
        # __post_init__ normalises this; the annotation stays permissive so
        # that any construction site may pass a plain string.
        return cast(SourcePath, self.source).rendered(redact=redact)

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        return f"<Finding {self.render()}>"


# ---------------------------------------------------------------------------
# P1 -- no path that identifies a person or a machine.
#
# Four detectors, each precise on its own. Drive-letter and UNC cannot collide
# with anything a web framework produces. "rooted" is shape, for prose. The
# path-bearing position is what catches a path whose shape says nothing.
# ---------------------------------------------------------------------------

# Allowlisted by EXACT STRING, never by prefix: a path that merely starts with
# one of these is still a finding. These are locations that carry no
# information about whose machine produced the file.
#
# ⚠️ **Exact against the path AS THE PATTERNS READ IT, not as it is spelled** --
# see ``_as_joined``. Comparing the spelling made this allowlist disagree with
# the detectors that had just matched the value, which is the regression that
# entry is written to prevent recurring.
PORTABLE_PATHS = frozenset(
    {
        "/usr/bin/env",
        "/bin/sh",
        "/bin/bash",
        "/dev/null",
        "/dev/stdin",
        "/dev/stdout",
        "/dev/stderr",
        "/tmp",
    }
)

# The patterns are ASSEMBLED FROM CONSTANTS rather than written as literals.
#
# The guard scans its own source, and twice now a hand-written pattern has
# reported itself: a lookbehind class read as a drive path, and a character
# class read as a leading-slash path. Careful editing is not a fix for that --
# it is the same mistake as enumerating cases, one careful edit at a time.
# Composition is: the separator never sits next to "]" or "=" in this file,
# because it is never typed next to them.
_SEPARATOR = "/"
_ESCAPED_BACKSLASH = chr(92) * 2
_ESCAPED_QUESTION = chr(92) + "?"

# A path component is anything that is not whitespace, a separator, or one of
# the characters no filesystem allows in a name. Deliberately not a script or
# alphabet: a path is a path in every language.
#
# Braces are excluded for a second reason: "{handle}" is route-parameter
# syntax, not a filename, so "/media/{handle}" stops being a two-component
# rooted path and reads as the route it is. Colon, already excluded, does the
# same job for the "/media/:handle" spelling.
_COMPONENT = "".join(("[^", r"\s", _SEPARATOR, _ESCAPED_BACKSLASH, ":*?\"'<>|{}]"))


def _joining(separator: str) -> str:
    """One or more separators, where a separator JOINS components.

    A run of separators is the same separator: nothing sits between them, and
    the empty string they enclose is not a component. Every filesystem reads
    both spellings as one path, so a rule that judges the spelling disagrees
    with itself about which path it was given. It disagreed in four places --
    the shape detector, the leading separator of a path-bearing position, the
    named home directory, and the drive-letter match, which reported a single
    character instead of the path.

    ⚠️ **Deliberately NOT used where two separators are SYNTAX rather than a
    join.** The UNC marker that opens a path and the pair that opens a URL
    authority are a fixed number of characters with a defined meaning, not a
    separator repeated; folding them SUBTRACTS detections rather than adding
    any. That is the same trade ``_decoded`` records for the escaped
    backslash, and it is written here because the obvious simplification --
    "then fold everywhere" -- is how this module has lost properties before.
    """
    return "(?:" + separator + ")+"


# The two spellings, each stated once. The class is a class rather than two
# patterns because a Windows path may be written with either separator, and
# has been in every real example this project has met.
_JOIN = _joining(_SEPARATOR)
_JOIN_BACKSLASH = _joining(_ESCAPED_BACKSLASH)
_JOIN_EITHER = _joining("[" + _ESCAPED_BACKSLASH + _SEPARATOR + "]")

# COMPILED FROM ``_JOIN`` ITSELF, and that is the whole fix rather than a
# convenience. Teaching the patterns that a run of separators is one separator
# while the allowlist below went on comparing the spelling left two readings of
# one rule, and the two disagreed: every portable location reported under every
# respelling of itself. One source cannot desynchronise from itself.
_SEPARATOR_RUN = re.compile(_JOIN)

# What may not precede a leading-slash path. Word characters and "." rule out
# relative paths; ":" and the separator rule out URLs; "<" rules out markup, so
# a closing tag is not read as a path.
# The hyphen that used to sit at the end of this class was never intentional,
# and it skipped every removed line in a quoted diff -- an ordinary thing to
# paste into a document. Removing it added no findings across the repository.
_NOT_BEFORE_PATH = "".join(("(?<![:", _SEPARATOR, _ESCAPED_BACKSLASH, ".~", r"\w", "<])"))

# Trailing punctuation belongs to the sentence, not to the path.
_TRAILING_PUNCTUATION = ".,;:!?" + _SEPARATOR + ")]}>\"'`"

# Windows spells the same paths a second way, with an extended-length prefix:
# two backslashes, a question mark, a backslash, and then either a drive path
# or the marker that introduces a UNC one. These are the SAME property in the
# operating system's alternate syntax, so they belong in the existing patterns
# as an optional prefix rather than in a detector of their own.
#
# The extended DRIVE form was already caught -- the drive-letter pattern
# matches inside it -- so only the volume form needed anything.
_EXTENDED_UNC_PREFIX = (
    "(?:" + _ESCAPED_QUESTION + _ESCAPED_BACKSLASH + "UNC" + _ESCAPED_BACKSLASH + ")?"
)

# The roots a real filesystem has. Closed and externally specified -- the FHS,
# Apple's layout, and WSL's /mnt -- which is what makes this enumeration
# acceptable where a provider-token list was not: it does not grow. Its newest
# member, /mnt/<drive>, is a decade old.
FILESYSTEM_ROOTS = frozenset(
    {
        "applications",
        "bin",
        "boot",
        "cores",
        "dev",
        "etc",
        "home",
        "lib",
        "lib32",
        "lib64",
        "libx32",
        "library",
        "media",
        "mnt",
        "network",
        "opt",
        "private",
        "proc",
        "root",
        "run",
        "sbin",
        "srv",
        "sys",
        "system",
        "tmp",
        "usr",
        "users",
        "var",
        "volumes",
    }
)

# The tilde spelling of a home directory, written ONCE and read by two
# detectors below. It used to be spelled inside the shape detector alone, so
# the position detector -- which already means "what follows is a filesystem
# path" -- did not know it, and a change-directory command naming an account
# matched nothing.
#
# That sentence is deliberately not the example. Its first draft wrote the
# command out, and the guard reported this file at this line -- the same trap
# the comment three lines below already records, sprung again by the very fix
# that reads it. Describe the construction; do not spell it.
#
# ⚠️ **A home path is complete at the account name.** What follows it is
# optional, and that optionality is why this is a shared constant rather than
# a widened pattern: the two detectors need DIFFERENT amounts of it. Shape
# alone must still require a component underneath, because `~30` in "takes ~30
# seconds" is otherwise an account name and every approximation in the
# repository becomes a finding. A position supplies the corroboration that
# shape lacks, so there it stands alone.
_HOME_PATH = "~[A-Za-z0-9._-]+"

# Identifiers and calls that mean "what follows is a filesystem path". This is
# root cause D's move applied to P1: position, not shape. It is what catches a
# username assigned to a home-directory variable, whose shape says nothing at
# all -- and, as it happens, what caught this comment's first draft, which
# spelled that example out.
_PATH_POSITION = re.compile(
    r"""
    (?:
        \b\w* (?: path | dir | directory | file | folder | root | home | location )
        \w* \s* ["']? \s* [:=] \s*
      | \b (?: open | Path | PurePath | PurePosixPath | PureWindowsPath
             | copy | copyfile | copytree | move | rmtree | unlink | remove
             | mkdir | makedirs | listdir | scandir | chdir | rename
             | realpath | abspath | expanduser | relpath | samefile
             | isfile | isdir | exists | stat | glob | join
          ) \s* \( \s*
      | \b cd \s+
    )
    ["']?
    (?P<found>
        # A home path, whose account name is the whole payload and needs
        # nothing under it, OR a leading-separator path.
        #
        # ⚠️ The LEADING separator is deliberately not a join, while the tail
        # below is. A run in this one position is a URL AUTHORITY, not a
        # repeated separator: "file" is itself a trigger above, so joining
        # here reads the authority as part of the path. Measured, over nine
        # file-URL constructions: the reported value gained the authority
        # separators, so the evidence shown to an operator would name the
        # authority as part of what it found. The tail already tolerated
        # repeats and always has.
        (?:"""
    + _HOME_PATH
    + r""" | """
    + _SEPARATOR
    + _COMPONENT
    + r"""+ )
      (?:"""
    + _JOIN
    + _COMPONENT
    + r"""*)*
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ABSOLUTE_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "UNC",
        re.compile(
            # The opening marker is SYNTAX -- two characters with a defined
            # meaning -- so it is written as itself and not joined. What
            # follows the host is a join, and is.
            _ESCAPED_BACKSLASH * 2
            + _EXTENDED_UNC_PREFIX
            + "[A-Za-z0-9._-]+"
            + _JOIN_BACKSLASH
            + _COMPONENT
            + "*"
        ),
    ),
    (
        "drive-letter",
        re.compile("(?<![A-Za-z0-9_])[A-Za-z]:" + _JOIN_EITHER + _COMPONENT + "*"),
    ),
    # Shape, for prose, where there is no position to read: a path rooted at a
    # real filesystem root with a component under it. This is the detector that
    # stops reporting /people, /health and /apply.
    (
        "rooted",
        # The trailing separator is optional, and the optional marker has to
        # wrap the whole join: written as a bare suffix it reads as a LAZY
        # repetition instead, which makes the trailing separator required and
        # silently truncates every match to its second-to-last component.
        re.compile(_NOT_BEFORE_PATH + "(?:" + _JOIN + _COMPONENT + "+){2,}" + "(?:" + _JOIN + ")?"),
    ),
    ("path-bearing position", _PATH_POSITION),
    # The tilde spelling of a home directory. P1 wanted a leading separator,
    # and this is the one form that carries an ACCOUNT NAME in plain sight
    # while having none -- so the spelling that identifies a person most
    # directly was the spelling the rule could not see.
    #
    # Not a decoding problem and not fixed by the normalisation: nothing here
    # is escaped. It is a path shape the pattern was never taught, which is
    # why it gets its own entry rather than riding on one.
    #
    # The lookbehind keeps a web path out of it: "/~account/page" under a host
    # is served, not stored, and the URL guard elsewhere makes the same
    # distinction for the same reason.
    #
    # The trailing component stays REQUIRED here and is not required by the
    # position detector above -- see _HOME_PATH. This is shape with nothing
    # corroborating it, and a bare tilde-word is "~30 seconds" as often as it
    # is an account.
    (
        "named home directory",
        re.compile("(?<![" + r"\w" + _SEPARATOR + "~])" + _HOME_PATH + _JOIN + _COMPONENT + "+"),
    ),
    # A file URL IS a filesystem path; it just arrives wearing a scheme. The
    # URL guard in the lookbehind -- which correctly ignores an http path,
    # because that one is served rather than stored -- was hiding it from every
    # other detector, prose included. One scheme with a defined meaning, not a
    # list of syntax forms.
    (
        "file URL",
        re.compile(
            # The pair after the scheme opens the AUTHORITY. Syntax, like the
            # UNC marker above, so it stays written as itself; every separator
            # inside the captured path is a join.
            r"(?i)\bfile:" + _SEPARATOR * 2 + "[^" + _SEPARATOR + r"\s]*"
            r"(?P<found>" + _JOIN + _COMPONENT + "+(?:" + _JOIN + _COMPONENT + "*)*)"
        ),
    ),
)


_ONE_BACKSLASH = chr(92)
_MATCHES_A_BACKSLASH = _ONE_BACKSLASH * 2

# What an escape may NOT decode to. Every one of these OPENS OR CLOSES a
# construct that a rule below reads: JSON's string delimiter, its object
# braces and its key separator, XML's angle brackets, and the backslash a
# Windows path is built from.
#
# The separator is deliberately ABSENT. It sits inside a construct and never
# begins one -- a solidus cannot open a tag without an angle bracket and means
# nothing at all to the JSON scorer -- so decoding it manufactures nothing,
# and it is the spelling the escaped-solidus branch exists for.
_STRUCTURE_CHARACTERS = frozenset('"{}:<>' + _ONE_BACKSLASH)

_JSON_ESCAPE = re.compile(
    # The escaped backslash comes FIRST so that a backslash-then-solidus pair
    # is consumed as one escape rather than read as an escaped separator.
    _MATCHES_A_BACKSLASH * 2
    + "|"
    + _MATCHES_A_BACKSLASH
    + _SEPARATOR
    + "|"
    + _MATCHES_A_BACKSLASH
    + "u[0-9A-Fa-f]{4}"
)


def _decoded(text: str) -> str:
    """Text as it will be READ, not as it was written.

    Every rule here judges spelling, so a document could keep its meaning and
    lose its verdict by choosing a different one. Two spellings did: an
    absolute path with each separator written as JSON's escaped solidus, and a
    GEDCOM X member name written with escapes. Both parse to exactly the thing
    the rule is looking for; neither reached it.

    ⚠️ **This is one normalisation at the funnel, not two patterns taught one
    more spelling each.** Teaching patterns is the enumeration this project has
    now paid for repeatedly -- the next spelling is always the one nobody
    listed.

    Two deliberate limits, both load-bearing:

    * **An escaped backslash is left exactly as written.** The Windows and UNC
      patterns are built to match the escaped form, so decoding it would move
      those detections rather than add any -- a fix that quietly subtracts.
      Consuming the pair here also stops the second backslash being re-read as
      the start of another escape.
    * **An escape decoding to an unprintable character is left alone.** Line
      numbers are computed from this text and reported to a human; an escape
      that decodes to a line break would silently renumber every finding below
      it. Nothing is lost -- a control character is not part of a path or a
      member name.
    * **An escape decoding to a STRUCTURE character is left alone**, for a
      reason rather than by a list -- see ``_STRUCTURE_CHARACTERS``. A
      ``\\uXXXX`` escape can only occur INSIDE a string literal, so a delimiter
      it decodes to is content of that string and is provably not a delimiter
      of the document around it. Producing one is not decoding; it is
      MANUFACTURING structure the source does not contain. Without this, prose
      inside one string value that quotes four member names decodes into four
      apparent structural keys and scores as an export -- a finding on a
      document that merely *describes* the format the guard looks for, which is
      a finding nobody can act on and therefore one contributors route around.

    A false positive is not the cheap side of this trade. Decoding still does
    the job it was adopted for: the escaped solidus above, and a member name
    spelled with escaped letters, both still reach the rules as what they parse
    to.
    """

    def one(match: re.Match[str]) -> str:
        escape = match.group(0)
        if escape == _ONE_BACKSLASH * 2:
            return escape
        if escape.endswith(_SEPARATOR):
            return _SEPARATOR
        character = chr(int(escape[2:], 16))
        if not character.isprintable() or character in _STRUCTURE_CHARACTERS:
            return escape
        return character

    return _JSON_ESCAPE.sub(one, text)


def _as_joined(found: str) -> str:
    """The path as the patterns that matched it READ it: a run of joins is one.

    Used for the allowlist comparison and for nothing else. The reported value
    stays exactly as written -- an operator is shown the text that is in the
    file, not a tidied version of it.

    ⚠️ **Only the separator, never the backslash.** The UNC opener is a fixed
    pair with a defined meaning rather than a separator repeated, which is the
    exception ``_joining`` records; and no location this allowlist holds is
    spelled with a backslash, so folding one would subtract detections to buy
    nothing.

    What this changes is bounded and can be stated rather than sampled: a value
    passes here only when it collapses to a string the allowlist already holds,
    so the verdicts that move are exactly the respellings of eight locations
    that carry no information about whose machine produced the file.
    """
    return _SEPARATOR_RUN.sub(_SEPARATOR, found)


def _first_component(found: str) -> str:
    return found.lstrip(_SEPARATOR).split(_SEPARATOR)[0].casefold()


def _overlaps(span: tuple[int, int], other: tuple[int, int]) -> bool:
    return span[0] < other[1] and other[0] < span[1]


def _scan_line_for_absolute_paths(
    line: str, number: int, source: SourcePath | str
) -> list[Finding]:
    findings: list[Finding] = []
    claimed: list[tuple[int, int]] = []

    for kind, pattern in _ABSOLUTE_PATH_PATTERNS:
        for match in pattern.finditer(line):
            group = "found" if "found" in match.groupdict() else 0
            found = match.group(group).rstrip(_TRAILING_PUNCTUATION)
            if not found or _as_joined(found) in PORTABLE_PATHS:
                continue
            if kind == "rooted" and _first_component(found) not in FILESYSTEM_ROOTS:
                # A leading-slash string that is not rooted anywhere real. It
                # is a route, a link or a fragment -- it identifies nobody.
                continue
            if any(_overlaps(match.span(group), claimed_span) for claimed_span in claimed):
                continue
            claimed.append(match.span(group))
            findings.append(
                Finding(
                    rule="P1",
                    message=f"absolute filesystem path ({kind})",
                    source=source,
                    line=number,
                    match=found,
                )
            )

    return findings


# ---------------------------------------------------------------------------
# P2 -- no genealogy data the guard has a property for, whatever it is
# named, and no content it cannot prove safe. See the module docstring:
# the second half is what carries a format nobody has written one for.
# ---------------------------------------------------------------------------

# Necessary, but nowhere near sufficient: a tree exported under any other name
# is caught by the content sniffing below.
GENEALOGY_EXTENSIONS = frozenset(
    {
        ".bsddb",
        ".db",
        ".db3",
        ".ftm",
        ".ged",
        ".gedcom",
        ".gno",
        ".gpkg",
        ".gramps",
        ".grdb",
        ".gw",
        ".paf",
        ".sqlite",
        ".sqlite3",
    }
)

_SQLITE_MAGIC = b"SQLite format 3" + bytes(1)

# GEDCOM is line-oriented: a level-0 record starts a line. Anchoring to the
# line start is what lets this module discuss GEDCOM without reporting itself.
#
# What the anchor tolerates before the record is ONE shared constant, used by
# every signature. Two of these were pinned to column zero while the third
# allowed leading whitespace, so the same pasted export was caught or missed
# depending on which format it was in and how the paste was indented -- and a
# four-space indent is simply how Markdown renders a code block. An
# inconsistency inside a single tuple is not a policy; it is an oversight
# waiting to be read as one.
#
# It is still an enumeration of decoration, and widening it is still the losing
# move. What stops it being the only defence is the density property below,
# which does not require a level-0 record to be present at all.
_QUOTE_MARKER = ">"
_LINE_PREFIX = "".join(("^[", r"\s", _QUOTE_MARKER, "]*"))

# Decoration a line may be wearing before its first real character: whitespace,
# quoting, diff markers, bullets, table pipes, the quotes a source file puts
# round a string, and an ordered-list marker. Stripped repeatedly, because
# these combine -- a quoted diff line inside a list wears three of them.
_DECORATION = re.compile("".join((r"^(?:\s|[", _QUOTE_MARKER, r"+*|#\"'`,\-])*(?:\d+[.)]\s+)?")))

# A GEDCOM record: a level number, an optional pointer, then a tag. Tags are
# short and upper-case; a custom one starts with an underscore.
_GENEALOGY_RECORD = re.compile(r"^\d{1,2} (?:@[^@\s]+@ )?[A-Z_][A-Z0-9_]{2,14}\b")

_GENEALOGY_RECORDS_PER_FILE = 3
"""How many records anywhere in one file make it genealogy data.

Counted **across the file, not consecutively**. Adjacency was the wrong axis:
the document this repository will actually produce is an importer design note
that explains one record and then shows the next, and twelve records with a
paragraph between each carried a whole identity through a rule that wanted
them touching. Counting across the file subsumes counting consecutively, so
this replaces that rule rather than layering over it.

The number is measured, not chosen -- see CONTRIBUTING for the table. At three
there are **zero** record lines in any tracked file and zero in any blob in the
published range. Two would begin to report ordinary prose; four would miss a
three-line fragment, which is a perfectly serviceable way to publish somebody's
name, sex and date of birth.
"""

# ---------------------------------------------------------------------------
# Gramps XML: weighted by what an element MEANS, not by how many there are.
#
# ⚠️ **The distinction this rests on is REAL versus MENTIONED, and it is load
# bearing, not a refinement.** A document *about* the format mentions its
# elements -- in backticks, in a mapping table, in prose. A document
# *containing* the format has them FILLED: an open tag, text of its own, and a
# closing tag. Score mentions and a genuine importer specification comes out at
# **18** against a threshold of 4; score only filled elements and the same
# document scores 2.
#
# So do NOT "simplify" this into matching any `<word`. That is the same
# simplification as re-anchoring the namespace and as re-arguing the
# prefix-free record match, and it has the same answer: the measurement is in
# CONTRIBUTING, and it is not close.
#
# The weights are the second half. Counting a name part the same as a
# structural tag was the real defect: the element list was chosen for elements
# that appear in quantity in a full export, which is a fair basis for a density
# count and the wrong basis for deciding which elements carry identity.
# `<name><first><surname>` is three elements and a whole person; five `<event>`
# tags are five elements and nobody in particular.
#
# This is still an enumeration. It is accepted deliberately, because it is
# weighted by what an element means rather than lengthened by whatever the last
# reviewer happened to find.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# THE VOCABULARY. One table, both formats, compiled -- not written twice.
#
# ⚠️ Every pattern below is DERIVED from this table. That is the whole point
# and it is not tidiness: the vocabulary used to live in four separate
# enumerations, so an addition could land in one format and miss the other --
# and the commit written to end partial application did exactly that, adding
# Gramps addresses and GEDCOM X name parts in one change and carrying neither
# across. The identical biography was then caught as XML and clean as JSON.
#
# Adding a category or a spelling here reaches both formats because nothing
# downstream has its own list to forget. Do not reintroduce one.
#
# THE ONE DELIBERATE EXCEPTION is the GEDCOM X name-part pairing, defined
# separately below. It is a SHAPE -- an object carrying a type beside a value
# -- rather than a key, so it has no XML counterpart to compile. Named here so
# that its absence from this table reads as a decision rather than an
# oversight, and so nobody folds it in and breaks it.
# ---------------------------------------------------------------------------

_VOCABULARY: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    # category, spellings BOTH formats share, XML-only, JSON-only.
    #
    # The shared column is the point. A row whose spellings were listed once
    # per format would still let an addition land in one of them -- which is
    # the defect this table exists to make impossible -- so anything the two
    # formats call by the same name is written ONCE, and the per-format columns
    # hold only what genuinely differs.
    (
        "identity",
        ("surname",),
        (
            "name",
            "first",
            "ptitle",
            "pname",
            # The rest of what the schema calls a person by, and the one name
            # in the researcher block: a call name, the nicknames, the suffix,
            # the surname group, and the author a source is credited to.
            "call",
            "nick",
            "familynick",
            "suffix",
            "group",
            "sauthor",
            "resname",
        ),
        ("fullText", "given"),
    ),
    (
        # Where somebody lives locates them as surely as what they are called.
        "address",
        ("street", "city", "county", "state", "postal", "country", "phone"),
        # The schema's own address spellings, and the researcher block, which
        # is a home address belonging to a named person by construction.
        ("locality", "resaddr", "reslocality", "rescity", "resstate", "rescountry", "respostal"),
        ("postalCode",),
    ),
    # A way to reach a person names them at least as directly as a home
    # directory does, which P1 already treats as identity.
    ("contact", ("url", "email"), ("resphone", "resemail"), ("emails",)),
    ("prose", ("text", "note"), (), ()),
    (
        "structure",
        (),
        (
            "person",
            "family",
            "gender",
            "birth",
            "death",
            "dateval",
            "placeobj",
            "address",
            "citation",
            "eventref",
            "childref",
            "noteref",
            "attribute",
            # Everything else the schema declares. Structural weight is not a
            # shrug: a document made of four of these is an export whatever
            # they are, which is the density question, while no single one of
            # them names anybody -- which is the whole distinction this table
            # was rewritten around.
            #
            # ⚠️ Three of these are the ones a reader will want to promote --
            # `description`, `cause` and `page` can hold a sentence, and
            # `<description>` in particular reads like prose. They stay at
            # structural weight deliberately. Prose weight is for containers
            # whose PURPOSE is narrative about a person, which the schema says
            # of `note` and `text` and does not say of a caption on a media
            # object or a URL. Promoting them costs a threshold-clearing score
            # for one filled element in any schema document that shows an
            # example, which is the document Phase 1 is about to write.
            "database",
            "created",
            "researcher",
            "mediapath",
            "people",
            "personref",
            "childof",
            "parentin",
            "families",
            "father",
            "mother",
            "rel",
            "events",
            "event",
            "type",
            "sources",
            "stitle",
            "spubinfo",
            "sabbrev",
            "places",
            "coord",
            "location",
            "objects",
            "file",
            "repositories",
            "repository",
            "rname",
            "reporef",
            "notes",
            "range",
            "tags",
            "tag",
            "tagref",
            "citations",
            "citationref",
            "sourceref",
            "srcattribute",
            "bookmarks",
            "bookmark",
            "namemaps",
            "name-formats",
            "format",
            "daterange",
            "datespan",
            "datestr",
            "page",
            "confidence",
            "place",
            "placeref",
            "cause",
            "description",
            "objref",
            "region",
            "data_item",
            "lds_ord",
            "temple",
            "status",
            "sealed_to",
        ),
        ("persons", "names", "nameForms", "relationships", "facts", "notes", "addresses"),
    ),
    (
        # ⚠️ **DELIBERATELY UNWEIGHTED, AND THE WIDENING IS UNAFFORDABLE
        # WITHOUT IT.** These are element names the published schema declares
        # AND the published HTML and SVG element indexes also list. At even the
        # smallest weight, four filled ones reach the threshold -- and this
        # repository is full of markup, so an ordinary snippet would be
        # reported and the gate would become something contributors route
        # around, which is a security failure here rather than an ergonomic
        # one.
        #
        # Accepted on exactly the ground ``FILESYSTEM_ROOTS`` and the drawing
        # exemption are: the collision is read off two published indexes, which
        # are closed and externally specified rather than a list maintained
        # here. The membership is asserted against those indexes by test.
        #
        # **The failure mode taken, stated rather than discovered:** a real
        # export earns nothing from its `<title>` or `<source>` elements. That
        # costs nothing, because such an export is caught many times over by
        # the spellings that collide with nothing -- `person`, `surname`,
        # `placeobj`, `childref` and eighty others.
        #
        # ⚠️ **THE STRUCTURAL GATE THIS BLOCK USED TO RECORD AS REJECTED WAS
        # RULED IN, and it is `_SPELLINGS_THE_DERIVATION_ADDED` above.** The
        # reason is that these two published indexes cannot see the collision
        # that matters: `type`, `file`, `status` and `description` are schema
        # spellings that are also ordinary XML names, they are in NEITHER index,
        # and four filled ones reached the threshold in any document showing an
        # example. This category answered the collision it was shown.
        #
        # ⚠️ **The gate does not make this category redundant, and deleting it
        # would be a widening.** What is left for it is the case the gate
        # deliberately lets through: `<title>` and `<source>` earn nothing
        # INSIDE a document that has named the format, where every other derived
        # row scores. That is a smaller job than it had, and it is a real one --
        # per the diminishing-returns rule, if a future round finds against this
        # category the candidate action is deletion rather than more hardening.
        #
        # ⚠️ **This category is for rows this audit ADDS, and never a
        # retraction.** `text` and `address` collide too and are NOT here: they
        # were weighted before the derivation, and zeroing them would drop
        # existing catches while every number in the measurement improved.
        "collides",
        (),
        ("title", "style", "code", "map", "object", "source", "header"),
        (),
    ),
)

_CATEGORY_WEIGHT = {
    "identity": 2,
    "address": 2,
    "contact": 2,
    "prose": 4,
    "structure": 1,
    "collides": 0,
}


def _elements_of(*categories: str) -> tuple[str, ...]:
    """The Gramps spellings for the named categories: shared plus XML-only."""
    return tuple(
        name
        for category, shared, xml_only, _ in _VOCABULARY
        if category in categories
        for name in shared + xml_only
    )


def _json_keys_of(*categories: str) -> tuple[str, ...]:
    """The GEDCOM X spellings for the named categories: shared plus JSON-only."""
    return tuple(
        name
        for category, shared, _, json_only in _VOCABULARY
        if category in categories
        for name in shared + json_only
    )


_GRAMPS_CATEGORY_OF = {
    name: category for category, shared, xml_only, _ in _VOCABULARY for name in shared + xml_only
}

_GRAMPS_IDENTITY_ELEMENTS = _elements_of("identity", "address", "contact")
_GRAMPS_PROSE_ELEMENTS = _elements_of("prose")
_GRAMPS_STRUCTURE_ELEMENTS = _elements_of("structure")
_GRAMPS_ALL_ELEMENTS = tuple(dict.fromkeys(_GRAMPS_CATEGORY_OF))

_WEIGHTS_BEFORE_THE_DERIVATION = {
    "surname": 2,
    "name": 2,
    "first": 2,
    "ptitle": 2,
    "pname": 2,
    "street": 2,
    "city": 2,
    "county": 2,
    "state": 2,
    "postal": 2,
    "country": 2,
    "phone": 2,
    "url": 2,
    "email": 2,
    "text": 4,
    "note": 4,
    "person": 1,
    "family": 1,
    "gender": 1,
    "birth": 1,
    "death": 1,
    "dateval": 1,
    "placeobj": 1,
    "address": 1,
    "citation": 1,
    "eventref": 1,
    "childref": 1,
    "noteref": 1,
    "attribute": 1,
}
"""Every Gramps spelling the vocabulary held, and its weight, before #4's audit.

⚠️ **This is not a duplicate of the vocabulary; it is a FROZEN SNAPSHOT of a
different moment, and the difference is the point.** The audit that derives the
container list from the published schema has one invariant standing over it:
*no row already in the vocabulary is gated or zero-weighted by this work.* That
is a claim about the past, so it needs a record of the past to be checked
against -- otherwise "nothing was retracted" is only ever a promise in a commit
message, and the quiet way to make a widening's measurement look good is to
zero an existing catch.

Three spellings here are **not** in the published schema at all -- ``birth``,
``death`` and ``email``. They stay exactly as they are for the same reason: the
derivation adds rows, and a row it cannot account for is not thereby wrong.

⚠️ **It lives HERE rather than in the test suite because the gate below reads
it, and two copies of a historical snapshot is the drift this project keeps
paying for.** The independence that move costs is bought back in the suite: the
MEMBERSHIP is pinned there as a sorted literal, so adding a spelling here fails
by name instead of silently widening the ungated domain. That pin is not
optional; it is what makes the move safe.
"""

_SPELLINGS_THE_DERIVATION_ADDED = frozenset(_GRAMPS_CATEGORY_OF) - frozenset(
    _WEIGHTS_BEFORE_THE_DERIVATION
)
"""The gate's domain: every spelling the vocabulary gained from the schema.

⚠️ **THE GATE IS SCOPED TO ROWS, AND A FILE-LEVEL GATE WOULD NOT BE SAFE.**
Conditioning the whole XML scorer on a marker would suppress a pre-existing
catch in a file that carries none -- a note holding a biography, a bare name
block -- which is the retraction the audit's first invariant forbids. Cutting
the domain out of the frozen snapshot instead makes that impossible rather than
merely unobserved: a pre-existing row is not in this set, so no measurement is
needed to show the gate did not reach it.

Derived by subtraction rather than listed, so a row a later schema version adds
is gated the day it is added and a row promoted into the snapshot stops being
gated on the same day, with nothing to remember.
"""

# ---------------------------------------------------------------------------
# THE QUALIFIED-NAME ALTERNATION. ONE CONSTRUCTION SITE, THREE PATTERNS.
#
# Namespaces in XML: a tag is an optional PREFIX, a colon, and the local name.
# The prefix is the DOCUMENT'S OWN ALIAS for a namespace, so two exports of one
# tree may spell the same element `<name>`, `<g:name>` or `<grampsxml:name>` and
# mean exactly the same thing by it. It therefore belongs inside the tag group,
# where a backreference can still close the element it opened, and nowhere at
# all in the category lookup, which asks what the element MEANS.
#
# ⚠️ **Every pattern that SCORES an element is built from this and nothing
# else**, because each used to spell the alternation itself and a prefix
# consequently meant a different thing to each. The gap is LEXICAL, not
# semantic -- with a prefix declared the matcher saw no element in ANY category,
# including the ones weighted correctly -- so filled elements, attributed
# elements and the database signature all scored nothing, and a complete
# identity document was clean.
#
# ⚠️ **AND THE DRAWING EXEMPTION IS DELIBERATELY NOT ONE OF THEM.** It was, and
# the fourth site was deleted: this alternation matches a prefix by SHAPE and
# never resolves it, which is conservative in a scorer -- matching more elements
# means more findings -- and fail-open in an exemption, where matching more
# containers means more SUPPRESSION. See `_DRAWING`, which fails closed instead.
#
# A fourth scoring site hand-rolling its own alternation is caught by test
# rather than by hoping, and so is the drawing being wired back in -- see the
# test that asserts which compiled patterns contain this and which must not.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# WHAT A NAMESPACE PREFIX MAY BE SPELLED WITH. TWO TABLES, TRANSCRIBED.
#
# XML 1.0 (Fifth Edition), W3C Recommendation 26 November 2008, section 2.3:
#
#     NameStartChar ::= ":" | [A-Z] | "_" | [a-z] | [#xC0-#xD6] | [#xD8-#xF6]
#                     | [#xF8-#x2FF] | [#x370-#x37D] | [#x37F-#x1FFF]
#                     | [#x200C-#x200D] | [#x2070-#x218F] | [#x2C00-#x2FEF]
#                     | [#x3001-#xD7FF] | [#xF900-#xFDCF] | [#xFDF0-#xFFFD]
#                     | [#x10000-#xEFFFF]
#     NameChar      ::= NameStartChar | "-" | "." | [0-9] | #xB7
#                     | [#x0300-#x036F] | [#x203F-#x2040]
#
# A prefix is not a Name, though: Namespaces in XML 1.0 (Third Edition), W3C
# Recommendation 8 December 2009, says which one it is --
#
#     Prefix ::= NCName
#     NCName ::= Name - (Char* ':' Char*)     /* An XML Name, minus the ":" */
#
# ⚠️ **THE COLON IS DROPPED FROM NameStartChar AND APPEARS NOWHERE ELSE IN
# EITHER PRODUCTION**, so removing it once yields NCNameStartChar and NCNameChar
# together. Left in, a prefix could BEGIN with a colon -- which is not a legal
# NCName, and which would make `<::name>` an element here.
#
# Closed and externally specified, so these enumerations are accepted on exactly
# the grounds ``FILESYSTEM_ROOTS``, ``_XML_PREDEFINED_ENTITIES`` and
# ``_XML_CHARACTER_RANGES`` are: they do not grow.
# ---------------------------------------------------------------------------

_NCNAME_START_RANGES: tuple[tuple[int, int], ...] = (
    (0x41, 0x5A),  # A-Z
    (0x5F, 0x5F),  # _
    (0x61, 0x7A),  # a-z
    (0xC0, 0xD6),
    (0xD8, 0xF6),
    (0xF8, 0x2FF),
    (0x370, 0x37D),
    (0x37F, 0x1FFF),
    (0x200C, 0x200D),
    (0x2070, 0x218F),
    (0x2C00, 0x2FEF),
    (0x3001, 0xD7FF),
    (0xF900, 0xFDCF),
    (0xFDF0, 0xFFFD),
    (0x10000, 0xEFFFF),
)
"""``NameStartChar`` minus the colon: what a prefix may BEGIN with.

The ranges are the specification's, coarse edges and all -- ``[#x3001-#xD7FF]``
admits ideographic punctuation, and that is the production's decision rather
than this module's. Transcribing it is the point: a hand-narrowed version is an
enumeration pointed backwards, which is the shape this module refuses everywhere
else.
"""

_NCNAME_CONTINUE_RANGES: tuple[tuple[int, int], ...] = _NCNAME_START_RANGES + (
    (0x2D, 0x2D),  # -
    (0x2E, 0x2E),  # .
    (0x30, 0x39),  # 0-9
    (0xB7, 0xB7),
    (0x300, 0x36F),
    (0x203F, 0x2040),
)
"""``NameChar`` minus the colon: what a prefix may CONTINUE with.

⚠️ **The two tables are NOT the same table, and collapsing them is a fail-open.**
A combining mark, a digit, ``-`` and ``.`` may continue a name and may not begin
one; a class that accepted them at the front would read ``<-9:name>`` as an
element and, worse, would stop this pair from being the production it claims to
be. The difference is asserted by test.
"""


def _escaped(code_point: int) -> str:
    """One code point as an ASCII escape a character class can hold."""
    return f"\\u{code_point:04X}" if code_point <= 0xFFFF else f"\\U{code_point:08X}"


def _character_class(ranges: tuple[tuple[int, int], ...]) -> str:
    r"""``ranges`` as a regex character class, spelled entirely in ASCII escapes.

    ⚠️ **Escapes rather than the characters themselves, and that is two problems
    solved by one decision.** A raw endpoint could arrive as ``-``, ``^``, ``]``
    or ``\`` and mean something to the engine instead of being itself; and a
    non-ASCII endpoint would put bytes into a pattern **this module reads back
    out of its own source**. Neither can happen to a character that is never
    emitted. It is also why the fixtures that exercise this are assembled with
    ``chr`` rather than pasted -- the same rule, one level further out.
    """
    return "[" + "".join(_escaped(first) + "-" + _escaped(last) for first, last in ranges) + "]"


_XML_NCNAME = (
    _character_class(_NCNAME_START_RANGES) + _character_class(_NCNAME_CONTINUE_RANGES) + "*"
)
"""``NCName``: one name, no colon in it -- the two tables above, in order.

Extracted so there is **one** transcribed ``NCName`` with three readers: the
element alternation's prefix below, the ``xmlns:`` prefix of a namespace
declaration, and the attribute names in between. A second copy written for the
declaration would be a table somebody has to keep in step with this one, which
is the shape every other duplication in this module has been removed for.
"""

_XML_NAME_END = "(?!" + _character_class(_NCNAME_CONTINUE_RANGES) + "|:)"
r"""Where a ``Name`` ENDS: not a character that could continue it, and not a colon.

⚠️ **A TRANSCRIPTION of the production, and the approximation was a live
fail-open at every site that read it.** This used to be ``\b`` at each call
site. ``\b`` is Python's word boundary, and ``-``, ``.``, ``·``, a combining
mark and an undertie all legally CONTINUE an XML name while satisfying it -- so
``<type-extra id="x"/>`` was scored as ``<type>``, an element the document never
wrote, and 103 vocabulary rows behaved that way under nineteen different
suffixes in both scoring shapes.

⚠️ **The combining mark is the SAME class this module already paid for at the
other end of the same name.** ``<type`` + U+0301 is a legal element name whose
local name is not ``type``; U+0301 is a ``NameChar`` and is not a ``\w``
character, which is exactly what made ``[^\W\d][\w.\-]*`` a live fail-open for
namespace PREFIXES in Change A. One production, one shorthand, missed at the
front of the name and then again at the back.

**The colon is refused as well, and it is a distinct defect rather than tidiness.**
``<type:extra>`` is a legal ``QName`` whose local name is ``extra``; ``\b`` sits
happily between ``e`` and ``:``, so the shared alternation read the PREFIX as
the tag and scored ``type``. Refusing the colon here is what makes
``_local_name`` -- which says the meaning is the local name and the prefix is an
alias -- true of the match as well as of the string.

**Built from ``_NCNAME_CONTINUE_RANGES``, which the module already holds**, so
there is no second character class to keep in step; and emitted by
``_qualified`` rather than written at the call sites, so a fourth scoring site
cannot hand-roll its own and a repair cannot reach two readers out of three.
"""

_XML_NAME_PREFIX = "(?:" + _XML_NCNAME + ":)?"
r"""An optional namespace prefix: an ``NCName``, then the colon.

⚠️ **A TRANSCRIPTION of the production, not an approximation of it, and the
approximation was a live fail-open.** This used to be ``[^\W\d][\w.\-]*``, built
from Python's word class. ``\w`` does not match a combining mark, but ``NameChar``
does -- so a document consistently using the legal alias ``a`` + U+0301 was
missed by every pattern that reads an element name at once, and with only the
namespace URI scoring two
against a threshold of four, **a complete identity document was clean.** Being
equally invisible before the prefix work is not a defence: this criterion says a
namespace-prefixed document scores what the unprefixed one scores, and that
document is namespace-prefixed.

**The two classes are different classes** -- a combining mark, a digit, ``-``
and ``.`` may continue a name and may not open one -- and using one in both
positions would read ``<-9:name>`` as an element.

The bound this constant has always claimed still holds and is now asserted
rather than argued: the class cannot match ``<``, ``>``, ``/``, ``=``, a quote,
XML ``S`` or the colon.

⚠️ **That last clause used to read "whitespace", and transcribing ``S`` made the
word false.** ``NameChar`` admits U+1680 OGHAM SPACE MARK, which Python's ``\s``
calls whitespace -- so the class DOES match something a reader of the old
sentence would have been told it could not. The bound that is true, and the one
the test asserts, is about the four characters XML's ``S`` names. A module
asserting something untrue about itself is the defect, not the wording.

**What is still not checked, deliberately: the alias is matched, never
RESOLVED.** Whether the document actually binds it to the Gramps namespace is a
question only a parser can answer, and the namespace URI is weighed separately
for that. Matching by shape errs toward reading more elements, which is the side
that reports.

⚠️ **Which is why nothing that EXEMPTS may be built from this.** "Reads more
elements" is the safe direction only where reading one adds a finding. In an
exemption it removes findings, so the same shape match becomes a fail-open --
see `_DRAWING`, which is not built from this and says why.
"""


# ---------------------------------------------------------------------------
# WHAT AN ATTRIBUTE IS. XML 1.0, W3C Recommendation, §3.1 -- and §2.3 for `S`:
#
#     S         ::= (#x20 | #x9 | #xD | #xA)+
#     STag      ::= '<' Name (S Attribute)* S? '>'
#     Attribute ::= Name Eq AttValue
#     Eq        ::= S? '=' S?
#     AttValue  ::= '"' ([^<&"] | Reference)* '"'
#                 | "'" ([^<&'] | Reference)* "'"
#
# Transcribed rather than approximated, on exactly the grounds the `NCName`
# tables above are -- and here the difference is not academic. The cheap
# approximation for "an attribute in a start tag" is `<[^<>]*xmlns=`, and it
# ACCEPTS THE NAMESPACE QUOTED INSIDE ANOTHER ATTRIBUTE'S VALUE: an element
# whose `desc` attribute describes a declaration has declared nothing. Reaching
# the attribute through a sequence of complete `Attribute` productions is what
# refuses that, and nothing weaker does.
#
# Closed and externally specified, so this transcription is accepted on exactly
# the grounds the productions above it are: it does not grow.
# ---------------------------------------------------------------------------

_XML_WHITESPACE_RANGES: tuple[tuple[int, int], ...] = (
    (0x9, 0x9),  # TAB
    (0xA, 0xA),  # LF
    (0xD, 0xD),  # CR
    (0x20, 0x20),  # SPACE
)
"""``S``: the four characters, and there are only ever four."""

_XML_S = _character_class(_XML_WHITESPACE_RANGES)
r"""``S``, as a character class -- built the way every other production here is.

⚠️ **A TRANSCRIPTION of the production, and the approximation it replaces was a
live fail-open.** All three constants below used to spell this ``\s``, which is
Python's whitespace class and matches **twenty-six** characters XML's ``S`` does
not: a non-breaking space, a vertical tab, a form feed, the C1 line separators,
the whole ``U+2000`` block. So ``<wrapper`` + U+00A0 + ``xmlns="…gramps…">`` was
read as a namespace declaration in attribute position. It is not one: XML reads
that tag's name as ``wrapper`` + U+00A0 + ``xmlns``, an element that declares
nothing at all -- and the marker firing on it re-enables some eighty derived
rows.

⚠️ **U+1680 is the sharpest of the twenty-six and says why the two questions are
different questions.** OGHAM SPACE MARK is whitespace to Python and a legal
``NameChar`` to XML, so it is part of the element's own name. A class built from
"what looks like a space" cannot get that right by being more careful; it is
asking the wrong production.

Read by ``_XML_EQ``, ``_XML_ATTRIBUTE``, ``_XMLNS_DECLARATION`` and ``_DRAWING``
-- **one transcription, four readers**, for the reason ``_XML_NCNAME`` is one:
the defect this module keeps paying for is a rule taught to some of the sites
that read a production and not to the rest.
"""

_XML_EQ = _XML_S + "*=" + _XML_S + "*"
r"""``Eq ::= S? '=' S?`` -- the equals sign and what may surround it."""


def _att_value_of(build: Callable[[str], str]) -> str:
    r"""``AttValue`` whose CONTENT is built by ``build`` from the value-body class.

    Either quoting, because the production admits either and a rule that reads
    only ``"…"`` refuses half of well-formed XML -- the same hole the
    derivation script's own ``AttValue`` was repaired for. The two quote
    spellings are stated once here, and ``build`` is handed the body class that
    goes with whichever quote is being written, so a caller cannot get the two
    out of step.

    ⚠️ **The body admits ``&``, which the production admits only as the start of
    a ``Reference``.** That is a deliberate widening of one character, and it
    runs toward reporting: a value is read as a value slightly more often, never
    less. It is also what keeps this pattern honest about `#50` -- a value
    spelling the namespace with character references still occupies an
    `AttValue`, so a `_decoded` that folds them closes that evasion here with no
    change to this production.

    ⚠️ **This exists because "contains" and "is" are different questions.** The
    older helper below could only say *the value holds this somewhere*, which is
    a bare substring test wearing an `AttValue`'s quotes -- and that is exactly
    how a URI naming a DIFFERENT namespace came to name this one. A caller that
    needs to constrain the WHOLE value builds it here instead.
    """
    alternatives = []
    for quote in ('"', "'"):
        alternatives.append(quote + build("[^<" + quote + "]*") + quote)
    return "(?:" + "|".join(alternatives) + ")"


def _att_value(containing: str = "") -> str:
    r"""``AttValue``, optionally required to CONTAIN ``containing``.

    Unchanged in behaviour and re-expressed through ``_att_value_of``: the body
    class, either quoting and the ``&`` widening are all that helper's now, and
    "somewhere inside the value" is spelled here as body-fragment-body.

    ``containing`` is a regex fragment, not a literal.
    """
    return _att_value_of(lambda body: (body + containing + body) if containing else body)


_XML_ATTRIBUTE = _XML_S + "+" + _XML_NAME_PREFIX + _XML_NCNAME + _XML_EQ + _att_value()
r"""``S Attribute`` -- one whole attribute, with the whitespace that must open it.

The whitespace belongs to this fragment rather than to the caller: the
production is ``(S Attribute)*``, so an attribute without a separator in front
of it is not an attribute, and a caller repeating ``S*`` between them would
read ``a="1"b="2"`` as two.

⚠️ **The separator is ``_XML_S``, not ``\s``**, and the two are not the same
question -- see that constant. This is one of the sites the reviewer named; the
declaration's own separator below is the one the audit found.
"""

_XML_ATTRIBUTE_SEQUENCE = "(?:" + _XML_ATTRIBUTE + ")*"
"""``(S Attribute)*`` -- what a start tag's name may be followed by.

⚠️ **This is the fragment that makes "in attribute position" mean anything**, and
the whole reason the productions above are transcribed. A rule that skipped
ahead with ``[^<>]*`` instead would let one attribute's VALUE stand in for the
path to the next one.
"""


def _qualified(*names: str) -> str:
    r"""The tag alternation, prefix and all, as ONE group's worth of pattern.

    ⚠️ **This emits no capturing group, and the alternation is wrapped.** Both
    are load-bearing, and neither is a style choice:

    * Group numbering is read by number in the scoring loops and by a ``\1``
      backreference in the patterns themselves -- see the note above
      ``_NOT_ENDING_AN_ELEMENT`` -- so a group added here would silently shift
      both. The call sites put their own parenthesis round this, which is how
      group 1 comes to hold the WHOLE qualified tag and how ``</\1\s*>`` still
      closes the element that opened.
    * ``(?:p:)?a|b`` parses as ``((?:p:)?a)|b``, so an unwrapped alternation
      would take the prefix on its first alternative and no other. Nothing
      behavioural would see that today, because no two spellings in the table
      collide -- which is exactly what makes it the kind that ships.

    Alternatives are ordered LONGEST FIRST, so a spelling is never shadowed by a
    shorter one it begins with: ``namemaps`` past ``name``, ``dateval`` past
    ``date``, ``placeobj`` past ``place``. The trailing ``_XML_NAME_END`` makes
    the engine backtrack into the longer alternative anyway today; ordering
    means the patterns do not DEPEND on that, which matters because this table
    is about to be derived from a published schema rather than written by hand.
    No behavioural test can see this until a colliding pair exists, so it is
    asserted structurally instead.

    ⚠️ **THE NAME'S END IS EMITTED HERE, NOT AT THE CALL SITES, AND THAT IS THE
    WHOLE POINT.** It used to be a ``\b`` written out at each of the three
    sites -- and the paragraph four lines above warns against exactly the shape
    that produces: a rule taught to some readers of a production and not the
    rest. Every site that reads this alternation now gets the transcribed end
    for free, a fourth site cannot hand-roll one, and
    ``test_every_pattern_that_scores_an_element_is_built_from_the_one_alternation``
    -- which asserts this fragment appears verbatim in each pattern -- becomes
    the assertion that all three end their names correctly, with nothing added
    to it.

    ⚠️ **The assertion is a LOOKAHEAD and consumes nothing**, so it sits inside
    the caller's capturing parenthesis without changing what group 1 holds or
    what ``\1`` closes.
    """
    alternation = "|".join(sorted(names, key=lambda name: (-len(name), name)))
    return _XML_NAME_PREFIX + "(?:" + alternation + ")" + _XML_NAME_END


def _local_name(tag: str) -> str:
    """What a matched tag MEANS: its local name, lowered, the prefix discarded.

    The prefix is an alias the document chose, so a category lookup that reads
    it is asking a question about spelling and calling the answer meaning.
    Written once rather than at each of the two scoring loops, for the reason
    the vocabulary above is written once.
    """
    return tag.rpartition(":")[2].lower()


# ---------------------------------------------------------------------------
# WHAT MAY SIT BETWEEN AN ELEMENT'S TAGS BESIDES CHARACTER DATA.
#
# XML 1.0's content production:
#
#     content ::= CharData? ((element | Reference | CDSect | PI | Comment) CharData?)*
#
# Closed and externally specified, so this enumeration is accepted on exactly
# the grounds ``FILESYSTEM_ROOTS``, ``_XML_PREDEFINED_ENTITIES`` and
# ``_XML_CHARACTER_RANGES`` are: it does not grow.
#
# ⚠️ **ONE TABLE, TWO DERIVED PATTERNS, because the alternative is what broke
# it.** A CDATA section was taught to the element pattern as a special case and
# nothing else was -- so a comment, which is the same production doing the same
# job, ended the element instead of sitting inside it, and a filled note
# carrying a whole identity scored nothing at all. Teaching the comment and not
# the processing instruction would be that defect a third time; the production
# says which members there are, so the table holds them all.
#
# The delimiters used to be spelled twice, once here and once in the length
# measurement, with a comment beside them saying that changing either meant
# changing both. That is the duplication, not a mitigation of it. They are
# spelled once now.
#
# CDATA IS FIRST AND THE ORDER IS LOAD-BEARING: a comment delimiter written
# inside a CDATA section is text, and an alternation reaching it first would
# split the section at it.
# ---------------------------------------------------------------------------

_MARKUP_IN_CONTENT: tuple[tuple[str, str, bool], ...] = (
    # opener, closer, and whether what it encloses is character data.
    ("<!" + "[CDATA[", "]]" + ">", True),
    ("<!" + "--", "--" + ">", False),
    ("<" + "?", "?" + ">", False),
)

_ENCLOSES_CHARACTER_DATA = tuple(denotes for _, _, denotes in _MARKUP_IN_CONTENT)


def _enclosed(opener: str, closer: str, *, captured: bool) -> str:
    """One such node, capturing what it encloses or deliberately not."""
    return re.escape(opener) + ("(.*?)" if captured else "(?:.*?)") + re.escape(closer)


# NON-CAPTURING, which is not a style choice: the element pattern below reads
# its tag back through a backreference and the scorer reads its two groups by
# number, so a group added here would silently shift both.
_NOT_ENDING_AN_ELEMENT = "|".join(
    _enclosed(opener, closer, captured=False) for opener, closer, _ in _MARKUP_IN_CONTENT
)

_MARKUP_NODE = re.compile(
    "|".join(_enclosed(opener, closer, captured=True) for opener, closer, _ in _MARKUP_IN_CONTENT),
    re.DOTALL,
)
"""The same table, capturing, for the measurement -- see ``_xml_logical_length``.

Which alternative matched says which row it is, and the row says whether what
it encloses denotes anything.
"""

_GRAMPS_FILLED_ELEMENT = re.compile(
    r"<(" + _qualified(*_GRAMPS_ALL_ELEMENTS) + r")[^>]*>"
    r"((?:" + _NOT_ENDING_AN_ELEMENT + r"|[^<])+)</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
r"""An element with content of its own: this is data rather than a mention.

Two groups: the tag and the content. The content alternative admits every
member of the table above, because none of them ends an element -- a CDATA
section is how XML carries prose containing markup, and a comment or a
processing instruction is something a person leaves in the middle of a note.
Reading any of them as markup meant the pattern could not reach its own closing
tag, so the element was not merely mis-scored, it was invisible.

The attributes used to be captured as a third group, for a short-prose
discriminator that read them. Nothing reads them now -- see ``_DRAWING`` -- and
a captured group nobody consumes is machinery pretending to be a rule.

⚠️ **The name ends where ``_XML_NAME_END`` says it does, and the ETag's ``\s*``
is a RECORDED approximation rather than a leftover.** ``</\1\s*>`` reads XML's
``S?`` loosely, and in a scorer that errs toward reading an element where XML
reads none, which errs toward reporting; transcribing it would subtract a catch
on a malformed paste and buy no false positive back. The licence table asserts
that this is the only shorthand this pattern holds.
"""

_GRAMPS_ATTRIBUTED_ELEMENT = re.compile(
    r"<(" + _qualified(*_GRAMPS_ALL_ELEMENTS) + r")[^>]*?\w+\s*=\s*[\"'][^>]*>", re.IGNORECASE
)
r"""An element carrying a quoted attribute -- a handle or an id is export syntax,
not something a specification writes in passing.

⚠️ **``[^>]*?\w+\s*=\s*["']`` IS the ``<[^<>]*xmlns=`` shape the marker block
condemns, and it is left standing on purpose.** There it decides whether a
document has DECLARED something, where a loose reading invents a declaration;
here it decides whether an element carries an attribute, where a loose reading
is one more finding rather than one fewer. Recorded in the licence table so the
next reader sees it was weighed, not missed -- and so a fifth round finds it
already dispositioned rather than reporting it again.
"""

_GRAMPS_PROSE_LENGTH = 20
"""How much text makes a prose container prose rather than a label.

Below this an axis label in an SVG snippet would score as a biography. That is
the false-positive side, and it is the ONLY side this number was calibrated
from -- which is how three short notes holding a name, a date of birth and a
place came to pass entirely. Both sides, measured, so the next person to
propose a shorter floor can see what it costs instead of rediscovering it:

    payload             floor 20   floor 8   short bare text -> 2
                        (before)   (naive)   (what is built)
    three short notes      0 miss  12 catch      6 catch
    two name notes         0 miss   8 catch      4 catch
    one short note         0        4             2   <- the ceiling; see below
    numeric axis labels    0 ok     0 ok          0 ok
    WORDED axis labels     0 ok     8 FALSE       0 ok
    two short bare notes   0 ok     8 FALSE       0 ok

Shortening the floor to 8 catches the real payloads and reports every chart
with a worded label -- the original false positive, returning. So the floor
stays at 20 and short content is instead credited by WHAT IT IS: a `text`
element is a note body unless it sits inside a drawing, where it is a label.
The discriminator, not the length, is what separates them.

⚠️ **That discriminator used to read the element's ATTRIBUTES, and the wording
here said so for several rounds. It was wrong** -- see ``_DRAWING``. Any
attribute at all counted as proof of a positioned label, so an ordinary
``xml:space`` returned an exact name, date and place payload clean. The
question is now the container. Do not put it back: a list of positioning
attributes fails open on the next one nobody listed, and the list pointed
backwards fails by admitting whatever is new.

One short note scores 2 and still escapes. That is not a gap in this rule; it
is the measured ceiling of the whole property -- one filled name part and one
filled surname also score 2, because all three are one name-fact. CONTRIBUTING
records why buying that last point is not affordable.

⚠️ **The number above counts CHARACTERS OF MEANING, and the two functions below
are what make that true.** Measured against the serialization instead, it is
not a floor at all: it moves with whichever spelling the document happens to
use. Both formats, one rule -- see the block beneath.
"""

# ---------------------------------------------------------------------------
# THE FLOOR MEASURES WHAT THE TEXT SAYS, NOT HOW IT IS WRITTEN.
#
# One rule, stated once, for both formats -- because it is a property of PROSE
# and not of a serialization. Stating it on one side only is the partial
# application this module has now paid for five times: the identical value
# spelled two ways got two verdicts, in whichever direction the spelling ran.
# A JSON escape and an XML character reference are the same device, and they
# broke the same floor.
#
# ⚠️ **BOTH RETURN AN int, AND THAT IS THE GUARDRAIL RATHER THAN A STYLE
# CHOICE.** Decoding is safe here only because the caller has already proved it
# is inside a string literal or inside element content -- see ``_decoded``,
# which refuses the same escapes precisely because at the funnel it CANNOT
# prove that. Hand the decoded text back as a string and ``<`` and
# ``&lt;`` become a way to manufacture the structure the source does not
# contain, which is the finding ``_STRUCTURE_CHARACTERS`` exists to prevent. A
# function that cannot return a string cannot be misused that way by the next
# person to need one.
#
# Neither ever materialises the decoded text: each counts what the escapes
# collapse to and subtracts. IMPRECISION ERRS LONG -- toward the finding, never
# away from it -- and every case of it is named in the two docstrings.
# ---------------------------------------------------------------------------

_JSON_ESCAPE_IN_A_STRING = re.compile(
    _MATCHES_A_BACKSLASH
    + "u[0-9A-Fa-f]{4}|"
    + _MATCHES_A_BACKSLASH
    + r"[\""
    + _MATCHES_A_BACKSLASH
    + r"/bfnrt]"
)

_XML_PREDEFINED_ENTITIES = ("amp", "lt", "gt", "quot", "apos")
"""The five XML 1.0 defines, and the only five that need no DTD to resolve.

Closed and externally specified, so this enumeration is accepted on exactly the
grounds ``FILESYSTEM_ROOTS`` and ``_DRAWING`` are: it does not grow. Anything
else -- ``&nbsp;``, an entity a document declares for itself -- would need real
entity resolution, which is not built and is not wanted. It counts as written,
which errs long.
"""

_XML_CHARACTER_REFERENCE = re.compile(
    "&(?:" + "|".join(_XML_PREDEFINED_ENTITIES) + r"|#([0-9]+)|#[xX]([0-9A-Fa-f]+));"
)

_XML_CHARACTER_RANGES = (
    (0x9, 0x9),
    (0xA, 0xA),
    (0xD, 0xD),
    (0x20, 0xD7FF),
    (0xE000, 0xFFFD),
    (0x10000, 0x10FFFF),
)
"""The XML 1.0 ``Char`` production: every code point XML lets a document say.

    Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

Closed and externally specified, so this is accepted on exactly the grounds
``_XML_PREDEFINED_ENTITIES`` and ``FILESYSTEM_ROOTS`` are: it does not grow.

⚠️ **This is a permitted-list, which is normally the enumeration pointed
backwards -- the shape that fails by admitting whatever is new. It is safe HERE
and only here, because of which way it fails.** A code point this table does not
recognise is not collapsed, so the value measures LONGER, and longer reports
rather than misses. The failure direction is closed, which is the whole reason
a list is allowed to answer the question at all.

It replaced a comparison against the largest code point alone -- one edge of six
ranges, so NUL, a control, a surrogate and a noncharacter all fell through. The
top of the last range is that comparison, which is why no separate maximum
survives beside this.

Note that XML permits the SUPPLEMENTARY noncharacters (``U+1FFFE`` and its kin);
only the two in the basic plane are excluded, by the end of the fifth range.
Unicode's opinion of them is not XML's, and XML's is what a measurement of XML
has to follow.
"""


def _json_logical_length(value: str) -> int:
    """How many characters the body of a JSON string literal DENOTES.

    Six characters of source for one character of meaning, at the extreme, so
    a caption of four angle brackets written as escapes measured twenty-four
    and was reported as a biography.

    Errs long, in two named places: an unrecognised escape (``\\U``) is not an
    escape at all and counts as the two characters it is, and a surrogate PAIR
    counts two where a parser would yield one. Both leave the value looking
    longer than it is, which is the side that reports rather than the side
    that misses.
    """
    length = len(value)
    for match in _JSON_ESCAPE_IN_A_STRING.finditer(value):
        length -= len(match.group()) - 1
    return length


def _names_an_xml_character(code_point: int) -> bool:
    """Whether XML lets a document contain the character this reference names."""
    return any(first <= code_point <= last for first, last in _XML_CHARACTER_RANGES)


def _references_collapsed(text: str) -> int:
    """How many characters ``text`` denotes, where XML is reading references.

    Errs long wherever it cannot be sure: an entity needing a DTD, a malformed
    reference, and a numeric reference naming no character at all are each
    counted as the source spells them. Only a reference that provably denotes
    exactly one character is collapsed to one.
    """
    length = len(text)
    for match in _XML_CHARACTER_REFERENCE.finditer(text):
        decimal, hexadecimal = match.group(1), match.group(2)
        digits = decimal or hexadecimal
        if digits is not None:
            base = 10 if decimal is not None else 16
            # A numeric reference is only a character if it NAMES one XML
            # PERMITS. A code point Unicode has and XML forbids -- NUL, a
            # control, a surrogate, a basic-plane noncharacter -- names nothing
            # here, and counting nothing as one character would shorten the
            # value, the one direction this must not err in.
            if not _names_an_xml_character(int(digits, base)):
                continue
        length -= len(match.group()) - 1
    return length


def _xml_logical_length(content: str) -> int:
    """How many characters XML element content DENOTES.

    The mirror of the above for the other format, and the reason this fix is
    not a JSON fix: the floor is a property of prose, so a rule stated for one
    serialization and not the other is the divergence this module keeps paying
    for. ``&amp;&amp;&amp;&amp;`` is four characters written as twenty.

    **One rule: a reference is collapsed only where XML would collapse it, and
    only when it names a character XML permits. Everywhere else the source
    length stands.** Two spellings of one cause, and they arrived together.

    WHERE. Segmented on ``_MARKUP_IN_CONTENT``, so each part of the content is
    measured as the thing it is. Inside a CDATA section XML collapses nothing,
    so the section contributes the characters it contains -- its delimiters
    denote nothing and its content denotes itself. This used to unwrap the
    section and then read the whole string as markup, which counted a reference
    written literally as the character it would have named somewhere else.

    WHAT. A numeric reference naming a code point XML forbids names no
    character at all; see ``_XML_CHARACTER_RANGES``. This used to check the
    largest code point and nothing else, so five of the production's six ranges
    had no edge tested.

    Both shortened the value, and both were this module's recurring shape: a
    rule already agreed, applied in only some of the places it holds.

    Segmenting also settles a reference straddling a boundary -- unwrapping
    first splices ``&am`` and ``p;`` into a match that the source does not
    contain. It counts as written, which errs long. It settles the same
    question inside a comment, where a reference denotes nothing whatever and
    collapsing one would shorten the character data around it.

    ⚠️ **A COMMENT AND A PROCESSING INSTRUCTION CONTRIBUTE NOTHING, delimiters
    and content alike, and that is a definition rather than an imprecision
    erring short.** The quantity being measured is characters of character
    data; XML says a comment holds none, so it is outside the measurement by
    construction. The decision was taken against the alternative -- measuring
    what a comment says, on the grounds that a name in a committed comment is
    published -- and the alternative was measured and declined. See
    CONTRIBUTING.md: it reports ordinary documentary comments, keeps a false
    positive this reading removes, and does not reach the far commoner case of
    a comment that is not inside a prose element at all. What it concedes is
    the ceiling already recorded, no wider: a prose element holding only a
    comment is worth what a bare short note is worth, one escapes and two do
    not, and the deny-list is the recorded backstop.

    ⚠️ **A parser is the repair this will keep suggesting, and it is refused
    on grounds that are not effort.** The guard scans FRAGMENTS of arbitrary
    files, not well-formed documents, and a parser refuses a fragment -- which
    means no measurement at all, failing in the direction that misses rather
    than the one that reports. A parser also returns strings, which is the one
    thing the block above forbids, and it brings entity-expansion hazards this
    function categorically does not have.
    """
    length = 0
    position = 0
    for node in _MARKUP_NODE.finditer(content):
        length += _references_collapsed(content[position : node.start()])
        row = next(index for index, group in enumerate(node.groups()) if group is not None)
        if _ENCLOSES_CHARACTER_DATA[row]:
            length += len(node.group(row + 1))
        position = node.end()
    return length + _references_collapsed(content[position:])


# READ FROM THE TABLE, never restated beside it. These were three literals
# holding the same numbers the table holds, which is a second place for a
# weight to live and therefore a second place for it to drift.
_GRAMPS_IDENTITY_WEIGHT = _CATEGORY_WEIGHT["identity"]
_GRAMPS_PROSE_WEIGHT = _CATEGORY_WEIGHT["prose"]

# Not a category: the namespace names the format rather than carrying a
# person, so it has no row and no spellings. See the warning below.
_GRAMPS_NAMESPACE_WEIGHT = 2

# The same two axes again, for the format the guard had no property for at
# all: GEDCOM X, which is JSON. Its keys play the parts the Gramps elements do
# -- a *filled* identity key carries a person, a structural key says the shape
# is an export, and a key named in prose or backticks says neither.
#
# This is where "no genealogy data, whatever it is named" was false rather than
# imprecise: the payload was refused as a text file because text is not a safe
# type, and passed clean as Markdown, Python or YAML, which are the three
# commonest types in this repository.
_CARRYING_CATEGORIES = tuple(
    category for category, _, _, _ in _VOCABULARY if category != "structure"
)

_JSON_STRING_BODY = r"(?:[^\"" + _MATCHES_A_BACKSLASH + "]|" + _MATCHES_A_BACKSLASH + r".)+"
"""The body of a JSON string literal: anything, or an escape, up to the end.

⚠️ **A string literal ends at its first UNESCAPED quote, and reading it as
``[^"]+`` ends it at the first quote of any kind.** A note whose text is a
quotation -- somebody transcribing a register entry -- therefore measured as
one backslash, so a whole biography scored as a two-character caption and
passed. The escape alternative is what makes the end of the string the end of
the string.

Kept as ``+`` deliberately: *filled* still means non-empty, which is the
distinction that lets a specification NAMING these keys through.

**What this gives up** is a literal whose only closing quote is an escaped one
-- an unterminated string, which now matches nothing where it used to match
whatever preceded the wrong quote. That old match was itself the defect above.
Recorded in CONTRIBUTING and asserted by test; the tempting repair is a
fallback to the old pattern, and two matchers with two ideas of where a string
ends is how the vocabulary came to differ between formats in the first place.
"""

_GEDCOM_X_FILLED_KEY = {
    category: re.compile(
        r"\"(?:"
        + "|".join(_json_keys_of(category))
        + r")\"\s*:\s*\"("
        + _JSON_STRING_BODY
        + r")\"",
        re.IGNORECASE,
    )
    for category in _CARRYING_CATEGORIES
    if _json_keys_of(category)
}
"""One compiled pattern PER CATEGORY, keyed by it. Compiled from the table.

⚠️ **A single pattern for several categories cannot be scored by category.**
That is not a subtlety, it is what happened: address, contact and prose were
compiled into one alternation and the scorer multiplied the lot by the address
weight, so prose scored two where the table says four -- a whole life in one
note passed in a safe-typed file while the identical prose as XML was caught.
Contact was flattened in the very same expression and is *right by
coincidence*, because contact and address both weigh two.

A dict keyed by category cannot lose one that way: the key that selects the
pattern is the key that selects the weight. A row is dropped here only by
having no JSON spelling at all, which is a fact about the table rather than
about this compilation, and the per-row test asserts that too.
"""
_DOUBLE_QUOTE = chr(34)

_GEDCOM_X_TYPE_KEY = re.compile(r"\"ty" + r"pe\"\s*:", re.IGNORECASE)
_GEDCOM_X_VALUE_KEY = re.compile(r"\"val" + r"ue\"\s*:", re.IGNORECASE)


def _shallow_json_objects(text: str) -> Iterator[tuple[int, str]]:
    """Each brace-balanced object in ``text``, with nested objects ELIDED.

    ⚠️ **Eliding is what keeps a pairing honest.** A child's keys never reach
    its parent's text, so a type in a child and a value in the parent are not
    read as one object. Flattening instead would report every schema that
    nests a type -- the exact false positive the pairing exists to avoid.

    Written because the previous matcher kept itself inside one object by
    refusing to cross a brace, which is a hand-rolled balancer and fails on
    the first nested object it meets. Depth is not the axis: widening it to
    admit one nested level is the same defect one document along.

    String literals are respected, so a brace inside a value cannot unbalance
    the scan. An unterminated object yields nothing, which is what the
    previous matcher did with a truncated document too.
    """
    stack: list[tuple[int, list[str]]] = []
    in_string = False
    escaped = False

    for index, character in enumerate(text):
        if in_string:
            if stack:
                stack[-1][1].append(character)
            if escaped:
                escaped = False
            elif character == _ONE_BACKSLASH:
                escaped = True
            elif character == _DOUBLE_QUOTE:
                in_string = False
            continue
        if character == _DOUBLE_QUOTE:
            in_string = True
        if character == "{":
            stack.append((index, []))
            continue
        if character == "}":
            if stack:
                start, buffer = stack.pop()
                yield start, "".join(buffer)
            continue
        if stack:
            stack[-1][1].append(character)


def _gedcom_x_name_part_offsets(text: str) -> list[int]:
    """Where each GEDCOM X name part starts: an object carrying a type AND a value.

    ⚠️ **The PAIRING is the property. Do not simplify this to matching a value
    key alone.** A value key by itself is in every configuration file and every
    JSON schema -- measured, and it is the difference between zero false
    positives here and reporting settings files. A type URI beside a value
    inside one object is the name-part shape, and nothing in ordinary
    configuration writes it.

    Two parts are a given name and a surname, which scores the same 4 that
    ``<first>`` plus ``<surname>`` scores on the Gramps side. One part stays
    below the bar, exactly as a lone surname does -- the ceiling recorded in
    round 10 is unchanged and no threshold moved for this.

    Asked of the object's SHALLOW text, so a part keeps its pairing whatever it
    nests. A qualifier -- ordinary GEDCOM X saying which part is primary --
    used to end the match, and a given name and a surname both escaped a valid
    document because of it.
    """
    return [
        start
        for start, shallow in _shallow_json_objects(text)
        if _GEDCOM_X_TYPE_KEY.search(shallow) and _GEDCOM_X_VALUE_KEY.search(shallow)
    ]


_GEDCOM_X_STRUCTURAL_KEY = re.compile(
    "".join(
        (
            r"\"(?:",
            "|".join(_json_keys_of("structure")),
            r")\"\s*:",
        )
    ),
    re.IGNORECASE,
)

_GRAMPS_SCORE_THRESHOLD = 4
"""What a file has to score to be genealogy data.

Measured, and the margins are in CONTRIBUTING. Four is what a bare name block
scores and what a note holding a biography scores -- the two smallest leaking
fragments. Three would catch one more shape and halve the margin over a
specification and an SVG snippet, which both score two.
"""

# ⚠️ The namespace is evidence, not a verdict, and that was learned the hard
# way. Treating it as a finding on its own -- so a fragment carrying it was
# caught wherever it sat -- reported *this module* and every historical copy of
# it, because a guard that detects a string contains that string. Composing the
# constant hid it at the tip; the published range showed it 43 times. It
# contributes weight now, and weight alone is below the threshold.


def _undecorated(line: str) -> str:
    """A line with its decoration removed, so the record can be seen under it.

    Round 7 tolerated a class of characters *before* a level-0 record. That
    axis cannot work: the reviewer's strongest case is a fragment containing no
    level-0 record at all, which no prefix class of any width will ever match.

    Matching the record shape ANYWHERE in the line was measured as the
    alternative -- no false positives on this repository -- and rejected,
    because a diff marker abuts the digit with no space in between and so the
    commonest way to paste an export stays invisible. Some notion of decoration
    is unavoidable in a line-oriented format; what this removes is the
    dependence on a header being present.
    """
    previous = None
    while previous != line:
        previous = line
        line = _DECORATION.sub("", line, count=1)
    return line


def _genealogy_record_density(text: str) -> int | None:
    """The line of the first record, if the file holds enough of them.

    Counted across the whole file. What is committed here is documents, and a
    document interleaves its records with prose.
    """
    first = None
    seen = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if _GENEALOGY_RECORD.match(_undecorated(line)):
            first = number if first is None else first
            seen += 1
            if seen >= _GENEALOGY_RECORDS_PER_FILE:
                return first
    return None


def _filled_key_weight(category: str, value: str) -> int:
    """What one filled key of ``category`` is worth, given what it holds.

    Prose is the one category whose weight depends on its content, and it
    depends on it THE SAME WAY IN BOTH FORMATS -- the floor is a property of
    prose, not of the XML spelling of it. Stating it on one side only is the
    same partial application as stating a weight on one side only, one level
    down; raising the JSON weight without carrying this across reports a
    two-character caption under a note key as a family tree.

    There is no positioned-label branch on this side and there cannot be: a
    JSON key carries no attributes, so the floor is the whole discriminator.

    ``value`` arrives as the SERIALIZATION of the string, so it is measured by
    what it denotes -- see the block above the two length functions.

    ⚠️ **It also answers the NO-CONTENT case, and the XML attributed pass calls
    it with the empty string for exactly that.** An element that encloses
    nothing holds no more prose than one enclosing a space, so it is worth what
    that one is worth; charging the flat category weight instead made the
    element carrying strictly less score strictly more.

    ⚠️ **Calling the JSON-side spelling of the floor from the XML side is not
    the partial application this function exists to prevent, and the reason is
    measurable rather than stylistic:** both length functions return 0 for no
    content, so at empty content the two serializations cannot disagree. What
    would be a leak is passing XML content through it -- that is the filled
    pass's job, and the filled pass measures its own.
    """
    if category != "prose":
        return _CATEGORY_WEIGHT[category]
    if _json_logical_length(value) < _GRAMPS_PROSE_LENGTH:
        return _GRAMPS_IDENTITY_WEIGHT
    return _GRAMPS_PROSE_WEIGHT


def _gedcom_x_identity_score(text: str) -> tuple[int, int] | None:
    """Score GEDCOM X the way Gramps XML is scored: identity over structure.

    A key with a non-empty string value is filled and carries weight; a key
    named in prose has no colon-and-value after it and carries none, which is
    what lets a specification about the format through.

    ⚠️ **Scored PER CATEGORY, from the table, in one loop.** The categories
    used to be summed in a hand-written expression with one term per group,
    and a group holding three categories was charged one category's weight.
    An expression with a term per category is a place to forget a category;
    a loop over the compiled table is not.
    """
    structural = [match.start() for match in _GEDCOM_X_STRUCTURAL_KEY.finditer(text)]

    score = _CATEGORY_WEIGHT["structure"] * len(structural)
    offsets = list(structural)

    for category, pattern in _GEDCOM_X_FILLED_KEY.items():
        # THE GATE, and it is load-bearing. The address, contact and prose keys
        # are ordinary English words, so they count only once the document has
        # said it is GEDCOM X. Without this, a caption under a text key in any
        # configuration file scores four and is reported.
        #
        # Identity is exempt, as it always was: its spellings are not ordinary
        # words, and the gate exists for the ones that are.
        if category != "identity" and not structural:
            continue
        for match in pattern.finditer(text):
            score += _filled_key_weight(category, match.group(1))
            offsets.append(match.start())

    # The one deliberate exception to the table -- a SHAPE rather than a key,
    # so it has no row to compile. See the note above the vocabulary.
    for start in _gedcom_x_name_part_offsets(text):
        score += _CATEGORY_WEIGHT["identity"]
        offsets.append(start)

    if score < _GRAMPS_SCORE_THRESHOLD or not offsets:
        return None
    return score, min(offsets)


_DRAWING = re.compile(
    "<svg" + _XML_NAME_END + "[^>]*>.*?</svg" + _XML_S + "*>", re.IGNORECASE | re.DOTALL
)
r"""A drawing, inside which a short text element is a label and not a note.

⚠️ **THE UNPREFIXED SPELLING ONLY, AND IT DOES NOT USE THE SHARED ALTERNATION.
Do not "finish the job" by wiring it back in.** It was built from it -- the
fourth site of four -- and that site was deleted, because the mechanism is
right for the other three and wrong here:

* those three SCORE. Matching a prefix by shape makes them read more elements,
  and reading more elements produces more FINDINGS. Conservative.
* this one EXEMPTS. Matching by shape makes it read more containers, and
  reading more containers produces more SUPPRESSION. Fail-open.

The input that proved it: a prefix bound to a namespace that is **not SVG**.
Nothing here resolves an alias, so ``<x:svg xmlns:x="…not-svg…">`` had the
shape of a drawing, the exemption applied, and every short text element inside
it was suppressed -- a name, a date of birth and a place went from a finding to
nothing by being wrapped in a tag whose meaning this module never checked.
**A conditional exemption is where fail-open lives.**

**Both repairs that keep the fourth site were rejected.** Resolving the prefix
means reading namespace bindings, which is a parser, which this project has
refused repeatedly. Requiring the namespace URI somewhere in the document is
still a *condition on an exemption*, and it is wrong in the case that matters:
a document may bind that URI to a different prefix entirely.

**The cost, and it is the accepted trade:** a namespace-prefixed chart is no
longer exempt, so its labels are reported. That is a false positive, it is
FAIL-CLOSED, and it is the direction this module's posture requires -- refuse
what cannot be proved safe. Recorded in CONTRIBUTING's residual table, with
**issue #33's rendering boundary named as where it eventually belongs**: a
structural guard over what the preview EMITS can answer "is this really a
drawing", and that is where the question goes, rather than into a condition
bolted onto an exemption here.

**How it rejects a prefixed drawing -- and THE OPENER IS NOW WHAT DOES IT.**
``<svg`` + ``_XML_NAME_END`` refuses the colon, so ``<svg:svg>`` is not an
opening tag here at all. The verdict is unchanged and the mechanism is not.

⚠️ **This paragraph used to say the opposite, and that reading was true of the
pattern it described.** ``<svg\b`` matched the opening tag of ``<svg:svg>`` --
the word boundary sits between the ``g`` and the colon -- and it was the closer
``</svg\s*>``, unable to match ``</svg:svg>``, that withheld the exemption. It
also warned against moving the rejection to the opener without measuring it.
**The warning was right and the measurement has now been done**, because
``\b`` was not merely imprecise here: it is the same shorthand standing in for
the same production that this module has now been wrong about five times, and
in an EXEMPTION it fails open.

**What moving it buys, and it is a live fail-open closed rather than a tidy-up:**

* ``<svg-chart …>`` was an ``svg``. ``-`` legally continues an XML name and
  satisfies ``\b``, so a name, a date of birth and a place wrapped between it
  and a later ``</svg>`` were suppressed **entirely** -- a whole identity going
  from a finding to nothing, which is the exact shape the fourth scoring site
  was deleted for. Every ``NameChar`` that is not a ``\w`` character did this:
  ``.``, the middle dot, a combining mark, an undertie -- nineteen of them,
  measured.
* The case this paragraph itself named as still open -- a document mixing a
  prefixed opener with a later UNPREFIXED ``</svg>`` -- is closed by the same
  move, because the opener no longer matches ``<svg:``.

**And the closer reads ``_XML_S``, which is the same repair at the other end.**
``</svg\s*>`` accepted ``</svg`` + U+00A0 + ``>``, where XML reads no ``ETag``
at all. A broader closer spans further, and in an exemption spanning further
suppresses more.

⚠️ **Neither half is built from the shared alternation, and that is unchanged.**
The exclusion above is about ``_qualified``'s optional PREFIX, which is matched
by shape and never resolved; ``_XML_NAME_END`` asserts where a name stops and
resolves nothing, so reading it here narrows the exemption and cannot widen it.
``test_every_pattern_that_scores_an_element_is_built_from_the_one_alternation``
still asserts the alternation itself is absent.

⚠️ **This replaced "the element carries an attribute", which asked the wrong
question and so let data out whatever the answer.** The discriminator has to
separate a positioned chart label from a note body, and ANY attribute counted
as proof of the first -- so adding ``xml:space``, which says how to treat
whitespace and nothing about position, returned an exact name, date and place
payload clean.

**Both obvious repairs are enumerations and both fail.** A list of positioning
attributes fails open on the next one nobody listed. A list of non-positioning
attributes is the same list pointed backwards and fails by admitting whatever
is new. This is an enumeration too, and it is accepted on the grounds
``FILESYSTEM_ROOTS`` is accepted on: SVG is closed and externally specified,
and it is the only markup in general use whose text elements are positioned
labels.

**The direction of failure is what decides it.** The attribute question failed
OPEN and data escaped. The container question fails CLOSED: a chart fragment
pasted without its drawing is reported, which is the posture this module
states -- refuse what cannot be proved safe. Recorded in CONTRIBUTING, both
directions, and asserted by test in both directions.
"""


def _inside_a_drawing(position: int, drawings: Sequence[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in drawings)


def _gramps_identity_score(text: str) -> tuple[int, int] | None:
    """Score the Gramps content in ``text``; return the score and where it starts.

    Only FILLED elements count -- see the block comment above. An element with
    a quoted attribute counts too, at structural weight, because a handle or an
    id is export syntax rather than something a specification writes in
    passing.

    ⚠️ **A spelling this audit ADDED counts only where the text names the
    format**, because some of what the schema declares are ordinary XML names --
    ``type``, ``file``, ``status``, ``description`` -- and four filled ones in a
    document about unrelated XML reached the threshold. See
    ``_SPELLINGS_THE_DERIVATION_ADDED`` for why the condition is on rows rather
    than on the file, and ``_names_the_gramps_format`` for what the marker is.
    """
    score = 0
    first: int | None = None
    filled: list[tuple[int, int]] = []
    drawings = [match.span() for match in _DRAWING.finditer(text)]
    # Once per call, not once per element: the answer is a property of the text.
    names_the_format = _names_the_gramps_format(text)

    for match in _GRAMPS_FILLED_ELEMENT.finditer(text):
        # Group 1 holds the WHOLE qualified tag, because the backreference that
        # closes the element has to match what opened it. The category is a
        # question about the local name -- see ``_local_name``.
        tag = _local_name(match.group(1))
        # The RAW content, deliberately: only the measurement can tell which
        # parts of it XML reads and which it takes literally, and unwrapping
        # here threw that away before the question was asked.
        content = match.group(2).strip()
        filled.append(match.span())
        if tag in _SPELLINGS_THE_DERIVATION_ADDED and not names_the_format:
            # THE GATE, and it sits BEFORE the prose branch on purpose: a prose
            # row the derivation adds later is gated with nothing edited here.
            #
            # Two properties copied from the unweighted branch below, and
            # load-bearing for the same reasons: the filled span STAYS recorded
            # above, so the attributed pass cannot score the same element again;
            # and ``first`` is NOT set, so no finding ever points at an element
            # that contributed nothing.
            continue
        if tag in _GRAMPS_PROSE_ELEMENTS:
            # Measured by what the content DENOTES, exactly as the JSON side
            # measures its values -- the floor is a property of prose, not of a
            # serialization. See the block above the two length functions.
            if _xml_logical_length(content) < _GRAMPS_PROSE_LENGTH:
                # SHORT prose: see the discriminator recorded beside the floor
                # and the reasoning recorded beside _DRAWING. A note body
                # scores identity weight; a label inside a drawing scores
                # nothing, whether or not it is positioned -- inside a drawing
                # a text element IS a label, which is the point of asking about
                # the container rather than about the attributes. Either way
                # the span stays recorded, so the attributed pass below cannot
                # pick a label up instead.
                if _inside_a_drawing(match.start(), drawings):
                    continue
                score += _GRAMPS_IDENTITY_WEIGHT
            else:
                score += _GRAMPS_PROSE_WEIGHT
        else:
            weight = _CATEGORY_WEIGHT[_GRAMPS_CATEGORY_OF[tag]]
            if not weight:
                # A deliberately-unweighted spelling: see the category at the
                # foot of the vocabulary. The span STAYS recorded above, so the
                # attributed pass cannot pick the same element up again, but it
                # must not become the offset a finding points at -- a report
                # whose line names evidence worth nothing is a report nobody
                # can act on, which is the failure this category exists to
                # avoid in the first place.
                continue
            score += weight
        first = match.start() if first is None else first

    for match in _GRAMPS_ATTRIBUTED_ELEMENT.finditer(text):
        # Skip anything already counted as filled, so one element is scored once.
        if any(start <= match.start() < end for start, end in filled):
            continue
        # The SAME table as the pass above. This loop used to ignore the tag
        # entirely and score everything structurally, so an attributed surname
        # weighed the same as a bare person element -- one principle stated in
        # the comment at the top and honoured by only one of the two loops
        # beneath it.
        tag = _local_name(match.group(1))
        if tag in _SPELLINGS_THE_DERIVATION_ADDED and not names_the_format:
            # The gate again, in the second pass, for the reason it is in the
            # first: a rule taught to one of these two loops and not the other
            # is the partial application this whole table exists to end.
            continue
        # THE SAME CONTENT-DEPENDENT RULE as the pass above, given the content
        # this element has: none. Charging the flat category weight here made an
        # element enclosing NOTHING outscore one enclosing a space -- the element
        # carrying strictly less scoring strictly more, which is two passes
        # reading one vocabulary by two rules. Stating the rule a third time is
        # the partial application this table exists to end, so the pass above's
        # own function is called rather than its condition re-written.
        #
        # ⚠️ **No drawing exemption here, and the ABSENCE is the decision.** The
        # filled pass's exemption sits BEHIND a short-content gate: only prose
        # too short to be prose is suppressed, which is what keeps it from
        # swallowing a note. This pass has no content to measure and so
        # structurally cannot carry that gate -- an exemption reaching it would
        # suppress the element whatever it holds, and an export's cross
        # references are exactly this element. An exemption that cannot carry
        # the gate that makes it safe does not exist. Pinned by test in two
        # directions, because prose cannot enforce it.
        weight = _filled_key_weight(_GRAMPS_CATEGORY_OF[tag], "")
        if not weight:
            # The same rule as the pass above, for the same reason.
            continue
        score += weight
        first = match.start() if first is None else first

    if _GRAMPS_XML_NAMESPACE in text:
        score += _GRAMPS_NAMESPACE_WEIGHT
        first = text.index(_GRAMPS_XML_NAMESPACE) if first is None else first

    if score < _GRAMPS_SCORE_THRESHOLD or first is None:
        return None
    return score, first


_GENEALOGY_TEXT_SIGNATURES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GEDCOM header record", re.compile(_LINE_PREFIX + r"0 HEAD\s*$", re.MULTILINE)),
    (
        "GEDCOM level-0 record",
        re.compile(
            _LINE_PREFIX + r"0 @[^@\s]+@ (?:INDI|FAM|SOUR|REPO|OBJE|NOTE|SUBM|SUBN)\b",
            re.MULTILINE,
        ),
    ),
    (
        "Gramps XML database element",
        # The same alternation as the two element patterns, for a table of one
        # spelling: an export that binds the namespace to an alias writes
        # `<g:database …>` and was not recognised as the format at all.
        #
        # ⚠️ Its name now ends where `_XML_NAME_END` says it does, because the
        # alternation emits that -- a DELIBERATE reach outside this round's
        # subject, measured rather than assumed. The effect on every genuine
        # input is nil: `<database` is followed by whitespace or `>` in every
        # export. What stops is `<database-x … gramps…>`, `<database.new …>`,
        # `<database:extra …>` and `<database` + a combining mark, none of which
        # is an element named `database` and all of which were signatures.
        re.compile(
            _LINE_PREFIX + r"<" + _qualified("database") + r"[^>]*gramps",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
)

# `_XML_PROLOG` stood here -- `\A\s*<\?xml\b`, TWO approximations of two XML
# productions -- and NOTHING IN THE REPOSITORY READ IT. It was deleted rather
# than transcribed: machinery nobody reads is a candidate for deletion, not for
# hardening, and an approximation with no reader is surface for the next review
# round and nothing else. The licence table would otherwise have carried a row
# that can never be exercised.
#
# Assembled, not written. Once the namespace stopped requiring a prolog at the
# start of the file, a module holding it as a literal reported itself -- the
# same self-report the patterns above are composed from constants to avoid, and
# it appeared the moment the anchor came off.
_GRAMPS_XML_NAMESPACE = "gramps-project" + ".org" + _SEPARATOR + "xml"

_GRAMPS_NAMESPACE_SCHEME = "ht" + "tp"
"""The scheme the schema serves its own ``#FIXED`` namespace value over.

Split for the reason the constant above it is, and placed beside it for the
same reason: it is a piece of the frozen value, composed in this module and
**bound to `FIXED_ATTRIBUTE_DEFAULTS` by test** rather than imported -- see the
block below on why nothing here reads `_specified_containers` at runtime.

⚠️ **It is a SCHEME, not a prefix**: the tolerance table below joins it to its
colon and to the authority marker, so no tracked file holds the two together.
"""

# ---------------------------------------------------------------------------
# WHAT COUNTS AS THE DOCUMENT SAYING IT IS GRAMPS. ONE SPELLING, DERIVED FROM A
# CLOSED SOURCE.
#
# ⚠️ **A hand-written list of markers would be the same defect the derivation
# just removed, one level up.** The container list stopped being a judgement in
# #4's Change C1; a gate on "is this Gramps" resting on spellings somebody chose
# would put the judgement straight back, in the place that decides whether ~80
# rows score at all. So the marker names its source and is bound to it by test:
#
#   the declared namespace  -- the `#FIXED` default the schema gives the
#                              `xmlns` attribute of its document element,
#                              emitted into the frozen table as
#                              `FIXED_ATTRIBUTE_DEFAULTS`
#
# ⚠️ **SHAPE AND VALUE, TOGETHER, IN ONE CONDITION. THE GATE HAS BEEN WRONG
# THREE TIMES ON THIS ONE AXIS AND EACH TIME IT HELD LESS THAN BOTH HALVES.**
#
#   * **Shape without value.** The gate read a doctype whose `Name` was the
#     document element, and that element carrying an `xmlns` attribute at all.
#     Both checked that something was PRESENT and never what it said, so
#     `<database xmlns="urn:unrelated">` beside four filled `<type>` elements --
#     a document that has explicitly named ANOTHER format -- re-enabled every
#     derived row and scored a P2.
#   * **Value without shape.** Those two were deleted and a plain substring test
#     over the decoded text was left. A PROSE SENTENCE naming the namespace --
#     an import note, a changelog entry, this project's own documents -- beside
#     four generic `<type>` elements then scored 6 and was reported.
#   * **Value in the right shape and the wrong PLACE inside it.** The shape was
#     transcribed and the VALUE was still read as a substring, now of the
#     `AttValue` rather than of the file. So `xmlns="urn:not-gramps:…"` --
#     a declaration naming a different namespace that happens to contain this
#     one -- was read as Gramps. **A substring test is a substring test however
#     deeply it is nested**, and this is what `_namespace_value_of` closes.
#
# Each was rejected only for lacking what the next one added, so the marker
# below requires all of it **at one position**: the schema-fixed value, as the
# WHOLE value of an `xmlns` attribute, reachable from a start tag's name through
# complete attributes.
#
# **What is transcribed here, and what each transcription bought:**
#
#   `S`        XML 1.0 §2.3  -- U+00A0 in the separator was a declaration
#   `NCName`   Namespaces §3 -- a combining-mark alias was invisible
#   `STag`, `Attribute`, `Eq`, `AttValue`
#              XML 1.0 §3.1  -- the namespace inside ANOTHER attribute's value
#
# Every one of them replaced a Python shorthand, every one was reported as a
# bypass first, and `test_no_pattern_reading_an_xml_production_uses_a_python_shorthand`
# is what stops the list needing another entry.
#
# ⚠️ **`scheme`, RFC 3986 §3.1, WAS on that list and is RETIRED rather than
# dropped, and the difference is the whole of this note.** It bought the
# `urn:not-gramps:…` refusal -- a scheme followed by anything other than `//`
# cannot reach the base -- and **that input is still refused**, now by the
# tolerance table below rather than by the production. The transcription itself
# had to go because it was the loose element: transcribed FAITHFULLY, `scheme`
# admits every syntactically valid scheme, so the base served over `ftp` named
# this format. A document that silently dropped the credit would leave the next
# reader thinking the property was lost with it.
#
# ⚠️ **AND THAT IS ONE COMPILED PATTERN, NOT A COMPOSITION.** An `or` over two
# results is the defect above wearing a conjunction. An `and` is wrong too, and
# it is the wrong one worth naming: `shape.search(text) and value in text` is
# satisfied by `<database xmlns="urn:unrelated">` in a file that mentions the
# Gramps namespace three paragraphs down. **Two conditions verified at two
# positions are not one condition.** Only a single pattern makes *the value
# occurs in the declaration* structural rather than a property of how two
# results were combined.
#
# ---------------------------------------------------------------------------
# ⭐ **HOW THIS GATE CAME TO BE A BARE SUBSTRING TEST, BECAUSE THE NEXT READER'S
# CHEAPEST MOVE IS TO SIMPLIFY IT BACK TO ONE.**
#
#   1. The conductor prescribed *bind the structural marker to the namespace
#      value*.
#   2. The plan gate DISPUTED it, and was right: bound to the value, a shape
#      marker is a strict SUBSET of the substring test and can never add a
#      match. Tightened they were dead weight; loose they were the false
#      positive. So they were deleted rather than tightened.
#   3. **That proof was valid and its premise was unsound.** It holds only
#      because the substring test matched ANYWHERE, and the unrestricted reach
#      it was measured against is itself the defect the next round found.
#      Nobody questioned the premise, including the conductor who approved the
#      dispute.
#
# **A subset argument is only as good as the set it is taken inside.** The
# review that produced step 2 was correct about the deduction and silent about
# the assumption, which stands as evidence that a DISPUTE needs re-examination
# on the same terms a prescription does.
# ---------------------------------------------------------------------------
#
# ⚠️ **The doctype could not be bound either way**, which is why it is gone
# rather than anchored: the only Gramps-specific evidence it carries beyond the
# namespace is the public identifier, which appears in no artifact this
# repository has frozen -- the DTD does not declare its own -- so correcting it
# would need exactly the hand-typed literal this design forbids.
#
# **What that costs, recorded rather than discovered.** A genuine document
# naming itself ONLY by a PUBLIC-only doctype, with no namespace anywhere, no
# longer enables derived rows. Round 1's own honest note recorded that this
# single case was the doctype marker's entire reach -- a whole export carrying a
# doctype or a namespaced document element already trips
# `_GENEALOGY_TEXT_SIGNATURES` above, which short-circuits `_sniff_genealogy`
# before any scorer runs. Measured in CONTRIBUTING and in the derivation note.
#
# **Anchoring costs two more, both measured rather than assumed and both
# recorded in CONTRIBUTING §(c):**
#
#   * a genuine fragment quoted beside a bare MENTION of the namespace is no
#     longer caught -- the third residual of one family, and the direct price of
#     closing the reproduction above;
#   * a declaration whose quotes are JSON-ESCAPED -- `xmlns=\"…\"` inside a JSON
#     string -- escapes the pattern, because `_decoded` deliberately leaves a
#     `\"` alone. **The pattern is NOT widened to absorb it.** Spelling-folding
#     belongs at `_decoded`, in one place, and teaching one more spelling to
#     every pattern that reads text is the enumeration this module refuses; that
#     is `#50`'s root cause rather than this gate's, and it is filed there.
#
# ⚠️ **The prefixed case is carried by the SHARED `NCName`, not by blindness.**
# The substring test was blind to prefixes by construction, which made Change
# A's equivalence property free and is now no longer available. `<x:database
# xmlns:x="…">` names the format because the declaration's name is `xmlns:` plus
# the same transcribed `NCName` the element patterns read -- one production,
# three readers, no second table to keep in step.
#
# ⚠️ **Case-sensitive, deliberately.** XML is: `XMLNS=` is not a namespace
# declaration and an upper-cased host is not this namespace. The substring test
# being replaced was case-sensitive too, so nothing moves.
#
# **A comment or a CDATA section quoting a start tag is read as a declaration**,
# and that is a residual rather than a repair postponed. It fails toward
# REPORTING, which is the direction a guard may fail in, and closing it needs a
# comment stripper -- machinery this project has watched fail open before. Its
# sharpest spelling is not reachable in any case: a comment quoting the real
# `<database … gramps…>` line trips `_GENEALOGY_TEXT_SIGNATURES` above, which
# short-circuits `_sniff_genealogy` before any scorer runs.
#
# ⚠️ **NOTHING HERE IMPORTS `_specified_containers`.** That module's docstring
# says it is data rather than behaviour and that the scan does not change if it
# is deleted, and that stays true: the marker is a composed constant in this
# module, BOUND BY TEST to the frozen table -- exactly the standing the
# vocabulary itself has, which is also placed here and bound by
# `test_every_container_the_published_schema_declares_has_a_weight`. "Derived"
# in this project means *nothing is maintained by hand without a test that would
# fail*, not *imported at runtime*.
# ---------------------------------------------------------------------------

_GRAMPS_DOCUMENT_ELEMENT = "database"
"""The element the schema attaches its namespace declaration to.

Placed here rather than imported, for the reason in the block above. It is what
SELECTS the `FIXED_ATTRIBUTE_DEFAULTS` row the marker is read from, and the
frozen table is asserted to name **exactly one** such element and to name this
one -- so a schema that moved or duplicated the declaration fails a test instead
of leaving the gate quietly pointing at an element that declares nothing.
"""

_XMLNS_DECLARATION = _XML_S + "+xmlns(?::" + _XML_NCNAME + ")?" + _XML_EQ
r"""``S 'xmlns' (':' NCName)? Eq`` -- a namespace declaration up to its value.

One `Attribute` like any other, spelled out because its `Name` is the fixed
`xmlns` rather than an arbitrary one, and because the optional prefix is the
whole of Change A's equivalence property at this site: it is the SAME `NCName`
the element patterns read.

⚠️ **THE THIRD SITE THAT SPELLS ``S``, AND THE ONE A REPAIR TO THE OTHER TWO
MISSES.** The reviewer who found `\s` standing in for the production named
`_XML_EQ` and `_XML_ATTRIBUTE`. A declaration with no ordinary attribute in
front of it never reaches `_XML_ATTRIBUTE` at all -- `(S Attribute)*` matches
empty -- so this separator is the one the reproduction actually walked through,
and fixing the two that were reported would have left it open. It reads
`_XML_S` for that reason, and the licence table asserts that none of the three
can drift back.
"""

# ---------------------------------------------------------------------------
# ⭐ **THE VALUE IS THE FIXED VALUE PLUS A DECLARED LIST OF RELAXATIONS, AND
# THAT ORDERING IS THE POINT.**
#
# The three rounds before this one each found a new dimension of looseness in
# this one check and each closed that dimension only: the namespace anywhere in
# the text, then any URI CONTAINING it, then any SCHEME whatever. That is the
# signature of a rule built permissively and narrowed by findings, and the
# module has already run the experiment on how to end one: five rounds repaired
# one Python shorthand at a time and what closed the set was
# `_XML_SHORTHAND_LICENCE` -- a row per pattern, a reason per row, walked off
# the module so the next entry has to pass a rule rather than be noticed.
#
# So the value below is **equality with the reassembled `#FIXED` value, THEN
# these five declared relaxations** -- not a pattern widened until the known
# spellings fit. ⚠️ Implemented the other way round it would pin `1.7.2`, or
# admit whatever the widening happened to reach; the tail row is exactly the
# first relaxation and it is why equality alone is not what is written.
#
# **What this buys over simply constraining the scheme is the ARTIFACT, not the
# pattern: the two compile to the SAME REGEX.** After the scheme is constrained
# there is no loose element left in the prefix either, so "a fourth dimension
# can appear" is a weaker argument here than it looks. What the table adds is a
# tolerance somebody has to justify in writing, held closed by a test that
# objects to a blank reason and to a row that has stopped earning its place.
#
# **The argument AGAINST it, recorded rather than skipped:** the table is new
# machinery, and machinery added in response to a finding is the next round's
# surface. Its mitigations are that it is plain data feeding the ONE compiled
# pattern that already existed -- no second reader, no second pattern -- and
# that constraining the scheme is a strict SIMPLIFICATION of it. If a later
# round finds against the table, the retreat is one commit rather than more
# hardening, which is what makes this choice reversible rather than merely
# defended.
# ---------------------------------------------------------------------------

_NAMESPACE_TOLERANCES: tuple[tuple[str, str, str], ...] = (
    (
        "prefix",
        _GRAMPS_NAMESPACE_SCHEME + ":" + _SEPARATOR * 2,
        "the #FIXED value's OWN scheme and authority marker: the canonical spelling, and the "
        "only one the specification's exact-match rule endorses. Bound to "
        "FIXED_ATTRIBUTE_DEFAULTS by test, so a schema revision that moved the format to "
        "another transport fails a test instead of silently blinding the gate",
    ),
    (
        "prefix",
        _GRAMPS_NAMESPACE_SCHEME + "s" + ":" + _SEPARATOR * 2,
        "the same authority over TLS. ⚠️ THIS IS THE ONE ROW WHOSE FRAGMENT IS THE FIXED SCHEME "
        "PLUS A HAND-WRITTEN 's', AND ITS REASON IS THE WEAKEST OF THE FIVE -- under exact-string "
        "comparison it is as different a namespace as ftp is. It stays because the marker "
        "identifies the format a document is ABOUT rather than the namespace a parser would "
        "bind, and because the tolerance fails toward REPORTING, which is the direction this "
        "guard may fail in. Dropping it costs this row and one line of "
        "_uris_that_are_the_namespace",
    ),
    (
        "prefix",
        _SEPARATOR * 2,
        "protocol-relative: a document may quote the namespace without committing to a transport",
    ),
    (
        "prefix",
        "",
        "the bare base. An export or a quotation may write it alone, and this tolerance is "
        "already load-bearing and already tested -- it is what the marker gate was built on "
        "before any of the anchoring rounds",
    ),
    (
        "tail",
        _SEPARATOR,
        "what OPENS the version segment, after which everything is free -- SO A LATER SCHEMA "
        "REVISION STILL NAMES THE FORMAT. _GRAMPS_XML_NAMESPACE deliberately stops short of the "
        "version, and equality with the whole fixed value would pin 1.7.2. This used to be an "
        "emergent property of the pattern and is a declared row now, so removing it BREAKS the "
        "three version spellings rather than quietly narrowing the gate",
    ),
)
"""``(position, fragment, reason)`` -- every relaxation of the fixed value, declared.

``position`` is ``"prefix"`` (what may stand before the base) or ``"tail"``
(what may open the free segment after it). The fragment is a LITERAL, escaped
where it is compiled, and every one of them is a transformation of the frozen
value rather than a string typed beside it.

⚠️ **A row is not a dispensation, it is a recorded decision**, exactly as a
licence row is: the reason is the artifact, and
`test_every_namespace_tolerance_is_declared_with_a_reason_and_earns_its_row`
is what stops the list growing by accident, going vacuous, or keeping a row
that has stopped mattering.
"""


def _namespace_value_of(tolerances: Sequence[tuple[str, str, str]]) -> str:
    r"""An ``AttValue`` that IS the Gramps namespace, rather than one containing it.

    ⚠️ **THE VALUE OCCUPIES THE WHOLE ``AttValue``, and that is the older half
    of the repair.** This used to be ``_att_value(re.escape(…))`` -- body,
    namespace, body -- which is a **bare substring test wearing an
    ``AttValue``'s quotes**, so a declaration whose value was ``urn:not-gramps:``
    followed by the base named a namespace that is explicitly not this one and
    the gate read it as Gramps. (Spelled that way round on purpose: writing the
    reproduction out would put the value contiguously into a tracked file,
    which this module's own sweep catches.)

    ⚠️ **What may PRECEDE the base is now a closed alternation** rather than an
    optional ``scheme://``, and that is this round's half. The RFC production
    admits every syntactically valid scheme, so the base served over ``ftp`` was
    read as this namespace -- and namespace names are compared by exact string
    match, so it is not.

    **Emitted LONGEST-FIRST with the empty alternative last**, reusing
    ``_qualified``'s ordering convention rather than inventing one: a shorter
    spelling must never shadow a longer one it begins with, and the empty
    tolerance begins every other. Asserted structurally, the way that helper's
    ordering is, because nothing behavioural can see it while the table is
    small.

    ⚠️ **NO VERSION IS PINNED.** The tail is the table's one ``tail`` row and
    everything after it is free, so an export written against a schema revision
    this project has never seen still names the format.

    A pure function of the table so the test can feed it a fabricated one and
    SHOW what each row is holding up -- the shape ``_unlicensed`` already uses.
    """
    prefixes = sorted(
        (fragment for position, fragment, _ in tolerances if position == "prefix"),
        key=lambda fragment: (-len(fragment), fragment),
    )
    tails = [fragment for position, fragment, _ in tolerances if position == "tail"]
    before = "(?:" + "|".join(re.escape(fragment) for fragment in prefixes) + ")"
    return _att_value_of(
        lambda body: (
            before
            + re.escape(_GRAMPS_XML_NAMESPACE)
            + "".join("(?:" + re.escape(tail) + body + ")?" for tail in tails)
        )
    )


def _marker_reading(tolerances: Sequence[tuple[str, str, str]]) -> re.Pattern[str]:
    """The one marker, compiled from ``tolerances``: the namespace, declared.

    ⚠️ **ONE compiled pattern, and the block above says why.** An ``or`` over
    two results is the shape-without-value defect wearing a conjunction, and an
    ``and`` is worse: ``shape.search(text) and value in text`` is satisfied by
    an unrelated declaration in a file that mentions this namespace three
    paragraphs down.

    ⚠️ **The element name is NOT required to be `database`.** A fragment
    declares the namespace on whatever wrapper it has, and requiring the
    document element would put back the structural judgement an earlier round
    removed. `_GRAMPS_DOCUMENT_ELEMENT` keeps the job it actually has: selecting
    the `FIXED_ATTRIBUTE_DEFAULTS` row the value is read from.

    ⚠️ **The closing `>` is not required either**, and that is the safe
    direction: a truncated paste of a real export still names itself. What the
    pattern insists on is the path to the declaration -- a start tag's name,
    then complete attributes -- because that is the half a mention can never
    satisfy.

    Nothing here is hand-typed and the value is never spelled contiguously;
    `re.escape` splits it with backslashes at runtime as well.
    """
    return re.compile(
        "<"  # STag
        + _XML_NAME_PREFIX
        + _XML_NCNAME  # ...its Name
        + _XML_ATTRIBUTE_SEQUENCE  # ...(S Attribute)*
        + _XMLNS_DECLARATION  # ...then the declaration
        + _namespace_value_of(tolerances)  # ...whose value IS the namespace
    )


_NAMES_THE_GRAMPS_FORMAT = _marker_reading(_NAMESPACE_TOLERANCES)
"""The marker the scan reads, compiled once from the declared tolerance table.

Accepted: the bare base, any version segment after a ``/``, the schema's own
scheme, that scheme over TLS, ``//`` alone, and either quoting. Refused: any
other scheme, a scheme with no ``//``, the base sitting in another host's PATH,
a host that merely ends with the base, and a host or path segment that merely
begins with it.
"""


def _names_the_gramps_format(text: str) -> bool:
    """Whether ``text`` says it is Gramps -- the condition a derived row scores under.

    ⚠️ **One marker, one pattern, one search -- and the block above says why.**
    Not a substring test, not two conditions combined: a document that MENTIONS
    the namespace has not declared it, and the difference is the whole gate.

    ⚠️ **"The file" is the string the scorer was handed, and nothing else.** No
    cross-file state and no cross-commit state, which keeps one answer per scan
    path: the tip scan asks it of the whole decoded blob, the history walk of
    that blob **at that commit** rather than of the tip's copy, and `scan_text`
    of the text it was given.

    ⚠️ **The committed NAME is the hole in that, and it is stated rather than
    smoothed over.** `scan_blob` also runs the genealogy properties over the
    path string, and one short filename can essentially never carry a marker --
    so a derived row will never score on a name. That is a residual of the gate
    rather than a defect in its scoping, and it costs nothing today, because the
    name that is a finding is a GEDCOM record and rests on the record signature.
    """
    return _NAMES_THE_GRAMPS_FORMAT.search(text) is not None


# The known-SAFE side of the classification. Everything not on it is a finding.
#
# This is deliberately the one enumeration in the guard, and deliberately the
# one pointing the safe way: growing the list of known-bad signatures is the
# losing side of the race, because there is always one more genealogy format --
# GEDCOM X, a vendor's JSON, next year's export. Refusing what cannot be proved
# safe means a new file type is a build failure and a one-line decision, rather
# than a silent pass.
#
# It is short on purpose. Adding to it is meant to be a deliberate, reviewed
# act; see CONTRIBUTING.md.
SAFE_EXTENSIONS = frozenset({".md", ".py", ".toml", ".yml"})
# "uv.lock" is a BASENAME rather than a ".lock" extension on purpose: nothing
# about that extension is safe, and admitting it would admit a class this
# project has no property for. One generated file, named. Being here exempts it
# from the type gate and from nothing else -- P1, P2 and the deny-list all
# still run over its contents. See CONTRIBUTING.md.
SAFE_BASENAMES = frozenset({".gitattributes", ".gitignore", "LICENSE", "uv.lock"})
"""Extensionless files this project publishes, admitted by NAME ANYWHERE.

⛔ A name belongs here only when it means the same thing in every directory. A
``.gitignore`` is a gitignore wherever it sits; a ``LICENSE`` is a licence; a
``.gitattributes`` is git's own per-path metadata, text, and cannot carry a
family tree any more than the other two.

⚠️ **Contrast ``pre-push`` in ``SAFE_PATHS``**, which does NOT belong here: a file
of that name means something only at one path, and admitting the name anywhere
waived the type check for every file called ``pre-push`` in the repository."""

SAFE_PATHS = frozenset({"scripts/hooks/pre-push"})
"""Extensionless files admitted at ONE PATH, and nowhere else.

⛔ **``pre-push`` was briefly in ``SAFE_BASENAMES`` and that was a hole.** Git
requires a hook's name without a suffix, so there is no extension to admit -- but
a basename-wide exemption waives the type check for **every** tracked file called
``pre-push``, in any directory, whatever it contains. A file of family records
renamed ``pre-push`` would have been reported clean while the identical bytes
named ``family.csv`` are a P2. **That defeats the fail-closed classification this
guard is built on**, and it was opened while fixing something else.

⚠️ The exemption is still only from the *prove-the-TYPE-is-safe* step. Every line
of the file is scanned for paths and deny-list entries exactly like any other, so
what is waived is the classification, never the content."""

_HOW_TO_ALLOW_A_TYPE = (
    "if this type belongs in the repository, add it to SAFE_EXTENSIONS or "
    "SAFE_BASENAMES in pii_guard and say why in the commit"
)

# Text carries these and nothing else below U+0020. A NUL is the giveaway for
# UTF-16 text mis-read as UTF-8, which decodes without error and is not text.
_TEXT_CONTROL_CHARACTERS = frozenset("\t\n\r\f\v")


_MAXIMUM_PATH_LENGTH = 4096
_PLAUSIBLE_PATH = re.compile(
    "(?:" + _SEPARATOR + "|" + _ESCAPED_BACKSLASH + "|" + _COMPONENT + ")+"
)


def _is_plausible_path(text: str) -> bool:
    """Whether a symlink blob is positively a path, rather than merely text.

    Reuses the component definition the path patterns already share, so this
    is not a second classifier: a target is separators and components, and a
    structured document is not -- its braces and quotes are excluded from a
    path component for reasons that predate this check.

    A target containing a space is refused. That is a behaviour change, it is
    fail-closed, and it is recorded in CONTRIBUTING.
    """
    candidate = text.strip()
    if not candidate or len(candidate) > _MAXIMUM_PATH_LENGTH:
        return False
    return _PLAUSIBLE_PATH.fullmatch(candidate) is not None


def _unprintable_control_character(text: str) -> str | None:
    for character in text:
        if character < " " and character not in _TEXT_CONTROL_CHARACTERS:
            return character
        if character == "\x7f":
            return character
    return None


def _line_number_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _sniff_genealogy(text: str, source: SourcePath | str) -> list[Finding]:
    """Report at most one finding: the content either is genealogy data or is not."""
    for description, pattern in _GENEALOGY_TEXT_SIGNATURES:
        match = pattern.search(text)
        if match is not None:
            return [
                Finding(
                    rule="P2",
                    message=f"genealogy data ({description})",
                    source=source,
                    line=_line_number_at(text, match.start()),
                    match=match.group(0).strip()[:60],
                )
            ]

    # The properties, after the single-line signatures have had their say.
    # Those catch a marker standing on its own; these catch a document made of
    # records, whatever the records are wearing and wherever they sit in it.
    line = _genealogy_record_density(text)
    if line is not None:
        return [
            Finding(
                rule="P2",
                message=(
                    f"genealogy data ({_GENEALOGY_RECORDS_PER_FILE} or more records in one "
                    "file, whatever the surrounding markup and however far apart)"
                ),
                source=source,
                line=line,
            )
        ]

    for described, scorer in (
        ("Gramps XML elements", _gramps_identity_score),
        ("GEDCOM X keys", _gedcom_x_identity_score),
    ):
        scored = scorer(text)
        if scored is not None:
            score, offset = scored
            return [
                Finding(
                    rule="P2",
                    message=(
                        f"genealogy data ({described} carrying identity, scoring {score} "
                        f"against a threshold of {_GRAMPS_SCORE_THRESHOLD})"
                    ),
                    source=source,
                    line=_line_number_at(text, offset),
                )
            ]

    return []


# ---------------------------------------------------------------------------
# The local-only personal deny-list.
#
# The properties above deliberately contain no personal information: a
# committed deny-list of real names would be the leak this module prevents. A
# developer who wants their own literals caught puts them in a gitignored file,
# and the guard reports matches without ever repeating them.
# ---------------------------------------------------------------------------


def _scan_line_for_text(
    line: str, number: int, source: SourcePath | str, denylist: Sequence[str]
) -> list[Finding]:
    """Every property that reads one line of text.

    Used for committed *path names* as well as file contents: a filename is
    published like anything else, and can carry a name or a path.
    """
    return [
        *_scan_line_for_absolute_paths(line, number, source),
        *_scan_line_for_denylisted(line, number, source, denylist),
    ]


def _comparable(text: str) -> str:
    """One canonical form for comparing names.

    Case-folding alone was not enough: it does not normalise, so a composed
    entry missed canonically equivalent decomposed text. Accented names are
    exactly what the deny-list exists to protect -- it is the recorded backstop
    for P1's residual -- so both sides are normalised as well as folded.
    """
    return unicodedata.normalize("NFC", text).casefold()


def _scan_line_for_denylisted(
    line: str, number: int, source: SourcePath | str, denylist: Sequence[str]
) -> list[Finding]:
    findings: list[Finding] = []
    folded = _comparable(line)

    for entry in denylist:
        if _comparable(entry) in folded:
            findings.append(
                Finding(
                    rule="LOCAL",
                    message="matches an entry in the local deny-list",
                    source=source,
                    line=number,
                    match=entry,
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Asking Git what the repository contains.
#
# The working tree is not the repository. It omits blobs that history still
# reaches -- content added and deleted within one push stays publicly
# reachable -- and it shows untracked files that were never published. Every
# enumeration used by the gate goes through Git.
# ---------------------------------------------------------------------------

_SYMLINK_MODE = "120000"
_GITLINK_MODE = "160000"


def _is_denylist_path(name: str) -> bool:
    """The local deny-list is never scanned: its literals would match themselves."""
    return name.startswith(DENYLIST_PREFIX)


def _run_git(root: Path, *arguments: str, stdin: bytes | None = None) -> bytes:
    """Run a Git command against ``root``, raising rather than failing quietly.

    ⚠️ **Every Git command in this module goes through here, and every one of
    them is anchored on the directory it was given** -- see the environment
    helper. Anchoring only the work-tree probe fixed which repository the guard
    *decided* to scan and left every later command still reading the
    environment's, which is the same defect one step along.
    """
    try:
        result = subprocess.run(
            # --no-replace-objects on EVERY command, here rather than at the
            # reads that looked like they needed it. A replacement reference
            # makes an ordinary object read return a different object, so a
            # GEDCOM in the index can read as harmless Markdown while the
            # commit still references the original -- the guard is shown a
            # substitute and reports clean. Which commands resolve an object
            # is not a list worth maintaining: they all get it.
            #
            # It is a flag rather than GIT_NO_REPLACE_OBJECTS because the
            # environment anchor above deliberately clears that variable --
            # it is one of the fifteen Git calls repository-local, and a fix
            # that depended on it would be undone by the fix beside it.
            ["git", "--no-replace-objects", *arguments],
            cwd=root,
            input=stdin,
            capture_output=True,
            check=False,
            env=_git_environment_anchored_on_the_target(),
        )
    except OSError as error:
        # Git missing, or a working directory that cannot be entered. The
        # message is NOT reported raw: on Linux the interpreter puts the
        # working directory in it, which is an absolute path on somebody's
        # machine, so it goes through the same redaction as everything else.
        raise ValueError(
            f"git {arguments[0]} could not be run ({type(error).__name__}, "
            f"detail {Secret(str(error))})"
        ) from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        # Only the subcommand is named. The root, the arguments and git's own
        # message can each carry an absolute path -- git echoes the revision it
        # was given -- and this message gets printed. An operator debugging a
        # range already knows the range they typed.
        raise ValueError(
            f"git {arguments[0]} failed (arguments {Secret(' '.join(arguments[1:]))}, "
            f"message {Secret(detail)})"
        )
    return result.stdout


def decode_path(raw: bytes) -> str:
    """The one way a committed path name becomes text.

    Both enumerations go through this. They used to differ -- strict in one,
    replacing in the other -- so a single name that is not UTF-8 aborted the
    tip scan while history merely mangled it. Undecodable bytes survive as the
    replacement character, and a name carrying one is a finding: content that
    cannot be classified is refused, which is P2's rule already.
    """
    return raw.decode("utf-8", errors="replace")


def decode_name(name: str) -> str:
    """A name in the one representation the rules are written against.

    Git output reaches the classifier through ``decode_path``, so an invalid
    byte arrives as the replacement character. A filesystem name reaches it as
    a Python string that already exists, and on POSIX an invalid byte is a
    *surrogate escape* there instead -- a different character, which the
    invalid-name rule was not looking for.

    Encoding back with surrogateescape recovers the original bytes and hands
    them to the same decoder Git output goes through, so both routes end up
    saying the same thing about the same bytes. On a name that is already
    decoded this returns it unchanged.
    """
    return decode_path(name.encode("utf-8", errors="surrogateescape"))


@functools.lru_cache(maxsize=1)
def _repository_local_git_variables() -> frozenset[str]:
    """The variables Git says redirect it at a repository -- ASKED FOR, NOT WRITTEN.

    ⚠️ **A hand-maintained list of Git's environment variables is a list that
    is always one release behind, and this one was already two short of being
    right on the day it was written.** It named the two that answer *which
    repository*; Git names fifteen, and the omission that mattered was
    ``GIT_INDEX_FILE`` -- which answers *which staged content*, and so decides
    just as much for a scan that reads the index. An alternate index holding
    one harmless file made a staged GEDCOM invisible and the scan exited clean.

    So the set is queried rather than curated. ``--local-env-vars`` is Git's
    own answer to this question, it needs no repository, and it is unaffected
    by the very variables it enumerates -- verified with all three of them
    pointing at nothing. When Git adds a sixteenth, this returns sixteen
    without anyone noticing it had to.

    **On failure this raises rather than falling back to the hand-written
    pair.** A silent fallback would restore exactly the fail-open being closed,
    at the moment we have least reason to trust the environment; and an empty
    answer is not an answer either. Callers already turn a ``ValueError`` into
    a refusal, so the scan stops instead of scanning the wrong index.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"],
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise ValueError(
            f"git rev-parse --local-env-vars could not be run, so the environment "
            f"cannot be anchored ({type(error).__name__}, detail {Secret(str(error))})"
        ) from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            f"git rev-parse --local-env-vars failed, so the environment cannot be "
            f"anchored (message {Secret(detail)})"
        )
    names = frozenset(
        line.strip() for line in result.stdout.decode("utf-8", errors="replace").splitlines()
    ) - {""}
    if not names:
        raise ValueError(
            "git rev-parse --local-env-vars named nothing, so the environment cannot be anchored"
        )
    return names


def _git_environment_anchored_on_the_target() -> dict[str, str]:
    """The environment with Git's repository overrides removed.

    Everything else is inherited -- Git needs a PATH and a HOME like any other
    program. What is dropped is every variable Git itself calls
    repository-local, because each of them lets something outside the target
    decide what a command reads.
    """
    redirecting = _repository_local_git_variables()
    return {name: value for name, value in os.environ.items() if name not in redirecting}


def names_a_real_directory(path: Path) -> bool:
    """Whether ``path`` is a directory in its own right rather than a link to one.

    ⚠️ **A named entry is judged by its own identity, never by what it resolves
    to.** ``is_dir`` follows a symlink, so every decision made with it was
    really a decision about the destination: which directory Git was asked
    about, and which deny-list was loaded. A deny-list beside a link named
    after one of its own entries was read from the link's target instead, and
    the deny-listed name passed.

    This is the one place following is decided, so a call that genuinely wants
    the destination has to say so rather than get it by default.
    """
    return path.is_dir() and not path.is_symlink()


def lexical_path(path: Path) -> Path:
    """An absolute path built without following a single link.

    The pathspec handed to Git goes through here so that this enumeration
    covers it: it was already lexical, and being already correct is not the
    same as being guarded.
    """
    return Path(os.path.abspath(path))


def same_path(one: Path, other: Path) -> bool:
    """Whether two paths name the same entry, compared lexically.

    ``resolve`` follows links, so a link pointing at the scan root compared
    equal to it and skipped the check that a named entry must be tracked.
    ``abspath`` normalises without following.
    """
    return os.path.abspath(one) == os.path.abspath(other)


def is_git_work_tree(root: Path) -> bool:
    """Whether ``root`` is inside a Git working tree."""
    if not root.is_dir():
        # A path we cannot enter is not a working tree. Whether it should have
        # been scanned at all is main's question, not this one's.
        return False
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            # ⚠️ Asked about THIS directory, not about whatever the environment
            # points at. Git honours GIT_DIR and GIT_WORK_TREE ahead of
            # discovery, and it then answers SUCCESSFULLY about somewhere else:
            # aimed at a bare repository it exits zero and says false, so the
            # named repository was silently walked; aimed at another work tree
            # it exits zero and says true, and that tree became the root while
            # this one was named. Both were clean reports over a staged tree.
            #
            # A failing rev-parse was already handled. This is the opposite
            # problem -- a successful answer to a question nobody asked -- and
            # clearing the two variables is what makes discovery anchor on the
            # target itself.
            env=_git_environment_anchored_on_the_target(),
        )
    except OSError as error:
        # Git itself is unavailable, which must not quietly degrade the gate
        # into a filesystem walk.
        #
        raise ValueError(
            f"git could not be run ({type(error).__name__}, detail {Secret(str(error))})"
        ) from error

    if result.returncode == 0:
        return result.stdout.strip() == "true"

    # Git ran and failed. That used to return False, which is the same answer
    # as "not a repository", so an invalid GIT_DIR or a checkout Git refuses to
    # trust silently downgraded the run to a filesystem walk.
    #
    # ⚠️ It was left that way on the reasoning that the walk is a safe subset --
    # broader than the index, with the scope word changing to say so. THAT
    # REASONING IS FALSE and this comment replaces it. The walk is not broader,
    # it is DIFFERENT: it reads the working tree, so it misses exactly what the
    # index holds. Stage something, leave an innocuous copy on disk, and a walk
    # reports clean over what the next commit publishes.
    #
    # The message is not the discriminator -- an invalid GIT_DIR and a plain
    # directory both say "not a git repository" -- so the filesystem is asked
    # instead. Repository metadata present means this IS a repository and git
    # owes an answer; absent means there is genuinely nothing to downgrade
    # from, and only that may take the walk.
    if _has_repository_metadata(root):
        raise ValueError(
            "git could not determine whether this is a working tree, and there is a "
            "repository here. Scanning the filesystem instead would read the working "
            "tree rather than the index, which is a different question -- so this run "
            "is refused rather than quietly answering it."
        )
    return False


def _has_repository_metadata(directory: Path) -> bool:
    """Whether ``directory`` or any parent holds Git's metadata entry.

    A worktree and a submodule use a FILE where an ordinary clone uses a
    directory, so the check is existence rather than kind.
    """
    return any((candidate / ".git").exists() for candidate in (directory, *directory.parents))


def iter_tracked_entries(root: Path) -> Iterator[tuple[str, str, str]]:
    """Yield ``(mode, object id, path)`` for every file Git tracks under ``root``.

    Tracked is the whole test. A directory called ``build`` or ``.venv`` is not
    excluded by its name -- Git can and does contain those paths, and a
    force-added artefact inside one is published like anything else. What is
    not scanned is what is not tracked.
    """
    listing = _run_git(root, "ls-files", "--stage", "-z")
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, _, path_text = decode_path(entry).partition("\t")
        mode, object_id, _stage = metadata.split()
        yield mode, object_id, path_text


def read_blob(root: Path, object_id: str) -> bytes:
    """The bytes Git holds for one object.

    Every entry is read this way, symlink or not. The blob is what gets
    published; the working tree is a different thing that may have been edited
    since, and following a symlink would read the target instead of the target
    *string* -- or nothing at all, on a platform that never created it.
    """
    return _run_git(root, "cat-file", "blob", object_id)


def count_range_commits(root: Path, revision_range: str) -> int:
    """How many commits ``revision_range`` covers.

    The gate asserts this positively. A gate that cannot tell "scanned
    everything, found nothing" from "scanned nothing" is not a gate, and an
    empty range reporting clean is exactly how the zero-SHA fail-open hid.
    """
    output = _run_git(root, "rev-list", "--count", revision_range)
    return int(decode_path(output).strip() or 0)


_EMPTY_MODE = "000000"


def count_range_introductions_and_deletions(root: Path, revision_range: str) -> tuple[int, int]:
    """``(introduced, removed)`` for ``revision_range``, from ONE traversal.

    ⚠️ **Every traversal spawns one ``git diff-tree`` per commit**, measured at
    about 32 ms each on Windows -- so over a full-history range, which is what a
    new branch's first push presents, a second walk is not a rounding error. The
    two counts are needed together and are read together.

    ⛔ **And they must come from the same walk for a second reason:** a pair of
    classifiers kept in step by hand will diverge, and this file already carries
    that scar over a symlink's mode. Introduced and removed are two sides of one
    comparison, taken once.
    """
    introduced = 0
    removed = 0
    for is_removal in _iter_range_classified(root, revision_range):
        if is_removal:
            removed += 1
        else:
            introduced += 1
    return introduced, removed


def count_range_deletions(root: Path, revision_range: str) -> int:
    """How many entries ``revision_range`` REMOVES.

    ⛔ **The complement of what ``iter_range_entries`` yields, and it exists to
    tell two contentless ranges apart.** A range that only deletes introduces no
    blob, and neither does a range of empty commits -- so a count of introduced
    entries is zero for both, and a check keyed on that zero would treat them as
    one thing. They are not one thing:

    - a **deletion** removes content that is already in the history, and was
      scanned by the commit that added it. Nothing new is published.
    - an **empty commit** carries a message and nothing else, and commit
      messages are not scanned. A clean verdict there would claim coverage of
      the only thing the commit actually holds.

    ⚠️ So the question is not *how many entries did I scan?* but *did this range
    remove something?* -- which is a property of the range, asked of git,
    instead of an inference from a count that is zero for two different reasons.
    """
    return count_range_introductions_and_deletions(root, revision_range)[1]


def iter_range_entries(root: Path, revision_range: str) -> Iterator[tuple[str, str, str]]:
    """Yield ``(mode, object id, path)`` for every entry introduced in ``revision_range``.

    ``git diff-tree`` rather than ``rev-list --objects``, because diff-tree
    reports the **mode**. Without it a symlink introduced in history looked
    like an unknown file type, so the two scanners disagreed about identical
    bytes -- and a pair of classifiers kept in step by hand will diverge again.
    Both callers now feed the same one.

    An unresolvable range raises: scanning nothing quietly is the failure this
    whole function exists to prevent.
    """
    for entry, is_removal in _iter_range_entries_with_side(root, revision_range):
        if not is_removal:
            yield entry


def _iter_range_classified(root: Path, revision_range: str) -> Iterator[bool]:
    """Whether each entry in the range is a removal. One walk, counted twice."""
    for _, is_removal in _iter_range_entries_with_side(root, revision_range):
        yield is_removal


def _iter_range_entries_with_side(
    root: Path, revision_range: str
) -> Iterator[tuple[tuple[str, str, str], bool]]:
    """One walk, two questions.

    ⚠️ **A pair of classifiers kept in step by hand will diverge**, and this file
    already carries the scar: two scanners once disagreed about the mode of a
    symlink introduced in history. The introduced entries and the removed ones
    are read from the same ``diff-tree`` output, by the same parser, differing
    only in which side of one comparison they keep.
    """
    commits = decode_path(_run_git(root, "rev-list", revision_range)).split()
    seen: set[tuple[tuple[str, str, str], bool]] = set()

    for commit in commits:
        raw = _run_git(
            root, "diff-tree", "-r", "-m", "--root", "--no-commit-id", "--raw", "-z", commit
        )
        fields = raw.split(b"\0")
        index = 0
        while index + 1 < len(fields):
            metadata = decode_path(fields[index])
            path_text = decode_path(fields[index + 1])
            index += 2
            if not metadata.startswith(":"):
                continue
            parts = metadata[1:].split()
            if len(parts) < 4:
                continue
            mode, object_id = parts[1], parts[3]
            # A deletion introduces no content; the blob it removed is reached
            # through the commit that added it.
            removed = mode == _EMPTY_MODE or set(object_id) == {"0"}
            entry = (mode, object_id, path_text)
            if (entry, removed) in seen:
                continue
            seen.add((entry, removed))
            yield entry, removed


# ---------------------------------------------------------------------------
# Walking a filesystem tree.
#
# A convenience for ad-hoc use and for tests over temporary directories. It is
# NOT the gate: outside a repository there is no such thing as "tracked", so
# tooling output can only be recognised by name, which Git can contain.
# ---------------------------------------------------------------------------

# Not committed content: a tooling cache, a virtual environment or the object
# store that holds the history rather than the working tree.
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".eggs",
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
)


def _is_excluded_directory(name: str) -> bool:
    return name in EXCLUDED_DIRECTORY_NAMES or name.endswith(".egg-info")


def iter_files(paths: Iterable[Path]) -> Iterator[Path]:
    """Yield every scannable file under ``paths``, skipping tooling directories.

    Symbolic links are not followed: a link points outside the committed tree,
    and its target is either committed elsewhere or not committed at all.
    """

    def refuse_unlistable(error: OSError) -> None:
        # The walk's DEFAULT is to drop a directory it cannot list and carry
        # on, which passed a run over a tree whose contents nobody saw -- the
        # same class as an unreadable file, failing the opposite way. The
        # message is redacted for the same reason theirs is: the interpreter
        # puts the directory it could not open into it.
        raise ValueError(
            f"a directory could not be listed ({type(error).__name__}, detail {Secret(str(error))})"
        ) from error

    for base in paths:
        if base.is_symlink():
            yield base
            continue
        if base.is_file():
            # The deny-list exemption was written inside the walk, so naming
            # the file directly scanned it -- and every literal in it matches
            # itself, so the one file guaranteed to hold personal names
            # printed them all. One check, both routes.
            if not _is_denylist_path(base.name):
                yield base
            continue
        for directory, subdirectories, filenames in os.walk(
            base, followlinks=False, onerror=refuse_unlistable
        ):
            # A symlink is an entry, and Git classifies the one it holds: the
            # committed blob IS the target, which can be an absolute personal
            # path. The walk dropped the entry altogether -- not merely its
            # name, the whole thing -- so the same link on disk was invisible.
            # Yielding it is not following it; the walk still passes
            # followlinks=False and never descends through one.
            #
            # This runs BEFORE the exclusions, and that order is the fix rather
            # than an accident of style. The exclusions filter by NAME, so
            # running them first consumed any link that merely shared a name
            # with a tooling directory -- target unread, while the coverage
            # line went on saying targets are classified. An exclusion removes
            # real directories from the walk; it does not decide what is an
            # entry.
            for name in sorted(subdirectories):
                candidate = Path(directory) / name
                if candidate.is_symlink():
                    yield candidate

            subdirectories[:] = sorted(
                name
                for name in subdirectories
                if not _is_excluded_directory(name) and not (Path(directory) / name).is_symlink()
            )

            for filename in sorted(filenames):
                candidate = Path(directory) / filename
                if _is_denylist_path(filename):
                    continue
                yield candidate


def scan_blob(
    content: bytes | None,
    path_text: str,
    *,
    source: SourcePath | str | None = None,
    denylist: Sequence[str] | None = None,
    is_symlink: bool = False,
) -> list[Finding]:
    """Every reason an entry stored at ``path_text`` must not be published.

    **The one funnel. Every entry any mode finds goes through here**, and no
    call site implements a check of its own. That is not tidiness: this project
    spent five rounds on redaction findings and four on scope, and both only
    stopped when the checks moved to a single place every path funnels through.
    Four more arrived together the moment four entry paths were each deciding
    for themselves.

    The NAME is classified here, always. The CONTENT is classified when there
    is any: ``content`` is None for an entry that genuinely has no bytes in
    this repository -- a gitlink names another one. Skipping the bytes must not
    skip the name, which is exactly what it used to do.

    A committed path is published content too: a filename or a parent
    directory carries a surname as readily as a line inside the file.
    """
    entries = denylist if denylist is not None else []

    # Normalised on the way in, so the rules below see ONE representation of a
    # name however it arrived. Git decodes an invalid byte to the replacement
    # character; a filesystem hands the same byte back as a surrogate escape,
    # and the invalid-name rule below only ever recognised the first -- so a
    # name Git refuses was clean once it came off a POSIX disk, and a
    # deny-listed surname typed in the wrong encoding went through with it.
    #
    # Idempotent on an already-decoded name, which is what lets it sit here
    # rather than at each entry point: the two paths cannot drift apart again
    # because there is only one of them.
    path_text = decode_name(path_text)
    if isinstance(source, str):
        source = decode_name(source)
    reported_as = source if source is not None else path_text

    # EVERY rule about the NAME lives here, and nothing below this line reads
    # the name for a verdict. That is the whole consolidation: the undecodable
    # check used to sit in the content classifier, so the one entry that
    # legitimately has no content -- a gitlink -- skipped a name rule as well.
    # A path that opts out of classifying bytes must not thereby opt out of
    # classifying its own name.
    if UNDECODABLE_MARKER in path_text:
        return [
            Finding(
                rule="P2",
                message=(
                    "the committed name is not valid UTF-8, so it cannot be classified; "
                    "refusing what cannot be proved safe"
                ),
                source=reported_as,
                line=1,
            )
        ]

    findings = list(_scan_line_for_text(path_text, 1, reported_as, entries))
    # And the genealogy properties over the same name, which is the one family
    # of rules that used to stop at the bytes. A name is published exactly as
    # the contents are -- an export dumped one record per file names its files
    # after the records -- so the question "is this genealogy data" is asked of
    # both or the answer is about half the entry.
    #
    # ⚠️ **HERE rather than inside ``_scan_line_for_text``**, which also runs
    # per line of a file's contents. Sniffing a document line by line is a
    # different property with a different false-positive profile: the density
    # rule counts records ACROSS a file and the scorers weigh a whole document,
    # and neither means anything applied to one line at a time.
    findings.extend(_sniff_genealogy(path_text, reported_as))
    if content is not None:
        findings.extend(
            _classify_content(
                content, path_text, source=source, denylist=denylist, is_symlink=is_symlink
            )
        )
    return findings


def _classify_content(
    data: bytes,
    path_text: str,
    *,
    source: SourcePath | str | None = None,
    denylist: Sequence[str] | None = None,
    is_symlink: bool = False,
) -> list[Finding]:
    """What the bytes are, leaving what the name says to the caller above.

    A symlink is exempt from file-type classification: its content is
    definitionally a path string, so it is positively classified already and
    goes straight to the text properties.
    """
    reported_as = source if source is not None else path_text
    suffix = PurePosixPath(path_text).suffix.lower()

    # A symlink is exempt from the two EXTENSION-based gates and nothing else.
    # Its name says nothing about its content, but its bytes are bytes: Git
    # stores whatever it is given under the symlink mode, so a database or a
    # differently-encoded tree hides there unless the content checks run.
    if suffix in GENEALOGY_EXTENSIONS and not is_symlink:
        return [
            Finding(
                rule="P2",
                message=f"genealogy data (file extension {suffix})",
                source=reported_as,
                line=1,
            )
        ]

    if data[: len(_SQLITE_MAGIC)] == _SQLITE_MAGIC:
        return [
            Finding(
                rule="P2",
                message="genealogy data (SQLite file magic)",
                source=reported_as,
                line=1,
            )
        ]

    def refuse(reason: str, *, match: str = "") -> list[Finding]:
        # Usually no match is recorded: the evidence is the *shape* of the
        # file, which the message already carries, and the content is exactly
        # what must not be echoed.
        #
        # The unprovable TYPE is the exception, and it must travel in this
        # field rather than in the message. A message is finished text by the
        # time it exists, so a value interpolated into one is redacted for
        # nobody and revealable by no flag -- and a file with no extension put
        # its whole filename there.
        return [
            Finding(
                rule="P2",
                message=f"{reason} ({len(data)} bytes); refusing what cannot be proved safe",
                source=reported_as,
                line=1,
                match=match,
            )
        ]

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return refuse("content is not UTF-8")

    control = _unprintable_control_character(text)
    if control is not None:
        # Decoding succeeded and proved nothing: UTF-16 text read as UTF-8
        # decodes to interleaved NULs, and arbitrary binary can decode too.
        return refuse(f"content decodes but is not text (control character U+{ord(control):04X})")

    genealogy = _sniff_genealogy(text, reported_as)
    if genealogy:
        return genealogy

    name = PurePosixPath(path_text).name
    if is_symlink and not _is_plausible_path(text):
        # The exemption is for the extension gate, whose premise is that a
        # name describes its content. It is not an exemption from being
        # classified at all: a document wearing this mode is still a document.
        return refuse("a symlink blob that is not a path")
    known = (
        suffix in SAFE_EXTENSIONS
        or name in SAFE_BASENAMES
        or PurePosixPath(path_text).as_posix() in SAFE_PATHS
    )
    if not is_symlink and not known:
        return refuse(
            f"the file type cannot be proved safe -- {_HOW_TO_ALLOW_A_TYPE}", match=suffix or name
        )

    return scan_text(text, source=reported_as, denylist=denylist)


def scan_file(
    path: Path,
    *,
    source: SourcePath | str | None = None,
    denylist: Sequence[str] | None = None,
) -> list[Finding]:
    """Report every reason the entry at ``path`` must not be committed."""
    try:
        # A symlink's content is its target, which is what Git commits for one
        # and therefore what the other mode already classifies. Reading the
        # bytes instead would read through the link, which is a different file
        # and quite possibly outside the tree.
        # os.readlink, not Path.readlink: the committed blob is the literal
        # target string, and constructing a Path from it rewrites the
        # separators to the local flavour -- a POSIX target read on Windows
        # stops looking like a POSIX path, which is exactly the shape P1 is
        # looking for.
        content = (
            os.readlink(path).encode("utf-8", errors="surrogateescape")
            if path.is_symlink()
            else path.read_bytes()
        )
    except OSError as error:
        # The same class as a Git command that cannot run, and it fails the
        # same way: the scan now covers less than it is about to claim, so it
        # refuses rather than reporting on what it managed to read. The
        # message is NOT reported raw -- the interpreter puts the file it
        # could not open into it, which is an absolute path on somebody's
        # machine, so it goes through the same redaction as everything else.
        raise ValueError(
            f"a file could not be read ({type(error).__name__}, detail {Secret(str(error))})"
        ) from error
    # The name handed to the classifier is the RELATIVE one, the same shape
    # Git hands it in the other mode. It was the absolute path, which stopped
    # mattering while only the suffix was read from it and starts mattering the
    # moment the name itself is scanned: every file would have reported the
    # absolute path it was found at.
    name = source if isinstance(source, str) else path.name
    return scan_blob(
        content,
        name,
        source=source if source is not None else name,
        denylist=denylist,
        is_symlink=path.is_symlink(),
    )


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def scan_text(
    text: str,
    *,
    source: SourcePath | str = "<memory>",
    denylist: Sequence[str] | None = None,
) -> list[Finding]:
    """Report every reason ``text`` must not be committed.

    ``source`` names the origin of the text for reporting; ``denylist`` supplies
    extra literal patterns loaded from a developer's local, never-committed
    deny-list.
    """
    findings: list[Finding] = []

    entries = denylist if denylist is not None else ()

    # DECODED ONCE, HERE, BEFORE ANY RULE LOOKS AT IT. Every rule below judges
    # spelling, so this is the one place that can stop a spelling deciding a
    # verdict; doing it per-pattern is how the escaped forms were missed.
    text = _decoded(text)

    for number, line in enumerate(text.splitlines(), start=1):
        findings.extend(_scan_line_for_absolute_paths(line, number, source))
        findings.extend(_scan_line_for_denylisted(line, number, source, entries))

    findings.extend(_sniff_genealogy(text, source))

    # THE KEY DOES NOT INCLUDE THE MATCHED VALUE, AND MUST NOT.
    #
    # It used to, and it crashed: Secret has no ordering, and the third element
    # is reached only when two findings share a line and a rule, so the failure
    # waited for the first file with two of anything on one line.
    #
    # The tempting repair is an ordering operator on Secret. Do not add one.
    # The wrapper's guarantee is not "nothing is printed" -- it is ONE AUDITED
    # ROUTE TO THE VALUE, through reveal(). Ordering is a second route to
    # information about it: a comparison is an oracle, the resulting order is
    # observable in output, and it sets the precedent that reaching through the
    # wrapper is fine. After __lt__ comes __contains__, then startswith.
    #
    # Dropping the value loses nothing. list.sort is stable and the scan order
    # is deterministic -- lines in order, patterns in a fixed order, matches
    # left to right -- so the output is identical run to run, which is what a
    # gate people diff actually needs. The message is the detector kind, so
    # ties group by what was found rather than by an accident of length.
    findings.sort(key=lambda finding: (finding.line, finding.rule, finding.message))
    return findings


def scan_paths(paths: Iterable[Path], *, denylist: Sequence[str] | None = None) -> list[Finding]:
    """Report every reason the files under ``paths`` must not be committed.

    ``denylist`` defaults to the local deny-list in the current directory, if
    the developer running the scan has written one.

    NOTE: the command line does not use this default -- it resolves each
    target's own deny-list and passes the result in. The two therefore differ
    for a caller standing somewhere other than the target. That is left alone
    deliberately rather than quietly changed: a documented default with a test
    on it is not something to alter as a side effect of another fix.
    """
    bases = list(paths)
    entries = denylist if denylist is not None else load_denylist()
    findings: list[Finding] = []

    for path in iter_files(bases):
        findings.extend(scan_file(path, source=_relative_source(path, bases), denylist=entries))

    return findings


def _relative_source(path: Path, bases: Sequence[Path]) -> str:
    """Name a finding relative to what was asked for, never absolutely.

    The source has to survive redaction or the finding is unusable, so it is
    the one sensitive-ish string that gets printed. Making it relative is what
    lets that be true: an absolute source names somebody's home directory in
    a public log, and no amount of care at the print site fixes that.
    """
    for base in bases:
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            continue
        # relative_to returns a single dot when the path IS the base, and a dot
        # is truthy, so an `or` fallback never fired and every file argument
        # reported the same unlocatable source.
        return path.name if relative in {"", "."} else relative
    return path.name


def scan_repository(
    root: Path | None = None,
    *,
    revision_range: str | None = None,
    denylist: Sequence[str] | None = None,
) -> list[Finding]:
    """Report every reason the repository at ``root`` must not be published.

    This is the gate. It asks Git what the repository contains, because the
    working tree is not that: it omits blobs that history still reaches, and it
    shows untracked files that were never published.

    ``revision_range`` additionally scans every blob introduced in that range,
    which is what catches content added and deleted within a single push. An
    unresolvable range raises rather than scanning nothing.
    """
    base = Path() if root is None else root
    entries = denylist if denylist is not None else load_denylist(base)
    findings: list[Finding] = []

    def scan_entry(
        mode: str, object_id: str, path_text: str, source: SourcePath | str
    ) -> list[Finding]:
        """The single classifier. Both enumerations go through here, so the
        tip and the history cannot reach different verdicts about one blob."""
        if _is_denylist_path(PurePosixPath(path_text).name):
            # Only an UNTRACKED local deny-list is exempt, and that one never
            # reaches here -- Git does not know about it. A Git entry with this
            # name is the leak the guard exists to prevent, whether it survives
            # to the tip or was deleted a commit later, because the blob stays
            # reachable. Its contents are never read: reporting it must not
            # republish the names it holds.
            return [
                Finding(
                    rule="DENYLIST",
                    message="a deny-list of personal literals is committed to this repository",
                    source=source,
                    line=1,
                )
            ]
        # A gitlink names another repository; the commit it points at is not an
        # object here, so there is nothing to read and reading it aborted the
        # gate permanently. That is the ONLY thing special about it -- it goes
        # through the same funnel with no content, rather than round the side
        # of it, which is how it came to skip a rule about its own name.
        return scan_blob(
            None if mode == _GITLINK_MODE else read_blob(base, object_id),
            path_text,
            source=source,
            denylist=entries,
            is_symlink=mode == _SYMLINK_MODE,
        )

    for mode, object_id, path_text in iter_tracked_entries(base):
        findings.extend(scan_entry(mode, object_id, path_text, path_text))

    if revision_range is not None:
        for mode, object_id, path_text in iter_range_entries(base, revision_range):
            findings.extend(
                scan_entry(mode, object_id, path_text, SourcePath(path_text, scope=HISTORY_SOURCE))
            )

    return findings


def find_committed_denylists(root: Path | None = None) -> list[str]:
    """Deny-list files Git tracks, at any depth.

    The glob pathspec matters: a bare ``.pii-denylist*`` is anchored at the
    repository root, and a subdirectory is exactly where a stray copy would
    sit. Asking Git rather than the filesystem also means a correctly ignored
    local deny-list -- which every contributor is told to create -- does not
    read as a committed one.
    """
    base = Path() if root is None else root
    listing = _run_git(base, "ls-files", "-z", "--", f":(glob)**/{DENYLIST_FILENAME}*")
    return [decode_path(entry) for entry in listing.split(b"\0") if entry]


def load_denylist(root: Path | None = None) -> list[str]:
    """Literal patterns from the developer's local, never-committed deny-list.

    One literal per line; blank lines and ``#`` comments are ignored. An absent
    file means an empty list -- the deny-list is an optional local addition to
    the properties, never a substitute for them.
    """
    location = (root if root is not None else Path.cwd()) / DENYLIST_FILENAME
    if not location.is_file():
        return []

    try:
        text = location.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        # A deny-list holds surnames, and an accented surname typed in the
        # wrong editor is a latin-1 file -- this project's own use case, not a
        # hypothetical. A decoding failure is not an operating-system error, so
        # it missed the handler below and reached the caller only as the kind
        # of error that happened to be caught. It says what failed now.
        raise ValueError(
            f"the local deny-list could not be decoded ({type(error).__name__}); it must be UTF-8"
        ) from error
    except OSError as error:
        # The quietest member of the same class. This read happens before any
        # file is scanned, so an unhandled error here aborts the run before a
        # finding could exist -- and this is the one file in the project
        # guaranteed to contain personal names, so its own path is redacted
        # like any other detail.
        raise ValueError(
            f"the local deny-list could not be read ({type(error).__name__}, "
            f"detail {Secret(str(error))})"
        ) from error

    entries = []
    for raw_line in text.splitlines():
        entry = raw_line.strip()
        if entry and not entry.startswith("#"):
            entries.append(entry)
    return entries


def find_work_tree_root(path: Path) -> Path | None:
    """The root of the Git working tree containing ``path``, if there is one.

    **Tracked content is a claim about a repository**, so it is the repository
    that has to be enumerated. Asking Git from a subdirectory lists only that
    subtree, and the verdict still spoke for the whole repository -- a clean
    gate over a committed family tree one directory up.
    """
    directory = path if names_a_real_directory(path) else path.parent
    if not names_a_real_directory(directory) or not is_git_work_tree(directory):
        return None
    return Path(decode_path(_run_git(directory, "rev-parse", "--show-toplevel")).strip())


@dataclass(frozen=True)
class Scan:
    """What a run will look at, and the words for it, from one place.

    Four rounds fixed coverage by asserting per mode that *something* had been
    scanned. Every assertion was true, and the fourth defect still got through:
    the phrase describing the scan was written by hand where it was printed,
    while the set was enumerated somewhere else, and nothing compared them. One
    phrase described three different sets depending on which directory was
    named.

    So the description is not a sentence someone remembers to keep in step. It
    is derived here, from the same values that decide what gets enumerated, and
    ``main`` may only print it.

    ⚠️ **Same inputs, not the same list.** The counts here and the scan that
    follows are two enumerations of one set of inputs -- the same root, the
    same bases, the same range -- not one enumeration shared between them.
    What that buys is that the words and the numbers cannot describe different
    *scopes*; what it does not buy is immunity to the tree changing underneath
    a run. Do not read this type as a snapshot.
    """

    root: Path | None
    """The work-tree root when this is a repository scan, otherwise nothing."""
    bases: tuple[Path, ...]
    denylist: tuple[str, ...]
    tracked: int
    submodules: int
    commits: int | None
    range_entries: int | None
    range_deletions: int | None
    """Entries the range REMOVES. Distinguishes a deletion-only range from an empty one."""
    widened: bool
    """Whether a path inside a work tree was widened to the whole repository."""

    @property
    def is_repository(self) -> bool:
        return self.root is not None

    @property
    def covered(self) -> int:
        """Everything this run will look at, across both halves of it.

        The total, not the tip: a repository whose tip tracks nothing can still
        have a range worth scanning, and that is the add-then-delete case the
        range exists for. Asserting on the tip alone refused it.
        """
        return self.tracked + (self.range_entries or 0)

    @property
    def description(self) -> str:
        if self.is_repository:
            scope = f"tracked content ({self.tracked} entries)"
            if self.range_entries is not None:
                plural = "" if self.commits == 1 else "s"
                if self.range_entries == 0 and self.range_deletions:
                    # ⛔ **Zero here is a FACT ABOUT THE RANGE, not a failure to
                    # look.** ``iter_range_entries`` skips a deletion because a
                    # deletion introduces no blob -- so a range of deletions,
                    # or of empty commits, genuinely has nothing new to scan.
                    # Publication needs a new blob; a range that adds none
                    # cannot publish. Said out loud rather than printed as a
                    # bare "0 entries", which reads like the scanner gave up.
                    scope += (
                        f" and the given range ({self.commits} commit{plural} "
                        "introducing no file content -- a deletion publishes no "
                        "blob, so there is nothing new there to scan)"
                    )
                else:
                    scope += (
                        f" and every blob in the given range ({self.commits} commit{plural}, "
                        f"{self.range_entries} entries scanned)"
                    )
            # Named rather than left to be discovered. A gap nobody wrote down
            # is indistinguishable from coverage.
            scope += "; commit messages, tags and notes not scanned"
            if self.submodules:
                # The count is honest -- those paths were scanned, and a path
                # can draw a deny-list or a path finding. What it cannot do is
                # contribute content, because the content is in another
                # repository. Countable and unclassifiable is worth saying.
                scope += (
                    f"; {self.submodules} submodule entr"
                    f"{'y' if self.submodules == 1 else 'ies'} whose content lives elsewhere"
                )
        else:
            # The walk names its exclusions for the same reason the repository
            # half does. It quietly drops tooling directories, egg-info, every
            # symlink and the deny-list, and a target whose only genealogy sat
            # under a build directory reported one file scanned and exit 0.
            # Re-read clause by clause against what the walk does, because
            # every previous time this line drifted it drifted in more than
            # one place. Tooling directories: still skipped. A deny-list:
            # still skipped, either route. Symlinks: no longer skipped -- the
            # consolidation made the walk classify a link's target, and this
            # line went on claiming the opposite. A link is an entry that gets
            # classified; what still does not happen is descending through one
            # into whatever it points at, and that is worth saying rather than
            # deleting.
            # "Not descended into" rather than "not scanned", because the two
            # are different and the difference is a defect this line already
            # carried: an exclusion prunes a real directory from the walk, and
            # a symlink that merely shares one of those names is still an entry
            # and still classified.
            scope = (
                f"files ({self.tracked} file(s) scanned); symlink targets classified but not "
                "followed; tooling directories not descended into; any deny-list not scanned"
            )
        return f"{scope}; {self.denylist_state}"

    @property
    def denylist_state(self) -> str:
        """Stated on every run, because its silent absence is the bad case.

        The local deny-list is the documented backstop for what P1 deliberately
        does not catch, and it used to be read from whatever directory the
        operator happened to be standing in -- so running from elsewhere
        dropped the property without saying anything.
        """
        if not self.denylist:
            return "no local deny-list"
        return f"deny-list in force ({len(self.denylist)} entries)"


def resolve_scan(paths: Sequence[Path], revision_range: str | None) -> Scan:
    """Decide what will be scanned and describe it, in one place.

    **A downgrade from the index to the working tree is never silent and never
    automatic.** Repository mode reads what is staged, which is what the next
    commit publishes; the walk reads what is on disk. They answer different
    questions, and anything that quietly swaps one for the other reports clean
    over content that is about to be committed.

    Not-a-repository is the only condition that may take the walk.
    """
    roots = {find_work_tree_root(path) for path in paths}

    if len(roots) > 1:
        # More than one distinct answer necessarily includes a repository -- a
        # set holds at most one None -- so this is either two work trees or one
        # work tree beside something outside it. Both used to resolve to "no
        # root" and put every target on the walk, so each index went unread
        # while a run naming either target alone would have read it.
        # targets in two different work trees, or one inside a work tree
        # beside one outside. Both used to resolve to "no root" and put every
        # target on the walk, so each index went unread while a run that named
        # either target alone would have read it.
        #
        # REFUSED rather than scanned per repository. That is the conservative
        # default and it matches the precedent already set for a named path Git
        # does not track. Scanning each index separately is more useful, and it
        # is more surface: the resolved scan is deliberately ONE value carrying
        # one enumeration and one set of words, and several of them would mean
        # several coverage claims to keep true -- which is the machinery four
        # rounds of scope defects came out of.
        raise ValueError(
            "the given targets do not share one Git working tree. Scanning tracked "
            "content means scanning one repository's index, and walking the filesystem "
            "instead would read working trees rather than indexes -- a different "
            "question. Scan them one repository at a time."
        )

    root = roots.pop() if roots else None

    if root is None:
        bases = tuple(paths)
        return Scan(
            root=None,
            bases=bases,
            denylist=tuple(_denylist_for(bases)),
            tracked=sum(1 for _ in iter_files(bases)),
            submodules=0,
            commits=None,
            range_entries=None,
            range_deletions=None,
            widened=False,
        )

    _refuse_targets_outside_the_scope(root, paths)

    commits = None
    range_entries = None
    range_deletions = None
    if revision_range is not None:
        commits = count_range_commits(root, revision_range)
        # Count what is SCANNED, not what exists. Counting commits while
        # scanning file entries is how a clean report was issued over an empty
        # commit whose message nobody looked at.
        #
        # ⚠️ Both counts come from ONE traversal. Each one spawns a git process
        # per commit, so a second walk over a full-history range -- what a new
        # branch's first push presents -- costs real seconds.
        range_entries, range_deletions = count_range_introductions_and_deletions(
            root, revision_range
        )

    entries = list(iter_tracked_entries(root))
    return Scan(
        root=root,
        bases=(root,),
        denylist=tuple(load_denylist(root)),
        tracked=len(entries),
        submodules=sum(1 for mode, _, _ in entries if mode == _GITLINK_MODE),
        commits=commits,
        range_entries=range_entries,
        range_deletions=range_deletions,
        widened=any(not same_path(path, root) for path in paths),
    )


def _refuse_targets_outside_the_scope(root: Path, paths: Sequence[Path]) -> None:
    """A named path is scanned, or the run is refused. Never neither.

    Widening a path inside a work tree to the whole repository created a way
    for the named path to be excluded from the very scope it caused: a scan of
    tracked content does not include a file Git has never seen. A new draft was
    reported clean by the repository half while nothing had looked at it, and
    the same bytes outside a repository are a finding. That is a clean report
    over content nobody read, which is the failure the whole coverage
    apparatus exists to prevent.

    Naming the work-tree root is exempt: that names the repository, which is
    the scope by definition, and a repository whose tip tracks nothing is still
    a legitimate target for a range scan.
    """
    for path in paths:
        if same_path(path, root):
            continue
        # LEXICALLY absolute, never resolved. Resolving follows the link, so
        # Git was asked about the destination rather than about the entry: an
        # untracked link pointing at a tracked file was accepted, and the
        # repository scan then never enumerated the link at all. A name is
        # judged before it is resolved.
        listing = _run_git(root, "ls-files", "-z", "--", str(lexical_path(path)))
        if listing.strip(b"\0"):
            continue
        if _is_denylist_path(path.name):
            # The one path where "stage it" is precisely the wrong advice: a
            # deny-list holds the personal literals this guard exists to keep
            # out of the repository, and staging one draws a DENYLIST finding.
            raise ValueError(
                "the local deny-list is never scanned -- its literals would match themselves -- "
                "and it must never be committed either. There is nothing to scan here."
            )
        raise ValueError(
            "Git does not track the given path. Scanning a repository means scanning "
            "tracked content, so the path that caused the scan would be the one thing "
            "left out of it. Stage it, or scan it outside a working tree."
        )


def _denylist_for(bases: Sequence[Path]) -> list[str]:
    """Every target's own deny-list, combined.

    A deny-list travels with the target, not with the shell -- and not with the
    *first* target either. Loading only the first one and applying it to all of
    them meant adding a second target silently switched off that target's
    protection: two directories scanned together missed a literal that either
    scanned alone would catch. A fail-open, in the one property that holds real
    names.

    **Combined rather than applied per target**, which is the conservative
    reading: more findings, never fewer. It means a name listed beside one
    target is looked for in all of them, so scanning two directories together
    can report a name in the one whose list does not mention it. That is the
    right way round -- a name is personal or it is not, and asking about two
    places at once is one question, not two. The narrower reading needs the
    deny-list to travel per file through the classifier, which is machinery the
    consolidation just removed.
    """
    directories: list[Path] = []
    for base in bases or (Path(),):
        directory = base if names_a_real_directory(base) else base.parent
        lexical = Path(os.path.abspath(directory))
        if not any(same_path(lexical, seen) for seen in directories):
            directories.append(lexical)
    combined: list[str] = []
    for directory in directories:
        for entry in load_denylist(directory):
            if entry not in combined:
                combined.append(entry)
    return combined


def show_matches_by_default(stream: object, environment: Mapping[str, str]) -> bool:
    """Whether matched values may be printed to ``stream``.

    Only for a human at an interactive terminal, where the value is already on
    their disk and hiding it just stops them fixing it. A pipe, a redirect and
    anything under CI are all treated as publication.
    """
    if environment.get("CI"):
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


def main(argv: Sequence[str] | None = None) -> int:
    """Scan the given paths; return non-zero if anything must not be published.

    Inside a Git working tree this is the repository gate: tracked content,
    plus every blob introduced by ``--range`` if one is given. Outside one --
    and ONLY outside one -- it walks the filesystem instead.

    The two are not interchangeable and neither is a fallback for the other:
    one reads the index, which is what a commit publishes, and the other reads
    the working tree. Every condition that used to slide from the first to the
    second now refuses instead.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)

    revision_range: str | None = None
    show_matches: bool | None = None
    targets: list[str] = []

    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--range":
            index += 1
            if index >= len(arguments):
                print("--range needs a revision range, for example before..after")
                return 2
            revision_range = arguments[index]
        elif argument.startswith("--range="):
            revision_range = argument.partition("=")[2]
        elif argument == "--show-matches":
            show_matches = True if show_matches is None else show_matches
        elif argument == "--redact":
            show_matches = False
        else:
            targets.append(argument)
        index += 1

    paths = [Path(target) for target in targets] or [Path()]
    if show_matches is None:
        show_matches = show_matches_by_default(sys.stdout, os.environ)

    # DO NOT "simplify" this into swallowing the error. Handling the exception
    # without refusing turns a crash into "0 findings, exit 0" -- a clean
    # report over a target nobody looked at. That fail-open is the failure this
    # guard keeps relapsing into, and it is the reason this check exists.
    try:
        unreadable = [path for path in paths if not path.exists()]
    except OSError as error:
        print(f"scan aborted: the given target cannot be read ({type(error).__name__}).")
        return 2
    if unreadable:
        print(
            "scan aborted: a given target does not exist. Scanning nothing is never a pass -- "
            "check the path and run again."
        )
        return 2

    try:
        scan = resolve_scan(paths, revision_range)
    except ValueError as error:
        print(f"scan aborted: {error}")
        return 2

    if scan.widened:
        # Surprising-but-safe only stays safe while it is impossible to miss.
        print(
            "note: the given path is inside a Git working tree, so the whole repository "
            "was scanned -- tracked content is a claim about a repository, not about a "
            "directory."
        )

    if not scan.is_repository and revision_range is not None:
        print("--range needs a Git working tree; the given path is not one")
        return 2

    # Scanning nothing is never a pass, and it is ONE rule asserted against the
    # set this run actually claims -- not a fourth per-mode check. The count
    # and the words for it come from the same value, so they cannot disagree.
    # ⛔ **Judged BEFORE the covers-nothing abort, and the order is the fix.**
    # A deletion that removes the last tracked file leaves ``tracked`` at zero
    # and ``range_entries`` at zero, so ``covered`` is zero -- and the range
    # would be refused precisely when it empties the tree. Nothing is published
    # either way: the tip holds no tracked content and the range introduces no
    # blob. The abort below exists to catch a target pointed at the wrong path,
    # and a resolved range that removed something is not that.
    deletion_only = scan.range_entries == 0 and bool(scan.range_deletions)

    if scan.covered == 0 and not deletion_only:
        print(
            "scan aborted: this run would cover nothing, so a clean report would mean "
            f"nothing. It found {scan.description}. Check the path -- and note that a "
            "deny-list and the tooling directories are never scanned, so a target holding "
            "only those covers nothing."
        )
        return 2
    if scan.commits == 0:
        print(
            "scan aborted: the given range covers no commits. A range covering "
            "nothing is never a pass -- resolve the range or scan the tip."
        )
        return 2
    if scan.range_entries == 0 and not deletion_only and scan.range_deletions is not None:
        # ⛔ **Nothing introduced AND nothing removed**, so these commits change
        # no file at all. What they do carry is messages, which are not scanned
        # -- so a clean verdict here would claim coverage of the only content
        # they hold. A deletion-only range is the other zero and is a pass; see
        # ``count_range_deletions`` for why the two must not share a check.
        print(
            f"scan aborted: the given range covers {scan.commits} commit(s) that change no "
            "file at all. Commit messages are not scanned yet, so reporting clean here "
            "would claim coverage of the only thing these commits carry."
        )
        return 2
    try:
        if scan.is_repository:
            findings = scan_repository(
                scan.root, revision_range=revision_range, denylist=list(scan.denylist)
            )
        else:
            findings = scan_paths(scan.bases, denylist=list(scan.denylist))
    except ValueError as error:
        # Fail closed and loudly. A range that cannot be resolved must never
        # be reported as "nothing found".
        print(f"scan aborted: {error}")
        return 2

    for finding in findings:
        print(finding.render(redact=not show_matches))

    # The scan target is not printed at all. It was printed on every run --
    # clean ones included, --redact ignored -- and it is an absolute path on
    # somebody's machine. Naming it adds nothing: the operator just typed it.
    # Not printing it is a property; printing it carefully is a call site.
    print(f"{len(findings)} finding(s) over {scan.description}")

    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
