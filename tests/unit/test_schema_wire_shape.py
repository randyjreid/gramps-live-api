"""``to_dict`` says it emits a JSON-shaped mapping. Nothing asserted it.

The docstring made the claim and the round-trip tests could not check it: they
compare an object to itself through both directions, so a value that survives
the trip unchanged passes whether or not any encoder could emit it. A non-JSON
value therefore passed straight through while the suite stayed green and the
claim quietly became false.

A new file rather than an edit, because the claim is not a round-trip claim:
``test_schema_serialisation.py`` compares an object to itself through both
directions, which is exactly the comparison this property is invisible to.

⚠️ **That reason used to be written as "its diff must stay empty", and the
reserved key made that false** -- a structural refusal quantified over the
registry is what that file is *for*, so the reservation's cases went beside its
unknown-field ones. Corrected rather than left standing: what must stay out of
it is wire-SHAPE work, not everything.

⚠️ **And it asserted the claim at ONE DEPTH, which is how the claim stayed
false.** A marker inside an ``ObjectRef`` was copied straight out of the
reference, so ``to_dict`` returned a raw ``Unrecorded`` and ``json.dumps``
raised -- while this file was green. The matrix below is now quantified over
**paths derived from the declaration, at every depth**, crossed with the values
this module models that no encoder can emit. That is the property; the recursion
in ``_to_wire`` satisfies it, and this is what states it, so the next depth
arrives already covered.

⚠️ **And then it was false again one container further out**, at a list or a
mapping holding either of those -- so the claim is no longer asserted over a
list of shapes at all. It is asserted over the module's own **value grammar**:
the kinds ``_to_wire`` branches on, composed. The generator's breadth and depth
are a **stated budget with its reasoning**, at the bottom of this file, because
a sample's size is a cost every future run pays; and the claim that actually
**closes** is the bounded sub-property below it, not the sample.

⚠️ **And for three rounds this file asserted an UNBOUNDED property, which is
why it kept being false in a new place each round.** *Total over any value that
can be constructed* has no fixed point: interrogating a value runs the value's
own code, so a reviewer can build a fresh pathological one every round and each
one is genuine -- the rounds were sampling an infinite space rather than
converging on correctness. **The claim is now narrowed to one that closes:**

    ``to_dict`` is TOTAL over DECODER-PRODUCIBLE values -- every payload
    ``from_dict`` accepts converts to a JSON-emittable wire carrying no fault
    marker, at any depth to the encoder's own ceiling.

Arbitrary in-process objects are **best-effort**, with the boundary stated
rather than defended: an exception raised by the caller's own object propagates
**as itself**, and the remedy is ``validate``, which reads the object without
transporting it. Three sections carry that split -- the generated values are
**partitioned** into the half the strong claim covers and the half labelled
evidence; the bounded sub-property at the bottom is the criterion, quantified
over breadth **and** depth; and the residual is pinned as a fence beneath it.

⚠️ **The sweep over the canonical examples is a REGRESSION FENCE, not
evidence.** It is green before the change that added this file and green after,
because every registered type already carries only JSON-shaped values. It is
here so that the day one does not, something says so. The case with teeth is
the one below it, which was red.

Two sources are asked to agree, which is the point of checking it twice: the
structural walk, which can name the path of the offending value, and
``json.dumps``, which is the encoder the claim is actually about but whose
``TypeError`` names no field.
"""

from __future__ import annotations

import functools
import json
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import fields, is_dataclass
from types import MappingProxyType
from typing import get_args, get_type_hints

import pytest

from gramps_live_api.core import schema
from gramps_live_api.core.schema import UNRECORDED, ObjectRef, Operation, RuleId, Unrecorded
from tests.fixtures.operations import EXAMPLES, WIRE_VALUES, carrying, payload_with

_JSON_SCALARS = (bool, int, float, str)


_A_KEY_NO_JSON_OBJECT_CAN_SPELL = object()
"""Stands where a non-text key sat, so the key check keeps its place in order.

The walk below reports the **first** offending path, and the recursion it
replaced interleaved its two checks: for each entry in turn it refused a non-text
key and only then descended into that entry's value. Hoisting the key check
ahead of the descent would be shorter and would report a different path for the
same payload -- the mapping itself rather than the unemittable value sitting at
an earlier entry. Pushing this in the key's place keeps the order the failure
messages already had.
"""


def _not_json(value: object, path: str) -> str | None:
    """The path of the first value no JSON encoder can emit, or ``None``.

    A path rather than a boolean: a refusal that does not say where the fault is
    is one nobody can act on, which is the rule the violations in this module
    already obey.

    ⚠️ **An explicit stack rather than a recursion, and not for tidiness.** This
    walk shared the recursive conversion's frame ceiling -- measured, both
    stopped at depth 995 on this box -- so a test written past that depth failed
    in this file's own machinery rather than in the module. **A test walk that
    cannot reach the depth it is testing asserts nothing**, and the file's "two
    sources must agree" convention would have had a hole at exactly the depth the
    section below is about.

    Depth-first in **source order** is preserved deliberately. The returned path
    is quoted in failure messages at seven call sites, so which offending value
    is named first is a quality-of-message obligation -- no test asserts a
    particular path, which is why it has to be written down here instead.

    Called on ``to_dict`` output, which is acyclic because the conversion breaks
    cycles with the fault marker. A cyclic input does not terminate here, the
    same way it did not terminate in the recursion this replaced.
    """
    stack: list[tuple[object, str]] = [(value, path)]
    while stack:
        item, where = stack.pop()
        if item is None or isinstance(item, _JSON_SCALARS):
            continue
        if isinstance(item, list):
            # Reversed, because a LIFO stack completes what was pushed last:
            # pushing backwards is what makes it come out in source order.
            stack.extend(
                (contained, f"{where}[{index}]")
                for index, contained in reversed(list(enumerate(item)))
            )
            continue
        if isinstance(item, dict):
            stack.extend(
                (contained, f"{where}.{key}" if where else key)
                if isinstance(key, str)
                else (_A_KEY_NO_JSON_OBJECT_CAN_SPELL, where)
                for key, contained in reversed(list(item.items()))
            )
            continue
        return where
    return None


_A_REFERENCE = ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044")
"""A reference built from invented values, in the register ``EXAMPLES`` uses."""

_A_VALUE_NO_MESSAGE_MAY_REPEAT = "Thessaly-Grendlemere-4417"
"""Invented, and distinctive so its absence from a payload means something.

Same register and the same rule as ``SENTINELS``: no path separator, no ``~``,
nothing path-shaped, because this is a literal in a file the guard scans.
"""


class _Unmodellable:
    """A value nothing here models, carrying something no payload may repeat.

    A module-level class rather than a lambda or a bare ``object()``: the fault
    marker names ``type(value).__name__``, so the name has to be one a reader
    meets in a failure message.
    """

    def __init__(self, carried: str) -> None:
        self.carried = carried

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.carried}>"


_THE_UNKNOWN = "a value the module cannot model"
"""The atom the deep spine is built over, named so the spine can find it."""

_ATOMS: Mapping[str, object] = MappingProxyType(
    {
        "an empty string": "",
        "zero": 0,
        "a null": None,
        "the not-recorded marker": UNRECORDED,
        "a reference": _A_REFERENCE,
        _THE_UNKNOWN: _Unmodellable("a value"),
    }
)
"""One value per branch the conversion takes, and that is what makes it a grammar.

Not a guess at what a client might send: these are the *kinds* ``_to_wire``
decides between, so a branch that stops being reached is a branch the tripwire
below reports missing.
"""


_UNEMITTABLE: Mapping[str, object] = MappingProxyType(
    {
        description: value
        for description, value in _ATOMS.items()
        if _not_json(value, "") is not None
    }
)
"""The values this module models that no JSON encoder can emit.

⚠️ **DERIVED from the atoms rather than written out, and the old justification
is exactly why.** It used to be a hand-written pair on the ground that those were
"exactly ``_to_wire``'s two branches" -- which stopped being true the moment the
conversion had six. A list kept beside a thing it claims to mirror goes stale
with nothing announcing it; asking ``_not_json`` which atoms it refuses cannot.

The reference is built from invented values, in the register ``EXAMPLES``
already uses, for the reason recorded on ``SENTINELS``.
"""


def _declared_paths(
    cls: type, prefix: str = "", seen: frozenset[type] = frozenset()
) -> Iterator[str]:
    """Every dotted path the declaration of ``cls`` reaches, at every depth.

    ⚠️ **A walk rather than one level of ``fields``, and the difference is the
    defect this file was extended for.** ``to_dict`` applies ``_to_wire`` to
    top-level fields, so a matrix built from ``fields(cls)`` alone asserts the
    JSON-shaped claim at exactly the depth the emitter happens to visit -- which
    is how a raw ``Unrecorded`` inside a reference passed a green suite. **A test
    that asserts a claim at one depth does not assert it at all depths.**

    Derived here from ``get_type_hints``/``get_args`` and deliberately NOT by
    calling ``schema.absence_fields``, which answers at the top level only --
    following this suite's precedent that a test reads the same declaration by
    its own route. A field whose annotation admits the marker is skipped: its
    declaration says the marker belongs there, so it is not a case about a value
    arriving where nothing declares it.

    ``seen`` carries the owner classes on the way down, so a self-referential
    declaration terminates rather than walking forever.
    """
    owners = seen | {cls}
    hints = get_type_hints(cls)
    for declared in fields(cls):  # type: ignore[arg-type]
        annotation = hints[declared.name]
        candidates = get_args(annotation) or (annotation,)
        if Unrecorded in candidates:
            continue
        path = f"{prefix}{declared.name}"
        yield path
        for candidate in candidates:
            if isinstance(candidate, type) and is_dataclass(candidate) and candidate not in owners:
                yield from _declared_paths(candidate, f"{path}.", owners)


