"""The in-process host R8 rules: a loopback HTTP listener inside Gramps.

⚠️ **Nothing in this package imports ``gramps`` or ``gi``, and that is what makes
it testable.** The plugin under ``gramps_plugin/`` -- the only place those
imports are permitted -- hands this package two things Gramps owns: the
``dbstate`` it must read through, and ``GLib.idle_add`` as the way onto the main
thread. Both arrive as arguments. So the whole host, including the thread
boundary the design rests on, runs under ordinary unit tests on a machine that
has never seen Gramps.

**What that buys and what it does not.** CI proves the marshalling, the auth
check, the route and the wire shape. It cannot prove that ``GLib.idle_add``
drains while a Gramps modal dialog holds a nested main loop, and it cannot prove
that Gramps' own ``dbstate`` answers the way the fake one here does. Those are
the owner's machine, and R8 lists two of them as open falsifiers.
"""
