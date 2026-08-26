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

import importlib.util

import pytest

# ⚠️ **The `core` CI leg is deliberately dependency-free and ASSERTS that `mcp`
# is not importable** -- it fails the job if it is, because a leg that has the
# extra measures nothing. This module reads the tool descriptions, which live in
# the optional package, so it has to skip there or it breaks collection.
#
# ⛔ `find_spec`, not `pytest.importorskip`, matching `test_mcp_server.py`.
# `importorskip` swallows ANY ImportError -- a typo in our own module included --
# and reports the file as skipped. This asks one question, *is the optional extra
# installed?*, and skips only on that answer; every other import error still
# fails collection, loudly.
#
# ⚠️ This was caught by CI and not by the local gate, and could not have been:
# the dev environment has the extra, so the leg that proves the split is the one
# that cannot run here.
#
# ⭐ The skip claims the seam-twin exemption in the words the hygiene test
# requires, and the claim is the honest one: without the extra there is no
# importable module to read a description FROM, so the SUBJECT is absent rather
# than the observation. A platform skip leaves a property uncovered and owes a
# twin; this leaves the thing being measured non-existent, and a twin would be a
# test of nothing.
if importlib.util.find_spec("mcp") is None:  # pragma: no cover - installed in dev
    pytest.skip(
        "the MCP server is an optional extra and it is not installed, so there is "
        "nothing to cover here -- the descriptions live in "
        "gramps_live_api_mcp.server, which cannot be imported at all. CI's mcp leg "
        "installs '.[mcp]' and asserts these tests actually ran.",
        allow_module_level=True,
    )

import gramps_live_api_mcp.server as server  # noqa: E402


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


def test_every_lookup_the_description_names_reads_the_LIVE_TREE() -> None:
    """⛔ A lookup rule pointing at a stale source manufactures the duplicate.

    ⚠️ ``list_people`` reads the owner's XML **export** -- ``people.read_export`` --
    which can predate a person added to the open tree. ``find_people`` queries the
    live ``/find/people`` route. The compressed rule named the stale one **and**
    had dropped the caveat that made it safe, so a model told to *look it up
    first* could look, miss, and create the duplicate anyway.

    ⭐ Asserted against the implementations rather than by reading the sentence:
    every tool the rule names must reach the host, not the export.
    """
    import inspect
    import re

    text = server.PROPOSE_DOCUMENT_DESCRIPTION
    rule = text[text.index("*** LOOK IT UP BEFORE YOU CREATE") :]
    rule = rule[: rule.index("***", 3)]

    named = sorted(set(re.findall(r"\b(?:find|list)_\w+", rule)))
    assert named, "the lookup rule names no tools at all"

    source = inspect.getsource(server)
    stale = []
    for tool in named:
        body = re.search(rf"def {tool}\(self.*?(?=\n    def |\nclass )", source, re.S)
        assert body, f"the rule names {tool!r}, which the server does not define"
        if "read_export" in body.group(0):
            stale.append(tool)

    assert not stale, (
        "the lookup rule points at tools that read the XML export rather than the "
        f"open tree, so a recently added record can be missed and duplicated: {stale}"
    )


def test_the_lookup_rule_covers_every_kind_that_can_carry_a_gramps_id() -> None:
    """⛔ A kind with no lookup named is a kind the model will duplicate.

    ⚠️ ``place`` was omitted from the enumeration entirely while ``find_place``
    existed, so an existing place had no advertised way to be found.
    """
    from gramps_live_api.host import document

    text = server.PROPOSE_DOCUMENT_DESCRIPTION
    rule = text[text.index("*** LOOK IT UP BEFORE YOU CREATE") :]
    rule = rule[: rule.index("***", 3)]

    for kind in document.ATTACHABLE.values():
        if kind == "event":
            continue  # named by ownership, asserted in test_attachable_bound
        assert f"{kind} ->" in rule, (
            f"{kind!r} can carry a gramps_id and the lookup rule never says how to "
            f"find one, so a model creates a second copy instead: {rule}"
        )


def test_the_description_does_not_claim_family_children_are_DROPPED() -> None:
    """⛔ The blanket claim was false, and false in the direction that loses data.

    ⚠️ *"a node with gramps_id is attached to, never modified; its other fields are
    dropped"* is true of every field except a family's ``children``, which the
    writer commits onto the existing family. A caller believing the blanket claim
    omits the children it meant to add, and the omission is silent.
    """
    text = server.PROPOSE_DOCUMENT_DESCRIPTION
    claim = text[text.index('A node with "gramps_id" is ATTACHED TO') :][:320]

    assert "children" in claim, (
        f"the dropped-fields claim does not carve out a family's children: {claim}"
    )
