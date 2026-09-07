"""``python -m gramps_agent_data_entry``. Everything it does is in ``cli``.

Kept to one line so the command the owner types and the code the tests exercise
are the same thing: ``cli.main`` takes its streams, its environment and its
runner as arguments, and this is where the real ones are supplied.
"""

from __future__ import annotations

import sys

from gramps_agent_data_entry.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
