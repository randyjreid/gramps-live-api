"""The three tools, and the two things an agent may never do through them.

⚠️ **An agent may not supply an operation, and it may not type ``y``.** Those
are the whole trust model: ``propose_note`` keeps the operation on the server
and hands back an id, a sentence and a digest; ``approve`` takes an id and a
digest and opens a console the agent cannot write to. Everything below is one of
those two properties or a refusal that keeps one of them true.

Covered to the process boundary. The spawner is injected, so what these tests
prove is that the console is reached and told the right proposal -- never that a
note reached a tree, and no longer what the window decided, because **nothing in
this server can find that out**. The demo proves both.

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
import io
from collections.abc import Mapping, Sequence
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

from gramps_live_api import cli, config, invocation  # noqa: E402
from gramps_live_api.core import apply, people, proposals, schema  # noqa: E402
from gramps_live_api_mcp import server as mcp_server  # noqa: E402
from tests.fixtures import synthetic  # noqa: E402
from tests.fixtures.trees import blessed  # noqa: E402
from tests.unit.test_cli import equipped, marker  # noqa: E402
from tests.unit.test_cli_approve import Recorder, written_and_read_back  # noqa: E402

PUBLIC = ("p0001", "I0044", "Elowen", "Ashenmoor")
PRIVATE = ("p0002", "I0055", "Quorvane", "Weissvane")


def export_document() -> str:
    """Two people, one of them carrying Gramps' own ``priv`` flag."""
    return synthetic.gramps_export_document(
        people="".join(
            synthetic.gramps_person(
                handle=handle,
                gramps_id=gramps_id,
                names=synthetic.gramps_name(first=first, surname=surname),
                private="1" if handle == PRIVATE[0] else "",
                event_handles=((f"e{gramps_id}", "Primary"),),
            )
            for handle, gramps_id, first, surname in (PUBLIC, PRIVATE)
        ),
        events="".join(
            synthetic.gramps_event(
                handle=f"e{gramps_id}",
                event_type="Birth",
                date=synthetic.gramps_dateval(year),
            )
            for (_, gramps_id, _, _), year in ((PUBLIC, "1856-03-04"), (PRIVATE, "1861"))
        ),
    )


class Spawner:
    """A console that never opens. Records what it would have been asked to run.

    ⚠️ **It hands nothing back, and neither does the real one.** The server
    starts the window and holds nothing that could act on it -- no handle, no
    ``poll``, no way to ask what it decided. ``then`` is how a test says *and
    this is what happened in that window*, which is the only thing that ever
    happens there.
    """

    def __init__(self, then: object = None) -> None:
        self.calls: list[Sequence[str]] = []
        self._then = then

    def __call__(self, argv: Sequence[str]) -> None:
        self.calls.append(list(argv))
        if callable(self._then):
            self._then(argv)


def equipment(tmp_path: Path, **extra: str) -> tuple[str, Mapping[str, str]]:
    """A blessed copy and an environment naming it and a real export."""
    copy = blessed(tmp_path / "tree")
    export = tmp_path / "tree.gramps"
    export.write_text(export_document(), encoding="utf-8")
    return copy.tree_dir, equipped(
        tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: str(export), **extra}
    )


def tools(
    tmp_path: Path,
    *,
    spawner: Spawner | None = None,
    platform: str = "win32",
) -> mcp_server.Tools:
    """⚠️ **``platform`` defaults to the one this project's write path targets.**

    ``approve`` refuses a host that cannot open a separate console, and it does
    so *before* the claim (L2), so a helper defaulting to the runner's own
    platform would refuse every approve test on the Linux matrix and pass them
    all on the owner's Windows box. Which is the failure ``equipped``'s runtime
    override already exists for, one layer down.
    """
    _, environ = equipment(tmp_path)
    return mcp_server.Tools(
        environ,
        session="sess0001",
        spawner=spawner or Spawner(),
        platform=platform,
    )


# ---------------------------------------------------------------------------
# Criterion 1 and 3 -- the surface, and what it says about itself
# ---------------------------------------------------------------------------