def _marker_cases() -> list[tuple[str, str, str]]:
    """Every (type, path, value) a value no encoder can emit can be put at.

    Derived rather than hand-picked, so a type registered later brings its own
    cases -- and, since the walk above is recursive, brings them at every depth
    its declaration reaches rather than at its top level only.

    An operation is a *transport* type, so a fixture can put any of these where
    any field goes and leave the judging to ``validate`` -- which is what makes
    this reachable at all while no registered type declares the marker.

    ⚠️ **``carrying`` handles two levels, so a depth-3 path would raise
    ``TypeError`` from ``dataclasses.replace`` rather than quietly skip.** Loud
    is correct: the day a declaration nests that deep, this says so.
    """
    return [
        (type_name, path, description)
        for type_name in sorted(EXAMPLES)
        for path in _declared_paths(type(EXAMPLES[type_name]))
        for description in sorted(_UNEMITTABLE)
    ]


MARKER_CASES = _marker_cases()


def test_the_generated_marker_matrix_is_not_empty() -> None:
    # A parametrized list that generates to nothing passes every test built on
    # it while asserting nothing at all.
    assert MARKER_CASES, "no field was reached; every marker case below is vacuous"


def test_the_marker_matrix_reaches_a_nested_path() -> None:
    # ⚠️ **The same idiom as the guard above and for the same reason, one level
    # deeper.** An empty matrix reads as coverage; so does a matrix that quietly
    # stops at depth 1 -- which is not hypothetical, it is exactly what this file
    # did while the claim it asserts was false inside a reference. The non-empty
    # guard cannot see it, because a shallow walk still generates plenty.
    #
    # A VACUITY GUARD, so it is green on arrival: it is not evidence of the
    # behaviour, it is what stops the evidence being read at the wrong depth.
    nested = sorted({path for _, path, _ in MARKER_CASES if "." in path})

    assert nested, (
        "no generated path is nested, so the matrix asserts to_dict's claim at "
        "the top level only -- which is how a raw value inside a reference "
        "passed this file green"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_a_canonical_example_serialises_to_something_json_can_emit(type_name: str) -> None:
    # ⚠️ The FENCE. Green before this file existed and green after -- it is not
    # evidence of new behaviour and must not be counted as such.
    payload = schema.to_dict(EXAMPLES[type_name])

    assert _not_json(payload, "") is None
    json.dumps(payload)


@pytest.mark.parametrize(("type_name", "path", "description"), MARKER_CASES)
def test_to_dict_emits_json_for_a_marker_at_a_field_that_does_not_declare_it(
    type_name: str, path: str, description: str
) -> None:
    # The case with teeth. to_dict is by VALUE, not by declaration, precisely so
    # that this holds: a marker at a field whose declaration does not admit it is
    # still emitted as JSON. Making to_dict declaration-driven instead would
    # leave a raw Enum in the payload in exactly the case this test exists for.
    #
    # The operation is not well-formed -- validate reports the marker at that
    # path -- and that is a separate question from whether the transport can
    # carry it. Judging it requires getting it to a judge first. An operation
    # that cannot be CARRIED is untransportable rather than reportably invalid,
    # which inverts this module's own boundary: shape faults are reported at a
    # field path, not raised out of the transport.
    #
    # ⚠️ **The name records criterion 5 and the matrix is wider than the name.**
    # It crosses every declared path with both values _to_wire converts, because
    # the claim is about the payload rather than about one of them.
    value = _UNEMITTABLE[description]
    payload = schema.to_dict(carrying(EXAMPLES[type_name], path, value))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {offending} carries "
        f"{type(value).__name__}, which no JSON encoder can emit"
    )
    json.dumps(payload)


# ---------------------------------------------------------------------------
# One container deeper -- the shapes round 2 reported, named
#
# ⚠️ **These are the REPORTED shapes and they are kept by name, not folded into
# the generated set below.** A sample that happens to contain today's finding is
# not the same artifact as a case that says which finding it is: the generator's
# breadth is a budget somebody will trim, and the shape a reviewer actually
# constructed must not be trimmable by arithmetic. Every one of them had the same
# signature -- ``validate`` already returned FIELD_WRONG_TYPE at the path, and
# ``json.dumps(to_dict(op))`` raised, so the verdict existed and the transport
# hid it.
# ---------------------------------------------------------------------------


def _first_reference_leaf(cls: type) -> str:
    """Where a value goes to be carried at depth: the first leaf of the first reference.

    Derived rather than spelled, so a type whose reference field is named
    something else brings its own placement.
    """
    reference = schema.reference_fields(cls)[0]  # type: ignore[arg-type]
    return f"{reference}.{fields(ObjectRef)[0].name}"


_CONTAINED: Mapping[str, object] = MappingProxyType(
    {
        "a list holding the not-recorded marker": [UNRECORDED],
        "a mapping holding the not-recorded marker": {"a key": UNRECORDED},
        "a list holding a list holding the not-recorded marker": [[UNRECORDED]],
        "a list holding a reference": [_A_REFERENCE],
        "a mapping holding a reference": {"a key": _A_REFERENCE},
        "a read-only mapping holding the not-recorded marker": MappingProxyType(
            {"a key": UNRECORDED}
        ),
    }
)
"""The shapes reported against the one-container-deep conversion, verbatim."""


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
@pytest.mark.parametrize("description", sorted(_CONTAINED))
def test_to_dict_emits_json_for_a_container_holding_a_value_the_module_models(
    description: str, type_name: str
) -> None:
    example = EXAMPLES[type_name]
    value = _CONTAINED[description]
    payload = schema.to_dict(carrying(example, _first_reference_leaf(type(example)), value))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {description} at "
        f"{offending} is not one an encoder can emit"
    )
    json.dumps(payload)


# ---------------------------------------------------------------------------
# The branch for the unknown
#
# ⚠️ **A value the module cannot model emits a MARKER rather than raising, and
# the reason is the line this module already draws and writes down.** A
# STRUCTURAL fault raises; a VALUE fault does not, because refusing one would be
# a second validator with no field path. An alien object at a declared field is a
# value fault, and ``validate`` already returns FIELD_WRONG_TYPE at its path.
# **A typed transport error is this finding with a better name.**
#
# Unmodellable and modellable-but-misplaced share the surface and differ only in
# the payload: a modellable value keeps its faithful spelling, and only an
# unmodellable one is replaced. Splitting them across two error surfaces would
# make a caller's handling depend on a distinction it cannot predict.
# ---------------------------------------------------------------------------


def _carrying_at_the_first_leaf(type_name: str, value: object) -> Operation:
    example = EXAMPLES[type_name]
    return carrying(example, _first_reference_leaf(type(example)), value)


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
def test_to_dict_emits_json_for_a_value_the_module_cannot_model(type_name: str) -> None:
    # The transport must carry it to the judge. validate already reports
    # FIELD_WRONG_TYPE at that path, so what raising would cost is not a verdict
    # -- it is the verdict's field path, reported out of a surface that has none.
    payload = schema.to_dict(_carrying_at_the_first_leaf(type_name, _Unmodellable("a value")))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {offending} carries a value the "
        "module cannot model, which no JSON encoder can emit"
    )
    json.dumps(payload)


def test_the_fault_marker_names_the_type_and_never_the_value() -> None:
    # The rule on RuleViolation, obeyed by the transport for the same reason: a
    # payload echoed into the record becomes content this repository then has to
    # scan. The TYPE is what a caller needs to fix it, and it is ours to name.
    value = _Unmodellable(_A_VALUE_NO_MESSAGE_MAY_REPEAT)

    wire = schema._to_wire(value)

    assert wire == {schema.UNCONVERTIBLE_KEY: type(value).__name__}
    assert _A_VALUE_NO_MESSAGE_MAY_REPEAT not in json.dumps(wire), (
        "the fault marker repeated the value it refused, which is the one thing "
        "no message in this module may do"
    )


def test_a_mapping_keyed_by_something_that_is_not_text_is_unconvertible() -> None:
    # A whole-mapping verdict rather than a per-key one, deliberately: a JSON
    # object is string-keyed, and stringifying the key would invent data the
    # payload never carried.
    value = {0: "a value"}

    assert schema._to_wire(value) == {schema.UNCONVERTIBLE_KEY: type(value).__name__}


def test_a_read_only_mapping_converts_rather_than_raising() -> None:
    # GREEN ON ARRIVAL from the container recursion, and kept because it is the
    # totality gain nobody asked for: this module hands MappingProxyType around
    # as REGISTRY and EXAMPLES, and json.dumps raises on one.
    wire = schema._to_wire(MappingProxyType({"a key": "a value"}))

    assert wire == {"a key": "a value"}
    assert type(wire) is dict


