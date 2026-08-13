"""The operation model: the vocabulary an agreed genealogical fact is expressed in.

⚠️ **A validated operation is WELL-FORMED, NOT CORRECT.** Everything this module
can decide is shape: required fields, membership of a closed set, type
correctness, internal consistency, and the *syntax* of a reference. Whether the
thing a reference names exists, whether it is the right thing, whether it
duplicates something already in the tree -- none of that is decidable without a
database, and none of it is attempted here. Those rules are declared on the
``PHASE_3`` side of ``RULES`` so the boundary is a table rather than a promise,
and a test asserts that no rule on that side can fire from ``validate``.

The result type is named ``WellFormedResult`` and never ``Valid`` anything, so
the distinction is hard to misread at a call site.

The registry is **closed**: there is no public registration function and
``REGISTRY`` is a read-only mapping. A closed set is what makes the provenance
partition assertable at all -- an open one makes this module's most important
property unfalsifiable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar


@dataclass(frozen=True, slots=True)
class Operation:
    """Base for every operation type. Carries no fields of its own."""


_Registered = TypeVar("_Registered", bound=type[Operation])


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """What the registry knows about one operation type."""

    type_name: str
    cls: type[Operation]


_REGISTRY: dict[str, OperationSpec] = {}

REGISTRY: Mapping[str, OperationSpec] = MappingProxyType(_REGISTRY)
"""Every operation type there is, keyed by its wire name.

Read-only, and populated only by ``_register`` calls inside this module. That
is what "closed" means mechanically: not a comment claiming the set is fixed,
but no route by which anything outside this file can add to it.
"""


def _register(type_name: str) -> Callable[[_Registered], _Registered]:
    """Add one operation type to the registry. Module-private, deliberately.

    Generic in the class so the decorated name keeps its own type. Returning
    ``type[Operation]`` would erase every subclass to its base at every call
    site, which is a type checker being told to stop helping.
    """

    def decorate(cls: _Registered) -> _Registered:
        if type_name in _REGISTRY:
            raise ValueError(f"{type_name} is registered twice")
        _REGISTRY[type_name] = OperationSpec(type_name=type_name, cls=cls)
        return cls

    return decorate


# ---------------------------------------------------------------------------
# The provenance partition
#
# ⚠️ **The classification is declared HERE, not passed to _register, and that
# is the point rather than an oversight.** A mandatory argument at registration
# would make the partition true by construction -- and a test that cannot fail
# is not the criterion. The criterion says a type in neither, or in both,
# FAILS THE TEST, which requires the classification to be losable. D3's
# "forced classification at registration" is a mechanism for the hypothetical
# open set, in a later phase; it is not this one's shape.
#
# Do not "simplify" this into the decorator.
# ---------------------------------------------------------------------------

FACT_ASSERTING: frozenset[str] = frozenset({"add_citation"})
"""Operations that assert a genealogical fact, and so must carry provenance."""

NON_FACT: Mapping[str, str] = MappingProxyType(
    {
        "add_note": (
            "a note records what a researcher observed or intends; it asserts nothing "
            "about a person that evidence could support, so it carries no citation field"
        ),
    }
)
"""Operations exempt from the provenance rule, each with why it is exempt.

The partition proves **totality, not correctness**: nothing here stops a
fact-asserting operation being filed on this side. The recorded rationale is
what a reviewer checks that against, which is why an empty one fails.
"""


# ⚠️ ``_register`` goes OUTSIDE ``@dataclass``. With ``slots=True`` the
# dataclass decorator returns a NEW class object, so registering underneath it
# files the half-built one and every consumer walks a class nobody uses.
# Asserted by test.


@_register("add_citation")
@dataclass(frozen=True, slots=True)
class AddCitation(Operation):
    """Attach evidence that already exists to an object that already exists."""


@_register("add_note")
@dataclass(frozen=True, slots=True)
class AddNote(Operation):
    """A research note or a to-do, attached to any object."""