def test_exactly_three_tools_are_exposed(tmp_path: Path) -> None:
    """Criterion 1. Asserted against the SERVER's own answer, not a constant."""
    exposed = asyncio.run(mcp_server.build_server(tools(tmp_path)).list_tools())
    assert {tool.name for tool in exposed} == {"list_people", "propose_note", "approve"}
    assert {tool.name for tool in exposed} == mcp_server.TOOL_NAMES


def test_every_tool_says_what_it_is_for(tmp_path: Path) -> None:
    exposed = asyncio.run(mcp_server.build_server(tools(tmp_path)).list_tools())
    for tool in exposed:
        assert tool.description and tool.description.strip()


def test_the_note_types_come_from_the_frozenset_in_both_directions() -> None:
    """Criterion 3. In a server the description is the ONLY documentation the
    caller ever sees, so a set spelled out beside the frozenset goes stale the
    first time somebody adds a member -- which is issue #64's second half."""
    listed = schema._one_of(schema.NOTE_TYPES)
    assert listed in mcp_server.PROPOSE_NOTE_DESCRIPTION
    assert set(listed.split(", ")) == set(schema.NOTE_TYPES), "every member, and nothing else"
    for member in schema.NOTE_TYPES:
        assert member in mcp_server.PROPOSE_NOTE_DESCRIPTION


def test_the_object_types_come_from_the_frozenset_and_name_the_restriction() -> None:
    listed = schema._one_of(schema.OBJECT_TYPES)
    assert listed in mcp_server.PROPOSE_NOTE_DESCRIPTION
    assert set(listed.split(", ")) == set(schema.OBJECT_TYPES)
    assert apply.TARGET_OBJECT_TYPE in mcp_server.PROPOSE_NOTE_DESCRIPTION


def test_the_description_says_the_chat_yes_is_not_the_approval() -> None:
    """The ruling's own words, in the place an agent will actually read them."""
    assert "console" in mcp_server.PROPOSE_NOTE_DESCRIPTION
    assert "console" in mcp_server.APPROVE_DESCRIPTION


# ---------------------------------------------------------------------------
# Criterion 2 -- list_people
# ---------------------------------------------------------------------------


def test_list_people_answers_the_question_the_demo_asked(tmp_path: Path) -> None:
    found = tools(tmp_path).list_people("ashenmoor")

    assert found["shown"] == 1
    listed = found["people"][0]  # type: ignore[index]
    assert listed["name"] == "Elowen Ashenmoor"
    assert listed["birth_year"] == 1856
    assert listed["gramps_id"] == "I0044"
    assert listed["handle"] == PUBLIC[0]


def test_a_handle_from_list_people_passes_the_reference_check_unedited(tmp_path: Path) -> None:
    """Criterion 2's sharpest clause. Returning the raw attribute hands the
    caller a value ``validate`` refuses, with no clue why."""
    listed = tools(tmp_path).list_people("ashenmoor")["people"][0]  # type: ignore[index]
    operation = schema.AddNote(
        target=schema.ObjectRef(
            object_type="person", handle=str(listed["handle"]), gramps_id=str(listed["gramps_id"])
        ),
        note_type="research",
        text="a note",
    )
    result = schema.validate(operation)
    assert result.well_formed, [violation.message for violation in result.violations]


def test_list_people_never_shows_a_private_person(tmp_path: Path) -> None:
    """Ruling 1, enforcement point one."""
    found = tools(tmp_path).list_people("weissvane")
    assert found["people"] == []
    assert found["matched"] == 0


def test_list_people_will_not_list_everybody(tmp_path: Path) -> None:
    with pytest.raises(people.SearchTermRequired):
        tools(tmp_path).list_people("  ")


def test_list_people_needs_no_blessed_copy(tmp_path: Path) -> None:
    """It writes nothing, so it must not require the permission to write.

    A read-only tool that refused until the write path was configured would
    push the owner to configure the write path in order to look somebody up.
    """
    export = tmp_path / "tree.gramps"
    export.write_text(export_document(), encoding="utf-8")
    environ = equipped(
        tmp_path, **{config.ENV_COPY: str(tmp_path / "not-a-tree"), config.ENV_EXPORT: str(export)}
    )
    reader = mcp_server.Tools(environ, session="sess0001", spawner=Spawner())

    assert reader.list_people("ashenmoor")["shown"] == 1