def test_a_self_referential_list_is_emitted_as_json() -> None:
    # ⚠️ **Termination is the OTHER HALF of "total", and without it the word is
    # simply false.** A list holding itself is constructible IN PROCESS in two
    # lines, and a structural recursion over it does not stop. It is a
    # termination condition rather than a case added to an enumeration, which is
    # the distinction that keeps this from being the next shape nobody wrote
    # down.
    #
    # ⚠️ **In process, and that is a scope rather than a hedge: a cycle is NOT
    # decoder-producible, JSON being a tree, so this serves the BEST-EFFORT side
    # of the narrowed claim.** It stays regardless, on its own merits -- without
    # it the walk does not terminate, and non-termination is the one failure mode
    # where nothing propagates as itself either, because nothing propagates at
    # all. Depth, by contrast, is inside the bounded claim.
    cycle: list[object] = []
    cycle.append(cycle)

    payload = schema.to_dict(_carrying_at_the_first_leaf("add_note", cycle))

    assert _not_json(payload, "") is None
    json.dumps(payload)


def test_a_self_referential_mapping_is_emitted_as_json() -> None:
    # The same, through the other container, because a fix applied to one branch
    # of a structural recursion is a fix applied to one branch.
    cycle: dict[str, object] = {}
    cycle["a key"] = cycle

    payload = schema.to_dict(_carrying_at_the_first_leaf("add_note", cycle))

    assert _not_json(payload, "") is None
    json.dumps(payload)


def test_a_value_appearing_twice_is_not_read_as_a_cycle() -> None:
    # ⚠️ **The guard on the SHAPE of the termination fix, and the reason it is
    # here before the fix is.** "Seen" carried as a set that accumulates across
    # the whole walk marks the second sibling as a cycle and emits the fault
    # marker for a value that is perfectly emittable -- a fail-closed defect that
    # every other test in this file would pass over. Carried along the current
    # PATH instead, a shared value is converted twice and neither is a cycle.
    shared = ["a value"]

    assert schema._to_wire([shared, shared]) == [["a value"], ["a value"]]


def test_a_tuple_becomes_a_json_array() -> None:
    # GREEN ON ARRIVAL, and recorded because it is a CONSEQUENCE rather than a
    # gain: that operation is no longer round-trip identical, since a tuple comes
    # back a list. Correct -- JSON has no tuple -- and reachable only on an
    # operation that is invalid either way. No fixture carries one.
    assert schema._to_wire(("a value",)) == ["a value"]


# ---------------------------------------------------------------------------
# DEPTH -- the half of termination that was still false
#
# ⚠️ **Cycles were the half that got written down; depth was the half that did
# not.** The conversion was a structural recursion, so it had a ceiling of its
# own, and that ceiling was BELOW the decoder's.
#
# ⚠️ **Every number in this banner is ONE BOX'S MEASUREMENT rather than a
# property of `json` or of this module** -- Windows CPython 3.12.13 at the
# default recursion limit of 1000:
#
#   the recursive _to_wire                   995
#   this file's own _not_json, as it was     995
#   json.loads                              2997
#   json.dumps                              2997
#
# They are kept because they are the record of WHY the conversion became
# iterative, which is what a later reader needs. They are not bounds anything
# below relies on: the depth the tests use is measured at import, on whatever
# interpreter is running them -- `_deepest_nesting_json_carries`.
#
# ⚠️ **So there was a band -- above the conversion's ceiling and below the
# encoder's -- where a payload was decoder-producible, was accepted by
# from_dict, and could not be carried.** to_dict raised RecursionError, which is
# neither of the two outcomes criterion 5 allows: it is not JSON, and it is not
# failing closed visibly at a field path. That band sits INSIDE the bounded
# sub-property at the bottom of this file, so it was a **correction** to a claim
# that was false, not a residual to record.
#
# ⚠️ **The lower number is not a property of the value -- it moves with the
# CALLER'S OWN STACK DEPTH.** Measured: 995 from a module-level call, 895 from
# one a hundred frames down. That is what decided the fix. Catching
# RecursionError and emitting the fault marker is much the smaller change, and it
# loses on merits rather than on taste: it would turn a deep
# decoder-producible payload into silent data loss, making the marker appear for
# a payload the bounded claim says it never appears for -- and it would make the
# emitted payload a function of where the conversion was called from rather than
# of the value converted. The same operation would serialise differently under
# pytest's assertion-rewriting frames than from a plain call.
#
# The conversion now carries an explicit stack, so its depth is bounded by memory
# rather than by the interpreter's frame budget; measured usable at depth
# 200 000 on that same box. ⭐ **The ceiling that remains is CPython's own json
# module rather than this module's -- for dumps and loads alike, so above it a
# payload is neither decoder-producible nor encoder-emittable. The band is
# CLOSED, not narrowed.**
#
# ⚠️ **But WHERE that ceiling sits is an interpreter's answer, and writing one
# interpreter's answer into this file as a literal is what broke CI.** On 3.12
# the C json module carries a recursion budget of its own; on 3.10 and 3.11 it
# draws on the same budget Python frames do, so the ceiling lands far lower AND
# moves with the caller's stack depth. A literal `2000` was comfortably inside
# the band on 3.12 and blew the stack in the tests' own builders on 3.10 and
# 3.11 -- RecursionError out of `json.loads`, before any assertion. The probe
# below asks the running interpreter instead of remembering an answer.
# ---------------------------------------------------------------------------

_PROBE_PAD_FRAMES = 100
"""Python frames the depth probe descends through before it measures.

⚠️ **A CHOSEN number, and recorded here as one rather than in a commit message,
because a number nobody can justify later is how the literal above got here.**

What is justified is the DIRECTION. The json ceiling moves with the caller's
stack depth -- this file records 995 from a module-level call against 895 from
one a hundred frames down -- so a probe run at import measures headroom a test
body may not have, and the two stacks are genuinely different: measured under
pytest, a test module imports 39 frames down and a test body runs 34 frames
down, and which of them has more room varies with how the run was invoked.
**The whole suite and this file alone disagreed by enough to fail one test.**
Padding first can only make the answer too SHALLOW, and too shallow merely means
the tests below assert a little less than they could; a chosen MARGIN, by
contrast, has to be exactly right in both directions. That argument justifies
padding. It does not justify 100.

100 is the distance the file's own 995/895 pair was measured over, which is the
only anchor there is. Measured for scale on 3.12.13 here: a pad this deep costs
two budget units per frame, so from a test body the probe answers 2778 against
an unpadded 2978 -- about 7% of the ceiling given up, and roughly a fifth of the
1000-frame budget on 3.10/3.11. That is the price of not choosing a margin, paid
in depth the tests do not need.

⚠️ **The pad has to be spent in the SAME CURRENCY as the thing it protects, and
a plain recursion is not.** See ``_carries_under_the_pad``: on 3.12 json counts
C recursion, which Python-to-Python calls do not touch, so the obvious pad
measured 2978 padded and 2978 unpadded and protected nothing on the one version
this whole change exists for.
"""

_WRAPPING_LEVELS = 4
"""Container levels a depth test puts AROUND the deep value before it dumps.

⚠️ **Derived by enumerating what the tests do rather than chosen, and
load-bearing precisely because the probe measures the ceiling EXACTLY.** Every
depth test below closes with ``json.dumps`` of a whole payload rather than of
the bare value, so the payload is deeper than the value by however much each one
wraps. Counted, with *d* for the constant below:

  reaches_the_wire            d lists, in a payload   ->  d + 2
  ..._not_read_as_a_cycle_    the pair around it      ->  d + 3
  ..._a_cycle_closed_...      d + 1 lists, then the
                              marker the cycle emits  ->  d + 4
  ..._could_have_produced_    d arrays, in a payload  ->  d + 2

The payload's own two are its root mapping and one nested reference mapping;
``payload_with`` reaches at most the same ``payload[head][rest]``. The worst of
the four is what this has to be. ⚠️ **It was 2 for one gate run -- the payload's
own envelope counted and the levels each test adds INSIDE it missed -- and the
cycle test failed with a ``RecursionError`` out of its own closing
``json.dumps``, which is the failure this constant exists to prevent.**

The probe spends these inside its own trial, so ``_PAST_THE_FRAME_LIMIT`` needs
no margin subtracted from it and none chosen for it. Mapping levels there
against lists here is deliberate and costs nothing: CPython's encoder and
decoder charge one recursion per container whichever it is. Measured unpadded on
3.12.13 here: 2978 with no wrapping, 2976 with two, 2974 with four -- one
apiece, exactly.

⚠️ **A depth test that wraps deeper than any of the four above must move this
number with it.** What keeps that from being fatal on the day someone forgets is
``_PROBE_PAD_FRAMES``, which is slack the probe gives up deliberately -- not the
few levels the import stack happens to be short by, which vary with how the
suite was invoked and are not headroom at all.
"""


def _json_carries(depth: int) -> bool:
    """Whether this interpreter both decodes and re-emits a value nested ``depth`` deep.

    One trial is ``json.dumps(json.loads(...))``, which is BOTH ceilings in one
    call: the loads side is exactly what ``_decoder_produced_nesting`` does, and
    the dumps side is exactly what every depth test below closes with. The
    answer is therefore the lesser of the two without this file having to say
    which one bound it, and without it having to assume they are equal.

    The trial is run with ``_WRAPPING_LEVELS`` containers already spent, so what
    it answers is the depth a test can actually USE rather than the raw ceiling.

    The text is built with ``"[" * depth``, never by recursing, because the
    builder must not share the ceiling it is measuring. ``RecursionError`` is
    caught around the trial and around nothing else.
    """
    text = '{"a": ' * _WRAPPING_LEVELS + "[" * depth + "]" * depth + "}" * _WRAPPING_LEVELS
    try:
        json.dumps(json.loads(text))
    except RecursionError:
        return False
    return True


