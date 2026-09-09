"""What ``/health`` says about the tree, as data with no database behind it.

⚠️ **This type is separate from the accessor on purpose.** The accessor's rule
is that everything callable reachable on it is a database helper that refuses a
non-main thread, and a dataclass is callable. Keeping the type here means the
accessor holds nothing but its helpers, so
``tests/unit/test_host_thread_boundary.py`` can discover them by reading the
file rather than by being told which names to skip.

⛔ **Two fields, and no third without a ruling.** R3 -- the injection widening --
is still owed, so this slice touches no tree text: a tree's own name and a count
of people is the whole of what leaves the process. Adding a field here is adding
free text to a response, which is the thing R3 has not settled.

⭐ **A2 adds a SECOND type below, and it is inside that rule rather than an
exception to it.** ``PersonStatus`` answers *does this Gramps ID name a person,
and may I use them* with **two booleans and nothing else**. No name, no date, no
Gramps ID echoed back -- the caller supplied the key and gets back only what is
true of it. So the sentence above is untouched: a field carrying free text is
still a ruling nobody has made, and neither of these is one.

⚠️ **The type is here for the same reason ``TreeStatus`` is**, and the reason is
mechanical rather than stylistic: a dataclass is callable, and every callable
reachable on the accessor has to be a database helper that refuses a non-main
thread. Putting it in the accessor would make the boundary test's discovery
wrong, not merely untidy.

⚠️ **``private`` is ``None`` when nobody was found, and that is ruling 1's second
enforcement point rather than a nicety.** *No such person* and *that person is
private* are different answers and stay different on the wire; collapsing them is
exactly what ``TargetIsPrivate`` refuses one level down, because silence would
leave the caller unable to tell the two apart.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TreeStatus:
    """Whether a tree is open, and if so which one and how big."""

    open: bool
    name: str | None = None
    people: int | None = None


@dataclass(frozen=True)
class PersonStatus:
    """Whether a Gramps ID names somebody, and whether they are out of reach.

    ``private`` is ``None`` exactly when ``found`` is false -- there is no flag
    to report about a person who is not there, and reporting ``False`` would say
    something about somebody the tree does not hold.
    """

    found: bool
    private: bool | None = None
