"""The store an agent may name a proposal in, and may never write an operation to.

⚠️ **The operation never leaves the server, and that is the whole binding.**
``propose_note`` builds the ``AddNote``, validates it, and files it here; it
returns the proposal's id, its rendered sentence and its digest. ``approve``
takes an id and a digest and **no operation parameter**, so an agent can only
say *which stored proposal* to act on. It cannot supply a different one; it can
only name one wrongly, and every way of naming it wrongly has its own type and
its own message below.

**Where the store lives, and why it is not a temp directory.** Inside the
blessed copy, on the precedent ``.gramps-live-api-undo`` already set: it is
derived from the one path the tool was given, it needs no second configuration
key, it travels with the copy, the blessing that authorised writing there covers
it -- and it keeps note text, which is personal data, out of a temp directory
that survives a crash and that nothing in this project blessed.

⚠️ **What this does NOT defend against**, stated here because the next reader
will otherwise take the list of refusals for a security model. ``approval_digest``
says in its own docstring that it is not a security boundary against a hostile
front end, and nothing here changes that. The store sits inside the copy and the
agent runs as the same user: ``ProposalCorrupt`` catches an edited *operation*,
and an attacker who edits operation, digest and rendered sentence together
defeats it, because the file is not signed. **The console rendering is a UI
defence, not a cryptographic one.** What it does buy is bounded and closable:
*one approved proposal produces at most one write attempt, of exactly the
operation whose full text was displayed at a console the agent cannot write to,
under the rendering rules in force when it was displayed.*
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import NoReturn

from gramps_live_api import __version__
from gramps_live_api.core import apply, schema

PROPOSAL_DIRECTORY = ".gramps-live-api-proposals"
"""Where proposals live, inside the tree directory. See the module docstring."""

PROPOSAL_FORMAT = 1
"""The stored layout's own version, so a later reader can tell which it has."""

DEFAULT_TTL_SECONDS = 15 * 60.0
"""How long a proposal may sit before it stops being approvable.

Long enough for a person to read a note and think about it; short enough that a
proposal nobody acted on is not still approvable after lunch.
"""

_ID_LENGTH = 8
_ID = re.compile(r"[0-9a-f]{16}")
"""What a proposal id may be, and it is checked by SHAPE.

⚠️ **The id is agent-supplied text that becomes part of a filename.** Refusing
by shape cannot be defeated by a link, a normalisation or a drive-relative
spelling, and there is no legitimate id it rejects -- ``mint`` produces exactly
this alphabet. Resolving the path and comparing it to the directory is the
alternative, and it answers a question about the filesystem where this answers a
question about the value.
"""

_PENDING = ".pending.json"
_APPROVED = ".approved.json"
_DECLINED = ".declined.json"
_REFUSED = ".refused.json"
_REPORT = ".report.json"


PROBE = schema.AddNote(
    target=schema.ObjectRef(object_type="person", handle="probehandle0000", gramps_id="I0000"),
    note_type="research",
    text=(
        "A fixed probe operation whose only purpose is to move when the rules that render "
        "and serialise an operation move. It carries no meaning and names nobody."
    ),
)
"""The committed operation the rules fingerprint is measured over.

Invented values throughout, and its text is deliberately longer than
``_PREVIEW_TEXT_LIMIT`` so that ``preview`` elides it and ``full_display`` does
not -- the elision is one of the rules being measured, and a probe that fits on
one line would leave it unexercised.
"""


class ProposalError(Exception):
    """This proposal cannot be approved. Nothing has been written."""


class ProposalNotFound(ProposalError):
    """No proposal by that name is awaiting approval.

    Also what an id that could not name one of ours gets: a value that is not
    the shape ``mint`` produces names nothing, and saying so is the whole answer.
    """


class ProposalExpired(ProposalError):
    """It was minted too long ago to still stand for a decision."""


class ProposalFromAnotherSession(ProposalError):
    """It was minted by a different run of this server."""


class ApprovalRulesChanged(ProposalError):
    """The operation is unchanged; the rules that render and serialise it are not.

    ⚠️ **A distinct event from ``ApprovalMismatch`` and it must stay one.** Under
    changed rules the stored digest no longer matches a recomputation, so
    reporting the digest first would say *this is not the operation you
    approved* -- a mystery about the operation, when the operation is fine and
    the rules moved underneath it.
    """