def _carries_under_the_pad(frames: int, depth: int) -> bool:
    """``_json_carries``, called ``frames`` further down the stack.

    A recursion, deliberately: spending stack is the whole job. It sits OUTSIDE
    the ``try`` above, so a pad that cannot fit propagates as itself rather than
    being mistaken for a ceiling. See ``_PROBE_PAD_FRAMES``.

    ⚠️ **The recursive call goes through ``map`` rather than being written
    directly, and that is the only reason the pad does anything on 3.12.** A
    Python function called from Python spends the Python frame budget alone;
    called from C it spends the C recursion budget as well, and the C budget is
    the one 3.12's json module counts. Written as a direct call the pad was
    measurably inert there -- padded and unpadded answered identically to the
    unit -- so it padded exactly the versions that were already green and left
    the one it was written for unprotected.
    """
    if frames <= 0:
        return _json_carries(depth)
    (answer,) = map(_carries_under_the_pad, (frames - 1,), (depth,))
    return answer


def _bracket_and_bisect(carries: Callable[[int], bool], seed: int) -> int:
    """The deepest depth ``carries`` accepts, bracketed OUTWARD from ``seed``.

    ⚠️ **``seed`` is a hint and nothing else, and the two outward arms are what
    make that true.** A trial at the seed decides which way to walk: accepted,
    the bracket doubles UPWARD until a trial fails; refused, it halves DOWNWARD
    until one succeeds. Only then does it bisect. So a seed above the answer and
    a seed below it reach the same number, and a wrong seed costs a few trials
    rather than capping the result. **Without both arms a seed is a cap wearing
    a hint's name**, which is the one thing this constant may not become.

    The invariant carried into the bisection is ``carries(good)`` and ``not
    carries(bad)``, with ``good == 0`` standing for "nothing carries at all" so
    the floor costs no trial of its own. Bisection is unchanged from the version
    that doubled from 1; only how the bracket is reached has moved.
    """
    start = max(1, seed)
    if carries(start):
        good, bad = start, start * 2
        while carries(bad):
            good, bad = bad, bad * 2
    else:
        good, bad = start // 2, start
        while good >= 1 and not carries(good):
            good, bad = good // 2, good
    while bad - good > 1:
        middle = (good + bad) // 2
        if carries(middle):
            good = middle
        else:
            bad = middle
    return good


@functools.lru_cache(maxsize=1)
def _deepest_nesting_json_carries() -> int:
    """The deepest nesting this interpreter carries, seeded then bracketed then bisected.

    The opening guess is ``sys.getrecursionlimit()`` rather than 1, which is the
    only number the interpreter offers that is about frame budgets at all. It
    replaces a doubling arm that started from 1 and so paid one trial per power
    of two below the answer -- measured here, 24 trials against 14. ⚠️ **A trial
    count rather than a saving: the whole search, before and after, is single-
    digit MILLISECONDS, and the reason it is worth doing anyway is that a probe
    nobody can afford to run is a probe that gets replaced by a literal again.**

    ⚠️ **The seed is wrong in ordinary use, on the very version this probe
    exists for, and that is why the outward arms are exercised rather than
    assumed.** On 3.10 and 3.11 the json module draws on the same budget Python
    frames do, so the limit is a fair opening guess. On 3.12 the C recursion
    budget is a different quantity: measured here, a limit of 1000 against an
    answer near 2790, so every run on this box walks the UPWARD arm to reach it.
    ⚠️ **"near", because four runs answered 2785, 2788, 2790 and 2793** -- the
    ceiling moves with the caller's own stack, which is the whole reason
    ``_PROBE_PAD_FRAMES`` exists, so a single figure written here as though it
    were stable would be this file's original defect at a smaller scale.
    ``_bracket_and_bisect``'s own tests below drive both arms from seeds either
    side of a synthetic ceiling, so neither arm depends on which interpreter
    happens to be running.

    ``lru_cache`` is robustness against a second import rather than a saving:
    the module-level call below is the only caller, and a module body runs once
    per process already. It buys nothing measurable here and is not claimed to.

    ⚠️ **A degenerate answer raises rather than returning it**, so a broken
    probe can read neither as a test failure nor as a pass. Returning 0 or 1
    would leave every depth test below asserting about a value nested once,
    which is green and says nothing at all.
    """
    good = _bracket_and_bisect(
        lambda depth: _carries_under_the_pad(_PROBE_PAD_FRAMES, depth),
        sys.getrecursionlimit(),
    )
    if good < 2:
        raise RuntimeError(
            f"the depth probe answered {good}, which is not a ceiling -- this is a "
            "PROBE failure rather than a result, and the depth tests below would "
            "otherwise run against a value nested once and pass saying nothing"
        )
    return good


_PAST_THE_FRAME_LIMIT = _deepest_nesting_json_carries()
"""The deepest nesting THIS interpreter both decodes and emits, measured at import.

⚠️ **Not a literal any more, and that is the whole fix.** It was `2000`: one
box's 3.12 measurement written down as though it were a property of `json`. On
3.10 and 3.11 the C json module shares the interpreter's frame budget with
Python frames, so 2000 is far above the ceiling there and the depth tests blew
the stack inside their own builders.

⚠️ **The NAME is false on 3.10 and 3.11, and is kept anyway -- a recorded
residual rather than an oversight.** There the derived depth lands BELOW the 995
the old recursive conversion reached, so a value nested this deep is not past
the frame limit; it is merely deep. The same goes for
``test_a_value_nested_past_the_frame_limit_reaches_the_wire``,
``test_a_cycle_closed_below_the_frame_limit_still_terminates``, their two
siblings, and the references to those names in
``docs/phase1-core-schema.spec.md``. Renaming ripples through four test names and
five spec references, which is more than this change is.

What the constant buys on every interpreter is the deepest value that one will
carry at all: past every ceiling this file has recorded on 3.12, and the most
the frame budget allows on 3.10/3.11 -- which is what a test asserting behaviour
at the limit can ask for. The machinery it exercises is the same either way.
"""


_SYNTHETIC_CEILING = 137
"""A ceiling the search below can be aimed at from either side, on any interpreter.

⚠️ **The seeded search's outward arms have to be EXERCISED rather than reasoned
about, and the real predicate cannot exercise both of them on one box.** Which
arm a real run walks is decided by whether ``sys.getrecursionlimit()`` happens
to sit above or below this interpreter's json ceiling -- upward on 3.12 here,
plausibly downward on 3.10 and 3.11 -- so a suite that only ever ran the real
probe would leave one arm untested on every machine and untested in CI.
Odd, and not a power of two, so a bracket that ends on a rounder number than the
answer cannot pass by coincidence.
"""


def _carries_below_the_synthetic_ceiling(depth: int) -> bool:
    """``_bracket_and_bisect``'s predicate, with a known answer and no stack spent."""
    return depth <= _SYNTHETIC_CEILING


@pytest.mark.parametrize(
    "seed",
    [1, 2, 68, 136, 137, 138, 139, 274, 1000, 4096],
    ids=lambda seed: f"seed-{seed}",
)
def test_the_seeded_search_finds_the_same_ceiling_from_either_side(seed: int) -> None:
    # ⭐ **This is what keeps the seed from becoming a cap by accident**, which is
    # the failure the derived constant exists to rule out and the one a seed
    # introduces. Seeds below the answer force the doubling arm, seeds above it
    # force the halving arm, and 137 itself forces neither -- and all of them
    # have to agree, because the seed is a hint about where to start looking
    # rather than a bound on what may be found.
    assert _bracket_and_bisect(_carries_below_the_synthetic_ceiling, seed) == (
        _SYNTHETIC_CEILING
    ), (
        f"a search seeded at {seed} answered something other than "
        f"{_SYNTHETIC_CEILING}, so the seed is deciding the answer rather than "
        "where the search begins"
    )


def test_the_real_probe_answers_the_same_from_a_seed_either_side_of_it() -> None:
    # The synthetic case above proves the arms work; this proves they work on the
    # predicate that actually measures json, whose ceiling no interpreter tells
    # us in advance. 1 is below every interpreter's answer and 8192 is above
    # every one this file has recorded, so between them the two arms are both
    # walked here whatever is running.
    #
    # Compared to each other rather than to `_PAST_THE_FRAME_LIMIT`: the json
    # ceiling moves with the CALLER'S stack depth -- that is the whole reason
    # `_PROBE_PAD_FRAMES` exists -- so the constant measured at import and a
    # measurement taken from a test body are not owed the same number, and
    # asserting they are would be a flake rather than a property.
    carries = functools.partial(_carries_under_the_pad, _PROBE_PAD_FRAMES)

    from_below = _bracket_and_bisect(carries, 1)
    from_above = _bracket_and_bisect(carries, 8192)

    assert from_below == from_above, (
        f"the probe answered {from_below} seeded from below and {from_above} "
        "seeded from above, so on the real predicate the seed is a bound rather "
        "than a starting point"
    )


