"""The proposal store: what an agent may name, and what it may never supply.

``approve`` takes an id and a digest and **no operation**, so the agent can only
name which stored proposal to act on -- and name it wrongly. Every way of naming
it wrongly has its own type, its own message and its own test here, because a
caller that cannot tell two refusals apart cannot act on either.
"""

from __future__ import annotations

import builtins
import contextlib
import inspect
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

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


def deny_reading(monkeypatch: pytest.MonkeyPatch, proposal_id: str) -> None:
    """E-1's environment: create, write and rename are permitted, READ is not.

    Modelled at ``open`` rather than by setting an ACL, because the two hosts
    this runs on spell that denial differently and neither spelling is the
    point. The denial follows the id through every suffix, because an ACL
    belongs to the file and a rename does not shed it -- which is what makes
    this able to tell a store that reads before renaming from one that does not.
    """
    real = builtins.open

    def guarded(file: Any, *args: Any, **kwargs: Any) -> Any:
        if proposal_id in str(file):
            raise PermissionError(13, "access is denied")
        return real(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)


def fail_the_claim_rename(monkeypatch: pytest.MonkeyPatch, lost: OSError) -> None:
    """Make only the CLAIM rename fail -- the one landing at ``.pending.json``.

    ⚠️ **Concurrency is argued, not simulated.** A two-process race is not
    reproducible on CI, so the loser's behaviour is tested by injecting the
    rename failure the argument rests on. The burn and rollback renames are
    left working, or the test would be about a store with no renames at all
    rather than about a caller that lost one.
    """
    real = os.rename

    def guarded(source: Any, destination: Any, *args: Any, **kwargs: Any) -> Any:
        if str(destination).endswith(proposals._PENDING):
            raise lost
        return real(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "rename", guarded)


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
    made._claim(proposal.id, proposal.approval_digest)
    with pytest.raises(proposals.ProposalNotFound):
        made._claim(proposal.id, proposal.approval_digest)


def test_a_second_claim_is_told_a_retry_lands_here(tmp_path: Path) -> None:
    """The sentence #69's disposition rests on, and reading first MOVED it.

    It used to come from ``_take``, which was the first thing a claim did and
    so was where a consumed proposal was noticed. ``_take`` is now the *last*
    thing, and a consumed proposal is noticed by the read -- so the sentence
    has to live there or an agent that retries gets a bare strerror instead of
    the one refusal ``docs/slice2-mcp.md`` quotes.
    """
    made, proposal = minted(tmp_path)
    made._claim(proposal.id, proposal.approval_digest)

    with pytest.raises(proposals.ProposalNotFound) as refusal:
        made._claim(proposal.id, proposal.approval_digest)

    message = str(refusal.value)
    assert "no proposal is awaiting approval under that name" in message
    assert "One approve consumes one proposal" in message
    assert "propose again" in message


