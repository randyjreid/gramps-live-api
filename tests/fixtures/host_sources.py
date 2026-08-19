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

import ast
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


def registered_filename(path: Path) -> str | None:
    """The ``fname=`` a ``.gpr.py`` registers, or ``None`` if it registers nothing.

    Read from the ``register`` call rather than matched as text, so a filename
    mentioned in the prose above it is not mistaken for the one being declared.
    """
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "fname" and isinstance(keyword.value, ast.Constant):
                registered = keyword.value.value
                return registered if isinstance(registered, str) else None
    return None


def plugin_sources() -> list[Path]:
    """Every plugin file that is part of the host, by a rule rather than a spelling.

    Two ways to qualify, and the second exists because a registration carries no
    imports of its own:

    - the file reaches into the host package;
    - the file is a ``.gpr.py`` whose ``fname`` names a file that does.

    ⚠️ **Neither is a naming convention.** ``gramps_plugin/`` also holds the
    spawned-CLI write path, which is not host code and which R8 retires in a
    later slice; picking files by what they are called would either sweep that in
    or miss the next host file. Gramps ``exec``s a ``.gpr.py``, so it is
    executable source on the same footing as anything else here.
    """
    candidates = [
        path for path in PLUGIN_DIRECTORY.rglob("*.py") if "__pycache__" not in path.parts
    ]
    reaching = {path for path in candidates if HOST_IMPORT in path.read_text(encoding="utf-8")}
    names = {path.name for path in reaching}

    registrations = {
        path
        for path in candidates
        if path.name.endswith(".gpr.py") and registered_filename(path) in names
    }

    return sorted(reaching | registrations)


def host_sources() -> list[Path]:
    """Everything the host consists of, on both sides of the Gramps boundary."""
    return package_sources() + plugin_sources()