def test_the_probe_is_measured_once_per_process() -> None:
    # The cache, asserted for what it is: a second call returns the first call's
    # answer without measuring again. ⚠️ **Not a saving, and not written up as
    # one** -- the module-level constant below is the only caller and a module
    # body already runs once per process. This is robustness against a second
    # import, and the honest claim is that it costs nothing rather than that it
    # bought anything.
    #
    # Stated as a DELTA rather than as absolute counts, so it does not depend on
    # which tests ran before it.
    before = _deepest_nesting_json_carries.cache_info()

    again = _deepest_nesting_json_carries()

    after = _deepest_nesting_json_carries.cache_info()
    assert (after.hits, after.misses) == (before.hits + 1, before.misses), (
        "the probe measured again on a second call, so the constant below is one "
        "search per import rather than one per process"
    )
    assert again == _PAST_THE_FRAME_LIMIT


def _nested_in_lists(innermost: object, depth: int) -> object:
    """``innermost`` wrapped in ``depth`` ordinary lists, built without recursing.

    Ordinary lists rather than the composers above, because the point is the
    interpreter's frame budget rather than the grammar's breadth -- and because
    the builder itself must not share the ceiling it is building past.
    """
    value = innermost
    for _ in range(depth):
        value = [value]
    return value


def test_a_value_nested_past_the_frame_limit_reaches_the_wire() -> None:
    # RED before the traversal became iterative, with RecursionError out of
    # to_dict rather than an assertion -- which is the finding, stated as a test:
    # the value is transportable, and the transport was what could not carry it.
    deep = _nested_in_lists("a value", _PAST_THE_FRAME_LIMIT)

    payload = schema.to_dict(_carrying_at_the_first_leaf("add_note", deep))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; a value nested "
        f"{_PAST_THE_FRAME_LIMIT} deep emitted something at {offending} that no "
        "encoder can emit"
    )
    json.dumps(payload)


def test_a_value_appearing_twice_is_not_read_as_a_cycle_at_depth() -> None:
    # ⚠️ **The path-scoping guard, carried to the depth where the mechanism
    # changed.** With a recursion, path scoping came free: the call stack unwound
    # and the frozenset went out of scope with it. An explicit stack does not
    # unwind, so the ancestors are held in a list that is TRUNCATED to the popped
    # entry's own depth -- and if that truncation never happens, the set has
    # quietly become the accumulated one, and the second sibling gets the fault
    # marker for a value that is perfectly emittable.
    #
    # This is half one of the discipline. The test below is half two, and one of
    # them alone cannot pin it: an implementation that never truncates passes
    # that one, and an implementation that truncates too far passes this one.
    shared = _nested_in_lists("a value", _PAST_THE_FRAME_LIMIT)

    payload = schema.to_dict(_carrying_at_the_first_leaf("add_note", [shared, shared]))

    assert schema.UNCONVERTIBLE_KEY not in json.dumps(payload), (
        "a value reachable twice from different branches was read as a cycle, so "
        "the ancestors are being accumulated across the walk rather than "
        "truncated to the current path"
    )


def test_a_cycle_closed_below_the_frame_limit_still_terminates() -> None:
    # Half two. A spine as deep as the interpreter will carry, whose innermost
    # element points back at the outermost container -- so the ancestor that
    # closes the cycle was pushed as many entries ago as the spine is deep and
    # must still be there. Truncating too eagerly drops it, and the walk then has
    # no reason to stop.
    outermost: list[object] = []
    innermost = outermost
    for _ in range(_PAST_THE_FRAME_LIMIT):
        deeper: list[object] = []
        innermost.append(deeper)
        innermost = deeper
    innermost.append(outermost)

    payload = schema.to_dict(_carrying_at_the_first_leaf("add_note", outermost))

    assert schema.UNCONVERTIBLE_KEY in json.dumps(payload), (
        f"a cycle closed {_PAST_THE_FRAME_LIMIT} levels down was not marked, so "
        "an ancestor was dropped from the current path before the entry that "
        "needed it"
    )
    assert _not_json(payload, "") is None
    json.dumps(payload)


def test_a_mapping_keeps_its_key_order_on_the_wire() -> None:
    # ⚠️ **GREEN ON ARRIVAL, and a shape guard rather than evidence** -- the same
    # standing as the sibling test above it, and here for a sharper reason. A
    # LIFO stack completes children in REVERSE, so an output mapping filled in
    # completion order comes out with every JSON object's keys backwards. Both
    # canonical payloads would move, and nothing else in this file would say so:
    # the fence above checks JSON-ness, not bytes.
    #
    # What stops it is that the container is created and pre-populated with its
    # keys in source order BEFORE its children are pushed, then filled slot by
    # slot. This is what asserts that, in bytes.
    ordered = {"zephyr": 1, "aster": 2, "marigold": {"quill": 4, "brack": 5}}

    wire = schema._to_wire(ordered)

    assert json.dumps(wire) == (
        '{"zephyr": 1, "aster": 2, "marigold": {"quill": 4, "brack": 5}}'
    ), "the emitted mapping's keys are not in the order the value carried them"


# ---------------------------------------------------------------------------
# The generative property -- the module's own grammar, composed
#
# The claim: **for any value composed from the module's own grammar to the
# stated depth, ``json.dumps(to_dict(op))`` does not raise and a structural walk
# finds no unemittable value.** A fixed list of shapes is the same mistake at a
# new depth, and the last two rounds were each "the shape nobody wrote down".
#
# ⚠️ **THIS PROPERTY CANNOT CLOSE, AND SAYING SO IS THE POINT.** It quantifies
# over an infinite space, so this generator SAMPLES it -- and a reviewer asked to
# construct a value outside the sample always can, every round, indefinitely.
# What actually closes is the **bounded sub-property at the bottom of this
# file**, over a space that really is bounded. Read the two together: the sample
# is evidence, and the bounded claim is the criterion.
#
# ⚠️ **So the generated values are PARTITIONED rather than asserted about
# uniformly, because two different claims are true of them and running them
# together states the weaker one about both.** A value a decoder could have
# produced gets the **strong** claim -- JSON-emittable **and the fault marker
# never appears** -- which is the bounded claim above, sampled across the
# grammar's breadth. Everything else gets the honest **best-effort** claim:
# JSON-emittable, marker permitted, because the marker is precisely the right
# answer for a value nothing models.
#
# ⚠️ **Partitioned and relabelled, NOT truncated, and the measurement is why.**
# Scoping the generator strictly to what it can close retains **9 of 41 values**
# -- and those nine ARE the closer's own `_DECODED_VALUES` under other names, so
# a truncated sampler would not become a sampler that closes something, it would
# become a duplicate of the closer. It would cost **-46 cases**, deleting the
# generative coverage of the fault marker at every declared path, which is inside
# the bounded claim and is not to be reverted. Same 82 cases, then, and the half
# that can carry the strong claim now carries it.
#
# ⚠️ **THE BUDGET IS STATED HERE, WITH ITS NUMBERS AND ITS REASONING, so that a
# later round cannot raise it quietly.** A sample's size is not a coverage dial;
# it is a cost every future run pays forever.
#
#   6 atoms x 5 composers, exhaustive to depth 1  =  6 + 30  =  36 values
#   one spine value per depth 2..6                            =   5 values
#                                                             ------------
#                                                                41 values
#   x 2 registered types, at each type's first reference leaf =  82 cases
#
# **Why the exhaustive depth is 1 and not 2.** Exhaustive to depth 2 was
# measured at 186 values and 380 cases: **+405 tests on a 923-test suite, +44%**,
# of which the second exhaustive level alone was 300 -- 74% of the whole growth.
# What that level buys is the cross product of the composers *with each other*,
# which is the one thing a structural recursion gives for free once each branch
# is right. So it is the level that was cut, and composition is still exercised
# -- by the spine, five composers deep, which costs five values rather than 300.
#
# **Why the spine depth stays at 6.** Depth is the dimension both previous
# rounds were wrong about, and it is nearly free: one value per level. Trimming
# the cheap dimension to protect the expensive one would be the trade backwards.
#
# ⚠️ **A generator that stops shallow must not read as coverage**, which is why
# three tripwires below are computed by THIS FILE's own walk rather than by
# asking the module. They are green on arrival and none of them is evidence;
# they are what stops the evidence being read at the wrong breadth or depth.
# ---------------------------------------------------------------------------

_EXHAUSTIVE_DEPTH = 1
"""How many composer levels every atom is put through. The expensive dial."""

_SPINE_DEPTH = 6
"""How deep the single spine reaches past the atoms. The cheap dial."""

_COMPOSERS: Mapping[str, Callable[[object], object]] = MappingProxyType(
    {
        "a list holding {}": lambda value: [value],
        "a mapping holding {}": lambda value: {"a key": value},
        "a mapping keyed by something that is not text, holding {}": lambda value: {0: value},
        "a read-only mapping holding {}": lambda value: MappingProxyType({"a key": value}),
        "a reference whose leaf holds {}": lambda value: ObjectRef(handle=value),
    }
)
"""One way of nesting a value per container the conversion knows about.

Their descriptions are templates rather than names, so a composed value carries
the story of how it was built into the failure message.
"""


