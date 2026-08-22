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
    """Every Gramps fetch in the accessor, and whether it is wrapped in the gate."""
    tree = ast.parse(ACCESSOR.read_text(encoding="utf-8"), filename=str(ACCESSOR))

    enclosing: dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for child in ast.walk(node):
                enclosing[child] = node.name

    wrapped: set[int] = set()
    gated_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == GATE:
            for argument in node.args:
                wrapped.add(id(argument))
                # ⭐ ``raw = db.get_x(...)`` then ``obj = _public(raw)`` counts as
                # gated. That two-line form is REQUIRED by the routes with a
                # direct target: ``_public`` returns None for both *absent* and
                # *private*, and those must stay distinguishable, so the ungated
                # fetch is kept purely to tell them apart and is never read from.
                if isinstance(argument, ast.Name):
                    gated_names.add(argument.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in gated_names:
                    wrapped.add(id(node.value))

    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and FETCH.match(node.func.attr)
        ):
            found.append((enclosing.get(node, "<module>"), node, id(node) in wrapped))
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
