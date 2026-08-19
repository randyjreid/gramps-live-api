"""Where the host's three files live: one directory, resolved one way.

⚠️ **Deliberately derived from ``config.user_config_path`` rather than spelled
again.** Two answers to "where does this project keep things" is how the front
end and the host end up looking in different directories on the same machine,
and the failure would be silent -- a client reading a ``port`` file that nothing
writes looks exactly like a host that is not running.

``config.py``'s rule about arguments applies here for its reason: ``environ`` and
``platform`` are passed in, so both layouts are exercised on whichever platform
is running.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from gramps_live_api import config

TOKEN_FILE = "token"
PORT_FILE = "port"
LOG_FILE = "host.log"


def state_directory(environ: Mapping[str, str], *, platform: str = sys.platform) -> Path:
    """The per-user directory this project already owns -- on Windows, under APPDATA."""
    return config.user_config_path(environ, platform=platform).parent


def token_path(directory: Path) -> Path:
    return directory / TOKEN_FILE


def port_path(directory: Path) -> Path:
    """Written only after a successful bind, so its presence means something."""
    return directory / PORT_FILE


def log_path(directory: Path) -> Path:
    return directory / LOG_FILE