def _spine() -> list[tuple[str, object]]:
    """One value per depth past the exhaustive core, cycling the composers.

    Built over the atom nothing models, whose own measured depth is zero, so the
    value produced at depth ``d`` measures exactly ``d`` -- which is what lets
    the depth tripwire state a number rather than an inequality.
    """
    order = sorted(_COMPOSERS)
    value = _ATOMS[_THE_UNKNOWN]
    deepened = []
    for depth in range(1, _SPINE_DEPTH + 1):
        value = _COMPOSERS[order[(depth - 1) % len(order)]](value)
        if depth > _EXHAUSTIVE_DEPTH:
            deepened.append((f"a spine of depth {depth} over {_THE_UNKNOWN}", value))
    return deepened


def _generated_values() -> list[tuple[str, object]]:
    """Every value the generator reaches, each described by how it was composed."""
    frontier = [(description, _ATOMS[description]) for description in sorted(_ATOMS)]
    generated = list(frontier)
    for _ in range(_EXHAUSTIVE_DEPTH):
        frontier = [
            (template.format(inner), _COMPOSERS[template](value))
            for template in sorted(_COMPOSERS)
            for inner, value in frontier
        ]
        generated.extend(frontier)
    return generated + _spine()


GENERATED = _generated_values()


def _measured_depth(value: object, seen: frozenset[int] = frozenset()) -> int:
    """How deeply ``value`` nests, by this file's own walk over what it IS.

    Its own walk rather than the module's, following this suite's precedent that
    a test reads the same thing by a different route: two sources that must agree
    is a test, and one source read twice would pass just as happily if the module
    had stopped composing.
    """
    if id(value) in seen:
        return 0
    below = seen | {id(value)}
    if isinstance(value, ObjectRef):
        return 1 + max(
            (_measured_depth(getattr(value, leaf.name), below) for leaf in fields(ObjectRef)),
            default=0,
        )
    if isinstance(value, Mapping):
        return 1 + max((_measured_depth(item, below) for item in value.values()), default=0)
    if isinstance(value, (list, tuple)):
        return 1 + max((_measured_depth(item, below) for item in value), default=0)
    return 0


_KINDS: tuple[str, ...] = (
    "a reference",
    "the not-recorded marker",
    "a value an encoder takes as it stands",
    "a mapping",
    "a mapping no JSON object can spell",
    "a sequence",
    _THE_UNKNOWN,
)
"""What the conversion branches on, named by this file rather than read off it."""


def _kind_of(value: object) -> str:
    """Which branch ``value`` takes, decided here and not by calling the module."""
    if isinstance(value, ObjectRef):
        return "a reference"
    if isinstance(value, Unrecorded):
        return "the not-recorded marker"
    if value is None or isinstance(value, _JSON_SCALARS):
        return "a value an encoder takes as it stands"
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            return "a mapping no JSON object can spell"
        return "a mapping"
    if isinstance(value, (list, tuple)):
        return "a sequence"
    return _THE_UNKNOWN


def test_the_generated_value_set_is_not_empty_and_names_each_value_once() -> None:
    # The non-empty idiom this file already uses, plus the uniqueness the case
    # ids rest on: two composed values sharing a description would collapse into
    # one reported case and the other would vanish without a word.
    assert GENERATED, "the generator produced nothing; every generative case is vacuous"
    assert len({description for description, _ in GENERATED}) == len(GENERATED), (
        "two generated values share a description, so one of them is unreportable"
    )


def test_the_generated_values_reach_the_stated_depth() -> None:
    # ⚠️ **The tripwire the budget rests on.** The dials above are constants, and
    # a constant is trimmable by anyone; what must not be trimmable is the CLAIM.
    # A composer that silently stops composing -- or a spine that stops being
    # applied -- makes this state a number that is no longer 6.
    deepest = max(_measured_depth(value) for _, value in GENERATED)

    assert deepest == _SPINE_DEPTH, (
        f"the generator states depth {_SPINE_DEPTH} and reaches {deepest}, so its "
        "breadth is being read as a depth it does not have"
    )


def test_every_kind_the_conversion_branches_on_is_generated() -> None:
    # ⚠️ The breadth half of the same guard. A composer dropped from the table
    # deletes a KIND, and a sample missing a kind is a sample that says nothing
    # about the branch it belongs to -- while still generating plenty.
    reached = {_kind_of(value) for _, value in GENERATED}

    assert reached == set(_KINDS), (
        f"the generated values reach {sorted(reached)}, and the conversion "
        f"branches on {sorted(_KINDS)}"
    )


def _a_decoder_could_have_produced(value: object) -> bool:
    """Whether ``json.loads`` could have returned ``value``.

    This file's own walk rather than a question put to the module, on the same
    convention as ``_kind_of`` and ``_measured_depth``: the partition below
    decides which claim each value is held to, so deriving it from the module
    would let the module choose its own marking.

    ⚠️ **EXACT types rather than ``isinstance``, and the direction is what makes
    that right.** ``_JSON_SCALARS`` in the module uses ``isinstance`` deliberately
    -- a ``str`` subclass is what ``json.dumps`` ACCEPTS, and acceptance is what
    the conversion claims. This asks the opposite question: what a decoder
    PRODUCES. ``json.loads`` returns ``dict``, ``list``, ``str``, ``int``,
    ``float``, ``bool`` and ``None`` and nothing else -- never a subclass, never a
    ``MappingProxyType``, never a tuple -- so admitting a subclass here would widen
    the strong claim past the argument that supports it.

    A JSON object is string-keyed, so a mapping with any other key is not
    produced by a decoder however ordinary its values are.

    An explicit stack, per the rule recorded on ``_names_the_fault_marker``:
    walks in this file are iterative from the start rather than discovered to
    need it. Called on generated values, which are acyclic by construction.
    """
    stack: list[object] = [value]
    while stack:
        item = stack.pop()
        if item is None or type(item) in (bool, int, float, str):
            continue
        if type(item) is list:
            stack.extend(item)
            continue
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                return False
            stack.extend(item.values())
            continue
        return False
    return True


_PRODUCIBLE = [pair for pair in GENERATED if _a_decoder_could_have_produced(pair[1])]
"""The generated values the STRONG claim covers: no fault marker, ever."""

_BEST_EFFORT = [pair for pair in GENERATED if not _a_decoder_could_have_produced(pair[1])]
"""The rest -- evidence, held to JSON-emittability alone. The marker is allowed
here, because for a value nothing models the marker is the correct answer."""


def test_the_partition_covers_the_generated_values_and_neither_half_is_empty() -> None:
    # ⚠️ **Three ways a partition lies, and this is the tripwire for all three.**
    # An empty strong half makes that claim vacuous while it still reads as the
    # thing that closes; an empty best-effort half means the predicate has gone
    # blind and is waving everything through as producible; and two independent
    # comprehensions can silently DROP a value from both halves, which is a
    # coverage cut that no failure anywhere would announce.
    #
    # Green on arrival and not evidence, like the tripwires above it.
    assert len(_PRODUCIBLE) + len(_BEST_EFFORT) == len(GENERATED), (
        "the partition does not cover the generated values, so a value is "
        "asserted about by neither half"
    )
    assert _PRODUCIBLE, (
        "no generated value is decoder-producible, so the strong half of the "
        "partition asserts nothing while still reading as the bounded claim"
    )
    assert _BEST_EFFORT, (
        "every generated value is decoder-producible, so the predicate is "
        "waving values through and the strong claim is being made about values "
        "no argument covers"
    )


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
@pytest.mark.parametrize(
    ("description", "value"), _PRODUCIBLE, ids=[description for description, _ in _PRODUCIBLE]
)
def test_a_value_a_decoder_could_have_produced_never_reaches_the_fault_marker_either(
    description: str, value: object, type_name: str
) -> None:
    # ⭐ **The STRONG half: the bounded claim, sampled across the grammar's
    # breadth.** The closer at the bottom of this file quantifies the same claim
    # over every declared path with a fixed set of values; this quantifies it over
    # the grammar's compositions at one leaf. Neither subsumes the other, and the
    # marker assertion is what makes this more than a restatement of the
    # best-effort half below.
    example = EXAMPLES[type_name]
    payload = schema.to_dict(carrying(example, _first_reference_leaf(type(example)), value))

    assert not _names_the_fault_marker(payload), (
        f"to_dict emitted the fault marker for {description}, which a decoder "
        "could have produced -- so the marker is reachable from the wire rather "
        "than only from a value built in process"
    )

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {description} at {offending} is "
        "not one an encoder can emit"
    )
    json.dumps(payload)


@pytest.mark.parametrize("type_name", sorted(EXAMPLES))
@pytest.mark.parametrize(
    ("description", "value"), _BEST_EFFORT, ids=[description for description, _ in _BEST_EFFORT]
)
def test_to_dict_emits_json_for_any_other_value_the_grammar_composes(
    description: str, value: object, type_name: str
) -> None:
    # ⚠️ **The BEST-EFFORT half, and the label is the point.** These are values no
    # decoder produces -- a value nothing models, a mapping no JSON object can
    # spell, a read-only mapping, a reference. The marker is PERMITTED here and
    # deliberately not asserted either way: for a value nothing models it is the
    # correct answer, and pinning which of these get it would be an enumeration of
    # the unbounded side.
    #
    # ⭐ **EVIDENCE, not a claim that closes.** What is asserted is the one thing
    # the transport owes unconditionally: whatever comes out, an encoder can emit
    # it.
    example = EXAMPLES[type_name]
    payload = schema.to_dict(carrying(example, _first_reference_leaf(type(example)), value))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; {description} at {offending} is "
        "not one an encoder can emit"
    )
    json.dumps(payload)


