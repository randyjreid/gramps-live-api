"""Registration for the throwaway dialog probe."""

from gramps.gen.plug._pluginreg import GENERAL, STABLE, register
from gramps.version import VERSION_TUPLE

MODULE_VERSION = f"{VERSION_TUPLE[0]}.{VERSION_TUPLE[1]}"

register(
    GENERAL,
    id="gramps_live_api_dialogprobe",
    name="gramps-live-api: dialog-from-idle_add probe (THROWAWAY)",
    description="Proves a modal dialog can be shown from inside a GLib.idle_add callback and that a write lands after it.",
    version="0.0.0",
    gramps_target_version=MODULE_VERSION,
    status=STABLE,
    fname="dialogprobe.py",
    authors=["randyjreid"],
    authors_email=[],
    load_on_reg=True,
)