# ---------------------------------------------------------------------------
# Ruling 1, enforcement point two -- and the amendment's explicit test
# ---------------------------------------------------------------------------


def test_propose_note_refuses_a_private_person(tmp_path: Path) -> None:
    with pytest.raises(mcp_server.TargetIsPrivate) as refusal:
        tools(tmp_path).propose_note(PRIVATE[1], PRIVATE[0], "research", "a note")
    assert "private" in str(refusal.value)


def test_a_private_person_is_unreachable_even_though_list_people_was_never_called(
    tmp_path: Path,
) -> None:
    """⚠️ **The two enforcement points are independent, and this is why.**

    A handle can arrive from a stale export, from a note somebody wrote down, or
    from a caller that never listed at all. Excluding a person from a listing
    says nothing about whether they can be named directly.
    """
    made = tools(tmp_path)
    with pytest.raises(mcp_server.TargetIsPrivate):
        made.propose_note(PRIVATE[1], PRIVATE[0], "research", "a note")


def test_private_and_not_found_do_not_produce_the_same_message(tmp_path: Path) -> None:
    """The amendment's own words. Silence here would leave the caller unable to
    tell *no such person* from *that person is private* -- the same defect class
    as a lock refusal that names no remedy."""
    made = tools(tmp_path)
    with pytest.raises(mcp_server.TargetIsPrivate) as private:
        made.propose_note(PRIVATE[1], PRIVATE[0], "research", "a note")
    with pytest.raises(mcp_server.TargetNotInExport) as absent:
        made.propose_note("I9999", "nosuchhandle", "research", "a note")

    assert type(private.value) is not type(absent.value)
    assert str(private.value) != str(absent.value)


def test_a_person_the_export_does_not_hold_is_refused_and_the_staleness_named(
    tmp_path: Path,
) -> None:
    """The same refusal carries the export-versus-copy answer, because a person
    added to the copy since the export was taken lands here and the message is
    the only place that fact can reach the caller."""
    with pytest.raises(mcp_server.TargetNotInExport) as refusal:
        tools(tmp_path).propose_note("I9999", "nosuchhandle", "research", "a note")
    assert "export" in str(refusal.value)


def test_a_note_type_outside_the_closed_set_is_refused_with_the_set(tmp_path: Path) -> None:
    with pytest.raises(mcp_server.OperationNotWellFormed) as refusal:
        tools(tmp_path).propose_note(PUBLIC[1], PUBLIC[0], "gossip", "a note")
    assert schema._one_of(schema.NOTE_TYPES) in str(refusal.value)


# ---------------------------------------------------------------------------
# propose_note -- the operation never leaves the server
# ---------------------------------------------------------------------------


def test_propose_note_hands_back_no_operation(tmp_path: Path) -> None:
    """⚠️ **The binding, stated as what is ABSENT.** ``approve`` has no operation
    parameter, so an agent that never received one cannot round-trip a different
    one back."""
    proposed = tools(tmp_path).propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")

    assert set(proposed) == {"proposal_id", "sentence", "approval_digest", "expires_utc", "next"}
    assert "operation" not in proposed


def test_the_sentence_returned_is_the_sentence_the_console_will_show(tmp_path: Path) -> None:
    made = tools(tmp_path)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    operation = schema.AddNote(
        target=schema.ObjectRef(object_type="person", handle=PUBLIC[0], gramps_id=PUBLIC[1]),
        note_type="research",
        text="a note",
    )
    assert proposed["sentence"] == schema.full_display(operation)
    assert proposed["approval_digest"] == apply.approval_digest(operation)


def test_the_return_says_the_chat_yes_is_not_the_approval(tmp_path: Path) -> None:
    proposed = tools(tmp_path).propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    assert "console" in str(proposed["next"])


# ---------------------------------------------------------------------------
# approve -- criteria 4, 6 and 7
# ---------------------------------------------------------------------------


def test_naming_one_proposal_with_another_digest_is_refused(tmp_path: Path) -> None:
    """Criterion 4, through the tool the agent actually calls."""
    made = tools(tmp_path)
    first = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "one note")
    second = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "another note")

    with pytest.raises(proposals.ApprovalMismatch):
        made.approve(str(first["proposal_id"]), str(second["approval_digest"]))


