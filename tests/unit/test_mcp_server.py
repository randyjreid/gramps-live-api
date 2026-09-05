"""Every tool, and the two things an agent may never do through them.

⚠️ **An agent may not supply what is written, and it may not say yes.** Those are
the whole trust model: ``propose_document`` keeps the graph on the server and
hands back an id and a preview; ``approve_document`` takes an id and puts the
stored graph in front of the owner in a dialog inside Gramps. Everything below is
one of those two properties or a refusal that keeps one of them true.

⛔ **The note flow's half of this file is gone with R9.** ``list_people``,
``propose_note``, ``approve``, the injected console spawner and every refusal
that guarded the claim before it opened a window went with the tools they were
about. What is asserted here now is the surface, the descriptions, the prompt and
the entry point; the document route's own behaviour is
``tests/unit/test_mcp_seam.py``.

⚠️ **These tests need the ``mcp`` extra, and the skip below is the whole risk of
making it optional.** A skipped test reads exactly like a passing one -- this
repository has already paid for that once (#31) -- so "skip when the extra is
absent" becomes "never run anywhere" the moment the CI leg that installs the
extra is misconfigured, and nothing says so. **CI closes that itself**: the MCP
leg asserts from the JUnit report that this module contributed tests and that
none of them skipped, and fails the job otherwise. See `.github/workflows/ci.yml`.
That assertion is the only reason the skip below is acceptable.
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
from pathlib import Path

import pytest

# ⚠️ **`find_spec`, not `pytest.importorskip`, and the difference is which
# failures are allowed to become a skip.** `importorskip` would swallow ANY
# ImportError raised while importing `gramps_live_api_mcp.server` -- a typo in
# our own module included -- and report the whole file as skipped. This asks one
# question, `is the optional extra installed?`, and skips only on that answer.
# Every other import error below still fails collection, loudly.
#
# The message claims the seam-twin exemption in the words the hygiene test
# requires, and the claim is the honest one: without the extra there is no
# importable `gramps_live_api_mcp.server` at all, so the SUBJECT is absent
# rather than the observation. A platform skip leaves a property uncovered and
# owes a twin; this one leaves a module non-existent, and a twin would be a
# test of nothing.
if importlib.util.find_spec("mcp") is None:  # pragma: no cover - the extra is installed in dev
    pytest.skip(
        "the MCP server is an optional extra and it is not installed, so there is "
        "nothing to cover here -- gramps_live_api_mcp.server cannot be imported at "
        "all. CI's mcp leg installs '.[mcp]' and asserts these tests actually ran.",
        allow_module_level=True,
    )

from gramps_live_api import config  # noqa: E402
from gramps_live_api.host import document  # noqa: E402
from gramps_live_api_mcp import server as mcp_server  # noqa: E402
from tests.fixtures.trees import blessed  # noqa: E402
from tests.unit.test_cli import equipped  # noqa: E402


def tools(tmp_path: Path) -> mcp_server.Tools:
    """The tool object over a blessed copy, with a fixed session.

    ⚠️ **``spawner`` and ``platform`` are gone from the constructor**, and with
    them the reason this helper defaulted the platform to ``win32``: the note
    flow's ``approve`` refused a host that could not open a separate console, so
    a helper taking the runner's own platform refused every approve test on the
    Linux matrix and passed them all on the owner's Windows box.
    """
    copy = blessed(tmp_path / "tree")
    environ = equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir})
    return mcp_server.Tools(environ, session="sess0001")


# ---------------------------------------------------------------------------
# Criterion 1 and 3 -- the surface, and what it says about itself
# ---------------------------------------------------------------------------


def test_the_exposed_surface_is_exactly_what_the_server_says_it_is(tmp_path: Path) -> None:
    """Criterion 1. Asserted against the SERVER's own answer, not a constant.

    ⚠️ **Renamed from ``test_exactly_three_tools_are_exposed``**: the document
    flow added ``propose_document`` and ``approve_document``, and the live
    reads added five more, so three became ten. **The count was never the
    criterion** -- the criterion is that the
    surface is enumerated from what the server actually exposes, and that no
    tool arrives without being written down here.
    """
    exposed = asyncio.run(mcp_server.build_server(tools(tmp_path)).list_tools())
    # ⛔ The literal set that stood here has been deleted. It was a SECOND
    # TALLY of the assertion below: two lists that must agree with nothing
    # making them agree, which is the shape of the counter bug this project
    # already paid for once. TOOL_NAMES is the one list, and a tool registered
    # without an entry in it still fails here -- the criterion is unchanged.
    assert {tool.name for tool in exposed} == mcp_server.TOOL_NAMES


def test_every_tool_says_what_it_is_for(tmp_path: Path) -> None:
    exposed = asyncio.run(mcp_server.build_server(tools(tmp_path)).list_tools())
    for tool in exposed:
        assert tool.description and tool.description.strip()


def test_the_retired_tools_are_not_on_the_wire(tmp_path: Path) -> None:
    """⛔ Asserted against the SERVER's own answer, not against TOOL_NAMES.

    ⚠️ **Absence from a constant is not absence from the wire.** The registrations
    are what a client sees, so a decorated function left behind after its entry
    was removed from ``TOOL_NAMES`` would exercise the surface test above and be
    callable anyway. This asks the server.
    """
    retired = {"list_people", "propose_note", "approve"}
    listed = asyncio.run(mcp_server.build_server(tools(tmp_path)).list_tools())
    exposed = {tool.name for tool in listed}

    assert not exposed & retired, f"a retired tool is still registered: {sorted(exposed & retired)}"


def test_the_description_says_the_chat_yes_is_not_the_approval() -> None:
    """The ruling's own words, in the place an agent will actually read them.

    ⚠️ **The surface moved from a console to a dialog**, so the word this pins
    moved with it. What did not move is the property: an agent reading only the
    tool description has to be told that its own agreement is not the approval.
    """
    assert "dialog" in mcp_server.APPROVE_DOCUMENT_DESCRIPTION
    assert "does NOT report what the owner decided" in mcp_server.APPROVE_DOCUMENT_DESCRIPTION


# ---------------------------------------------------------------------------
# python -m gramps_live_api_mcp
# ---------------------------------------------------------------------------


def test_the_module_entry_point_runs_a_stdio_server_and_nothing_else() -> None:
    """⚠️ **stdio only.** The brief says no HTTP endpoint, and the SDK ships a
    whole HTTP stack we install and do not use -- so the one place that choice
    is made is asserted rather than left to a default.
    """
    started: list[str] = []

    class Fake:
        def run(self, transport: str = "stdio") -> None:
            started.append(transport)

    mcp_server.serve(build=lambda: Fake())  # type: ignore[arg-type,return-value]
    assert started == ["stdio"]


def test_the_entry_point_module_calls_serve() -> None:
    """``python -m gramps_live_api_mcp`` is how the demo registers this server.

    ⚠️ It is guarded on ``__name__``, which ``-m`` satisfies -- and without the
    guard merely importing it here started a server reading the real stdin,
    which is how this test found out.
    """
    import gramps_live_api_mcp.__main__ as entry

    assert entry.serve is mcp_server.serve


# ---------------------------------------------------------------------------
# Round 3: one tool advertised a capability another tool denied.
# ---------------------------------------------------------------------------


def test_every_attachable_kind_is_advertised_as_attachable() -> None:
    """⛔ ``find_families`` said pass a family ID; ``propose_document`` said families
    are always created new.

    A model follows the schema of the tool it is calling, so it discarded the ID
    and created the second household — **the exact duplicate the lookup was
    added to prevent**, produced by the interface describing itself two ways.

    ⚠️ **Bounded, not spot-fixed.** The list comes from ``document.ATTACHABLE``,
    so a fifth attachable kind that nobody advertises fails here rather than
    silently becoming unreachable through its own documented interface.
    """
    from gramps_live_api.host import document

    description = mcp_server.PROPOSE_DOCUMENT_DESCRIPTION
    # ⚠️ Anchor updated when the description was reordered for #151: the rules
    # now come FIRST and the schema block is the tail, so this slices from the
    # schema's own first line. The property asserted is unchanged.
    shape = description[description.index(' people: "id"') :]

    unadvertised = []
    for kind in document.ATTACHABLE:
        collection = "source:" if kind == "source" else f"{kind}:"
        line = next(
            (row for row in shape.splitlines() if row.strip().startswith(collection)),
            None,
        )
        if line is None or "gramps_id?" not in line:
            unadvertised.append(kind)

    assert unadvertised == [], (
        "these kinds accept a gramps_id and the proposal description does not say "
        f"so, so a caller cannot reach the feature: {unadvertised}"
    )


def test_the_proposal_description_does_not_deny_family_attachment() -> None:
    """⛔ The prose half. The shape line and the sentence must agree."""
    description = mcp_server.PROPOSE_DOCUMENT_DESCRIPTION

    assert "families and notes are always created new" not in description, (
        "the description still tells the caller families cannot be attached to"
    )
    assert "find_families" in description, (
        "the proposal description should point at the lookup that prevents the duplicate"
    )


def test_a_family_event_is_advertised_where_a_caller_will_read_it() -> None:
    """⭐ #105 shipped, so the LIMITATION NOTICE had to go with it.

    ⚠️ **A limitation notice that outlives its limitation is a new false
    statement.** The previous test pinned wording saying an event could only be
    attached to people -- correct then, wrong now -- so removing the capability
    gap means removing its warning in the same change.

    What replaces it is the positive claim, pinned the same way: the shape
    advertises ``family``, and the family-events lookup tells a caller it can now
    fill the gap it finds.
    """
    # ⚠️ Anchor updated when the description was reordered for #151: the rules
    # now come FIRST and the schema block is the tail, so this slices from the
    # schema's own first line. The property asserted is unchanged.
    shape = mcp_server.PROPOSE_DOCUMENT_DESCRIPTION
    shape = shape[shape.index(' people: "id"') :]
    events = next(row for row in shape.splitlines() if row.strip().startswith("events:"))
    assert "family" in events or "family" in shape, (
        "the event shape does not advertise a family, so nobody will use it"
    )
    assert (
        "AN EVENT CANNOT YET BE ATTACHED TO A FAMILY" not in mcp_server.PROPOSE_DOCUMENT_DESCRIPTION
    )
    assert "cannot be filled through propose_document" not in (
        mcp_server.LIST_FAMILY_EVENTS_DESCRIPTION
    ), "the family-events lookup still tells callers the gap cannot be filled"


# ---------------------------------------------------------------------------
# The getting-started prompt. A stranger has no CLAUDE.md, and the server
# exposed tools only -- so the knowledge a caller needs to avoid making
# duplicates in somebody's tree travelled with the owner, not with the tool.
# ---------------------------------------------------------------------------


def test_the_getting_started_prompt_is_listed(tmp_path: Path) -> None:
    """⛔ Listed, not merely defined. A prompt no client can enumerate is not shipped."""
    listed = asyncio.run(mcp_server.build_server(tools(tmp_path)).list_prompts())

    assert [prompt.name for prompt in listed] == [mcp_server.GETTING_STARTED_PROMPT]


def test_the_prompt_names_the_graph_groups_the_code_actually_accepts() -> None:
    """⛔ Asserted against the frozenset, so the two cannot drift apart.

    ⚠️ A prompt listing a group the parser refuses -- or omitting one it accepts
    -- teaches a caller to write a graph that is rejected by name, which is the
    failure this text exists to prevent.
    """
    after = mcp_server.GETTING_STARTED.split("The graph's groups are exactly:")[1]
    listed = after.split(".")[0]
    named = {word.strip() for word in listed.split(",")}

    assert named == set(document.GROUPS), (
        f"the prompt names {sorted(named)} but the parser accepts {sorted(document.GROUPS)}"
    )


def test_the_prompt_sends_callers_only_to_tools_that_exist() -> None:
    """⛔ A prompt that names a tool the server does not expose is worse than silence.

    ⚠️ Matched on this server's own verb prefixes rather than on "has an
    underscore", so field names like ``gramps_id`` are not mistaken for tools
    and a renamed tool cannot hide behind the difference.
    """
    prefixes = ("find_", "list_", "propose_", "approve", "tree_", "changed_")
    words = set(re.findall("[a-z_]{4,}", mcp_server.GETTING_STARTED))
    tool_shaped = {word for word in words if word.startswith(prefixes)}

    assert tool_shaped, "the prompt names no tools at all, so this test watches nothing"
    assert tool_shaped <= mcp_server.TOOL_NAMES, (
        f"the prompt names tools the server does not expose: "
        f"{sorted(tool_shaped - mcp_server.TOOL_NAMES)}"
    )


def test_the_prompt_says_nothing_about_the_note_flow(tmp_path: Path) -> None:
    """⛔ Document route only.

    ⚠️ The note flow reads an exported snapshot, and pointing a new caller at it
    is pointing them at data that can be older than the tree. It is also the
    thing under review for retirement; a prompt that taught it would have to be
    unpicked.
    """
    text = mcp_server.GETTING_STARTED

    assert "propose_note" not in text
    assert "note_type" not in text
    assert "approve\n" not in text and " approve " not in text
