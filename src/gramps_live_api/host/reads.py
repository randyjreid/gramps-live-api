"""The privacy bounds every live read carries, and the shape a read answers in.

⚠️ **This module exists because R3's precondition P2 was not met.** R3 is ruled,
and its only egress bound is what ``core/people.py`` implements -- the ``priv``
exclusion, the required search term and ``RESULT_CAP``. **Nothing in
``src/gramps_live_api/host/`` implemented any of them**, so a live read surface
built without this would ship R3's bound with nothing behind it.

⛔ **Three bounds, and they answer different questions.** Getting that wrong is
how one of them silently stops working:

1. **``priv`` people are excluded from listings and refused BY NAME when named
   directly.** ``core/people.py`` deliberately returns private people from its
   reader and filters above, *"because the two enforcement points ruling 1 sets
   are different questions"* -- a listing must not show them, and a target must
   be refused by name rather than reported absent, or the caller cannot tell *no
   such person* from *that person is private*.
2. **A search term is required.** There is no *list everybody*.
   ``SearchTermRequired`` is documented in the export reader as *"a privacy
   control rather than an ergonomic one"*.
3. **A result cap**, with the count of what was withheld -- ⚠️ **and a private
   person is in NEITHER the results nor the count.** Reporting *42 matched, 25
   shown* over a set that included people it will never show would leak the
   existence of the excluded ones by arithmetic. That is ruling 1's first
   enforcement point in its own words.

⚠️ **Nothing here imports ``gramps`` or ``gi``**, so all of it runs under CI.
The walking lives in the accessor; the bounding lives here.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

RESULT_CAP = 25
"""How many rows one read may return.

⚠️ **A cap rather than a page**, and the same number the export reader uses --
its own docstring says why: *"every name it returns enters a model's context"*.
``Found.matched`` says how many there were, so a caller that hits the cap is told
to narrow rather than left believing it saw everything.
"""


class ReadRefused(Exception):
    """This read is refused. Nothing was returned."""


class SearchTermRequired(ReadRefused):
    """A listing was asked for with no term to narrow it.

    ⚠️ **Deliberate, and a privacy control rather than an ergonomic one** -- the
    same wording ``core/people.py`` uses. *List everyone* would put the whole
    tree into a model's context in one call, which is a different act from
    looking somebody up.
    """


class TargetIsPrivate(ReadRefused):
    """The record carries Gramps' own ``priv`` flag, so it cannot be a target.

    ⚠️ **Refused BY NAME rather than reported absent**, which is ruling 1's own
    wording: silence would leave the caller unable to tell *no such person* from
    *that person is private*, and the difference is the whole point.
    """


@dataclass(frozen=True)
class Match:
    """One row of a read. ``gramps_id`` is what the graph needs."""

    gramps_id: str
    display: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Found:
    """What a read answers with.

    ⛔ **``matched`` counts only rows that could be shown.** Private records are
    excluded before counting, so the arithmetic cannot be run backwards to learn
    that they exist.
    """

    matches: tuple[Match, ...] = ()
    matched: int = 0

    @property
    def shown(self) -> int:
        return len(self.matches)

    @property
    def withheld(self) -> int:
        """How many non-private matches the cap held back."""
        return max(0, self.matched - len(self.matches))

    @property
    def capped(self) -> bool:
        return self.withheld > 0


def require_term(text: Any) -> str:
    """The search term, or refuse. ⛔ There is no *list everybody*."""
    term = str(text or "").strip()
    if not term:
        raise SearchTermRequired(
            "a search term is required -- there is no way to list everybody. "
            "This is a privacy control rather than an ergonomic one."
        )
    return term


def fold(text: Any) -> str:
    """A form for comparing names that differ only by accent or case.

    ⭐ **Unicode normalisation, not orthography.** ``NFKD`` then dropping
    combining marks makes ``Kunkele`` match ``Künkele``. ⚠️ **It does NOT make
    ``Kuenkele`` match ``Künkele``** -- that is a German transliteration rule,
    not a Unicode property, and inventing language-specific spelling rules here
    is how a search starts guessing. The alternate-name walk is what catches
    that case, because the tree records the ``ue`` spelling as an actual name.
    """
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def matches_term(term: str, *candidates: Any) -> bool:
    """Whether any candidate contains ``term``, compared on the folded form."""
    needle = fold(term)
    return any(needle in fold(candidate) for candidate in candidates if candidate)


def bound(rows: Iterable[tuple[bool, Match]], *, cap: int = RESULT_CAP) -> Found:
    """Apply all three bounds to ``(is_private, match)`` pairs.

    ⛔ **Private rows are dropped before anything is counted.** They are not in
    ``matches`` and not in ``matched``; there is no arithmetic that reveals them.
    """
    visible = [match for is_private, match in rows if not is_private]
    return Found(matches=tuple(visible[:cap]), matched=len(visible))
