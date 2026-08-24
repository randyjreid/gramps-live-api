"""#103's ratchet: every reachable ``priv``-carrying container is gated.

⭐ **The criterion, stated as bounded:** *every ``priv``-carrying container the
frozen checklist names, reachable from any accessor path, is gated.* That closes.
⛔ *"No private data reaches the wire"* does not, and is **not** what this claims.

⚠️ **This is a RATCHET, not remediation.** The audit that motivated it found
**every reachable container already gated and nothing leaking.** Its entire value
is what it refuses tomorrow, and saying so plainly matters: a test introduced as
a fix implies there was something to fix, and the next reader would go looking
for it.

**Why it exists anyway.** Rounds 2, 4 and 5 of PR #104 each found a *different*
container ungated -- ``eventref``/``childref``/``personref``, then the membership
backlink, then ``name`` -- by review rather than by audit. **Three genuine,
non-repeating findings in three consecutive rounds is the shape of a criterion
with no fixed point**, and the answer to that is a bound, not more rounds.

## What the ratchet reads

1. The ``priv`` rows of ``core/_specified_containers.py`` -- derived from the
   published DTD against recorded digests, so **re-derivable and diffable**:
   re-fetch, compare digest, re-run, and the diff is empty. ⭐ That is the
   licensed form of a frozen table rather than a hand-written list.
2. ``tests/fixtures/privacy_containers.py`` -- the container-to-getter map.
3. ``accessor.py``'s own source.

## ⛔ The fail-open, recorded here because a bound that reads as a proof is worse
## than no bound

**The map in (2) is hand-written and cannot be derived from the DTD**, which
names containers and not Python methods. **A getter nobody lists makes its
container read as unreachable.** ``test_the_accessor_calls_no_getter_the_map_has_
never_heard_of`` is the mitigation and not a cure: it catches a container-shaped
name the map does not know, and it cannot catch a getter shaped like nothing.

⚠️ **And two further limits, both measured rather than supposed:**

* **Gating is checked per RECEIVING VARIABLE, not per container.** A function
  that reaches two containers and gates one satisfies this for both. The
  per-container work is done by the sibling tests --
  ``test_accessor_privacy_gate.py``'s reference and name bounds -- and by the
  behavioural tests in ``test_accessor_reads.py``.
* ⛔ **A private RELATIONSHIP between two public records is outside this
  entirely.** Round 4's finding was exactly that, and gating every container
  would not have caught it: both ends were public and the ``ChildRef`` joining
  them was the private thing. **This bounds containers. It does not bound the
  graph.**
"""

from __future__ import annotations

import ast
import pathlib

from gramps_live_api.core import _specified_containers as checklist
from tests.fixtures import privacy_containers

ACCESSOR = (
    pathlib.Path(__file__).resolve().parents[2] / "src" / "gramps_live_api" / "host" / "accessor.py"
)

GATE = "_public"
PRIVACY = "get_privacy"


def priv_containers() -> set[str]:
    """Every container the CHECKLIST says carries ``priv``. ⛔ Derived, never listed.

    ⚠️ **A hand-written list got this wrong the first time.** An audit read the
    rows with a regular expression matching ``[a-z]*`` and silently dropped
    ``lds_ord`` -- an underscore -- reporting **19** where the checklist holds
    **20**. The conclusion happened to survive because ``lds_ord`` is
    unreachable, and it need not have.
    """
    return {
        container
        for container, attribute, _ in checklist.SPECIFIED_ATTRIBUTES
        if attribute == "priv"
    }


def _accessor_tree() -> ast.Module:
    return ast.parse(ACCESSOR.read_text(encoding="utf-8"), filename=str(ACCESSOR))