class ApprovalMismatch(ProposalError):
    """The digest supplied names a different proposal than the id does.

    Named for ``apply.ApprovalMismatch``, which asks the same question one
    boundary further in -- *is the thing written the thing that was approved?*
    They are separate types because they are separate boundaries: this one is
    about an agent naming the wrong stored proposal, that one about an operation
    reaching the write that is not the one the digest covers.
    """


class ProposalCorrupt(ProposalError):
    """The stored file does not say what its own digest says it says."""


@dataclass(frozen=True, slots=True)
class Proposal:
    """One operation awaiting a human's yes, with everything needed to check it."""

    id: str
    session: str
    created_utc: datetime
    operation: schema.Operation
    approval_digest: str
    full_display: str
    rules_fingerprint: str


def store_directory(tree_dir: str) -> str:
    """Where proposals live for the copy at ``tree_dir``."""
    return os.path.join(tree_dir, PROPOSAL_DIRECTORY)


def new_session() -> str:
    """A fresh session identifier, minted once at server start."""
    return secrets.token_hex(_ID_LENGTH)


def _declared_fields(cls: type) -> tuple[str, ...]:
    """The field names a dataclass declares, in declaration order."""
    return tuple(item.name for item in fields(cls))


def rules_fingerprint() -> str:
    """A digest of the rules that render and serialise an operation.

    ⚠️ **Measured, not remembered.** It is taken over what a fixed committed
    probe operation actually produces -- its digest, its one-line preview and
    its full display -- plus the declared field names of every registered type
    and the record layout's version. Any change to ``to_dict``/``_to_wire``, to
    a renderer, to ``_PREVIEW_TEXT_LIMIT``, or to a dataclass's fields moves the
    probe's answers and so moves this. **Nothing has to be maintained by hand**,
    which is the only version binding that stays true.

    ⚠️ **A persisted digest is version-bound, and that is why this exists.** The
    premise that made slice 1's digest safe -- both ends computing it in one
    invocation from one checkout -- is gone the moment a proposal outlives the
    call that minted it.
    """
    registered = [
        [type_name, list(_declared_fields(spec.cls))]
        for type_name, spec in sorted(schema.REGISTRY.items())
    ]
    measured = [
        PROPOSAL_FORMAT,
        apply.RECORD_FORMAT,
        apply.approval_digest(PROBE),
        schema.preview(PROBE),
        schema.full_display(PROBE),
        registered,
    ]
    payload = json.dumps(measured, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Store:
    """Proposals on disk, for one server run.

    ``now`` is injected for the same reason every stream in ``cli`` is: a TTL
    tested by sleeping is a TTL nobody runs.
    """

    def __init__(
        self,
        directory: str,
        *,
        session: str,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        now: Callable[[], datetime] = apply.utc_now,
    ) -> None:
        self.directory = directory
        self.session = session
        self.ttl = timedelta(seconds=ttl_seconds)
        self._now = now

    # -- naming -------------------------------------------------------------

    def path_of(self, proposal_id: str, suffix: str = ".json") -> str:
        """Where a proposal in a given state sits. Refuses an id it did not mint."""
        return os.path.join(self.directory, f"{self._named(proposal_id)}{suffix}")

    def _named(self, proposal_id: str) -> str:
        if not _ID.fullmatch(proposal_id):
            raise ProposalNotFound(f"{proposal_id!r} is not the name of a proposal")
        return proposal_id

    # -- minting ------------------------------------------------------------

    def mint(self, operation: schema.Operation) -> Proposal:
        """File ``operation`` and return what the caller may be told about it.

        The caller gets the id, the sentence and the digest. **It does not get
        the operation**, which is what makes ``approve`` unable to act on one.
        """
        proposal = Proposal(
            id=secrets.token_hex(_ID_LENGTH),
            session=self.session,
            created_utc=self._now(),
            operation=operation,
            approval_digest=apply.approval_digest(operation),
            full_display=schema.full_display(operation),
            rules_fingerprint=rules_fingerprint(),
        )
        os.makedirs(self.directory, exist_ok=True)
        record = {
            "proposal": PROPOSAL_FORMAT,
            "id": proposal.id,
            "session": proposal.session,
            "created_utc": proposal.created_utc.isoformat(),
            "operation": schema.to_dict(operation),
            "approval_digest": proposal.approval_digest,
            "full_display": proposal.full_display,
            "rules_fingerprint": proposal.rules_fingerprint,
            "tool_version": __version__,
        }
        self._durably(self.path_of(proposal.id), record)
        return proposal

    # -- claiming -----------------------------------------------------------

    def claim(self, proposal_id: str, approval_digest: str) -> Proposal:
        """Take the proposal out of reach of any other caller, then check it.

        ⚠️ **The rename happens FIRST, and that ordering is the mutual
        exclusion.** Two concurrent approves cannot both proceed, because
        exactly one of them gets the rename; checking first and renaming after
        would leave a window between the two in which both are still valid.

        The price is stated rather than hidden: **any claim consumes the
        proposal, including a refused one.** A wrong digest burns it and the
        agent must propose again, which costs the owner a second reading and
        cannot cost him an unapproved write. That is the direction this rail
        fails in everywhere else.

        The order of the checks after the claim is itself load-bearing:

        1. the file must parse at all -- otherwise nothing below can be read;
        2. **the rules fingerprint, before anything else that could disagree**;
        3. the session that minted it;
        4. the stored digest against the stored operation -- integrity;
        5. the TTL;
        6. the caller's digest against the stored one.

        ⚠️ **Two goes before three, and that is not the plan's ordering.** The
        plan says the fingerprint is checked before any digest comparison, which
        is right and is not enough: changing a rendering rule means changing
        code, which means the server was restarted, which means the session id
        moved too. Checking the session first would make ``ApprovalRulesChanged``
        **structurally unreachable** -- reporting the restart, which is a
        symptom, in place of the rule change, which is the cause.

        ⚠️ **Two also goes before four for a mechanical reason**, not only a
        legible one: under changed rules ``from_dict`` may not be able to read
        the stored operation at all, so step 4 could raise rather than refuse.
        """
        pending = self._take(proposal_id)
        record = self._parsed(proposal_id, pending)

        stored_fingerprint = str(record.get("rules_fingerprint", ""))
        current = rules_fingerprint()
        if stored_fingerprint != current:
            self._refuse(
                proposal_id,
                ApprovalRulesChanged(
                    f"{proposal_id}: the operation is unchanged; the rules that render and "
                    f"serialise it are not. It was proposed under rules "
                    f"{stored_fingerprint} by tool version {record.get('tool_version')!r}, and "
                    f"this server renders under rules {current} by tool version "
                    f"{__version__!r}. Propose it again and read the new sentence."
                ),
            )

        if record.get("session") != self.session:
            self._refuse(
                proposal_id,
                ProposalFromAnotherSession(
                    f"{proposal_id}: this proposal was minted by a different run of the "
                    "server, so nothing here can vouch for what was shown. Propose it again."
                ),
            )

        stored_digest = str(record.get("approval_digest", ""))
        operation = self._operation(proposal_id, record, stored_digest)
        created = self._created(proposal_id, record)
        if self._now() - created > self.ttl:
            self._refuse(
                proposal_id,
                ProposalExpired(
                    f"{proposal_id}: this proposal has expired -- it was minted at "
                    f"{created.isoformat()} and stands for {self.ttl}. Propose it again."
                ),
            )

        if approval_digest != stored_digest:
            self._refuse(
                proposal_id,
                ApprovalMismatch(
                    f"{proposal_id}: the digest supplied is not this proposal's digest, so "
                    "the proposal being approved and the proposal being named are not the "
                    "same thing. Nothing was written."
                ),
            )

        return Proposal(
            id=proposal_id,
            session=self.session,
            created_utc=created,
            operation=operation,
            approval_digest=stored_digest,
            full_display=str(record.get("full_display", "")),
            rules_fingerprint=stored_fingerprint,
        )

    def claimed(self, proposal_id: str) -> Proposal:
        """The claimed proposal, read by the console that will display it.

        ⚠️ **This re-reads the file rather than taking anything from an
        argument**, which is the point of the whole store: what the console
        prints comes off the disk, not off anything the agent sent.
        """
        record = self._parsed(proposal_id, self.path_of(proposal_id, _PENDING))
        stored_digest = str(record.get("approval_digest", ""))
        return Proposal(
            id=proposal_id,
            session=str(record.get("session", "")),
            created_utc=self._created(proposal_id, record),
            operation=self._operation(proposal_id, record, stored_digest),
            approval_digest=stored_digest,
            full_display=str(record.get("full_display", "")),
            rules_fingerprint=str(record.get("rules_fingerprint", "")),
        )

    def consume(self, proposal_id: str, *, approved: bool) -> str:
        """Retire the claimed proposal, whichever way the human answered.

        ⚠️ **Called BEFORE Gramps is launched**, which is #69's disposition: a
        retried ``approve`` gets ``ProposalNotFound`` rather than a second note.
        To write a second one the agent must propose again -- a new console, and
        **a human saying yes a second time**, which is the correct place for a
        duplicate to become possible.
        """
        return self._move(proposal_id, _PENDING, _APPROVED if approved else _DECLINED)

    # -- the report the console leaves ---------------------------------------

    def report_path(self, proposal_id: str) -> str:
        return self.path_of(proposal_id, _REPORT)

    def write_report(self, proposal_id: str, payload: Mapping[str, object]) -> str:
        """What happened, for the server to relay and for the owner to find later."""
        return self._durably(self.report_path(proposal_id), dict(payload))

    def read_report(self, proposal_id: str) -> dict[str, object] | None:
        """The console's report, or ``None`` while it has not written one yet."""
        try:
            with open(self.report_path(proposal_id), encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    # -- the disk -----------------------------------------------------------

    def _take(self, proposal_id: str) -> str:
        try:
            return self._move(proposal_id, ".json", _PENDING)
        except OSError as failure:
            raise ProposalNotFound(
                f"{proposal_id}: no proposal is awaiting approval under that name. "
                "One approve consumes one proposal, so a retry lands here -- propose again."
            ) from failure

    def _move(self, proposal_id: str, was: str, becomes: str) -> str:
        source = self.path_of(proposal_id, was)
        destination = self.path_of(proposal_id, becomes)
        os.rename(source, destination)
        return destination

    def _refuse(self, proposal_id: str, failure: ProposalError) -> NoReturn:
        """Retire the claimed proposal and raise.

        ⚠️ **``NoReturn`` is load-bearing rather than documentation.** Every
        caller below goes on to read a value one of these checks may already
        have refused, and a helper the type checker believes can fall through
        turns each of those into a possibly-unbound name -- which is the same
        claim as *this refusal might not have refused*.
        """
        with suppress(OSError):  # the refusal is what matters, not the tidying
            self._move(proposal_id, _PENDING, _REFUSED)
        raise failure

    def _parsed(self, proposal_id: str, path: str) -> Mapping[str, object]:
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except OSError as failure:
            raise ProposalNotFound(f"{proposal_id}: {failure.strerror or failure}") from failure
        except json.JSONDecodeError as failure:
            self._refuse(
                proposal_id,
                ProposalCorrupt(f"{proposal_id}: the stored proposal is not readable: {failure}"),
            )
        if not isinstance(record, dict):
            self._refuse(
                proposal_id, ProposalCorrupt(f"{proposal_id}: the stored proposal is not an object")
            )
        return record

    def _operation(
        self, proposal_id: str, record: Mapping[str, object], stored_digest: str
    ) -> schema.Operation:
        """The stored operation, and proof that it is the one the digest covers."""
        payload = record.get("operation")
        try:
            if not isinstance(payload, Mapping):
                raise schema.SchemaError("an operation is an object")
            operation = schema.from_dict(payload)
        except schema.SchemaError as failure:
            self._refuse(
                proposal_id,
                ProposalCorrupt(f"{proposal_id}: the stored operation cannot be read: {failure}"),
            )
        if apply.approval_digest(operation) != stored_digest:
            self._refuse(
                proposal_id,
                ProposalCorrupt(
                    f"{proposal_id}: the stored operation is not the operation this proposal's "
                    "own digest covers, so the file has been edited since it was written."
                ),
            )
        return operation

    def _created(self, proposal_id: str, record: Mapping[str, object]) -> datetime:
        try:
            return datetime.fromisoformat(str(record.get("created_utc")))
        except ValueError:
            self._refuse(
                proposal_id,
                ProposalCorrupt(f"{proposal_id}: the stored proposal carries no readable time"),
            )

    def _durably(self, path: str, record: dict[str, object]) -> str:
        """Create ``path`` exclusively, write ``record``, and force it to disk.

        ``core.apply._durably``'s rule, for the same reason and with the same
        residual: the bytes are durable and the directory entry is not, because
        a directory cannot be ``fsync``'d portably.
        """
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "x", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as failure:
            raise ProposalError(f"{path}: {failure.strerror or failure}") from failure
        return path
