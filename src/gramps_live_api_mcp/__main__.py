"""``python -m gramps_live_api_mcp`` -- the stdio server an agent host launches.

Registered with an **absolute interpreter path**, deliberately -- the venv's
own ``python.exe`` in this checkout, named in full. ``docs/slice2-mcp.md`` gives
the command that composes it.

⚠️ **Not a fix for #60, a sidestep of it.** On this machine ``python`` is the
Microsoft Store shim, so a registration that says ``python`` launches something
that is not this checkout's interpreter and reports a missing module. Naming the
interpreter avoids the question; the issue stays open, because the next person
to write ``python`` in a setup instruction meets it again.
"""

from gramps_live_api_mcp.server import serve

# ⚠️ **Guarded, and not as a formality.** ``python -m pkg`` runs this file with
# ``__name__ == "__main__"``, so the guard costs nothing there -- and without it
# merely IMPORTING this module starts a server reading real stdin, which is what
# a test that wanted to look at it did.
if __name__ == "__main__":
    serve()
