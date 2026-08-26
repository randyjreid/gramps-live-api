"""⛔ Two inputs the graph used to accept and quietly do the wrong thing with.

Both are the same principle: **the parser is the one place that decides what the
graph means**, so an input it tolerates is an input every consumer downstream has
to defend against separately -- and they drift.

* **An alias** -- two local ids naming one record -- produced two defects on one
  branch. The writer attached a citation twice; routing it through the existing
  ``_unique`` fixed the writer and left the renderer, so the dialog then promised
  two additions and one happened. ⚠️ **Correcting one side of a two-sided
  description is what creates the preview/writer class**, so the answer is not a
  second dedup but removing the two-sidedness.
* **An unknown key** was dropped in silence. ``people[].events`` -- the natural
  reverse of the supported ``events[].people`` -- linked nothing, raised nothing,
  and appeared nowhere in the dialog. The owner approved a preview that was
  accurate about what would be written and silent about what he had asked for.

⭐ Both are now refused **by name**, and both bounds are driven off the tables the
rest of the module is driven off, so a sixth group or kind inherits them.
"""

from __future__ import annotations

from typing import Any

import pytest

from gramps_live_api.host import document
from tests.fixtures.host_sources import REPOSITORY_ROOT

PERSON = {"id": "p0"}
"""⛔ **A local id and nothing else.**

⚠️ Deliberately carries no ``given``, ``surname``, ``title`` or ``page``. Every
group accepts a bare entry, so the descriptive fields were never needed here --
and a file about *which keys are accepted* had accumulated a dense cluster of the
very key names the repository's own P2 guard scores. **The guard refused this
file, correctly, and the fix is the content rather than the threshold.**

⭐ It also makes each test below change exactly one thing from a minimal entry.
"""


def _one_of(group: str, **fields: Any) -> dict[str, Any]:
    """A minimal valid entry for ``group``, so a test changes ONE thing.

    ⚠️ Three groups are not shaped like the rest and say so here rather than in
    each test: a note has no ``id``, a citation must name its source, and a
    family must name something to be written at all.
    """
    minimal: dict[str, Any] = {"id": "n1"}
    if group == "notes":
        minimal = {"text": "x"}
    elif group == "citations":
        minimal = {"id": "n1", "source": "s1"}
    elif group == "families":
        minimal = {"id": "n1", "gramps_id": "F0001"}
    return {**minimal, **fields}


# ---------------------------------------------------------------------------
# One local id per record
# ---------------------------------------------------------------------------


def test_an_ALIAS_is_refused_for_every_attachable_kind_naming_both_ids() -> None:
    """⛔ Driven off ``ATTACHABLE``, so a sixth attachable kind inherits it."""
    for group in document.ATTACHABLE:
        if group == "source":
            continue  # a single node cannot alias itself; asserted below.
        first = _one_of(group, id="n1", gramps_id="X0001")
        second = _one_of(group, id="n2", gramps_id="X0001")
        body: dict[str, Any] = {"people": [dict(PERSON)]}
        body[group] = (
            body.get(group, []) + [first, second]
            if group != "people"
            else [
                dict(PERSON),
                first,
                second,
            ]
        )

        with pytest.raises(document.GraphInvalid) as refused:
            document.parse(body)

        message = str(refused.value)
        assert "n1" in message and "n2" in message, (
            f"{group!r}: the refusal names only one id, so the caller must hunt "
            f"for the other: {message}"
        )
        assert "X0001" in message, f"{group!r}: the shared gramps_id is not named: {message}"


def test_the_SAME_id_string_on_DIFFERENT_kinds_is_not_an_alias() -> None:
    """⚠️ The key is (kind, gramps_id), not the id string.

    ⭐ Without this the bound above would pass against a check that refused any
    repeated string anywhere -- which would reject perfectly ordinary graphs.
    """
    assert (
        document.parse(
            {
                "people": [dict(PERSON), {"id": "n1", "gramps_id": "X0001"}],
                "events": [{"id": "n2", "gramps_id": "X0001"}],
            }
        )
        is not None
    )


def test_one_local_id_named_twice_in_a_LIST_is_still_allowed() -> None:
    """⭐ The other duplicate, deliberately still accepted.

    One node listed twice in ``children`` or ``attach_to`` is a single record
    named twice, not two descriptions of it -- so it has no two-sidedness to
    remove, and the writer's ``_unique`` collapses it. Refusing it would reject a
    harmless input and is not what the alias rule is about.
    """
    assert (
        document.parse(
            {
                "people": [dict(PERSON)],
                "families": [{"id": "f1", "gramps_id": "F0001", "children": ["p0", "p0"]}],
            }
        )
        is not None
    )


