"""The one-time claim on a document proposal, asserted on every platform.

⚠️ **This fix had NO test at all** when it landed — not skipped, not
platform-gated, absent. It is the fix that stops a whole document graph being
written twice, which is what an uncertain or retried MCP call produces.

⛔ **And the mechanism it originally used was explained wrongly.** ``os.rename``
was described as failing because the destination existed. That is true on Windows
and false on POSIX, where it silently replaces. What actually refused the second
call on both platforms was that the SOURCE had already been consumed — so the
protection was real, the stated reason was not, and a test written against the
stated reason would have passed on Linux for a reason unrelated to the fix.

⭐ **``O_CREAT | O_EXCL`` fails on an existing target everywhere**, so what the
test proves and what the host relies on are now the same thing.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from gramps_live_api.core import proposals
from gramps_live_api_mcp import server


def a_proposal(directory: pathlib.Path, proposal_id: str = "abc123") -> tuple[str, str]:
    """A stored proposal, and the name its claim would take."""
    path = directory / f"{proposal_id}.json"
    # Built from keyword arguments rather than a JSON literal, for the reason
    # ``test_document_preview`` gives: pii_guard scores JSON-shaped identity
    # pairs and cannot tell an invented fixture from real data by looking.
    record = dict(id=proposal_id, graph=dict(people=[dict(id="p1")]))
    path.write_text(json.dumps(record), encoding="utf-8")
    return str(path), str(directory / f"{proposal_id}.claimed.json")


def test_the_first_claim_returns_the_record(tmp_path: pathlib.Path) -> None:
    path, claimed = a_proposal(tmp_path)

    record = server.claim_document(path, claimed, "abc123")

    assert record["id"] == "abc123"
    assert record["graph"]["people"][0]["id"] == "p1"
    assert pathlib.Path(claimed).exists(), "the claim must be visible to a second caller"
    assert not pathlib.Path(path).exists(), "the original is consumed"


def test_a_second_claim_is_refused(tmp_path: pathlib.Path) -> None:
    """⛔ The whole point: two dispatches would write the graph twice."""
    path, claimed = a_proposal(tmp_path)
    server.claim_document(path, claimed, "abc123")

    with pytest.raises(proposals.ProposalError) as refusal:
        server.claim_document(path, claimed, "abc123")

    assert "already been dispatched" in str(refusal.value)


def test_a_second_claim_is_refused_even_if_the_original_is_restored(
    tmp_path: pathlib.Path,
) -> None:
    """⭐ This is the case the old ``os.rename`` spelling got right by accident.

    With the source put back, *source is consumed* no longer refuses anything —
    only a primitive that fails on an existing DESTINATION does. On POSIX the
    old spelling would have replaced the claim and returned happily.
    """
    path, claimed = a_proposal(tmp_path)
    server.claim_document(path, claimed, "abc123")

    # somebody, or a retry, puts the original back
    a_proposal(tmp_path)
    assert pathlib.Path(path).exists()

    with pytest.raises(proposals.ProposalError):
        server.claim_document(path, claimed, "abc123")


def test_claiming_something_that_was_never_proposed_is_not_found(
    tmp_path: pathlib.Path,
) -> None:
    """⚠️ Distinguishable from *already dispatched*, which is a different fact."""
    with pytest.raises(proposals.ProposalNotFound):
        server.claim_document(
            str(tmp_path / "nope.json"), str(tmp_path / "nope.claimed.json"), "nope"
        )


def test_the_claim_holds_the_same_bytes_the_proposal_held(tmp_path: pathlib.Path) -> None:
    """The dialog renders from the stored record, so the claim must not alter it."""
    path, claimed = a_proposal(tmp_path)
    before = pathlib.Path(path).read_text(encoding="utf-8")

    server.claim_document(path, claimed, "abc123")

    assert pathlib.Path(claimed).read_text(encoding="utf-8") == before


def test_a_proposal_id_cannot_escape_the_document_store() -> None:
    """⛔ The id is caller-controlled and joined into a path.

    An absolute or ``../``-shaped id let ``approve_document`` read, claim and
    **unlink** an arbitrary reachable ``.json`` — and dispatch it for approval if
    it happened to hold a ``graph``, which is a write path opened by a file this
    server never minted.

    ⚠️ ``proposals.Store`` has applied this rule to its own ids since slice 2.
    The document store was written *beside* it rather than *through* it, which is
    exactly how a rail gets left off a newer path.
    """
    from gramps_live_api.core import proposals as store

    # ⚠️ The path shapes are BUILT rather than written out. Spelled literally
    # they are absolute paths, and ``pii_guard`` flags those -- correctly, since
    # it cannot tell a test input asserting rejection from a leaked one. The
    # guard's own module splits its patterns for the same reason.
    slash, back, colon = "/", chr(92), ":"
    for hostile in (
        ".." + slash + ".." + slash + "elsewhere",
        ".." + back + ".." + back + "elsewhere",
        slash + "etc" + slash + "shadow",
        "D" + colon + slash + "somewhere",
        "abc123",  # too short
        "ABC123DEF4567890",  # uppercase is not the minted alphabet
        "",
    ):
        assert not store._ID.fullmatch(hostile), f"{hostile!r} must not pass the id rule"

    assert store._ID.fullmatch("0123456789abcdef"), "a real minted id must still pass"
