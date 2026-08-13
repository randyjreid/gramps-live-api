"""The operation registry is closed, and the provenance partition is total.

These tests are asserted **over the registry**, never against a hand-written
list of types. That is deliberate and it is the criterion: an enumeration fails
on the case nobody listed, so a tenth operation type must extend this file's
coverage without this file being edited.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema


def test_the_registry_cannot_be_added_to_from_outside() -> None:
    with pytest.raises(TypeError):
        schema.REGISTRY["add_anything"] = None  # type: ignore[index]


def test_the_module_exposes_no_public_registration_function() -> None:
    exported = [
        name for name in dir(schema) if not name.startswith("_") and "register" in name.lower()
    ]

    assert exported == [], (
        "the registry is CLOSED: a public registration function makes the set "
        f"open, and an open set makes the provenance partition unfalsifiable; got {exported}"
    )


def test_the_registry_is_not_empty() -> None:
    # Every test below quantifies over the registry. An empty registry would
    # pass all of them while proving nothing, so vacuity is refused here once
    # rather than guarded against in each.
    assert schema.REGISTRY, "a registry with no types makes every structural test vacuous"


def test_the_registry_holds_the_class_the_module_actually_exposes() -> None:
    # ``@dataclass(slots=True)`` returns a NEW class object rather than
    # modifying the one it was given, so a registration decorator applied
    # underneath it registers the pre-dataclass class -- which has no fields,
    # no __eq__ and no generated __init__. Everything downstream then walks a
    # class nobody uses, silently.
    #
    # ``is_dataclass`` cannot see this: it reads ``__dataclass_fields__``,
    # which the half-built class inherits from the Operation base and so
    # answers True for both. Identity against the module binding is the check
    # that actually discriminates.
    stale = [
        name
        for name, spec in schema.REGISTRY.items()
        if spec.cls is not getattr(schema, spec.cls.__name__, None)
    ]

    assert stale == [], (
        "the registered class must be the finished dataclass the module "
        "exposes, so the registration decorator goes OUTSIDE @dataclass, "
        f"never inside it; got {stale}"
    )


def test_every_registered_type_is_classified_exactly_once() -> None:
    registered = set(schema.REGISTRY)
    fact_asserting = set(schema.FACT_ASSERTING)
    non_fact = set(schema.NON_FACT)

    unclassified = registered - (fact_asserting | non_fact)
    both = fact_asserting & non_fact
    unregistered = (fact_asserting | non_fact) - registered

    assert not unclassified, (
        "the provenance partition must be TOTAL over the registry: these types "
        f"are in neither FACT_ASSERTING nor NON_FACT, so nothing says whether "
        f"they may assert a fact without evidence; got {sorted(unclassified)}"
    )
    assert not both, (
        "the provenance partition must be DISJOINT: these types are in both "
        f"FACT_ASSERTING and NON_FACT; got {sorted(both)}"
    )
    assert not unregistered, (
        "a classification naming a type the registry does not have is a stale "
        f"entry, and it hides the type it was meant to cover; got {sorted(unregistered)}"
    )


def test_every_non_fact_type_records_why_it_is_exempt() -> None:
    # What the partition does NOT catch is a misclassification -- a
    # fact-asserting operation placed in NON_FACT. Totality is provable;
    # correctness is not. The recorded rationale is what review checks, so an
    # empty one is the same defect as no classification at all.
    missing = [name for name, reason in schema.NON_FACT.items() if not reason.strip()]

    assert missing == [], (
        "every NON_FACT member carries a one-line rationale, because the "
        "partition proves totality and not correctness, and the rationale is "
        f"the only thing a reviewer can check a misclassification against; got {missing}"
    )
