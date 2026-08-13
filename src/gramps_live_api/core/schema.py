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


@dataclass(frozen=True, slots=True)
class Operation:
    """Base for every operation type. Carries no fields of its own."""


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


def _register(type_name: str) -> Callable[[type[Operation]], type[Operation]]:
    """Add one operation type to the registry. Module-private, deliberately."""

    def decorate(cls: type[Operation]) -> type[Operation]:
        if type_name in _REGISTRY:
            raise ValueError(f"{type_name} is registered twice")
        _REGISTRY[type_name] = OperationSpec(type_name=type_name, cls=cls)
        return cls

    return decorate
