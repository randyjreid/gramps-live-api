"""Registration for the CLI tool Gramps runs on our behalf.

⚠️ **This directory is OUTSIDE ``src/`` and outside the package, and that is the
whole point.** ``CONTRIBUTING.md`` records it as the second exception to
"nothing imports ``gramps`` or ``gi``": the rule exists so the core tests
without Gramps, and a plugin directory that Gramps loads and the package never
imports honours that exactly. Nothing under ``src/`` imports anything here.

Gramps ``exec``s a ``.gpr.py`` with ``register``, ``TOOL`` and the status
constants already injected as globals (``gen/plug/_pluginreg.py``). They are
imported explicitly anyway, so this file reads as ordinary Python and a linter
is not asked to believe in names from nowhere.

Installed once, by hand, as a directory junction into Gramps' user plugin
folder. See ``docs/using.md``.
"""

from gramps.gen.plug._pluginreg import (
    STABLE,
    TOOL,
    TOOL_MODE_CLI,
    TOOL_UTILS,
    register,
)
from gramps.version import VERSION_TUPLE

# ⚠️ DERIVED rather than pinned to a literal, and the trade is deliberate. A
# hardcoded "6.0" stops matching the day Gramps updates, and the plugin then
# silently stops being registered -- the owner sees "Unknown tool name" while
# `check` still reports the plugin as installed, which is the most confusing
# pair of answers available. Deriving keeps those two in agreement. What it
# gives up is a version wall, and the wall was never what protects the tree:
# the sentinel, the undo record and the read-back are.
MODULE_VERSION = f"{VERSION_TUPLE[0]}.{VERSION_TUPLE[1]}"

register(
    TOOL,
    id="gramps_live_api_apply",
    name="gramps-live-api: apply one agreed operation",
    description=(
        "Writes a single validated, previewed and human-approved operation into "
        "a family tree that has been blessed for writing by hand. Command line "
        "only; it has no interface and does nothing without its environment set."
    ),
    version="0.0.0",
    gramps_target_version=MODULE_VERSION,
    status=STABLE,
    fname="gramps_live_api_apply.py",
    authors=["randyjreid"],
    authors_email=[],
    category=TOOL_UTILS,
    toolclass="ApplyTool",
    optionclass="ApplyToolOptions",
    # ⚠️ CLI ONLY. A GUI entry would put a write with no preview and no prompt
    # into Gramps' Tools menu, one click from the live tree -- the sentinel
    # would still refuse it, and offering it at all is not the shape of this.
    tool_modes=[TOOL_MODE_CLI],
)
