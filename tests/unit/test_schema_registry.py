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


def test_the_provenance_rule_is_carried_by_the_schema_not_only_by_the_table() -> None:
    # "No operation may assert a genealogical fact without a citation
    # reference" -- asserted against the fields each type actually declares,
    # so the classification table and the schema cannot drift apart. Two
    # sources that must agree is a test; one source read twice is not.
    disagreements = []

    for name, spec in schema.REGISTRY.items():
        declares_citation = spec.citation_field is not None
        classified_fact_asserting = name in schema.FACT_ASSERTING
        if declares_citation != classified_fact_asserting:
            disagreements.append((name, spec.citation_field, classified_fact_asserting))

    assert disagreements == [], (
        "a FACT_ASSERTING type must declare the field carrying its provenance, "
        "and a NON_FACT type must declare none -- the exempt side of the "
        "partition requires no citation field AT ALL, which is a different "
        f"kind of operation and not a weaker one; got {disagreements}"
    )


def test_the_declared_citation_field_is_a_citation_reference_that_exists() -> None:
    wrong = []

    for name, spec in schema.REGISTRY.items():
        if spec.citation_field is None:
            continue
        expects = schema.expected_object_types(spec.cls)
        if expects.get(spec.citation_field) != schema.OBJECT_TYPE_CITATION:
            wrong.append((name, spec.citation_field, expects.get(spec.citation_field)))

    assert wrong == [], (
        "the provenance field must name a real field of the operation that "
        "expects a citation reference; a name pointing at nothing, or at a "
        f"reference to something else, records provenance nowhere; got {wrong}"
    )


def test_no_exempt_type_smuggles_a_citation_reference_in_under_another_name() -> None:
    # The partition's exempt side is checked against the schema in both
    # directions. Without this, a NON_FACT type could carry a citation field
    # the spec says it must not have, and the test above would not look.
    smuggled = []

    for name in schema.NON_FACT:
        expects = schema.expected_object_types(schema.REGISTRY[name].cls)
        carrying = [field for field, kind in expects.items() if kind == schema.OBJECT_TYPE_CITATION]
        if carrying:
            smuggled.append((name, carrying))

    assert smuggled == [], (
        "a NON_FACT operation requires no citation field at all; one that has "
        f"a citation reference is misclassified or mis-modelled; got {smuggled}"
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