def _functions(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def _called_getters(function) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def _functions_that_gate_their_argument(tree: ast.Module) -> dict[str, set[int]]:
    """``function name -> which of its parameter POSITIONS it proves it gates.``

    ⛔ **Delegation is gating, and refusing to model it would have been the guard
    switching itself off.** ``_person_names`` hands each ``Name`` to
    ``_name_spellings``, which gates it and returns nothing when it is private.
    That is round 5's chosen design -- a ``Name`` may only be taken apart inside
    two helpers, both of which gate -- and it is *stronger* than gating inline,
    because it confines the unsafe operation rather than repeating the check.

    ⚠️ **So this proves the delegation rather than assuming it.** A helper counts
    only if its own body hands that exact parameter to ``_public`` or asks it for
    ``get_privacy``. A helper that merely looks trustworthy counts for nothing.

    ⛔ **One level, not transitive.** A helper delegating to a helper is not
    recognised, and would fail here rather than pass -- the safe direction, and
    recorded so the next reader knows it is a limit rather than an oversight.
    """
    gating: dict[str, set[int]] = {}
    for function in _functions(tree):
        proven = _gated_names(function)
        positions = {
            index for index, argument in enumerate(function.args.args) if argument.arg in proven
        }
        if positions:
            gating[function.name] = positions
    return gating


def _gated_names(function) -> set[str]:
    """Names this function hands to ``_public``, plus names it asks ``get_privacy`` of.

    ⚠️ **Both mechanisms, and that is the whole difficulty.** ``_public`` guards
    direct fetches; the five iterating routes instead pass a privacy flag into
    ``reads.bound``, which drops private rows before counting so they are in
    neither the results nor ``matched``. **A test that knew only ``_public``
    would fail loudly on five correct routes** -- and a guard that fails on
    correct code is a guard somebody switches off.
    """
    names: set[str] = set()

    # ⛔ A ``get_privacy()`` whose RESULT IS THROWN AWAY is not a gate. Crediting
    # any invocation let a route call ``url.get_privacy()`` on its own line and
    # then return private content with this test green -- the guard failing open,
    # which is worse than no guard.
    discarded = {
        id(node.value)
        for node in ast.walk(function)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    }
    # ⚠️ **What this does NOT detect, stated rather than left to be found.** A
    # flag that is read and USED but reaches nothing -- ``if x.get_privacy():
    # pass`` -- still counts. An earlier version of this fix also required the
    # function to call ``reads.bound``, which is tighter and WRONG: it reported
    # ``person_status`` as ungated, whose entire job is to answer whether a
    # person is private and which the sibling gate test already exempts by name.
    # The reported hole was the DISCARDED read, and that is what is closed here.

    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == GATE:
            names.update(arg.id for arg in node.args if isinstance(arg, ast.Name))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == PRIVACY
            and isinstance(node.func.value, ast.Name)
            and id(node) not in discarded
        ):
            names.add(node.func.value.id)
    return names


def _getter_sites(
    function, getters: set[str], delegates: dict[str, set[int]] | None = None
) -> list[tuple[str, str | None, int]]:
    """Every call to one of ``getters``, classified by how its result is handled.

    ``("wrapped", None, line)``
        the call sits directly inside ``_public(...)`` -- ``_public(db.get_event_
        from_handle(h))`` -- so it is gated at the call site and there is no
        variable to check.
    ``("receiver", name, line)``
        the result is assigned to, or iterated into, ``name``.
    ``("opaque", None, line)``
        neither. ⛔ **Fails closed.** ``person.get_url_list()[0].get_path()``
        materialises a container through a shape this cannot follow, and a check
        that verified nothing must not answer *fine*.
    """
    sites: list[tuple[str, str | None, int]] = []

    def is_getter(node) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in getters
        )

    # ⭐ A getter is gated AT THE CALL SITE when it sits inside ``_public(...)``
    # or inside a helper already PROVEN to gate that argument position --
    # ``_name_shown(person.get_primary_name())``. Recognising only ``_public``
    # reported nine correctly-gated call sites as unverified, and a guard that
    # fails on correct code is a guard somebody switches off.
    proven = delegates or {}
    wrapped: set[int] = set()
    for node in ast.walk(function):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id == GATE:
            positions = set(range(len(node.args)))
        else:
            positions = proven.get(node.func.id, set())
        for index, argument in enumerate(node.args):
            if index not in positions:
                continue
            for inner in ast.walk(argument):
                if is_getter(inner):
                    wrapped.add(id(inner))

    accounted: set[int] = set()
    for node in ast.walk(function):
        target_name = None
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            found = [n for n in ast.walk(node.iter) if is_getter(n)]
            target_name = node.target.id if found else None
            for call in found:
                accounted.add(id(call))
                sites.append(("receiver", target_name, node.lineno))
        elif isinstance(node, ast.Assign):
            found = [n for n in ast.walk(node.value) if is_getter(n)]
            names = [tgt.id for tgt in node.targets if isinstance(tgt, ast.Name)]
            for call in found:
                accounted.add(id(call))
                if id(call) in wrapped:
                    sites.append(("wrapped", None, node.lineno))
                elif names:
                    sites.append(("receiver", names[0], node.lineno))
                else:
                    sites.append(("opaque", None, node.lineno))

    for node in ast.walk(function):
        if is_getter(node) and id(node) not in accounted:
            kind = "wrapped" if id(node) in wrapped else "opaque"
            sites.append((kind, None, node.lineno))
    return sites