_THE_DEEPEST_VALUE = max(GENERATED, key=lambda pair: _measured_depth(pair[1]))[1]
"""The deepest value the generator built, for the path dimension below."""


_DEEP_PATH_CASES = [
    (type_name, path)
    for type_name in sorted(EXAMPLES)
    for path in _declared_paths(type(EXAMPLES[type_name]))
]


@pytest.mark.parametrize(("type_name", "path"), _DEEP_PATH_CASES)
def test_to_dict_emits_json_for_the_deepest_value_at_every_declared_path(
    type_name: str, path: str
) -> None:
    # ⚠️ **This is what crosses DEPTH with PATH.** The matrix above places every
    # generated value at one leaf, and the matrix at the top of this file places
    # an unemittable atom at every path -- so on their own the two dimensions are
    # each asserted with the other held at its cheapest. Round 1's defect lived
    # at a path the conversion did not visit and round 2's lived at a depth it did
    # not reach, which is precisely the corner neither matrix covers alone.
    payload = schema.to_dict(carrying(EXAMPLES[type_name], path, _THE_DEEPEST_VALUE))

    offending = _not_json(payload, "")

    assert offending is None, (
        f"to_dict claims a JSON-shaped mapping; the deepest generated value at "
        f"{path} emitted something at {offending} that no encoder can emit"
    )
    json.dumps(payload)


# ---------------------------------------------------------------------------
# The bounded sub-property -- **this is the one that CLOSES**
#
# ⭐ Everything above samples an infinite space, and this project has a rule
# about that: **an unbounded property cannot be closed by review.** A reviewer
# asked to construct a value the generator does not reach will construct one,
# every round, for ever, and each one will be genuine -- so the rounds are not
# converging on correctness, they are sampling.
#
# **So the claim that closes is a bounded one:**
#
#     for every payload a JSON decoder could have produced and ``from_dict``
#     accepts, ``to_dict`` emits JSON **and the fault marker never appears**,
#     **at any depth to the encoder's own ceiling**.
#
# ⚠️ **The depth clause is asserted rather than assumed, and it was not.** For
# one round this claim was quantified over `_DECODED_VALUES`, whose deepest
# member nests **3** levels, while the depth work above reached the interpreter's
# ceiling with a value built IN PROCESS -- never through `from_dict` -- and asserted
# JSON-emittability without ever asking about the marker. **Two dimensions, each
# asserted with the other held at its cheapest**, which is round 1's defect and
# round 2's defect a third time. Both cases below are quantified over
# `_BOUNDED_CASES`, and the deep one builds its value with `json.loads` so that
# "decoder-producible" is a fact about the value rather than this file's opinion
# of it.
#
# The marker's rarity becomes a property rather than a hope, and the space is
# genuinely bounded **in kind**: a decoder emits ``dict``, ``list``, ``str``,
# a number, a bool and ``None``, a JSON object is string-keyed, and the only
# other things ``from_dict`` builds are an ``ObjectRef`` of decoded values and
# the marker. Every one of those takes a branch that converts. No composition of
# them reaches the branch for the unknown, and that is an argument over a closed
# set of kinds rather than over a set of values.
#
# ⚠️ **"A payload a JSON decoder could have produced" is load-bearing and the
# qualifier is not a hedge.** ``from_dict`` takes a ``Mapping``, so a caller can
# hand it one built in process holding a set or an arbitrary object -- and the
# marker WOULD appear for that. That is the unbounded side by design, recorded on
# ``Operation``: fields accept anything so that ``validate`` can be the only
# judge. Stating the property without the qualifier would make it false in
# exactly the case the rest of this file exists for.
# ---------------------------------------------------------------------------

_DECODED_VALUES: tuple[object, ...] = (
    *WIRE_VALUES,
    [[{"a key": [1, "a value"]}]],
    {"a key": {"another key": [None, 1.5]}},
    {schema.UNCONVERTIBLE_KEY: "set"},
    {"a key": [{schema.UNCONVERTIBLE_KEY: "set"}]},
)
"""What a decoder can hand back where a field goes: the JSON types, and nested.

``WIRE_VALUES`` is the whole space one level deep, and the two composites are
there because "bounded in kind" is a claim about composition too.

⚠️ **The last two spell the fault marker's own key, and they are the reason the
claim below is now true rather than merely untriggered.** A decoder produces
them as readily as anything else, ``from_dict`` used to accept them and
``to_dict`` re-emitted them byte-identical to a genuine conversion failure -- so
the closer asserted something false and stayed green only because nothing
sampled spelled the key. ``from_dict`` now RESERVES it, which is what makes the
marker injective; the closer skips them as structural refusals, and
``test_a_decoded_value_naming_the_fault_marker_is_refused_at_every_path`` is
what keeps that skip from being the vacuous way to pass.
"""


def _names_the_fault_marker(value: object) -> bool:
    """Whether the fault marker appears anywhere in an emitted payload.

    ⚠️ **An explicit stack rather than a recursion, for the reason recorded on
    ``_not_json``, and this is the THIRD walk to have needed it.** ``_not_json``
    was the first and the conversion itself was the second; this one was left
    recursive both times, because nothing had yet asked it a deep question. It
    died at ``_PAST_THE_FRAME_LIMIT`` the moment the closer above was quantified
    over depth -- **a test walk that cannot reach the depth it is testing asserts
    nothing**, which is now three helpers with the same defect discovered three
    separate times.

    ⚠️ **So the rule, written down here rather than learned a fourth time: a walk
    added to this file is written with an explicit stack from the start.** The
    one remaining recursion is ``_measured_depth``, and it is deliberate --
    it walks only ``GENERATED``, whose depth is a stated 6 that
    ``test_the_generated_values_reach_the_stated_depth`` pins.

    Traversal order carries no obligation here, unlike ``_not_json``, whose
    returned path is quoted in failure messages at seven call sites: this answers
    yes or no, so any order finds the same marker.

    Called on ``to_dict`` output, which is acyclic because the conversion breaks
    cycles with the fault marker -- the same standing as ``_not_json``.
    """
    stack: list[object] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if schema.UNCONVERTIBLE_KEY in item:
                return True
            stack.extend(item.values())
            continue
        if isinstance(item, list):
            stack.extend(item)
    return False


_BOUNDED_CASES = [
    (type_name, path)
    for type_name in sorted(EXAMPLES)
    for path in schema.required_paths(type(EXAMPLES[type_name]))
]

_RESERVED_DECODED_VALUES = [value for value in _DECODED_VALUES if _names_the_fault_marker(value)]
"""The decoded values that spell the reserved key, found by the detector itself.

Derived rather than listed, so a value added to ``_DECODED_VALUES`` carrying the
key is covered by the refusal test below without anything here being edited --
and, more to the point, cannot be added as a value the closer silently skips.
"""


def _decoder_produced_nesting(depth: int) -> object:
    """``depth`` nested JSON arrays, built by the DECODER rather than in process.

    ⚠️ **``json.loads`` rather than ``_nested_in_lists``, and the difference is
    the whole point of the case below.** The claim is quantified over what a
    decoder could have produced, and a value assembled in process is only
    decoder-producible *in kind* -- it is this file asserting that the kinds
    match, which is the assumption under test rather than evidence for it. Handed
    to the decoder, the qualifier is a fact about the value: this text went
    through ``json.loads`` and that is what came back.

    Ordinary arrays, because the dimension here is depth rather than breadth, and
    the string is built without recursing so the builder cannot share the ceiling
    it is building past.
    """
    return json.loads("[" * depth + "]" * depth)


@pytest.mark.parametrize(("type_name", "path"), _BOUNDED_CASES)
def test_a_payload_a_decoder_could_have_produced_reaches_the_wire_at_depth(
    type_name: str, path: str
) -> None:
    # ⚠️ **The two dimensions of the narrowed claim, crossed -- and each was
    # asserted with the other held at its cheapest.** The closer below quantifies
    # over `_DECODED_VALUES`, whose deepest member nests 3 levels; round 3's depth
    # work reaches the interpreter's ceiling but builds its value in process,
    # never through `from_dict`, and asserts JSON-emittability only, **not
    # marker-absence**. So
    # *decoder-producible* x *depth* is exactly the corner neither covers -- which
    # is round 1's defect and round 2's defect, one helper further out.
    #
    # No new dial: the existing `_PAST_THE_FRAME_LIMIT` is the deepest nesting
    # this interpreter's decoder produces at all, envelope included, so this
    # depth is one a decoder can in fact produce.
    deep = _decoder_produced_nesting(_PAST_THE_FRAME_LIMIT)

    try:
        operation = schema.from_dict(payload_with(type_name, path, deep))
    except schema.SchemaError:
        # Skipped rather than asserted about, exactly as the sibling closer does:
        # the property is quantified over what `from_dict` ACCEPTS, and a
        # structural refusal is the other error surface.
        return

    emitted = schema.to_dict(operation)

    assert not _names_the_fault_marker(emitted), (
        f"{type_name} carrying a decoder-produced value {_PAST_THE_FRAME_LIMIT} "
        f"deep at {path} emitted the fault marker, so the bounded claim holds at "
        "the depth it was sampled at rather than at the depth it states"
    )
    assert _not_json(emitted, "") is None
    json.dumps(emitted)


