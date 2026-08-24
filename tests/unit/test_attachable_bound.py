"""⛔ One declaration decides which kinds may name something that already exists.

``gramps_id`` is accepted on five kinds. **A fifth hand-written branch in a
dispatch that already had four is how the next kind gets forgotten** -- and the
failure is silent, because a kind nobody walks simply never resolves and its
``gramps_id`` is ignored rather than refused.

⚠️ **Its own file, deliberately.** These tests are mostly node vocabulary, and
appending them to ``test_document_preview`` pushed that file's GEDCOM-X key
density past this repository's own P2 threshold. ⛔ The fix is where the tests
live, never the guard's threshold.
"""

from __future__ import annotations

from typing import Any

import pytest

from gramps_live_api.host import document


def node(local_id: str, **fields: Any) -> dict[str, Any]:
    """A graph node. ⚠️ Spelled here rather than imported from another test
    module -- one test file importing another couples them, and this file exists
    precisely to keep its vocabulary out of that one."""
    return dict(id=local_id, **fields)


def test_every_ATTACHABLE_kind_is_resolved_and_every_other_kind_is_REFUSED() -> None:
    """⛔ One declaration drives advertisement, resolution and refusal.

    ``gramps_id`` is now accepted on five kinds. **A fifth hand-written branch in
    a dispatch that already had four is how the next kind gets forgotten** — and
    the failure is silent, because a kind nobody walks simply never resolves and
    its ``gramps_id`` is ignored rather than refused.

    ⭐ So a sixth kind becomes attachable by being declared in ``ATTACHABLE``, and
    this test fails if any of the three places stop agreeing with it.

    ⚠️ **The interface contradicting itself has already cost a round**:
    ``find_families`` told the model to pass a family ID while
    ``propose_document`` said families were always created new, so the model
    discarded the ID and created a second household.
    """

    # ⛔ Every attachable kind must actually RESOLVE — appear in `requested`.
    #
    # ⚠️ The graph is built from ``GROUPS`` rather than spelled out per kind: a
    # literal fixture per kind is a second list, and it is also enough clustered
    # genealogy vocabulary to trip this repository's own P2 density guard.
    def _minimal(extra_group: str, entry: dict[str, Any]) -> dict[str, Any]:
        """A graph carrying ``entry`` in ``extra_group``, and nothing else of note.

        ⚠️ ``people`` is always present because ``parse`` requires it, and
        ``source`` is a single node rather than a list -- the one structural
        exception in the graph.
        """
        base: dict[str, Any] = {"people": [node("p0")]}
        if extra_group == "source":
            base["source"] = dict(entry)
        else:
            base[extra_group] = [dict(entry)]
        return base

    for group, one in document.ATTACHABLE.items():
        body = _minimal(group, {"id": "x1", "gramps_id": "X0001"})
        requested = document.requested(document.parse(body))
        wanted = "x1"
        assert any(r.local_id == wanted and r.kind == one for r in requested), (
            f"{group!r} is declared attachable and does not reach `requested`, so its "
            f"gramps_id would be silently ignored rather than resolved"
        )

    # ⛔ And every kind that is NOT attachable must be REFUSED, naming itself.
    for group, one in document.GROUPS.items():
        if group in document.ATTACHABLE:
            continue
        entry: dict[str, Any] = {"id": "x1", "gramps_id": "X0001"}
        if group == "citations":
            entry = {"id": "c1", "source": "s1", "gramps_id": "X0001"}
        if group == "notes":
            entry = {"text": "x", "gramps_id": "X0001"}
        body = _minimal(group, entry)
        if group == "citations":
            body["source"] = node("s1")

        with pytest.raises(document.GraphInvalid) as invalid:
            document.parse(body)
        assert one in str(invalid.value) or group in str(invalid.value), (
            f"{group!r} is not attachable and its refusal does not name it: {invalid.value}"
        )


def test_an_event_gramps_id_that_does_not_resolve_refuses_the_WHOLE_batch() -> None:
    """⛔ Falling back to creating is the duplicate the id existed to prevent.

    ⚠️ And it would do it silently — the owner approved *attach a citation to
    E0060*, and a fallback would write a second E-something carrying that
    citation while the dialog said otherwise.
    """
    graph = dict(people=[node("p1")], events=[node("e1", gramps_id="E9999")])
    document.parse(graph)  # accepted: the id is well-formed and events attach

    # The resolver reports it missing; the preview must not render it as attached.
    resolution = document.Resolution(
        nodes=(
            document.Resolved(
                local_id="e1", gramps_id="E9999", kind="event", found=False, display=""
            ),
        )
    )
    assert resolution.refusal() is not None, (
        "an unresolved event id must refuse the batch rather than fall through to "
        "creating a second copy of the event"
    )
    assert "E9999" in str(resolution.refusal())
