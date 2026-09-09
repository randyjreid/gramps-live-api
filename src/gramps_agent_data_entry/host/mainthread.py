"""The one way across the thread boundary, and the guard that says which side you are on.

R8's load-bearing invariant is that no Gramps database object and no GTK object
is ever touched from the HTTP thread. Two mechanisms carry it, and they are
deliberately separate:

``on_main_thread``
    a decorator that **refuses** rather than a convention that asks. Anything
    wearing it raises ``WrongThread`` when it is called from anywhere but the
    interpreter's main thread -- which, inside Gramps, is the thread running the
    GTK loop.

``Marshal``
    the way to get work onto that thread from the HTTP thread: schedule it, wait
    for it, and **give up rather than hang**.

⚠️ **The refusal is the point, not the crossing.** A helper that merely gets
called on the right thread today is a helper that gets called on the wrong one
after the next refactor, and the failure would be ``sqlite3.ProgrammingError``
from inside a request handler -- if it failed at all. Gramps' connection is made
with a bare ``sqlite3.connect()``, so cross-thread use raises; but ``emit()``
dispatching handlers in the emitting thread has no such backstop, and a GTK
object touched off-thread is undefined rather than loud.

⚠️ **``schedule`` is a parameter and not an import.** Inside Gramps it is
``GLib.idle_add``; here it is whatever the caller passes, which is what lets the
crossing be tested on a runner with no ``gi`` at all. The contract is exactly
GLib's: the callable is invoked on the main loop, and a return of ``False``
means "do not run me again".
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import Any, TypeVar

Result = TypeVar("Result")

DEFAULT_TIMEOUT_SECONDS = 5.0
"""How long the HTTP side waits for the GTK loop before answering 503.

R8's accepted risk 4: long work inside ``idle_add`` blocks the GTK loop, so the
HTTP side gets a hard timeout rather than hanging. Five seconds is long enough
to cross a busy loop and short enough that a client learns something is wrong
while the owner is still looking at the screen. It is not tuned -- there is no
use-derived trigger to tune it against, and R8's own unmeasured falsifier is
whether a single read round trip exceeds ~2 s.
"""


class WrongThread(RuntimeError):
    """A database helper was called from somewhere that is not the main thread."""


class MainThreadTimeout(RuntimeError):
    """The main thread did not run the scheduled work in time."""


def on_main_thread(helper: Callable[..., Result]) -> Callable[..., Result]:
    """Refuse this call unless it is happening on the main thread.

    The check runs **before the arguments are looked at**, so a caller on the
    wrong thread gets the same answer whatever it passed -- and so the
    boundary test can call every helper with placeholder arguments and still be
    exercising the guard rather than the body.
    """

    @functools.wraps(helper)
    def guarded(*arguments: Any, **keywords: Any) -> Result:
        if threading.current_thread() is not threading.main_thread():
            raise WrongThread(
                f"{helper.__name__} touches the Gramps database and was called from "
                f"{threading.current_thread().name!r}; cross this boundary with "
                "Marshal.call instead"
            )
        return helper(*arguments, **keywords)

    return guarded


class Marshal:
    """Run work on the main thread from another one, or give up saying so.

    ⚠️ **Work per callback is capped by what is scheduled, not by a limit here.**
    One call schedules one callable which runs once and returns ``False``; there
    is no loop, no batch and no retry. Keeping the callable itself cheap is the
    caller's job, and in this slice the only thing ever scheduled is a status
    read of two O(1) values.

    ⚠️ **A timeout abandons the work; it does not cancel it.** GLib has already
    been handed the callable and will run it whenever the loop next drains. That
    is deliberate -- reaching into the loop to withdraw a source is more GTK
    surface than a 503 is worth -- and it is why the scheduled callable writes
    only into a box nobody reads once the wait has expired.
    """

    def __init__(
        self,
        *,
        schedule: Callable[[Callable[[], bool]], Any],
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._schedule = schedule
        self._timeout = timeout

    def call(self, work: Callable[[], Result]) -> Result:
        """Run ``work`` on the main thread and return what it returned.

        Raises ``MainThreadTimeout`` if the loop did not get to it in time, and
        re-raises whatever ``work`` itself raised.
        """
        finished = threading.Event()
        box: dict[str, Any] = {}

        def run_on_the_main_thread() -> bool:
            try:
                box["value"] = work()
            except BaseException as failure:  # noqa: BLE001 -- carried to the caller
                box["failure"] = failure
            finally:
                finished.set()
            # GLib removes an idle source whose callback returns False. Returning
            # None would too, by accident; returning False says so.
            return False

        self._schedule(run_on_the_main_thread)

        if not finished.wait(self._timeout):
            raise MainThreadTimeout(
                f"the Gramps main thread did not run the scheduled read within "
                f"{self._timeout} seconds"
            )

        if "failure" in box:
            raise box["failure"]
        return box["value"]  # type: ignore[no-any-return]