def test_approve_opens_the_console_and_returns_without_an_outcome(tmp_path: Path) -> None:
    """Criterion 7. The server performs no write of any kind: it spawns, and it
    returns -- and what it returns says nothing about what the owner decided,
    because it does not know and there is nothing left that could tell it."""
    spawner = Spawner()
    made = tools(tmp_path, spawner=spawner)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id = str(proposed["proposal_id"])

    reply = made.approve(proposal_id, str(proposed["approval_digest"]))

    assert spawner.calls, "the console was never opened, so nobody was asked"
    assert proposal_id in spawner.calls[0]
    assert reply["console"] == "opened"
    assert "outcome" not in reply


def test_approves_reply_is_exactly_three_keys(tmp_path: Path) -> None:
    """⚠️ **A red line rather than a comment**, and the same idiom as
    ``TOOL_NAMES``: re-adding an outcome word to this reply is a failing test,
    not a silent regression that a reader has to notice.

    The layer that carried an outcome to the agent drew a finding in four
    consecutive review rounds and was deleted rather than hardened. Nothing in
    the wire replaces it -- the owner watched the window, and he is the channel.
    """
    made = tools(tmp_path)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")

    reply = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    assert set(reply) == {"proposal_id", "console", "next"}


def test_the_description_promises_no_outcome_and_does_not_widen_the_refusal(
    tmp_path: Path,
) -> None:
    """⚠️ **In a server the description is the ONLY documentation the caller
    sees**, so what it promises is the interface.

    Two halves, and the second is the one a fix would get wrong. It must say
    this call cannot see the decision -- otherwise an agent reads a returning
    call as a completed write. And it must **not** say a refusal means nothing
    was consumed: ``ApprovalMismatch``, ``ProposalExpired``, ``ProposalCorrupt``,
    ``ApprovalRulesChanged`` and ``ProposalFromAnotherSession`` all consume by
    design, and the rollback added beside them tempts exactly that sentence.
    """
    said = mcp_server.APPROVE_DESCRIPTION

    assert "cannot see what he decides" in said
    assert "ask him what it said" in said
    assert "nothing was consumed" not in said, (
        "five refusals consume the proposal by design, so that sentence is false -- "
        "and a fix may not widen the claim it fixes"
    )
    for word in ("still_open", "unknown", "unverified"):
        assert word not in said, f"{word!r} is a word from the layer that was deleted"


def test_a_second_approve_is_refused_whatever_the_console_answered(tmp_path: Path) -> None:
    """Criterion 6, at the tool boundary."""
    made = tools(tmp_path)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id, digest = str(proposed["proposal_id"]), str(proposed["approval_digest"])
    made.approve(proposal_id, digest)

    with pytest.raises(proposals.ProposalNotFound):
        made.approve(proposal_id, digest)


# ---------------------------------------------------------------------------
# ⭐ What the agent is NOT told, and cannot ask
# ---------------------------------------------------------------------------


def test_approve_returns_before_the_console_has_been_answered(tmp_path: Path) -> None:
    """⚠️ **The whole shape of the deletion, asserted as a fact about time.**

    There is no polling, no timeout and no window in which a client may give up
    while the owner reads: the call returns as soon as the window is open. What
    used to make that dangerous -- an agent left with an undefined answer -- is
    gone with the answer itself, and what stays is the ordering that made the
    old timeout safe anyway: the proposal is consumed at the claim, so a retry
    meets ``ProposalNotFound`` whatever the owner does next.
    """
    answered: list[str] = []
    made = tools(tmp_path, spawner=Spawner(lambda _: answered.append("the owner is still reading")))
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id, digest = str(proposed["proposal_id"]), str(proposed["approval_digest"])

    reply = made.approve(proposal_id, digest)

    assert reply["console"] == "opened"
    assert "next" in reply, "the agent is told what to do instead of being told an outcome"
    with pytest.raises(proposals.ProposalNotFound):
        made.approve(proposal_id, digest)


