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
import os
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from weakref import WeakKeyDictionary

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
    ("identity", ("surname",), ("name", "first", "ptitle", "pname"), ("fullText", "given")),
    (
        # Where somebody lives locates them as surely as what they are called.
        "address",
        ("street", "city", "county", "state", "postal", "country", "phone"),
        (),
        ("postalCode",),
    ),
    # A way to reach a person names them at least as directly as a home
    # directory does, which P1 already treats as identity.
    ("contact", ("url", "email"), (), ("emails",)),
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
        ),
        ("persons", "names", "nameForms", "relationships", "facts", "notes", "addresses"),
    ),
)

_CATEGORY_WEIGHT = {"identity": 2, "address": 2, "contact": 2, "prose": 4, "structure": 1}


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

# ---------------------------------------------------------------------------
# THE QUALIFIED-NAME ALTERNATION. ONE CONSTRUCTION SITE, FOUR PATTERNS.
#
# Namespaces in XML: a tag is an optional PREFIX, a colon, and the local name.
# The prefix is the DOCUMENT'S OWN ALIAS for a namespace, so two exports of one
# tree may spell the same element `<name>`, `<g:name>` or `<grampsxml:name>` and
# mean exactly the same thing by it. It therefore belongs inside the tag group,
# where a backreference can still close the element it opened, and nowhere at
# all in the category lookup, which asks what the element MEANS.
#
# ⚠️ **All four patterns that read an element name are built from this and
# nothing else**, because the four used to spell the alternation themselves and
# a prefix consequently meant four different things. The gap is LEXICAL, not
# semantic -- with a prefix declared the matcher saw no element in ANY category,
# including the four weighted correctly -- and it pointed both ways at once:
# filled elements, attributed elements and the database signature scored nothing
# (data out), while the drawing exemption stopped applying (a chart reported).
# One blindness, opposite directions, which is why one table fixes both and why
# each direction is measured on its own.
#
# A fifth site hand-rolling its own alternation is caught by test rather than by
# hoping -- see the test that asserts each compiled pattern contains this.
# ---------------------------------------------------------------------------

_XML_NAME_PREFIX = r"(?:[^\W\d][\w.\-]*:)?"
"""An optional namespace prefix: a name character that is not a digit, then name
characters, then the colon.

An approximation of the NCName production rather than a transcription of it, and
the DIRECTION of the approximation is what makes it acceptable: a prefix using a
character this misses is invisible to all four patterns today and stays exactly
as invisible, so the residual is left unchanged rather than created here. The
other direction is bounded by the class itself, which cannot match ``<``, ``>``,
``/``, ``=``, a quote or whitespace.
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
    ``date``, ``placeobj`` past ``place``. The trailing ``\b`` at each call site
    makes the engine backtrack into the longer alternative anyway today;
    ordering means the patterns do not DEPEND on that, which matters because
    this table is about to be derived from a published schema rather than
    written by hand. No behavioural test can see this until a colliding pair
    exists, so it is asserted structurally instead.
    """
    alternation = "|".join(sorted(names, key=lambda name: (-len(name), name)))
    return _XML_NAME_PREFIX + "(?:" + alternation + ")"


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
    r"<(" + _qualified(*_GRAMPS_ALL_ELEMENTS) + r")\b[^>]*>"
    r"((?:" + _NOT_ENDING_AN_ELEMENT + r"|[^<])+)</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
"""An element with content of its own: this is data rather than a mention.

Two groups: the tag and the content. The content alternative admits every
member of the table above, because none of them ends an element -- a CDATA
section is how XML carries prose containing markup, and a comment or a
processing instruction is something a person leaves in the middle of a note.
Reading any of them as markup meant the pattern could not reach its own closing
tag, so the element was not merely mis-scored, it was invisible.

The attributes used to be captured as a third group, for a short-prose
discriminator that read them. Nothing reads them now -- see ``_DRAWING`` -- and
a captured group nobody consumes is machinery pretending to be a rule.
"""

_GRAMPS_ATTRIBUTED_ELEMENT = re.compile(
    r"<(" + _qualified(*_GRAMPS_ALL_ELEMENTS) + r")\b[^>]*?\w+\s*=\s*[\"'][^>]*>", re.IGNORECASE
)
"""An element carrying a quoted attribute -- a handle or an id is export syntax,
not something a specification writes in passing."""

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


_DRAWING = re.compile(r"<svg\b[^>]*>.*?</svg\s*>", re.IGNORECASE | re.DOTALL)
"""A drawing, inside which a short text element is a label and not a note.

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
    """
    score = 0
    first: int | None = None
    filled: list[tuple[int, int]] = []
    drawings = [match.span() for match in _DRAWING.finditer(text)]

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
            score += _CATEGORY_WEIGHT[_GRAMPS_CATEGORY_OF[tag]]
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
        score += _CATEGORY_WEIGHT[_GRAMPS_CATEGORY_OF[_local_name(match.group(1))]]
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
        re.compile(
            _LINE_PREFIX + r"<" + _qualified("database") + r"\b[^>]*gramps",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
)

_XML_PROLOG = re.compile(r"\A\s*<\?xml\b")
# Assembled, not written. Once the namespace stopped requiring a prolog at the
# start of the file, a module holding it as a literal reported itself -- the
# same self-report the patterns above are composed from constants to avoid, and
# it appeared the moment the anchor came off.
_GRAMPS_XML_NAMESPACE = "gramps-project" + ".org" + _SEPARATOR + "xml"

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
SAFE_BASENAMES = frozenset({".gitignore", "LICENSE", "uv.lock"})

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
    commits = decode_path(_run_git(root, "rev-list", revision_range)).split()
    seen: set[tuple[str, str, str]] = set()

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
            if mode == _EMPTY_MODE or set(object_id) == {"0"}:
                continue
            entry = (mode, object_id, path_text)
            if entry in seen:
                continue
            seen.add(entry)
            yield entry


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
    if not is_symlink and suffix not in SAFE_EXTENSIONS and name not in SAFE_BASENAMES:
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
            widened=False,
        )

    _refuse_targets_outside_the_scope(root, paths)

    commits = None
    range_entries = None
    if revision_range is not None:
        commits = count_range_commits(root, revision_range)
        # Count what is SCANNED, not what exists. Counting commits while
        # scanning file entries is how a clean report was issued over an empty
        # commit whose message nobody looked at.
        range_entries = sum(1 for _ in iter_range_entries(root, revision_range))

    entries = list(iter_tracked_entries(root))
    return Scan(
        root=root,
        bases=(root,),
        denylist=tuple(load_denylist(root)),
        tracked=len(entries),
        submodules=sum(1 for mode, _, _ in entries if mode == _GITLINK_MODE),
        commits=commits,
        range_entries=range_entries,
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
    if scan.covered == 0:
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
    if scan.range_entries == 0:
        print(
            f"scan aborted: the given range covers {scan.commits} commit(s) but no file "
            "content. Commit messages are not scanned yet, so reporting clean here "
            "would claim coverage of something nobody looked at."
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
