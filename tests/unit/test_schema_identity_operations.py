"""The identity-side operations: person, place, name, and the family links.

Everything generic is inherited. ``test_schema_registry``, ``test_schema_validation``,
``test_schema_rule_table``, ``test_schema_preview``, ``test_schema_preview_guard``,
``test_schema_serialisation`` and ``test_schema_violation_privacy`` all quantify over
the registry, so widening it covers the new types in those files **without any of them
being edited**. That is the criterion, not a happy accident: a test that must be
modified to admit a new type was restated rather than derived.

So this file holds only what is about *these* operations -- the properties the
generated sweeps cannot state, each named for the criterion it carries.
"""

from __future__ import annotations

from collections.abc import Mapping

from gramps_live_api.core import schema

_SIDES = ("FACT_ASSERTING", "NON_FACT")


def _table(side: str) -> object:
    return getattr(schema, side)


def _recorded_rationales() -> dict[str, str]:
    """Every classified type, and the rationale its own side records for it.

    A side that records no rationale at all contributes an empty one rather than
    raising, so the failure below names the types and says what is missing
    instead of dying on a ``TypeError`` from subscripting a set.
    """
    recorded: dict[str, str] = {}
    for side in _SIDES:
        table = _table(side)
        for type_name in table:  # type: ignore[attr-defined]
            recorded[type_name] = table[type_name] if isinstance(table, Mapping) else ""
    return recorded


def test_both_sides_of_the_partition_record_a_rationale_per_type() -> None:
    # The partition proves TOTALITY, not correctness -- a fact-asserting
    # operation can be filed on the exempt side and nothing structural will say
    # so. The recorded rationale is the only thing a reviewer can check a
    # misclassification against, and that argument does not stop at the exempt
    # side: "this asserts a fact" is exactly as losable as "this does not".
    wrong = [side for side in _SIDES if not isinstance(_table(side), Mapping)]

    assert wrong == [], (
        "each side of the provenance partition must map a type name to the "
        "one-line reason it is on that side, because the classification is "
        "recorded PER TYPE and a bare set of names records no reason at all; "
        f"got {wrong} carrying names only"
    )


def test_every_registered_type_records_why_it_is_classified_as_it_is() -> None:
    recorded = _recorded_rationales()
    missing = sorted(
        type_name for type_name in schema.REGISTRY if not recorded.get(type_name, "").strip()
    )

    assert missing == [], (
        "every registered type records a one-line rationale for its "
        "classification. TO FIX: give each of these an entry on the side it is "
        f"classified on, saying why it belongs there: {missing}"
    )
