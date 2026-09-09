"""The only place a failed startup can be seen, and the only reason this file exists.

R8's accepted risk 2: ``load_on_reg`` catches whatever the hook raises, prints a
traceback and lets startup continue -- and the Windows all-in-one build has no
console for that traceback to land in. So a host that fails to start does so
**invisibly**: Gramps opens normally, the socket is not there, and nothing
anywhere says why.

⭐ **What a client can tell apart, which is the requirement rather than the
mechanism.** It reads the ``port`` file and tries the socket; if that does not
answer, the LAST LINE of this file says which of three things happened:

``ERROR``
    the host **errored** -- the line says how, and it is the case that is
    otherwise completely invisible.
``INFO listening``
    the host started, and is not there now: Gramps has been closed since.
no log file at all
    the host **never ran**. The plugin is not installed, or Gramps never reached
    the hook.

⚠️ **The last line, not the port file, is what answers this.** The port file is
removed before every startup and written only after a successful bind, which
makes its presence meaningful while the host is alive -- but Gramps exiting takes
the daemon thread without running anything, so a port file outlives a host that
closed normally. A client that read "port file exists" as "running" would report
a closed Gramps as a broken host. Try the socket; believe the log.

⚠️ **Writing the log must never be what fails the startup.** A record that cannot
be written returns ``False`` and the host carries on; the alternative is a
logging fault taking down the thing the log exists to report on.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

INFO = "INFO"
ERROR = "ERROR"


def record(path: Path, level: str, message: str) -> bool:
    """Append one line. Returns whether it was written.

    ``datetime.now()`` rather than ``utcnow()``: the second is deprecated from
    3.12 and this file is read by a person looking at their own machine's clock,
    for whom local time is the right answer.
    """
    line = f"{datetime.now().isoformat(timespec='seconds')} {level} {message}\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        return False
    return True
