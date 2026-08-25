"""⛔ A tool description longer than the delivery budget is CUT, and the model is
never told what fell past the cut.

⚠️ Measured, not assumed: ``propose_document`` ran to 5618 characters and arrived
at **exactly 2048** -- 63% lost, mid-sentence. What fell past the cut was every
*look it up before you create it* rule, so a model received the exact shape of a
graph and no instruction to look anything up. It would then duplicate a person or
an event and hit **no refusal**, because creating is the default and legitimate.

⭐ The budget is **per tool, not shared**: loading that one description alone still
cut it at 2048, where a shared budget would have given it the whole allowance.

⛔ Enforced here rather than by reading the docstring and judging it short enough.
That check takes its answer from the reader instead of from the thing checked, and
it is the class that has failed repeatedly in this repository.
"""

from __future__ import annotations

import gramps_live_api_mcp.server as server


def _descriptions() -> dict[str, str]:
    """Every advertised description, found by NAME rather than listed.

    ⭐ So a tool added later inherits the ceiling instead of needing to be
    remembered -- the same reason ``ATTACHABLE`` drives the graph rules.
    """
    return {
        name: getattr(server, name)
        for name in dir(server)
        if name.endswith("_DESCRIPTION") and isinstance(getattr(server, name), str)
    }


def test_every_tool_description_is_delivered_WHOLE() -> None:
    """⛔ The ceiling, applied to all of them."""
    found = _descriptions()
    assert found, "no descriptions were found, so this test proves nothing"

    over = {
        name: len(text) for name, text in found.items() if len(text) > server.DESCRIPTION_BUDGET
    }
    assert not over, (
        "these descriptions are longer than the delivery budget of "
        f"{server.DESCRIPTION_BUDGET} characters and will be CUT mid-sentence, "
        f"with everything past the cut never reaching the model: {over}"
    )


def test_the_budget_is_measured_in_CHARACTERS_and_the_text_is_ascii() -> None:
    """⚠️ Characters and bytes agree only while every description is ASCII.

    ⭐ The cut was observed at 2048 on text where 5618 characters == 5618 bytes, so
    the two readings are **indistinguishable on that evidence**. This asserts the
    condition under which the constant stays meaningful; if a description gains a
    non-ASCII character the budget must be re-measured rather than trusted, and
    this test is where that is noticed.
    """
    for name, text in _descriptions().items():
        assert len(text) == len(text.encode("utf-8")), (
            f"{name} contains non-ASCII, so characters and bytes no longer agree "
            "and DESCRIPTION_BUDGET is no longer known to be the right unit -- "
            "re-measure the cut before changing this test"
        )


def test_the_rules_come_BEFORE_the_schema_in_propose_document() -> None:
    """⛔ Order is the safety property, not tidiness.

    ⚠️ If the tail is ever lost again, what is lost should make the tool **fail
    loudly** rather than quietly. A model missing the schema cannot build a graph
    at all and says so. A model missing a *lookup rule* builds a perfectly valid
    graph that silently duplicates a record -- which is what happened.

    ⭐ So the rules go first and the schema last, and that ordering is asserted
    rather than left to whoever edits next.
    """
    text = server.PROPOSE_DOCUMENT_DESCRIPTION
    rules = text.index("*** LOOK IT UP BEFORE YOU CREATE")
    schema = text.index(' people: "id"')

    assert rules < schema, (
        "the schema now precedes the lookup rules, so a future overflow would "
        "silently drop the rules and leave a model able to build a graph with no "
        "instruction to look anything up"
    )

    for rule in (
        "*** LOOK IT UP BEFORE YOU CREATE",
        "*** A MARRIAGE GOES ON THE FAMILY",
        "*** THE SHAPE BELOW IS EXACT",
        "*** ONE LOCAL ID PER RECORD",
    ):
        assert text.index(rule) < schema, f"{rule!r} fell after the schema block"