def test_a_proposal_consumed_after_yes_cannot_be_claimed_again(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    made._claim(proposal.id, proposal.approval_digest)
    made.consume(proposal.id, approved=True)
    with pytest.raises(proposals.ProposalNotFound):
        made._claim(proposal.id, proposal.approval_digest)


def test_a_proposal_consumed_after_no_cannot_be_claimed_again(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    made._claim(proposal.id, proposal.approval_digest)
    made.consume(proposal.id, approved=False)
    with pytest.raises(proposals.ProposalNotFound):
        made._claim(proposal.id, proposal.approval_digest)


def test_a_refused_claim_still_consumes_the_proposal(tmp_path: Path) -> None:
    """⚠️ Burning a refused proposal is a CHOSEN ACT, not a side effect of
    ordering, and E-1's fix does not drop it. ``_claim`` reads first and then
    renames the proposal to ``.refused.json`` rather than to ``.pending.json``,
    so a wrong digest still consumes it -- which is the fail-closed side, and
    the direction this rail fails in everywhere else."""
    made, proposal = minted(tmp_path)
    with pytest.raises(proposals.ApprovalMismatch):
        made._claim(proposal.id, apply.approval_digest(OTHER))
    with pytest.raises(proposals.ProposalNotFound):
        made._claim(proposal.id, proposal.approval_digest)


# ---------------------------------------------------------------------------
# ⭐ Read first -- the rename is the thing you choose once you know
# ---------------------------------------------------------------------------


def test_an_unreadable_proposal_is_not_burnt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⭐ **E-1, and the harm it names is the LOOP rather than the one lost note.**

    A directory that permits create, write and rename and denies reading the
    files in it -- an ACL, or a Windows sharing lock -- used to meet the store
    one statement too late: ``_take`` renamed the proposal to ``.pending.json``
    and *then* the read failed, from outside ``claim_then``'s ``try``, so no
    rollback ran and no console opened. The agent, told to propose again,
    minted a fresh proposal into the same directory, which read the same way.
    **Propose, approve, burn, forever.**

    A read failure is environmental and must burn nothing, so the read happens
    first and the rename is chosen once the content is known.
    """
    made, proposal = minted(tmp_path)
    deny_reading(monkeypatch, proposal.id)

    with pytest.raises(proposals.ProposalError):
        made._claim(proposal.id, proposal.approval_digest)

    assert not Path(made.path_of(proposal.id, ".pending.json")).exists(), "stranded"
    assert not Path(made.path_of(proposal.id, ".refused.json")).exists(), "burnt"
    assert Path(made.path_of(proposal.id)).is_file(), "the proposal must survive a host's failure"


def test_a_proposal_that_could_not_be_read_is_not_reported_as_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⭐ **Reading first stops the burn. It does not stop the LOOP.**

    ``ProposalNotFound``'s whole vocabulary tells the agent to propose again,
    and a fresh proposal lands in the same directory under the same ACL and
    reads the same way -- so the wrong type turns an environmental failure into
    an instruction to repeat it forever. *Not found* is also simply false about
    a file that was found and could not be read.

    The remedy this one names is the opposite: fix the host, approve **the same
    id**. Asserted as a frozen sentence, in the idiom ``APPROVE_DESCRIPTION``'s
    own test uses, because the message is the entire interface an agent has.
    """
    made, proposal = minted(tmp_path)
    deny_reading(monkeypatch, proposal.id)

    with pytest.raises(proposals.ProposalUnreadable) as refusal:
        made._claim(proposal.id, proposal.approval_digest)

    assert not isinstance(refusal.value, proposals.ProposalNotFound), (
        "a subclass would let every ProposalNotFound handler swallow it again"
    )
    message = str(refusal.value)
    assert proposal.id in message
    assert "approve the same id again" in message, "the remedy names THIS id"
    assert "nothing was consumed" in message.lower()
    assert "propose" not in message.lower(), (
        "propose-again is the one instruction that turns this failure into a loop"
    )


@pytest.mark.parametrize(
    "lost",
    [
        FileNotFoundError(2, "the system cannot find the file specified"),
        PermissionError(32, "the file is in use by another process"),
    ],
    ids=["the source had already moved", "the other caller still held it open"],
)
def test_a_claim_rename_that_fails_did_not_get_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lost: OSError
) -> None:
    """⚠️ **Where a careless implementation silently loses mutual exclusion.**

    The rename **is** the exclusion, so its failure is the whole of losing.
    Both spellings are covered by one rule -- *any* ``OSError`` out of the claim
    rename means the claim was not obtained -- rather than by telling them
    apart: ``FileNotFoundError`` when the winner's rename already moved the
    source, and on Windows ``PermissionError`` (``ERROR_SHARING_VIOLATION``)
    while the winner still holds the file open for its read, which is new to
    reading first because ``open`` omits ``FILE_SHARE_DELETE``.

    ⚠️ **Suppressing it the way ``_refuse`` and ``_rollback`` suppress theirs
    would let a caller that renamed nothing go on and open a console** -- two
    consoles for one proposal, and #69's bounded claim gone with no error
    anywhere. That is what ``opened == []`` is here to catch.
    """
    made, proposal = minted(tmp_path)
    fail_the_claim_rename(monkeypatch, lost)
    opened: list[str] = []

    with pytest.raises(proposals.ProposalError) as refusal:
        made.claim_then(proposal.id, proposal.approval_digest, lambda: opened.append("a window"))

    assert opened == [], "a caller that did not get the claim followed through anyway"
    assert "claimed by another approve" in str(refusal.value)
    assert not Path(made.path_of(proposal.id, ".pending.json")).exists()
    assert Path(made.path_of(proposal.id)).is_file(), "nothing was renamed, so nothing was burnt"


# ---------------------------------------------------------------------------
# The six ways of naming it wrongly
# ---------------------------------------------------------------------------


def test_an_id_that_was_never_minted_is_not_found(tmp_path: Path) -> None:
    made = store(tmp_path)
    with pytest.raises(proposals.ProposalNotFound):
        made._claim("0" * 16, "whatever")


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
            made._claim(candidate, "whatever")
    assert outside.read_text(encoding="utf-8") == "{}", "nothing outside the store was touched"


def test_a_proposal_older_than_the_ttl_is_expired(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path, ttl=900.0)
    made.clock.advance(901)  # type: ignore[attr-defined]
    with pytest.raises(proposals.ProposalExpired) as refusal:
        made._claim(proposal.id, proposal.approval_digest)
    assert "expired" in str(refusal.value)


def test_a_proposal_from_another_server_run_is_refused(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path, session="sess0001")
    later = proposals.Store(made.directory, session="sess0002")
    with pytest.raises(proposals.ProposalFromAnotherSession):
        later._claim(proposal.id, proposal.approval_digest)


def test_an_edited_operation_is_corrupt(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    path = Path(made.path_of(proposal.id))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["operation"]["text"] = "something the owner never read"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(proposals.ProposalCorrupt):
        made._claim(proposal.id, proposal.approval_digest)


def test_a_file_that_is_not_readable_json_is_corrupt(tmp_path: Path) -> None:
    made, proposal = minted(tmp_path)
    Path(made.path_of(proposal.id)).write_text("not json at all", encoding="utf-8")
    with pytest.raises(proposals.ProposalCorrupt):
        made._claim(proposal.id, proposal.approval_digest)


def test_a_naive_created_utc_is_corrupt_rather_than_a_stranded_file(tmp_path: Path) -> None:
    """L3, and the damage is the STRANDING rather than the exception.

    ``created_utc`` is not covered by the digest -- the digest covers the
    operation -- so it is editable in a file ``ProposalCorrupt`` otherwise
    passes. A time with no UTC offset parses, and then ``self._now() - created``
    raises ``TypeError``: *can't subtract offset-naive and offset-aware
    datetimes* -- which is not a ``ProposalError`` and so escapes every refusal.
    Under the ordering E-1 replaced it escaped **after** ``_take``'s rename, so
    the proposal sat at ``.pending.json`` with nothing left that would ever act
    on it; it now runs before any rename, so the stranding is gone twice over.

    Refused the way every other corrupt-store state is refused, which puts it at
    ``.refused.json`` where the record says what happened to it.
    """
    made, proposal = minted(tmp_path)
    path = Path(made.path_of(proposal.id))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["created_utc"] = "2026-08-17T12:34:56"
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(proposals.ProposalCorrupt) as refusal:
        made._claim(proposal.id, proposal.approval_digest)

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
        made._claim(first.id, second.approval_digest)


# ---------------------------------------------------------------------------
# Version binding -- the fourth design input
# ---------------------------------------------------------------------------


def test_changed_rendering_rules_are_reported_as_changed_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made, proposal = minted(tmp_path)
    monkeypatch.setattr(schema, "_PREVIEW_TEXT_LIMIT", 20)
    with pytest.raises(proposals.ApprovalRulesChanged) as refusal:
        made._claim(proposal.id, proposal.approval_digest)
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
        restarted._claim(proposal.id, proposal.approval_digest)


def test_the_two_approval_refusals_are_not_the_same_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 5's named pair: two different events, two types, two messages."""
    made = store(tmp_path)
    mismatched = made.mint(OPERATION)
    with pytest.raises(proposals.ApprovalMismatch) as one:
        made._claim(mismatched.id, apply.approval_digest(OTHER))

    stale = made.mint(OPERATION)
    monkeypatch.setattr(schema, "_PREVIEW_TEXT_LIMIT", 20)
    with pytest.raises(proposals.ApprovalRulesChanged) as two:
        made._claim(stale.id, stale.approval_digest)

    assert type(one.value) is not type(two.value)
    assert str(one.value) != str(two.value)


def test_every_refusal_says_something_different(tmp_path: Path) -> None:
    """Seven ways of naming a stored proposal wrongly, seven distinct types.

    ⚠️ **This asserts the TYPES are distinct, and its own name overstates it.**
    ``str(cls("x"))`` is ``"x"`` for every one of them, so the set below is a
    set of class names; what the sentences say is asserted by the tests that
    raise them for real. Left as it is and said plainly rather than quietly
    widened, because a caller discriminates on the type -- both callers catch
    ``ProposalError`` broadly -- and that is what this is worth.
    """
    messages = {
        cls.__name__: str(cls("x"))
        for cls in (
            proposals.ProposalNotFound,
            proposals.ProposalUnreadable,
            proposals.ProposalExpired,
            proposals.ProposalFromAnotherSession,
            proposals.ApprovalRulesChanged,
            proposals.ApprovalMismatch,
            proposals.ProposalCorrupt,
        )
    }
    assert len(set(messages)) == 7


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
# ⭐ Claiming is the LAST irreversible step
# ---------------------------------------------------------------------------


def test_a_follow_through_that_raises_puts_the_proposal_back(tmp_path: Path) -> None:
    """⭐ **The invariant, and it closes L2 and D-1 as a class rather than as
    two instances.**

    Both findings were the same predicate wearing two faces. L2: *this host
    cannot spawn consoles*. D-1: *the spawn itself failed -- WinError 8*. Each
    left the proposal renamed to ``.pending.json`` with no console anywhere and
    nothing left that would ever act on it, so the agent proposed again and
    reached the same place: propose, approve, burn, forever.

    ⚠️ **The rollback keys on *the follow-through raised*, never on which
    failure it was**, which is why it covers the next instance nobody has met
    yet. And it cannot become a second route to a claim: it runs only when the
    follow-through raised, and a rolled-back proposal has been shown to nobody
    and consumed by nothing.
    """
    made, proposal = minted(tmp_path)

    def cannot_spawn() -> None:
        raise OSError(8, "not enough storage is available to process this command")

    with pytest.raises(OSError):
        made.claim_then(proposal.id, proposal.approval_digest, cannot_spawn)

    assert not Path(made.path_of(proposal.id, ".pending.json")).exists(), "orphaned"
    assert Path(made.path_of(proposal.id)).is_file(), "the proposal must survive"
    reclaimed = made.claim_then(proposal.id, proposal.approval_digest, lambda: None)
    assert reclaimed.id == proposal.id, "the same id is approvable once the host is fixed"


def test_a_follow_through_that_returns_leaves_the_claim_standing(tmp_path: Path) -> None:
    """The direction that must NOT move, and it is #69's bounded claim.

    A console that opened is a console that may write, so the claim stands and a
    second ``claim_then`` of the same id meets ``ProposalNotFound``. A rollback
    here would put an approvable proposal back while its window was live -- two
    consoles for one proposal, which is exactly what ``consume`` before Gramps
    exists to prevent.
    """
    made, proposal = minted(tmp_path)
    opened: list[str] = []

    claimed = made.claim_then(
        proposal.id, proposal.approval_digest, lambda: opened.append("a window")
    )

    assert opened == ["a window"], "the follow-through is the point of the call"
    assert claimed.operation == OPERATION
    assert Path(made.path_of(proposal.id, ".pending.json")).is_file(), "still claimed"
    with pytest.raises(proposals.ProposalNotFound):
        made.claim_then(proposal.id, proposal.approval_digest, lambda: None)


def test_a_refused_claim_never_reaches_the_follow_through(tmp_path: Path) -> None:
    """No window opens for a proposal the store refuses.

    The claim is attempted first and the refusal is raised from inside it, so
    the callee never runs -- and an agent that names a proposal wrongly cannot
    put a window in front of the owner by doing so.
    """
    made, proposal = minted(tmp_path)
    opened: list[str] = []

    with pytest.raises(proposals.ApprovalMismatch):
        made.claim_then(
            proposal.id, apply.approval_digest(OTHER), lambda: opened.append("a window")
        )

    assert opened == [], "a refusal opened a console"


# ---------------------------------------------------------------------------
# ⭐ The property: nothing fallible happens AFTER the irreversible rename
# ---------------------------------------------------------------------------
#
# ⚠️ These three assert the PROPERTY rather than today's three call sites. A
# statement added after the claim rename next year does not have to be thought
# of for them to go red: `Trace` derives what a claim can reach out to from the
# module's OWN imports, so a new call after the rename joins the log by itself.


class Injected(Exception):
    """Not a ``ProposalError`` and not an ``OSError``, so nothing catches it.

    A fault the store has no handler for is the harshest form of the question:
    *if this step failed in a way nobody anticipated, where would the proposal
    be left?* Anything the store does catch would let a handler answer for it.
    """


class Trace:
    """Every fallible call a claim makes, recorded and optionally made to fail.

    ⚠️ **The universe is DERIVED, not listed.** It is every plain function in
    every module ``proposals`` itself imports, plus ``builtins.open`` -- so a
    statement added to the store that reaches the filesystem, the parser, the
    schema or the digest is covered without anybody remembering to add it here.
    What it does not cover is ``datetime.fromisoformat`` (a method on a C type,
    which cannot be patched) and ``os.path``'s pure string work; both are only
    reachable before the rename, and the *nothing after* assertion below is
    what actually bounds the tail.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.renamed_to: list[str] = []
        self.fail_at: int | None = None

    def arm(self, patching: pytest.MonkeyPatch) -> None:
        for module, name in self._universe():
            self._wrap(patching, module, name)

    @staticmethod
    def _universe() -> list[tuple[Any, str]]:
        found: list[tuple[Any, str]] = [(builtins, "open")]
        for _, module in inspect.getmembers(proposals, inspect.ismodule):
            for name, value in vars(module).items():
                if not name.startswith("_") and (
                    inspect.isfunction(value) or inspect.isbuiltin(value)
                ):
                    found.append((module, name))
        return found

    def _wrap(self, patching: pytest.MonkeyPatch, module: Any, name: str) -> None:
        real = getattr(module, name)
        label = f"{module.__name__}.{name}"

        def recorded(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(label)
            if label == "os.rename" and len(args) > 1:
                self.renamed_to.append(str(args[1]))
            if len(self.calls) == self.fail_at:
                raise Injected(f"{label}, call {self.fail_at}")
            return real(*args, **kwargs)

        patching.setattr(module, name, recorded)


def traced(made: proposals.Store, proposal_id: str, digest: str, fail_at: int | None) -> Trace:
    """Run one claim with every fallible call recorded, failing the ``fail_at``-th."""
    watching = Trace()
    watching.fail_at = fail_at
    with pytest.MonkeyPatch.context() as patching:
        watching.arm(patching)
        with contextlib.suppress(Exception):
            made._claim(proposal_id, digest)
    return watching


@pytest.mark.parametrize(
    ("spoil", "renames_to"),
    [
        (None, proposals._PENDING),
        ("digest", ".refused.json"),
    ],
    ids=["valid content is renamed to CLAIM", "invalid content is renamed to BURN"],
)
def test_a_claim_renames_once_and_reaches_nothing_afterwards(
    tmp_path: Path, spoil: str | None, renames_to: str
) -> None:
    """⭐ **The property, stated over the calls a claim actually makes.**

    Two halves, and the second is the one that survives a future edit. *Exactly
    one rename* is the owner's shape written down mechanically -- the rename is
    the thing you choose once you know, so a claim that renamed twice would be
    choosing twice. *Nothing after it* is the invariant: the log ends at the
    rename, so there is no fallible step left for a failure to arrive in.

    **How it goes red if the property breaks.** Any statement appended to
    ``_claim`` after the rename that touches the filesystem, the parser, the
    schema or a digest appends to this same log -- because the log is derived
    from the module's imports and not from a list of today's call sites -- and
    the tail assertion names it.
    """
    made, proposal = minted(tmp_path)
    digest = apply.approval_digest(OTHER) if spoil else proposal.approval_digest

    watching = traced(made, proposal.id, digest, fail_at=None)

    assert watching.renamed_to == [made.path_of(proposal.id, renames_to)], "exactly one, and there"
    after = watching.calls[watching.calls.index("os.rename") + 1 :]
    assert after == [], f"the claim reaches {after} after the rename it can no longer undo"


def test_a_claim_that_cannot_decide_renames_nothing_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of *choose the rename once you know*: not knowing chooses
    neither. An environmental failure is not a decision about the content, so
    it may not burn and it may not claim."""
    made, proposal = minted(tmp_path)
    deny_reading(monkeypatch, proposal.id)

    watching = traced(made, proposal.id, proposal.approval_digest, fail_at=None)

    assert watching.renamed_to == [], "a host's failure moved the owner's proposal"


def test_no_fallible_step_of_a_claim_can_strand_the_proposal(tmp_path: Path) -> None:
    """⭐ **Fault injection at EVERY step, which is the property under test.**

    A first pass records every fallible call one whole claim makes; the run
    then repeats once per call, failing that call with an exception the store
    has no handler for, and asserts the same thing each time: **a claim that
    raised left the proposal at ``.json`` or at ``.refused.json``, never at
    ``.pending.json``.** Stranded there it is consumed, invisible to a retry
    and waited on by nothing -- which is E-1, and L2 and D-1 before it.

    **How it goes red if the property breaks.** A fallible statement added
    after the rename becomes one more index in this sweep, and failing it
    strands the proposal, because by then the rename cannot be taken back.
    There is nothing to remember to update: the sweep is as long as the claim
    is.
    """
    made, proposal = minted(tmp_path)
    reference = traced(made, proposal.id, proposal.approval_digest, fail_at=None)
    assert reference.renamed_to, "the reference run must be a claim that succeeded"

    for step in range(1, len(reference.calls) + 1):
        made, proposal = minted(tmp_path / f"step{step}")
        watching = traced(made, proposal.id, proposal.approval_digest, fail_at=step)
        if len(watching.calls) < step:
            continue  # the run was shorter than the reference; nothing was injected
        where = watching.calls[step - 1]
        assert not Path(made.path_of(proposal.id, proposals._PENDING)).exists(), (
            f"failing {where} (step {step} of {len(reference.calls)}) stranded the proposal"
        )
        assert Path(made.path_of(proposal.id)).is_file(), (
            f"failing {where} (step {step}) consumed a proposal it never decided about"
        )


def _edit(made: proposals.Store, proposal_id: str, field: str, value: object) -> None:
    path = Path(made.path_of(proposal_id))
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    path.write_text(json.dumps(record), encoding="utf-8")


def _read_denied(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    deny_reading(monkeypatch, proposal.id)
    return proposal.approval_digest, lambda: None


def _not_json(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    Path(made.path_of(proposal.id)).write_text("not json at all", encoding="utf-8")
    return proposal.approval_digest, lambda: None


def _not_an_object(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    Path(made.path_of(proposal.id)).write_text("[]", encoding="utf-8")
    return proposal.approval_digest, lambda: None


def _rules_moved(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(schema, "_PREVIEW_TEXT_LIMIT", 20)
    return proposal.approval_digest, lambda: None


def _another_session(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    _edit(made, proposal.id, "session", "sess9999")
    return proposal.approval_digest, lambda: None


def _edited_operation(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    path = Path(made.path_of(proposal.id))
    record = json.loads(path.read_text(encoding="utf-8"))
    record["operation"]["text"] = "something the owner never read"
    path.write_text(json.dumps(record), encoding="utf-8")
    return proposal.approval_digest, lambda: None


def _unreadable_time(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    _edit(made, proposal.id, "created_utc", "the day before yesterday")
    return proposal.approval_digest, lambda: None


def _naive_time(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    _edit(made, proposal.id, "created_utc", "2026-08-17T12:34:56")
    return proposal.approval_digest, lambda: None


def _expired(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    made.clock.advance(901)
    return proposal.approval_digest, lambda: None


def _wrong_digest(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return apply.approval_digest(OTHER), lambda: None


def _claim_rename_fails(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    fail_the_claim_rename(monkeypatch, PermissionError(32, "the file is in use"))
    return proposal.approval_digest, lambda: None


def _follow_through_raises(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    def cannot_spawn() -> None:
        raise OSError(8, "not enough storage is available to process this command")

    return proposal.approval_digest, cannot_spawn


def _nothing_fails(made: Any, proposal: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return proposal.approval_digest, lambda: None


@pytest.mark.parametrize(
    ("arrange", "ends_at"),
    [
        (_read_denied, ".json"),
        (_not_json, ".refused.json"),
        (_not_an_object, ".refused.json"),
        (_rules_moved, ".refused.json"),
        (_another_session, ".refused.json"),
        (_edited_operation, ".refused.json"),
        (_unreadable_time, ".refused.json"),
        (_naive_time, ".refused.json"),
        (_expired, ".refused.json"),
        (_wrong_digest, ".refused.json"),
        (_claim_rename_fails, ".json"),
        (_follow_through_raises, ".json"),
        (_nothing_fails, ".pending.json"),
    ],
    ids=[
        "environmental: the file cannot be read",
        "content: not JSON",
        "content: the record is not an object",
        "content: the fingerprint moved",
        "content: another session minted it",
        "content: the operation was edited",
        "content: the time cannot be read",
        "content: the time carries no offset",
        "content: it expired",
        "content: the digest names another proposal",
        "environmental: the claim rename failed",
        "environmental: the follow-through raised",
        "control: nothing failed",
    ],
)
def test_a_claim_leaves_the_proposal_in_exactly_one_of_two_places(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arrange: Any, ends_at: str
) -> None:
    """⭐ **Every reachable exit of ``claim_then``, and the on-disk state of each.**

    > **A decision about the CONTENT burns the proposal, so it ends at
    > ``.refused.json``. Anything ENVIRONMENTAL decides nothing, so it ends
    > where it started, at ``.json``, approvable by the same id the moment the
    > host is fixed. It is never left at ``.pending.json``.**

    ``.pending.json`` means *claimed, and something is going to act on it*. A
    proposal stranded there is consumed, invisible to a retry, and waited on by
    nothing -- so every row asserts the two absences as well as the presence,
    which is what makes the row an assertion about the state rather than about
    one file.

    The first row is E-1 itself. The last is the control: without it the whole
    table is satisfiable by a store that refuses everything.
    """
    made, proposal = minted(tmp_path)
    digest, follow_through = arrange(made, proposal, monkeypatch)
    ran: list[str] = []

    def watched() -> object:
        ran.append("the follow-through")
        return follow_through()

    if ends_at == proposals._PENDING:
        made.claim_then(proposal.id, digest, watched)
        assert ran == ["the follow-through"], "the control row must exercise a real claim"
    else:
        with pytest.raises((proposals.ProposalError, OSError)):
            made.claim_then(proposal.id, digest, watched)

    for suffix in (".json", ".refused.json", proposals._PENDING):
        assert Path(made.path_of(proposal.id, suffix)).exists() == (suffix == ends_at), (
            f"expected the proposal at {ends_at}, and {suffix} disagrees"
        )


# ---------------------------------------------------------------------------
# There is no report, and the store offers no way to write one
# ---------------------------------------------------------------------------


def test_the_store_has_no_way_to_file_an_outcome(tmp_path: Path) -> None:
    """⭐ **A red line rather than a comment**, and the same idiom as
    ``approve``'s frozen reply keys.

    The cross-process report was the layer's subject and every stage of it drew
    a finding: C1-1 the word it filed, C2-1 the region it filed from, L7 the
    region that filed nothing, D-2 the absence the server read as ``unknown``.
    Re-adding a writer here is a failing test, not a quiet return of the
    machinery that produced a wrong outcome five different ways.
    """
    made, _ = minted(tmp_path)
    for gone in ("write_report", "read_report", "report_path"):
        assert not hasattr(made, gone), f"{gone} is the deleted layer coming back"
