"""Every object the accessor fetches goes through the privacy gate, asserted by reading it.

⚠️ **This test exists because A2 was enumerated rather than bounded.** It asked
*is the thing being returned private?* — and two leaks got through review as
separate patches because they were in what the returned thing **pointed at**:

1. a public person leaking a **private birth event's** date;
2. a public event leaking a **private place's** name;
3. and a third, found by audit rather than by review — ``/resolve`` answering
   ``found: true`` for a private record, confirming its existence to the agent.

⭐ **Three instances of one class is the signature of a rule with no fixed
point.** Patching the third would have been the same mistake as patching the
first two, so the bound is structural instead: **every** fetch goes through
``_public``, and this test reads ``accessor.py`` to say so.

⭐ **The shape is deliberately the thread-boundary test's.** That one discovers
accessor helpers by parsing the source rather than trusting a list, and it is
why a new helper cannot quietly skip ``@on_main_thread``. This does the same for
privacy: **a new read route inherits the bound by being written, not by somebody
remembering.**
"""

from __future__ import annotations

import ast
import pathlib
import re

ACCESSOR = (
    pathlib.Path(__file__).resolve().parents[2] / "src" / "gramps_live_api" / "host" / "accessor.py"
)

FETCH = re.compile(r"^get_\w+_from_(handle|gramps_id)$")
"""How Gramps hands back an object. Every one of these can carry ``priv``."""

GATE = "_public"

EXEMPT = {
    "person_status": (
        "⛔ DELIBERATE, and it is ruling 1's second enforcement point. This helper "
        "exists to answer 'does this ID name somebody, and may I use them' -- so it "
        "MUST fetch a private person and report private=True. Gating it would "
        "collapse 'no such person' and 'that person is private' into one answer, "
        "which is the exact thing the ruling forbids."
    ),
}


def fetch_calls() -> list[tuple[str, ast.Call, bool]]:
    """Every Gramps fetch in the accessor, and whether it is wrapped in the gate.

    ⚠️ **Everything here is resolved PER FUNCTION, and that is not tidiness.**
    An earlier version collected gated variable names module-wide, so because
    one route legitimately gates a variable called ``raw``, a future route
    containing an ungated ``raw = database.get_person_from_gramps_id(...)``
    counted as wrapped **without ever calling the gate.** The structural claim
    would then have passed while leaking -- a guard that reports success for a
    reason unrelated to the property, which is the failure this whole file
    exists to prevent one level down.
    """
    tree = ast.parse(ACCESSOR.read_text(encoding="utf-8"), filename=str(ACCESSOR))

    found: list[tuple[str, ast.Call, bool]] = []
    for function in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        # 1. calls passed straight into the gate, inside THIS function
        wrapped: set[int] = set()
        gated_names: set[str] = set()
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == GATE
            ):
                for argument in node.args:
                    wrapped.add(id(argument))
                    if isinstance(argument, ast.Name):
                        gated_names.add(argument.id)

        # 2. ``raw = db.get_x(...)`` then ``obj = _public(raw)`` -- but only when
        #    both halves are in the SAME function. That two-line form is required
        #    by the direct-target routes: ``_public`` returns None for both
        #    *absent* and *private*, and those must stay distinguishable.
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in gated_names:
                        wrapped.add(id(node.value))

        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and FETCH.match(node.func.attr)
            ):
                found.append((function.name, node, id(node) in wrapped))
    return found


def test_the_accessor_actually_contains_fetches() -> None:
    """A test that watches nothing passes for the wrong reason."""
    calls = fetch_calls()
    assert len(calls) >= 5, f"only found {len(calls)} fetches -- is the pattern still right?"


def test_every_fetch_goes_through_the_privacy_gate() -> None:
    """⛔ The bound. A new read route inherits it by being written."""
    ungated = [
        (where, node.func.attr, node.lineno)
        for where, node, is_wrapped in fetch_calls()
        if not is_wrapped and where not in EXEMPT
    ]
    assert ungated == [], (
        "these fetches do not go through _public(), so whatever they return can "
        f"leak its text even when the tree marks it private: {ungated}"
    )


def test_the_exemption_is_documented_and_still_applies() -> None:
    """⚠️ An exemption nobody can read is an exemption nobody re-checks.

    It is also asserted to be USED: an exemption for a helper that no longer
    fetches anything is a hole left open for a reason that has expired.
    """
    for name, reason in EXEMPT.items():
        assert len(reason) > 80, f"{name}'s exemption needs a reason, not a label"
        assert any(where == name for where, _, _ in fetch_calls()), (
            f"{name} is exempted but fetches nothing -- drop the exemption"
        )
