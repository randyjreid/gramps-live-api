"""3.10 source, 3.14 runtime -- the gap R8's probe opened and nothing else measures.

The AIO ships **Python 3.14.4**. This repository targets ``py310`` and CI runs
3.10, 3.11 and 3.12. So the host is linted, typed and tested against a floor it
never executes on, and executes on an interpreter no gate here can run. Both ends
are compulsory and the gap between them is untested by construction.

⭐ **This is the half a gate can hold: nothing newer than the floor is WRITTEN.**
``ast.parse(..., feature_version=(3, 10))`` is the compiler's own answer to
"would 3.10 have parsed this", so it does not approximate and it does not
enumerate. ``match`` is 3.10 and passes; ``except*``, ``type X = …`` and PEP 695
parameter lists do not.

⚠️ **Its bound, stated rather than implied: this is SYNTAX and nothing else.** A
3.11-only standard-library call parses perfectly on 3.10 and this test says
nothing about it. For the package half ``mypy`` at ``python_version = "3.10"``
covers that; ``gramps_plugin/`` is outside ``mypy src`` and is covered by nothing
but its own deliberate restraint -- which is why that file uses only stdlib that
predates the floor by years.

⚠️ **And it says nothing at all about 3.14**, which is the direction that can
actually break the owner's machine: a behaviour that moved between 3.12 and 3.14
is a defect no gate in this repository can see.
"""

from __future__ import annotations

import ast

import pytest

from tests.fixtures.host_sources import host_sources

FLOOR = (3, 10)

NEWER_THAN_THE_FLOOR = {
    "3.11 exception groups": "try:\n    pass\nexcept* ValueError:\n    pass\n",
    "3.12 type statement": "type Handle = str\n",
    # ⚠️ The type variable is spelled ``Item`` rather than ``T`` because ``T:``
    # followed by a newline is a drive-letter absolute path to the PII guard, and
    # this file would report itself. A single capital letter before a colon is
    # exactly the shape P1 watches for.
    "3.12 type parameter list": (
        "def first[Item](values: list[Item]) -> Item:\n    return values[0]\n"
    ),
}


def test_every_host_source_would_have_parsed_on_the_floor() -> None:
    """The gate. One check per file, and the file set is a rule rather than a list."""
    sources = host_sources()
    assert sources, "no host source files were found at all -- this test watches nothing"

    too_new = []
    for path in sources:
        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
                feature_version=FLOOR,
            )
        except SyntaxError as failure:
            too_new.append(f"{path.name}:{failure.lineno} {failure.msg}")

    assert too_new == [], (
        "these files use syntax the 3.10 floor does not have, so the gates here "
        f"will not run them and neither will anything else: {too_new}"
    )


@pytest.mark.parametrize("label", sorted(NEWER_THAN_THE_FLOOR))
def test_the_floor_check_actually_rejects_something(label: str) -> None:
    """The control, because a checker that accepts everything passes the gate above.

    Three constructions, one from 3.11 and two from 3.12. If a future interpreter
    stops honouring ``feature_version``, this goes red and the gate above is known
    to have become decorative -- rather than staying green and proving nothing.
    """
    with pytest.raises(SyntaxError):
        ast.parse(NEWER_THAN_THE_FLOOR[label], feature_version=FLOOR)