# ---------------------------------------------------------------------------
# Exactly the documented shape
# ---------------------------------------------------------------------------


def test_EVERY_group_has_a_key_set_so_none_escapes_the_check() -> None:
    """⛔ The bound: a new group cannot be added without declaring its shape.

    ⚠️ Without this, adding a group to ``GROUPS`` and forgetting ``NODE_KEYS``
    would raise ``KeyError`` at parse time, or -- worse, if the check were written
    defensively -- silently accept anything in it, which is the defect this file
    exists to close.
    """
    assert set(document.NODE_KEYS) == set(document.GROUPS), (
        "GROUPS and NODE_KEYS disagree about what groups exist: "
        f"{set(document.GROUPS) ^ set(document.NODE_KEYS)}"
    )


def test_an_unknown_key_is_refused_in_EVERY_group_naming_the_key_and_the_node() -> None:
    """⛔ Every group, including the two shaped differently: source and notes."""
    for group in document.GROUPS:
        body: dict[str, Any] = {"people": [dict(PERSON)]}
        entry = _one_of(group, invented_key="x")
        if group == "source":
            body["source"] = entry
        elif group == "people":
            body["people"] = [dict(PERSON), entry]
        else:
            body[group] = [entry]

        with pytest.raises(document.GraphInvalid) as refused:
            document.parse(body)

        message = str(refused.value)
        assert "invented_key" in message, f"{group!r}: the key is not named: {message}"
        assert group in message, f"{group!r}: the node is not named: {message}"


def test_an_unknown_GROUP_is_refused_because_it_drops_everything_in_it() -> None:
    """⚠️ The worst case: a misspelled group costs every node inside it."""
    with pytest.raises(document.GraphInvalid) as refused:
        document.parse({"people": [dict(PERSON)], "peple": [{"id": "x"}]})

    message = str(refused.value)
    assert "peple" in message and "node group" in message, message


def test_gramps_id_is_NOT_shadowed_by_the_unknown_key_check() -> None:
    """⛔ A general check must not steal a specific refusal's message.

    ``citations`` may not carry a ``gramps_id``, and the reason -- *a document
    asserting a fact is asserting a new claim* -- is what the caller needs. If
    ``gramps_id`` were merely 'unknown' for citations, that reason would be lost.
    """
    with pytest.raises(document.GraphInvalid) as refused:
        document.parse(
            {
                "people": [dict(PERSON)],
                "source": {"id": "s1"},
                "citations": [{"id": "c1", "gramps_id": "C0001", "source": "s1"}],
            }
        )

    message = str(refused.value)
    assert "always created" in message, (
        f"the specific refusal was shadowed by the unknown-key check: {message}"
    )


# ---------------------------------------------------------------------------
# What the model is TOLD must be what the parser DOES
# ---------------------------------------------------------------------------