def _names_handed_to_a_gating_helper(function, delegates: dict[str, set[int]]) -> set[str]:
    """Names this function passes into a helper PROVEN to gate that position."""
    names: set[str] = set()
    for node in ast.walk(function):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        positions = delegates.get(node.func.id)
        if not positions:
            continue
        for index, argument in enumerate(node.args):
            if index in positions and isinstance(argument, ast.Name):
                names.add(argument.id)
    return names


def test_the_checklist_still_names_twenty_priv_containers() -> None:
    """⚠️ The pin on the derived input, so a re-derivation that changes it is seen.

    Not a magic number: a **diff detector**. If a re-derived checklist adds a
    container, this fails and the ratchet's coverage is reconsidered
    deliberately rather than silently widening or narrowing.
    """
    assert len(priv_containers()) == 20, (
        "the checklist's priv-carrying container set changed; re-run the audit "
        f"before adjusting this number. Now: {sorted(priv_containers())}"
    )


def test_every_reachable_priv_container_is_gated() -> None:
    """⭐ The ratchet. A new route inherits the bound by being written.

    Reachability is computed **from the accessor's source**, so a route that
    calls ``get_url_list()`` makes ``url`` reachable *and starts requiring a gate
    for it in the same commit*. Nobody has to remember; the failure arrives with
    the change that caused it.
    """
    tree = _accessor_tree()
    functions = list(_functions(tree))
    delegates = _functions_that_gate_their_argument(tree)
    offenders: list[str] = []

    for container in sorted(priv_containers()):
        object_getters = set(privacy_containers.YIELDS_OBJECT.get(container, ()))
        handle_getters = set(privacy_containers.YIELDS_HANDLE.get(container, ()))
        if not object_getters and not handle_getters:
            continue

        reached_by_handle = False
        materialised = False

        for function in functions:
            called = _called_getters(function)
            if called & handle_getters:
                reached_by_handle = True
            if not (called & object_getters):
                continue
            materialised = True
            gated = _gated_names(function) | _names_handed_to_a_gating_helper(function, delegates)
            for kind, name, line in _getter_sites(function, object_getters, delegates):
                if kind == "wrapped":
                    continue
                if kind == "opaque":
                    # ⛔ FAIL CLOSED -- see ``_getter_sites``. A shape this
                    # cannot follow is not a shape it may bless.
                    offenders.append(
                        f"{container}: {function.name} reaches it on line {line} "
                        "through a shape with no checkable receiver, so nothing "
                        "was verified"
                    )
                elif name not in gated:
                    offenders.append(
                        f"{container}: {function.name} takes {name!r} from a "
                        f"{container} getter on line {line} and never gates it"
                    )

        if reached_by_handle and not materialised:
            # ⛔ Round 4's shape as a rule: a container reached only through
            # handles is a container nothing ever gated, because a handle cannot
            # be gated and no fetch turned it into an object.
            offenders.append(
                f"{container}: reached through handles only, so nothing ever "
                "materialised it to gate"
            )

    assert offenders == [], "ungated priv-carrying containers:\n  " + "\n  ".join(offenders)


def test_the_accessor_calls_no_getter_the_map_has_never_heard_of() -> None:
    """⛔ The mitigation for the hand-written map, and it is not a cure.

    A container-shaped getter the map does not know would make its container read
    as unreachable and the ratchet above would pass vacuously. This fails
    instead. ⚠️ It recognises a *shape*, so a getter shaped like nothing still
    escapes -- which is the fail-open this file's docstring records.
    """
    known = privacy_containers.every_mapped_getter()
    shaped = []
    for function in _functions(_accessor_tree()):
        for name in _called_getters(function):
            if name in known:
                continue
            if name.endswith(("_ref_list", "_from_handle", "_from_gramps_id")) or name.startswith(
                "iter_"
            ):
                shaped.append(f"{function.name}: {name}")

    assert shaped == [], (
        "the accessor calls container-shaped getters the privacy map does not "
        "know, so their containers read as unreachable: " + "; ".join(sorted(set(shaped)))
    )