@pytest.mark.parametrize(("type_name", "path"), _BOUNDED_CASES)
def test_a_payload_a_decoder_could_have_produced_never_reaches_the_fault_marker(
    type_name: str, path: str
) -> None:
    # Payloads from_dict REFUSES are skipped rather than asserted about: the
    # property is quantified over what it accepts, and a structural refusal is
    # the other error surface, which this file has nothing to say about.
    assert not _names_the_fault_marker(schema.to_dict(EXAMPLES[type_name]))

    for value in _DECODED_VALUES:
        try:
            operation = schema.from_dict(payload_with(type_name, path, value))
        except schema.SchemaError:
            continue

        emitted = schema.to_dict(operation)

        assert not _names_the_fault_marker(emitted), (
            f"{type_name} carrying a decodable value at {path} emitted the fault "
            "marker, so the marker is reachable from the wire rather than only "
            "from a value built in process"
        )
        assert _not_json(emitted, "") is None
        json.dumps(emitted)


def test_the_decoded_values_include_one_that_names_the_fault_marker() -> None:
    # ⚠️ **A tripwire, in the style of the partition's.** The closer above passes
    # over a refused payload with ``continue``, so a value that spells the
    # reserved key satisfies it by being REFUSED -- and if no such value is in
    # the set at all, the refusal test below is quantified over nothing while
    # still reading as the thing that closed the marker's ambiguity. Green on
    # arrival and not evidence.
    assert _RESERVED_DECODED_VALUES, (
        "no decoded value spells the reserved key, so the closer above is once "
        "again true only because nothing sampled tests it"
    )


@pytest.mark.parametrize(("type_name", "path"), _BOUNDED_CASES)
def test_a_decoded_value_naming_the_fault_marker_is_refused_at_every_path(
    type_name: str, path: str
) -> None:
    # ⭐ **This is what makes the closer's skip meaningful rather than vacuous.**
    # The claim is quantified over what ``from_dict`` ACCEPTS, so a value it
    # refuses is skipped -- which is correct, and is also exactly how a payload
    # that quietly still round-tripped the marker would hide. So: refused at
    # every declared path, loudly, with a field path naming where.
    #
    # Two truthful surfaces answer, and the assertion is over what they share. A
    # reference ROOT is refused by ``_reference_from`` as an undeclared leaf,
    # everything else by the reservation itself; ``test_schema_serialisation.py``
    # pins which is which. A caller handles both by ``SchemaError`` and a path.
    for value in _RESERVED_DECODED_VALUES:
        with pytest.raises(schema.SchemaError) as raised:
            schema.from_dict(payload_with(type_name, path, value))

        field_path = getattr(raised.value, "field_path", "")

        assert field_path.startswith(path), (
            f"{type_name} refused a decoded value naming the fault marker at "
            f"{path}, but reported {field_path!r} -- a refusal with no path, or "
            "one pointing somewhere else, is one nobody can act on"
        )


# ---------------------------------------------------------------------------
# The OTHER side of the boundary -- best-effort, and what that honestly means
#
# ⚠️ **The bounded claim above is what closes. Everything outside it is
# BEST-EFFORT, and the boundary is stated rather than left to be discovered.**
# ``from_dict`` takes a ``Mapping``, and ``Operation``'s fields accept anything,
# so a caller can build a value in process that no decoder could have produced.
# **Interrogating such a value RUNS THE VALUE'S OWN CODE** -- ``list(item)`` calls
# its ``__iter__`` and its ``__len__``, ``id(item) in on_path`` is a set
# membership, ``isinstance`` reads its ``__class__`` -- and any of those may
# raise.
#
# ⭐ **What is guaranteed there is the SHAPE of the failure, not its absence: an
# exception from the caller's own object arrives AS ITSELF -- same type, same
# message -- never masked as the fault marker and never swallowed.** The measured
# residual, all three at ``target.handle`` of the ``add_note`` example:
#
#   released memoryview              to_dict=ValueError   validate=FIELD_WRONG_TYPE
#   Sequence whose __iter__ raises   to_dict=ValueError   validate=FIELD_WRONG_TYPE
#   Sequence whose __len__ raises    to_dict=ValueError   validate=FIELD_WRONG_TYPE
#
# ⚠️ **This is not a closable set and the three are not an enumeration to be
# extended.** ``__iter__``, ``__len__``, ``__eq__``, ``__hash__``, ``__getitem__``
# and a raising ``__class__`` are ONE defect with no enumeration, because the
# defect is *interrogation runs the object's own code* rather than any particular
# dunder. A fourth is always constructible, which is exactly why the claim is
# bounded above instead of being defended here.
#
# ⚠️ **THE REMEDY IS ``validate``, and it is the reason no handler is added
# here.** It reads the object **without transporting it** and returns
# FIELD_WRONG_TYPE at the path, in every case measured -- so a caller wanting a
# verdict on a pathological value already has one that works.
#
# ⚠️ **A FENCE, not evidence** -- green on arrival, the same standing as
# ``test_a_mapping_keeps_its_key_order_on_the_wire``. Its job is to make the
# broad exception handler the owner ruled against **fail a test rather than pass
# review**: a blanket ``except Exception`` would return a payload here instead of
# raising, making our own defect indistinguishable from the caller's bad data.
# ---------------------------------------------------------------------------

_A_MESSAGE_ONLY_THE_CALLERS_ITERATION_COULD_RAISE = "Quillon-Vasterby-9903"
"""Invented, distinctive, and the same register and rule as ``SENTINELS``.

Distinctive because the assertion is that the CALLER's message arrives, and a
generic one would pass against a message this module invented. A bare token
rather than a sentence, no path separator and no ``~``, because this is a
literal in a tracked file the guard scans.
"""

_A_MESSAGE_ONLY_THE_CALLERS_LENGTH_COULD_RAISE = "Merrowbeck-Talvane-2216"
"""Its own value, not shared with the one above: two objects failing by two
different dunders must be distinguishable, or one test passes on the other's
exception."""


class _IterationRaises(Sequence[object]):
    """A ``Sequence`` that refuses to be iterated, raising the caller's own error.

    A real ``Sequence`` registration rather than an arbitrary object, and that is
    the whole point: an arbitrary object takes the branch for the unknown and
    gets the fault marker without anything being run. Reaching the code that
    **interrogates** the value requires passing the isinstance check first.
    """

    def __iter__(self) -> Iterator[object]:
        raise ValueError(_A_MESSAGE_ONLY_THE_CALLERS_ITERATION_COULD_RAISE)

    def __getitem__(self, index: int) -> object:
        raise ValueError(_A_MESSAGE_ONLY_THE_CALLERS_ITERATION_COULD_RAISE)

    def __len__(self) -> int:
        return 1


class _LengthRaises(Sequence[object]):
    """A ``Sequence`` whose length cannot be taken. The other dunder, same defect.

    Two of them rather than one, because ``list(value)`` consults both and a fix
    that guarded only the first would leave this one raising -- which is the
    "patch the shape you were shown" failure this module has refused three times.
    """

    def __getitem__(self, index: int) -> object:
        raise IndexError(index)

    def __len__(self) -> int:
        raise ValueError(_A_MESSAGE_ONLY_THE_CALLERS_LENGTH_COULD_RAISE)


def _a_released_memoryview() -> memoryview:
    """A buffer whose every operation now raises. Not a hand-written pathology.

    ⚠️ **The one of the three that is a STANDARD LIBRARY type**, and it reaches
    the sequence branch by a route that is not incidental: ``_collections_abc``
    carries ``Sequence.register(memoryview)``, so this is stable across 3.10-3.12
    rather than an accident of one version. A reader who dismisses the two
    hand-written classes as contrived has to account for this one.
    """
    view = memoryview(bytearray(b"abc"))
    view.release()
    return view


_THE_RESIDUAL: Mapping[str, tuple[object, str | None]] = MappingProxyType(
    {
        "a released memoryview": (_a_released_memoryview(), None),
        "a sequence whose iteration raises": (
            _IterationRaises(),
            _A_MESSAGE_ONLY_THE_CALLERS_ITERATION_COULD_RAISE,
        ),
        "a sequence whose length raises": (
            _LengthRaises(),
            _A_MESSAGE_ONLY_THE_CALLERS_LENGTH_COULD_RAISE,
        ),
    }
)
"""The measured residual, with the message each caller's object raises.

``None`` for the memoryview: its message is CPython's own, and pinning a message
this repository does not author would be a test of the standard library's
wording. Its **type** is pinned like the others.
"""


@pytest.mark.parametrize("description", sorted(_THE_RESIDUAL))
def test_an_exception_from_the_callers_own_object_propagates_as_itself(
    description: str,
) -> None:
    value, message = _THE_RESIDUAL[description]
    operation = _carrying_at_the_first_leaf("add_note", value)

    with pytest.raises(ValueError) as raised:
        schema.to_dict(operation)

    if message is not None:
        assert str(raised.value) == message, (
            f"{description} was transported and the caller's own message did not "
            "survive, so the exception was masked rather than propagated"
        )

    # The remedy, asserted rather than promised: the verdict the caller wants
    # exists on the same operation, from the surface that reads the object
    # WITHOUT transporting it.
    verdict = schema.validate(operation)

    assert not verdict.well_formed
    assert [(violation.rule, violation.field_path) for violation in verdict.violations] == [
        (RuleId.FIELD_WRONG_TYPE, _first_reference_leaf(type(EXAMPLES["add_note"])))
    ], f"{description} has no verdict from validate, so the residual has no remedy"
