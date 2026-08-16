"""Where the copy is, and which Gramps to write it with. Never in the checkout.

⚠️ **The one value this project cannot commit is where the owner's tree
actually is**, so this loader resolves the **user configuration directory
only** -- never the current directory, never anything relative to the checkout.
A ``config.json`` committed by accident into a public repository must not
become working configuration, and a loader that reads beside the working
directory is exactly how it would.

JSON rather than TOML: ``tomllib`` is 3.11 and up, and this project's floor is
3.10.

Everything here takes ``environ`` and ``platform`` as arguments rather than
reading ``os.environ`` and ``sys.platform`` directly. That is not ceremony --
both layouts and both discovery behaviours are then exercised on whichever
platform is running, and a branch only its own operating system can reach is a
branch CI proves nothing about.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DIRECTORY_NAME = "gramps-live-api"
CONFIG_FILE = "config.json"

ENV_COPY = "GRAMPS_LIVE_API_COPY"
ENV_RUNTIME = "GRAMPS_LIVE_API_RUNTIME"

RUNTIME_NAME = "grampsd.exe"
"""The daemon launcher, and never ``gramps.exe``.

Measured: ``gramps.exe`` takes a named mutex and refuses to start while another
Gramps is open, which is precisely the state the demo is in. ``grampsd.exe``
runs the same application with no single-instance lock.
"""

_INSTALL_GLOB = "GrampsAIO64-*"
"""How the Windows all-in-one installer names its directory under Program Files."""

_KEYS = frozenset({"copy_path", "gramps_runtime"})


class ConfigError(Exception):
    """The configuration cannot be read, or does not say what it appears to."""


@dataclass(frozen=True, slots=True)
class Settings:
    """What the front end was told, with nothing inferred that was not asked for."""

    copy_path: str | None
    runtime: str | None


def user_config_path(environ: Mapping[str, str], *, platform: str = sys.platform) -> Path:
    """Where the configuration file lives, on this platform, for this user."""
    if platform == "win32":
        return Path(environ.get("APPDATA", "")) / DIRECTORY_NAME / CONFIG_FILE
    xdg = environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path(environ.get("HOME", "")) / ".config"
    return base / DIRECTORY_NAME / CONFIG_FILE


def load(environ: Mapping[str, str], *, platform: str = sys.platform) -> Settings:
    """The copy and the runtime, from the environment over the file.

    An absent file is no configuration rather than a failure; an unreadable one
    is a failure. The difference matters: nothing configured is an ordinary
    first run, while a file the owner edited and this cannot parse would
    otherwise run against a default while he believes his edit is in force.
    """
    filed = _from_file(user_config_path(environ, platform=platform))
    return Settings(
        copy_path=environ.get(ENV_COPY) or filed.get("copy_path"),
        runtime=environ.get(ENV_RUNTIME) or filed.get("gramps_runtime"),
    )


def discover_runtime(environ: Mapping[str, str], *, platform: str = sys.platform) -> str | None:
    """The installed Gramps runtime, when there is exactly one to find.

    ⚠️ **Two installations are REFUSED rather than chosen between.** A plain
    sort picks 6.0.9 over 6.0.11 -- "9" sorts after "1" -- and the repair is a
    version comparison, which this project would then own and get wrong on the
    first pre-release it met. Refusing costs the owner one line in a
    configuration file, once, and it is the only answer that cannot quietly
    write a tree with the wrong Gramps.

    Off Windows this says nothing at all: the all-in-one layout is a Windows
    fact, Gramps is installed a dozen other ways elsewhere, and a guess would be
    a guess. ``gramps_runtime`` answers it there.
    """
    if platform != "win32":
        return None
    program_files = environ.get("ProgramFiles")
    if not program_files:
        return None
    found = sorted(glob.glob(os.path.join(program_files, _INSTALL_GLOB, RUNTIME_NAME)))
    if len(found) > 1:
        raise ConfigError(
            f"{len(found)} Gramps runtimes are installed and this will not choose "
            f"between them -- name one under gramps_runtime in {CONFIG_FILE}, or set "
            f"{ENV_RUNTIME}"
        )
    return found[0] if found else None


def _from_file(path: Path) -> Mapping[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as failure:
        raise ConfigError(f"{path}: {failure}") from failure
    if not isinstance(payload, dict):
        raise ConfigError(f"{path}: a configuration file holds an object")

    unknown = sorted(set(payload) - _KEYS)
    if unknown:
        # The reading ``schema.from_dict`` takes of an unknown field, for the
        # same reason: a misspelled key silently dropped means the configuration
        # in force is not the one that was written, and nothing says so.
        raise ConfigError(
            f"{path}: {unknown} is not a setting -- known settings are {sorted(_KEYS)}"
        )
    mistyped = sorted(key for key, value in payload.items() if not isinstance(value, str))
    if mistyped:
        raise ConfigError(f"{path}: {mistyped} must be text")
    return payload
