"""Which files ARE the host, answered by a rule rather than by a list.

Two tests need the same answer -- the thread-boundary test, which asserts that
nothing outside the accessor reaches the database, and the language-floor test,
which asserts every one of these files parses on 3.10. A list in each of them
would be two lists, and the second file somebody adds would go into neither.

⚠️ **The plugin half is found by what it IMPORTS, not by what it is called.**
``gramps_plugin/`` also holds the spawned-CLI write path, which is not host code
and which R8 retires in a later slice; naming files by a spelling convention
would either sweep that in or miss the next host file. A plugin module that
reaches into ``gramps_live_api.host`` is host code by construction, whatever it
is named.
"""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

HOST_PACKAGE = REPOSITORY_ROOT / "src" / "gramps_live_api" / "host"
PLUGIN_DIRECTORY = REPOSITORY_ROOT / "gramps_plugin"

ACCESSOR = HOST_PACKAGE / "accessor.py"
"""The one module permitted to touch the database. Everything else is bound."""

HOST_IMPORT = "gramps_live_api.host"


def package_sources() -> list[Path]:
    """Every module of the host package, accessor included."""
    return sorted(path for path in HOST_PACKAGE.rglob("*.py") if "__pycache__" not in path.parts)


def plugin_sources() -> list[Path]:
    """Every plugin file that reaches into the host package.

    ``.gpr.py`` files are included when they qualify: Gramps ``exec``s them, so
    they are executable source on the same footing as anything else here.
    """
    return sorted(
        path
        for path in PLUGIN_DIRECTORY.rglob("*.py")
        if "__pycache__" not in path.parts and HOST_IMPORT in path.read_text(encoding="utf-8")
    )


def host_sources() -> list[Path]:
    """Everything the host consists of, on both sides of the Gramps boundary."""
    return package_sources() + plugin_sources()
