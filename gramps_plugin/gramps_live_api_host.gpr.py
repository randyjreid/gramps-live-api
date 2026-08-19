"""Registration for the host Gramps starts on our behalf.

⚠️ **This directory is OUTSIDE ``src/`` and outside the package, and that is the
whole point.** ``CONTRIBUTING.md`` records it as the exception to "nothing
imports ``gramps`` or ``gi``": the rule exists so the core tests without Gramps,
and a plugin directory that Gramps loads and the package never imports honours
that exactly.

⭐ **``GENERAL`` with ``load_on_reg``, and R8 says why the alternatives are not
viable.** ``CLIManager.do_reg_plugins()`` passes ``load_on_reg=True`` only for
``USER_PLUGINS``, so third-party addons are exactly what the hook is for, and it
fires **unconditionally at startup with no tree open**. A gramplet is not viable
-- ``GrampletPane`` builds gramplets only when its page is built, and
``ViewManager.goto_page()`` builds pages lazily. A tool is not viable -- it needs
a menu click every session.

⚠️ **A ``.gpr.py`` body is ``exec``'d unsandboxed on every launch.** R8's accepted
risk 3: that is Gramps' model rather than ours, and it is why the plugin
directory stays a hand-created junction rather than a copied folder.

Installed once, by hand, as a directory junction into Gramps' user plugin
folder. See ``docs/slice-a-demo.md``.
"""

from gramps.gen.plug._pluginreg import (
    GENERAL,
    STABLE,
    register,
)
from gramps.version import VERSION_TUPLE

# ⚠️ DERIVED rather than pinned to a literal, for the reason the apply plugin's
# registration records at length: a hardcoded version stops matching the day
# Gramps updates, and the plugin then silently stops being registered.
MODULE_VERSION = f"{VERSION_TUPLE[0]}.{VERSION_TUPLE[1]}"

register(
    GENERAL,
    id="gramps_live_api_host",
    name="gramps-live-api: loopback host",
    description=(
        "Answers a loopback HTTP request about the tree that is currently open, "
        "on 127.0.0.1 only, with a bearer token generated at startup. Read only: "
        "it reports the open tree's name and how many people it holds, and "
        "nothing else."
    ),
    version="0.0.0",
    gramps_target_version=MODULE_VERSION,
    status=STABLE,
    fname="gramps_live_api_host.py",
    authors=["randyjreid"],
    authors_email=[],
    # ⭐ The whole reason this is a GENERAL plugin. Gramps loads the module at
    # registration and calls its ``load_on_reg(dbstate, uistate, plugin)``.
    load_on_reg=True,
)