def test_there_is_no_second_tool_that_could_report_the_outcome(tmp_path: Path) -> None:
    """Criterion 1 read as a deletion: three tools, and none of them asks.

    ``outcome_of`` existed as unexposed machinery with a residual recorded
    against it. Its subject -- the report file -- is gone, so the residual is
    closed by having nothing left to expose.
    """
    made = tools(tmp_path)
    assert not hasattr(made, "outcome_of")
    exposed = asyncio.run(mcp_server.build_server(made).list_tools())
    assert {tool.name for tool in exposed} == mcp_server.TOOL_NAMES


# ---------------------------------------------------------------------------
# The console the agent cannot write to
# ---------------------------------------------------------------------------


def test_the_console_is_a_new_window_on_the_platform_this_targets() -> None:
    started: list[dict[str, object]] = []

    def popen(argv: Sequence[str], **options: object) -> object:
        started.append({"argv": list(argv), **options})
        return object()

    mcp_server.new_console(
        ["python", "-m", "gramps_live_api", "approve", "x"], platform="win32", popen=popen
    )

    assert started[0]["creationflags"] == mcp_server.CREATE_NEW_CONSOLE


def test_a_host_that_cannot_open_a_console_does_not_burn_the_proposal(tmp_path: Path) -> None:
    """L2, and the defect is a loop rather than a single refusal.

    ``approve`` claimed the proposal -- an irreversible rename, by design --
    **before** asking whether a console could be opened at all. On a host where
    it cannot, every proposal was consumed and orphaned as ``.pending.json``,
    the refusal advised proposing again, and proposing again reached the same
    place: propose, approve, burn, forever, with a growing pile of orphans
    inside the owner's copy.

    ⚠️ **The platform check needs nothing from the claim**, which is why the
    ordering was free to be wrong and is free to be right. The second half of
    this test is the part that matters: the proposal is still there afterwards,
    so a host that CAN spawn a console still approves the same one.
    """
    _, environ = equipment(tmp_path)
    spawner = Spawner()
    refuses = mcp_server.Tools(environ, session="sess0001", spawner=spawner, platform="linux")
    proposed = refuses.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id, digest = str(proposed["proposal_id"]), str(proposed["approval_digest"])
    store = refuses._store()

    with pytest.raises(mcp_server.ConsoleUnavailable):
        refuses.approve(proposal_id, digest)

    assert spawner.calls == [], "nothing may be spawned on a host that has no console"
    assert not Path(store.path_of(proposal_id, ".pending.json")).exists(), "orphaned"
    assert Path(store.path_of(proposal_id)).is_file(), "the proposal must survive the refusal"

    opens = Spawner()
    answers = mcp_server.Tools(environ, session="sess0001", spawner=opens, platform="win32")
    assert answers.approve(proposal_id, digest)["console"] == "opened"
    assert opens.calls, "the surviving proposal must reach a console that can be opened"


def test_a_spawn_that_fails_leaves_the_proposal_approvable(tmp_path: Path) -> None:
    """D-1, and it is L2's defect one stage further along.

    ``require_console`` only validates the platform. On a host that passes it,
    ``Popen`` can still raise -- WinError 8, *not enough storage is available to
    process this command* -- and that ran **after** the claim had renamed the
    proposal to ``.pending.json``. No console opened, the exception escaped, and
    retrying got ``ProposalNotFound``: the same propose-approve-burn loop L2
    closed for the other cause.

    ⚠️ **Asserted BY CLASS rather than by that instance.** The rollback keys on
    the follow-through raising, not on which failure it was, so what this test
    fixes is the predicate -- the next launch failure nobody has met is covered
    by the same line.
    """
    _, environ = equipment(tmp_path)

    def cannot_launch(_: Sequence[str]) -> None:
        raise OSError(8, "not enough storage is available to process this command")

    made = mcp_server.Tools(environ, session="sess0001", spawner=cannot_launch, platform="win32")
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id, digest = str(proposed["proposal_id"]), str(proposed["approval_digest"])
    store = made._store()

    with pytest.raises(OSError):
        made.approve(proposal_id, digest)

    assert not Path(store.path_of(proposal_id, ".pending.json")).exists(), "orphaned"
    assert Path(store.path_of(proposal_id)).is_file(), "the proposal must survive the failure"

    opens = Spawner()
    working = mcp_server.Tools(environ, session="sess0001", spawner=opens, platform="win32")
    assert working.approve(proposal_id, digest)["console"] == "opened"
    assert opens.calls, "the same id must still be approvable once the host is fixed"


