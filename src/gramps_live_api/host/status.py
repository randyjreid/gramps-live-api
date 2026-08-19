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
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TreeStatus:
    """Whether a tree is open, and if so which one and how big."""

    open: bool
    name: str | None = None
    people: int | None = None