def _advertised_shape() -> dict[str, set[str]]:
    """The per-group key sets the tool description advertises, parsed from it.

    ⛔ Parsed rather than restated. A second copy of the table in this file would
    be a third description of one thing, which is the class the whole module is
    about.
    """
    import re

    text = (REPOSITORY_ROOT / "src" / "gramps_live_api_mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    # ⚠️ The schema block now sits at the END of the description, after the rules,
    # so it is sliced from its own first line to the close of the constant rather
    # than between two headings. That reordering is deliberate and asserted in
    # tests/unit/test_tool_descriptions_fit.py: if the tail is ever cut again,
    # losing the schema fails loudly where losing a rule fails silently.
    block = text[text.index(' people: "id"') :]
    block = block[: block.index('"""')]
    shape: dict[str, set[str]] = {}
    current: str | None = None
    for line in block.splitlines():
        heading = re.match(r"\s*([a-z]+):\s", line)
        if heading and heading.group(1) in document.GROUPS:
            current = heading.group(1)
            shape[current] = set()
        if current and not line.strip().startswith("--"):
            # ⚠️ The description writes an optional key as ``"gramps_id?"`` --
            # the ``?`` is INSIDE the quotes -- so the pattern has to allow it
            # and strip it. A pattern that missed it read the description as
            # advertising no gramps_id at all.
            shape[current].update(
                found.rstrip("?") for found in re.findall(r'"([a-z_]+\??)"', line)
            )
    return shape


def test_the_ADVERTISED_shape_is_exactly_what_the_parser_accepts() -> None:
    """⛔ The description is a claim about the code, and it has been false before.

    ⚠️ ``role`` was advertised as *dropped and shown to the owner as dropped*
    after it had become refused, so a caller following the documented behaviour
    had its whole proposal rejected. **An advertised constraint that does not hold
    has already cost a round on this branch.**

    ⭐ Now that unknown keys are refused, the cost of drift is higher in the other
    direction too: a key the parser accepts but the description omits is a
    capability nobody uses, and a key the description names but the parser refuses
    is a documented instruction that fails.
    """
    advertised = _advertised_shape()

    assert set(advertised) == set(document.NODE_KEYS), (
        "the description and NODE_KEYS disagree about which groups exist: "
        f"{set(advertised) ^ set(document.NODE_KEYS)}"
    )

    for group, keys in document.NODE_KEYS.items():
        # ``gramps_id`` is advertised as ``gramps_id?`` only where it is allowed,
        # so compare on the mandatory shape and check the optional one separately.
        assert advertised[group] - {"gramps_id"} == keys, (
            f"{group!r}: the description advertises "
            f"{sorted(advertised[group] - {'gramps_id'})} but the parser accepts "
            f"{sorted(keys)}"
        )
        advertises_id = "gramps_id" in advertised[group]
        assert advertises_id == (group in document.ATTACHABLE), (
            f"{group!r}: the description "
            f"{'advertises' if advertises_id else 'does not advertise'} a gramps_id, "
            f"but the group is {'attachable' if group in document.ATTACHABLE else 'not'}"
        )


def test_the_description_TELLS_the_model_both_constraints() -> None:
    """⛔ A constraint the model is not told about does not exist.

    ⚠️ It meets these two by hitting them mid-document, and a refusal rejects the
    whole proposal -- so an undocumented rule costs a rebuild of the graph rather
    than a corrected field.
    """
    text = (REPOSITORY_ROOT / "src" / "gramps_live_api_mcp" / "server.py").read_text(
        encoding="utf-8"
    )

    assert "THE SHAPE BELOW IS EXACT" in text, "the model is not told unknown keys are refused"
    assert "people[].events" in text, (
        "the likeliest wrong key is not named, and it is the one a model reaches "
        "for because it is the reverse of a supported field"
    )
    assert "ONE LOCAL ID PER RECORD" in text, "the model is not told two ids for one record fail"
    assert "head of household" in text, (
        "the alias rule is stated without the shape that produces it, which is "
        "the census case this tool exists for"
    )


# ---------------------------------------------------------------------------
# What a failed lookup is told to do next
# ---------------------------------------------------------------------------


def test_EVERY_attachable_kind_has_a_lookup_tool_named() -> None:
    """⛔ The bound: a kind became attachable and the advice did not follow.

    ⚠️ That is exactly what happened -- events and families were made attachable
    while the refusal still named ``find_people / find_place / find_source``, so a
    caller holding an unresolvable event id was directed at three tools that
    cannot find one.
    """
    for kind in document.ATTACHABLE.values():
        assert kind in document.LOOKUP_TOOLS, (
            f"{kind!r} is attachable, so its gramps_id can fail to resolve, and "
            f"nothing tells the caller how to find one: {sorted(document.LOOKUP_TOOLS)}"
        )


def test_the_tools_the_advice_NAMES_actually_exist() -> None:
    """⛔ Advice pointing at a tool that does not exist is worse than none.

    ⭐ Same binding as the tool description: the text is a claim about the code,
    and a claim nobody checks is one that goes stale silently.
    """
    server = (REPOSITORY_ROOT / "src" / "gramps_live_api_mcp" / "server.py").read_text(
        encoding="utf-8"
    )
    named = set()
    for tool in document.LOOKUP_TOOLS.values():
        named.update(
            word for word in tool.replace(",", " ").split() if word.startswith(("find_", "list_"))
        )

    assert named, "the advice names no tools at all"
    for tool in sorted(named):
        assert f"def {tool}(" in server, (
            f"the refusal tells callers to use {tool!r}, which the server does not define"
        )


def test_the_advice_does_not_recommend_DROPPING_the_id() -> None:
    """⛔ The half that was actively harmful, asserted so it cannot come back.

    ⚠️ *"leave gramps_id out to create a new record"* is sound for a node that
    describes a record and wrong for one that does not. Following it on an event
    being cited writes a second copy of that event -- the duplication this feature
    exists to prevent, recommended by the feature's own refusal.

    ⭐ Stated as ONE property rather than a branch per kind, because the measured
    behaviour is broader than *"events are special"*: a node carrying only a
    gramps_id renders as an empty placeholder for people, places and sources too.
    Only a family refuses, needing parents, children or an id to be written at all.
    """
    advice = document.how_to_resolve_them()

    assert "Do NOT simply leave the gramps_id out" in advice, (
        f"the advice no longer warns against dropping the id: {advice}"
    )
    assert "only when the node also describes one" in advice, (
        "the warning is stated without the property that makes it true, so a "
        f"reader cannot tell when dropping the id IS correct: {advice}"
    )
    assert "second copy" in advice, (
        "the consequence for an event -- the one this branch exists to prevent "
        f"-- is not named: {advice}"
    )


def test_BOTH_refusal_sites_carry_the_SAME_advice() -> None:
    """⛔ Two messages saying one thing is the drift shape, and it drifted.

    ⭐ Asserted by identity, not by similarity: both must contain the shared
    function's output verbatim, so neither can be edited alone.
    """
    advice = document.how_to_resolve_them()

    resolution = document.Resolution(nodes=(document.Resolved("n1", "X0001", "event", False),))
    written = resolution.refusal()
    assert written is not None and advice in written, (
        f"Resolution.refusal() does not carry the shared advice: {written}"
    )

    # ⛔ **Comment lines are stripped before searching, and that is not fussiness.**
    #
    # ⚠️ A first version searched the whole file, and the negative control -- delete
    # the call, spell the advice out again -- **passed anyway**, because a comment
    # in that very function names ``document.how_to_resolve_them()`` in prose. The
    # assertion was satisfied by text ABOUT the code rather than by the code. Same
    # family as a fixture encoding the claim under test: the check succeeded for a
    # reason unrelated to the property it names.
    code = chr(10).join(
        line
        for line in (REPOSITORY_ROOT / "src" / "gramps_live_api_mcp" / "server.py")
        .read_text(encoding="utf-8")
        .splitlines()
        if not line.strip().startswith("#")
    )
    assert "document.how_to_resolve_them()" in code, (
        "the MCP refusal spells its own advice instead of sharing one copy, which "
        "is how the two went out of step in the first place"
    )


# ---------------------------------------------------------------------------
# The anchor: a graph must produce at least one committed change
# ---------------------------------------------------------------------------


def test_a_graph_that_would_write_NOTHING_is_refused() -> None:
    """⛔ Every node already exists and nothing attaches to any of them."""
    for body in (
        {"people": [{"id": "n1", "gramps_id": "I0001"}]},
        {
            "people": [{"id": "n1", "gramps_id": "I0001"}],
            "events": [{"id": "e1", "gramps_id": "E0060"}],
        },
        {"families": [{"id": "f1", "gramps_id": "F0001"}]},
    ):
        with pytest.raises(document.GraphInvalid) as refused:
            document.parse(body)
        assert "would not change the tree" in str(refused.value), str(refused.value)


def test_the_shape_the_PROXY_wrongly_refused_is_accepted() -> None:
    """⭐ The case #149 was filed for: a citation onto an existing event, no person.

    ⚠️ ``people`` non-empty was a PROXY for *at least one committed change*. This
    graph writes a source, a citation and an attachment, and names nobody -- and
    the proxy refused it as having "nothing to write". The only workaround was to
    bolt on an unrelated person, who then appeared in the approval dialog for no
    reason connected to the proposal.
    """
    assert (
        document.parse(
            {
                "source": {"id": "s1", "title": "Invented Register"},
                "citations": [{"id": "c1", "source": "s1", "attach_to": ["e1"]}],
                "events": [{"id": "e1", "gramps_id": "E0060"}],
            }
        )
        is not None
    )


def test_a_RESOLUTION_is_not_held_to_the_committed_change_rule() -> None:
    """⛔ Reading is not writing, and the old proxy made the same category error.

    ⚠️ ``resolve_nodes`` and ``/resolve`` ask *what do these ids point at?*.
    Requiring a committed change of them refuses a perfectly good lookup. The
    proxy had this error too and merely did not bite, because a resolution
    usually names people -- replacing it with the honest rule is what exposed it.

    ⭐ Polarity is deliberate: ``parse`` is STRICT by default and a reader opts out
    by name, so a write path added later that forgets gets the strict answer.
    """
    body = {"events": [{"id": "e1", "gramps_id": "E0060"}]}

    with pytest.raises(document.GraphInvalid):
        document.parse(body)

    assert document.parse(body, writes=False) is not None


def test_a_SPECIFIC_refusal_is_not_shadowed_by_the_anchor_rule() -> None:
    """⛔ Ordering. The anchor check runs LAST.

    ⚠️ Checked first, it reported *nothing to write* for a graph whose real fault
    was a refused ``role`` -- true, and useless, because the caller needed the
    specific fault named. Same rule as ``gramps_id`` passing the unknown-key check
    so its own refusal survives.
    """
    with pytest.raises(document.GraphInvalid) as refused:
        document.parse(
            {
                "people": [{"id": "p1", "gramps_id": "I0001"}],
                "events": [{"id": "e1", "gramps_id": "E0060", "role": "Primary"}],
            }
        )
    assert "role" in str(refused.value), (
        f"the anchor rule shadowed the role refusal: {refused.value}"
    )

    with pytest.raises(document.GraphInvalid) as unknown:
        document.parse({"people": [{"id": "p1", "gramps_id": "I0001", "nickname": "x"}]})
    assert "nickname" in str(unknown.value), (
        f"the anchor rule shadowed the unknown-key refusal: {unknown.value}"
    )


def test_an_existing_family_gaining_existing_children_IS_a_committed_change() -> None:
    """⭐ The one attachment that creates nothing and still writes.

    ⚠️ It is also the only reachable case in that half of the rule. ``attach_to``
    was checked alongside it and was **dead code** -- only citations and notes take
    ``attach_to``, and neither may carry a ``gramps_id``, so such a node is already
    counted as created. A negative control stayed SILENT on that branch, which is
    how it was found rather than reasoned about.
    """
    assert (
        document.parse(
            {
                "people": [{"id": "p1", "gramps_id": "I0001"}],
                "families": [{"id": "f1", "gramps_id": "F0001", "children": ["p1"]}],
            }
        )
        is not None
    )

    # ⛔ The same family WITHOUT the children writes nothing, and is refused.
    with pytest.raises(document.GraphInvalid) as refused:
        document.parse(
            {
                "people": [{"id": "p1", "gramps_id": "I0001"}],
                "families": [{"id": "f1", "gramps_id": "F0001"}],
            }
        )
    assert "would not change the tree" in str(refused.value)


def test_a_citation_that_can_reach_NO_source_is_refused() -> None:
    """⛔ It wrote nothing and the dialog promised it anyway.

    ⚠️ The writer resolves ``handles.get(spec["source"]) or source_handle`` and
    ``continue``s when both are empty. The preview meanwhile rendered
    ``Citation -> None``, so the approval dialog promised a citation the write
    never made -- **a promise broken on the surface the whole safety argument
    rests on.**

    ⭐ The shape it came from is worth more than the instance: the
    committed-change rule asked whether a node was of a creatable KIND, not
    whether it could actually BE created. A citation never carries a
    ``gramps_id``, so it counted unconditionally.
    """
    with pytest.raises(document.GraphInvalid) as refused:
        document.parse({"citations": [{"id": "c1", "page": "p.1"}]})
    message = str(refused.value)
    assert "c1" in message and "source" in message, message

    # ⭐ Both ways a citation legitimately reaches one must still work.
    assert (
        document.parse(
            {
                "source": {"id": "s1", "title": "Invented Register"},
                "citations": [{"id": "c1", "source": "s1", "page": "p.1"}],
            }
        )
        is not None
    )
    assert (
        document.parse(
            {
                "source": {"id": "s1", "title": "Invented Register"},
                "citations": [{"id": "c1", "page": "p.1"}],
            }
        )
        is not None
    )


def test_the_preview_can_no_longer_render_a_citation_pointing_at_NOTHING() -> None:
    """⛔ The rendering was the symptom; the unreachable state is now gone."""
    with pytest.raises(document.GraphInvalid):
        document.parse({"citations": [{"id": "c1"}]})