# ---------------------------------------------------------------------------
# ⭐ Every precondition the invariant names, answered BEFORE the claim
# ---------------------------------------------------------------------------


def unclaimed(tmp_path: Path, environ: Mapping[str, str]) -> tuple[str, str, proposals.Store]:
    """One minted proposal, and the store it sits in. Nothing is claimed yet."""
    made = mcp_server.Tools(environ, session="sess0001", spawner=Spawner(), platform="win32")
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    return str(proposed["proposal_id"]), str(proposed["approval_digest"]), made._store()


def test_a_copy_that_stopped_being_blessed_is_refused_before_the_claim(tmp_path: Path) -> None:
    """The authorisation half of the invariant. It already held; this is its test.

    ``_store`` runs ``apply.authorise`` -- the same constructor the write path
    uses -- and it runs before the claim, so a copy whose sentinel has gone
    since the proposal was minted refuses without burning it.
    """
    copy, environ = equipment(tmp_path)
    proposal_id, digest, store = unclaimed(tmp_path, environ)
    Path(copy, apply.SENTINEL_NAME).unlink()

    spawner = Spawner()
    made = mcp_server.Tools(environ, session="sess0001", spawner=spawner, platform="win32")
    with pytest.raises(apply.UnblessedTree):
        made.approve(proposal_id, digest)

    assert spawner.calls == [], "no window may open over a copy that is not blessed"
    assert Path(store.path_of(proposal_id)).is_file(), "the proposal must survive the refusal"


def test_a_host_with_no_gramps_runtime_is_refused_before_the_claim(tmp_path: Path) -> None:
    """⭐ **The one addition this change makes, and the invariant names it.**

    ``_approve`` asks for a runtime as its second act, in the console -- which
    is *after* the window has opened, and by then the proposal is claimed. So a
    host with no Gramps consumed a proposal on every ``approve``, showed the
    owner a window that refused, and advised proposing again into the same
    place. That is L2 and D-1's burn loop arriving through the one precondition
    the invariant names that nothing asked before the claim.

    ⚠️ **The console keeps its own discovery**, for ``require_console``'s
    reason: one guarantee is *the proposal is not burnt reaching the check*, the
    other is *no caller anywhere launches without one*.
    """
    _, environ = equipment(tmp_path, **{config.ENV_RUNTIME: "", "ProgramFiles": ""})
    proposal_id, digest, store = unclaimed(tmp_path, environ)

    spawner = Spawner()
    made = mcp_server.Tools(environ, session="sess0001", spawner=spawner, platform="win32")
    with pytest.raises(config.ConfigError) as refusal:
        made.approve(proposal_id, digest)

    assert config.RUNTIME_NAME in str(refusal.value), "the refusal names what is missing"
    assert spawner.calls == [], "no window may open on a host that cannot run Gramps"
    assert Path(store.path_of(proposal_id)).is_file(), "the proposal must survive the refusal"


def test_a_configured_runtime_that_is_not_there_is_refused_before_the_claim(
    tmp_path: Path,
) -> None:
    """The same precondition reached by the way the owner will actually reach it.

    A configured ``gramps_runtime`` naming a path that no longer exists -- an
    uninstall, a version bump, a typo -- satisfies *a runtime was named* and
    fails at the launch. ``check``'s own runtime line has always asked
    ``os.path.isfile``; this asks the same question in the same words, before
    the irreversible step rather than after it.
    """
    _, environ = equipment(tmp_path, **{config.ENV_RUNTIME: str(tmp_path / "gone" / "grampsd.exe")})
    proposal_id, digest, store = unclaimed(tmp_path, environ)

    spawner = Spawner()
    made = mcp_server.Tools(environ, session="sess0001", spawner=spawner, platform="win32")
    with pytest.raises(config.ConfigError) as refusal:
        made.approve(proposal_id, digest)

    assert "gone" in str(refusal.value), "the refusal names the path that is not there"
    assert spawner.calls == [], "no window may open when the runtime it needs is absent"
    assert Path(store.path_of(proposal_id)).is_file(), "the proposal must survive the refusal"


