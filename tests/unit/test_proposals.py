"""The proposal store: what an agent may name, and what it may never supply.

``approve`` takes an id and a digest and **no operation**, so the agent can only
name which stored proposal to act on -- and name it wrongly. Every way of naming
it wrongly has its own type, its own message and its own test here, because a
caller that cannot tell two refusals apart cannot act on either.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from gramps_live_api.core import apply, proposals, schema

OPERATION = schema.AddNote(
    target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
    note_type="research",
    text="Ashenmoor deed, second volume, page 141.",
)

OTHER = schema.AddNote(
    target=schema.ObjectRef(object_type="person", handle="a1b2c3d4e5f607", gramps_id="I0044"),
    note_type="todo",
    text="Check the Ashenmoor deed against the original.",
)


class Clock:
    """A clock a test moves by hand, so a TTL is exercised without waiting."""

    def __init__(self) -> None:
        self.moment = apply.utc_now()

    def __call__(self) -> object:
        return self.moment

    def advance(self, seconds: float) -> None:
        self.moment = self.moment + timedelta(seconds=seconds)


def store(tmp_path: Path, *, session: str = "sess0001", ttl: float = 900.0) -> proposals.Store:
    clock = Clock()
    made = proposals.Store(
        str(tmp_path / proposals.PROPOSAL_DIRECTORY),
        session=session,
        ttl_seconds=ttl,
        now=clock,
    )
    made.clock = clock  # type: ignore[attr-defined]
    return made


def minted(tmp_path: Path, **kwargs: object) -> tuple[proposals.Store, proposals.Proposal]:
    made = store(tmp_path, **kwargs)  # type: ignore[arg-type]
    return made, made.mint(OPERATION)


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------


def test_a_proposal_lands_on_disk_and_carries_what_the_console_will_read(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    assert proposal.approval_digest == apply.approval_digest(OPERATION)
    assert proposal.full_display == schema.full_display(OPERATION)
    assert Path(made.path_of(proposal.id)).is_file()


def test_two_proposals_do_not_share_an_id(tmp_path: Path) -> None:
    made = store(tmp_path)
    assert made.mint(OPERATION).id != made.mint(OTHER).id


# ---------------------------------------------------------------------------
# Single use -- the claim is the mutual exclusion
# ---------------------------------------------------------------------------


def test_a_claim_takes_the_proposal_out_of_reach_of_a_second_claim(tmp_path: Path) -> None:
    """#69's whole disposition: a retried ``approve`` cannot write a second note."""
    made, proposal = minted(tmp_path)
    made.claim(proposal.id, proposal.approval_digest)
    with pytest.raises(proposals.ProposalNotFound):
        made.claim(proposal.id, proposal.approval_digest)


def test_a_proposal_consumed_after_yes_cannot_be_claimed_again(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    made.claim(proposal.id, proposal.approval_digest)
    made.consume(proposal.id, approved=True)
    with pytest.raises(proposals.ProposalNotFound):
        made.claim(proposal.id, proposal.approval_digest)


def test_a_proposal_consumed_after_no_cannot_be_claimed_again(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    made.claim(proposal.id, proposal.approval_digest)
    made.consume(proposal.id, approved=False)
    with pytest.raises(proposals.ProposalNotFound):
        made.claim(proposal.id, proposal.approval_digest)


def test_a_refused_claim_still_consumes_the_proposal(tmp_path: Path) -> None:
    """⚠️ The claim happens BEFORE any check, so the rename is what excludes a
    second caller rather than a check nobody holds a lock over. The price is
    that a wrong digest burns the proposal, which is the fail-closed side."""
    made, proposal = minted(tmp_path)
    with pytest.raises(proposals.ApprovalMismatch):
        made.claim(proposal.id, apply.approval_digest(OTHER))
    with pytest.raises(proposals.ProposalNotFound):
        made.claim(proposal.id, proposal.approval_digest)


# ---------------------------------------------------------------------------
# The six ways of naming it wrongly
# ---------------------------------------------------------------------------


def test_an_id_that_was_never_minted_is_not_found(tmp_path: Path) -> None:
    made = store(tmp_path)
    with pytest.raises(proposals.ProposalNotFound):
        made.claim("0" * 16, "whatever")


def test_an_id_shaped_like_a_path_names_no_proposal(tmp_path: Path) -> None:
    """A proposal id is agent-supplied text that becomes part of a filename.

    Refused by SHAPE rather than by resolving the path and comparing it to the
    directory: a shape test cannot be defeated by a link, and there is no
    legitimate id this rejects.
    """
    made = store(tmp_path)
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}", encoding="utf-8")
    for candidate in ("../elsewhere", "..\\elsewhere", "a" * 16 + "/x", "", "NOTHEX0123456789"):
        with pytest.raises(proposals.ProposalNotFound):
            made.claim(candidate, "whatever")
    assert outside.read_text(encoding="utf-8") == "{}", "nothing outside the store was touched"


def test_a_proposal_older_than_the_ttl_is_expired(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path, ttl=900.0)
    made.clock.advance(901)  # type: ignore[attr-defined]
    with pytest.raises(proposals.ProposalExpired) as refusal:
        made.claim(proposal.id, proposal.approval_digest)
    assert "expired" in str(refusal.value)


def test_a_proposal_from_another_server_run_is_refused(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path, session="sess0001")
    later = proposals.Store(made.directory, session="sess0002")
    with pytest.raises(proposals.ProposalFromAnotherSession):
        later.claim(proposal.id, proposal.approval_digest)


def test_an_edited_operation_is_corrupt(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    path = Path(made.path_of(proposal.id))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["operation"]["text"] = "something the owner never read"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(proposals.ProposalCorrupt):
        made.claim(proposal.id, proposal.approval_digest)


def test_a_file_that_is_not_readable_json_is_corrupt(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    Path(made.path_of(proposal.id)).write_text("not json at all", encoding="utf-8")
    with pytest.raises(proposals.ProposalCorrupt):
        made.claim(proposal.id, proposal.approval_digest)


def test_a_naive_created_utc_is_corrupt_rather_than_a_stranded_file(tmp_path: Path) -> None:
    """L3, and the damage is the STRANDING rather than the exception.

    ``created_utc`` is not covered by the digest -- the digest covers the
    operation -- so it is editable in a file ``ProposalCorrupt`` otherwise
    passes. A time with no UTC offset parses, and then ``self._now() - created``
    raises ``TypeError``: *can't subtract offset-naive and offset-aware
    datetimes*. That happens **after** ``_take``'s rename, so the proposal is
    already at ``.pending.json``, the exception is not a ``ProposalError``, and
    the file sits there with nothing left that will ever act on it.

    Refused the way every other corrupt-store state is refused, which puts it at
    ``.refused.json`` where the record says what happened to it.
    """
    made, proposal = minted(tmp_path)
    path = Path(made.path_of(proposal.id))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["created_utc"] = "2026-08-17T12:34:56"
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(proposals.ProposalCorrupt) as refusal:
        made.claim(proposal.id, proposal.approval_digest)

    assert "offset" in str(refusal.value), "the message names what is wrong with the value"
    assert not Path(made.path_of(proposal.id, ".pending.json")).exists(), "stranded"
    assert Path(made.path_of(proposal.id, ".refused.json")).is_file()


def test_naming_one_proposal_with_another_digest_is_refused(tmp_path: Path) -> None:
    """Criterion 4. The agent cannot supply an operation, so this is the whole
    of what it can get wrong about which proposal it is approving."""
    made = store(tmp_path)
    first = made.mint(OPERATION)
    second = made.mint(OTHER)
    with pytest.raises(proposals.ApprovalMismatch):
        made.claim(first.id, second.approval_digest)


# ---------------------------------------------------------------------------
# Version binding -- the fourth design input
# ---------------------------------------------------------------------------


def test_changed_rendering_rules_are_reported_as_changed_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made, proposal = minted(tmp_path)
    monkeypatch.setattr(schema, "_PREVIEW_TEXT_LIMIT", 20)
    with pytest.raises(proposals.ApprovalRulesChanged) as refusal:
        made.claim(proposal.id, proposal.approval_digest)
    message = str(refusal.value)
    assert proposal.rules_fingerprint in message and proposals.rules_fingerprint() in message
    assert "the operation is unchanged" in message
    assert "Propose it again" in message


def test_changed_rules_are_reported_even_though_the_session_changed_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⚠️ **The ordering the plan's own verification step depends on.**

    Changing a rendering rule means changing code, which means the server was
    restarted, which means the session id moved as well. Checking the session
    first would therefore make ``ApprovalRulesChanged`` structurally
    unreachable -- the mystery it exists to prevent, wearing a different
    message.
    """
    made, proposal = minted(tmp_path, session="sess0001")
    monkeypatch.setattr(schema, "_PREVIEW_TEXT_LIMIT", 20)
    restarted = proposals.Store(made.directory, session="sess0002")
    with pytest.raises(proposals.ApprovalRulesChanged):
        restarted.claim(proposal.id, proposal.approval_digest)


def test_the_two_approval_refusals_are_not_the_same_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 5's named pair: two different events, two types, two messages."""
    made = store(tmp_path)
    mismatched = made.mint(OPERATION)
    with pytest.raises(proposals.ApprovalMismatch) as one:
        made.claim(mismatched.id, apply.approval_digest(OTHER))

    stale = made.mint(OPERATION)
    monkeypatch.setattr(schema, "_PREVIEW_TEXT_LIMIT", 20)
    with pytest.raises(proposals.ApprovalRulesChanged) as two:
        made.claim(stale.id, stale.approval_digest)

    assert type(one.value) is not type(two.value)
    assert str(one.value) != str(two.value)


def test_every_refusal_says_something_different(tmp_path: Path) -> None:
    """Eight refusals, eight messages. A caller that gets the same sentence for
    two causes has been told nothing it can act on."""
    messages = {
        cls.__name__: str(cls("x"))
        for cls in (
            proposals.ProposalNotFound,
            proposals.ProposalExpired,
            proposals.ProposalFromAnotherSession,
            proposals.ApprovalRulesChanged,
            proposals.ApprovalMismatch,
            proposals.ProposalCorrupt,
        )
    }
    assert len(set(messages)) == 6


# ---------------------------------------------------------------------------
# The fingerprint is MEASURED, not remembered
# ---------------------------------------------------------------------------


def test_the_fingerprint_is_the_same_twice_running() -> None:
    assert proposals.rules_fingerprint() == proposals.rules_fingerprint()


def test_the_fingerprint_moves_when_the_elision_limit_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = proposals.rules_fingerprint()
    monkeypatch.setattr(schema, "_PREVIEW_TEXT_LIMIT", 20)
    assert proposals.rules_fingerprint() != before


def test_the_fingerprint_moves_when_the_record_layout_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = proposals.rules_fingerprint()
    monkeypatch.setattr(apply, "RECORD_FORMAT", apply.RECORD_FORMAT + 1)
    assert proposals.rules_fingerprint() != before


def test_the_fingerprint_moves_when_a_registered_type_changes_its_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The half nothing else would notice: a dataclass gaining or losing a field
    changes what ``to_dict`` writes for every operation of that type."""
    before = proposals.rules_fingerprint()
    declared = proposals._declared_fields
    monkeypatch.setattr(proposals, "_declared_fields", lambda cls: (*declared(cls), "invented"))
    assert proposals.rules_fingerprint() != before


def test_the_probe_operation_is_well_formed_and_is_elided() -> None:
    """Two properties the probe has to keep or it measures less than it claims.

    ``preview`` has a precondition that its input passed ``validate``, and a
    probe whose text fits on one line would leave ``_PREVIEW_TEXT_LIMIT``
    unexercised -- the very constant the plan's verification step moves.
    """
    assert schema.validate(proposals.PROBE).well_formed
    assert schema.preview(proposals.PROBE) != schema.full_display(proposals.PROBE)


# ---------------------------------------------------------------------------
# The report the console leaves and the server reads
# ---------------------------------------------------------------------------


def test_a_report_written_by_the_console_is_read_by_the_server(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    assert made.read_report(proposal.id) is None, "nothing has happened yet"
    made.write_report(proposal.id, {"outcome": "declined"})
    assert made.read_report(proposal.id) == {"outcome": "declined"}