def test_a_platform_that_cannot_separate_the_console_is_refused() -> None:
    """⚠️ **Fail closed rather than run the console in our own window.**

    The whole design rests on a window the agent cannot write to. Without a
    separate console that premise is false, and running anyway would keep the
    shape of the mechanism while losing the property it exists for.
    """
    with pytest.raises(mcp_server.ConsoleUnavailable) as refusal:
        mcp_server.new_console(["python"], platform="linux", popen=lambda *a, **k: None)
    assert "console" in str(refusal.value)


# ---------------------------------------------------------------------------
# ⭐ Criterion 8 -- every slice 1 rail, through the MCP path, to the boundary
# ---------------------------------------------------------------------------


def test_the_whole_path_from_propose_to_a_written_note(tmp_path: Path) -> None:
    """Propose, approve, a real console process running in-process, a runner at
    the Gramps boundary -- and the note's identifier **at the window**.

    ⚠️ **This is criterion 8 read as the owner ruled it**: unit-tested through
    the MCP path with an injected runner up to the process boundary, and
    demo-verified beyond it. It does not prove the sentinel, the lock, the undo
    record or the read-back hold inside Gramps. CI has no Gramps, no ``gi`` and
    no tree, and a criterion reading as *CI-proven* is the false claim
    ``docs/using.md`` exists to avoid.

    ⚠️ **What moved is where the Gramps ID is asserted, and only that.** It used
    to come back in the tool's reply; it is now printed at the console the owner
    is standing in front of, and the reply says nothing about it. The route from
    that window to the transcript is the owner typing what he read.
    """
    copy, environ = equipment(tmp_path)
    runner = Recorder(*written_and_read_back())
    window = io.StringIO()

    def console(argv: Sequence[str]) -> None:
        cli.main(
            ("approve", argv[-1]),
            environ=environ,
            stdin=io.StringIO("y\n\n"),
            stdout=window,
            stderr=io.StringIO(),
            runner=runner,
        )

    made = mcp_server.Tools(environ, session="sess0001", spawner=Spawner(console), platform="win32")
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "Ashenmoor deed, volume two.")
    reply = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    assert set(reply) == {"proposal_id", "console", "next"}
    assert "N0021" not in str(reply), "the agent is not told what was written"
    assert "note N0021 written" in window.getvalue(), "the owner is"
    assert len(runner.runs) == 2, "the write, and the read-back in a fresh process"
    argv, environment = runner.runs[0]
    assert "-u" not in argv and "--force-unlock" not in argv, "Gramps keeps its lock"
    assert environment[invocation.ENV_APPROVED_DIGEST] == str(proposed["approval_digest"])
    assert Path(copy, apply.SENTINEL_NAME).is_file(), "the token was over a blessed copy"


def test_the_environment_cap_is_inherited_and_reaches_the_owner_verbatim(
    tmp_path: Path,
) -> None:
    """#66 is OUT, so the MCP path inherits the Windows environment-block cap.

    It fails closed -- Gramps does not launch and nothing is written -- and the
    underlying message must travel rather than a paraphrase of it.

    ⚠️ **It reaches the OWNER, not the agent, and that is the trade this
    deletion makes.** The cap is crossed after the window is open, so the tool
    call has already returned; the refusal is on the screen he is looking at.
    An agent that has not been told cannot relay it, which is why the reply's
    ``next`` tells it to ask.
    """
    _, environ = equipment(tmp_path)
    refusal = "OSError: [WinError 206] The filename or extension is too long"
    window = io.StringIO()

    def console(argv: Sequence[str]) -> None:
        cli.main(
            ("approve", argv[-1]),
            environ=environ,
            stdin=io.StringIO("y\n\n"),
            stdout=io.StringIO(),
            stderr=window,
            runner=Recorder(marker(ok=False, error=refusal)),
        )

    made = mcp_server.Tools(environ, session="sess0001", spawner=Spawner(console), platform="win32")
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a very long note")
    reply = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    assert refusal in window.getvalue(), "the underlying message travels, not a paraphrase"
    assert refusal not in str(reply), "the agent was not told, and cannot be"
    assert "ask him" in str(reply["next"]).lower()


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
