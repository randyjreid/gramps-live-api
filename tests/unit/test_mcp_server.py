"""The three tools, and the two things an agent may never do through them.

⚠️ **An agent may not supply an operation, and it may not type ``y``.** Those
are the whole trust model: ``propose_note`` keeps the operation on the server
and hands back an id, a sentence and a digest; ``approve`` takes an id and a
digest and opens a console the agent cannot write to. Everything below is one of
those two properties or a refusal that keeps one of them true.

Covered to the process boundary. The spawner is injected, so what these tests
prove is that the console is reached, told the right proposal, and believed
about the outcome -- never that a note reached a tree. The demo proves that.

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

    ``handle`` is what the real spawner hands back -- the process, so a caller
    can ask whether it is still alive. ``None`` is *we cannot tell*, which is
    what every test written before that mattered gets and what keeps their
    behaviour unchanged.
    """

    def __init__(self, then: object = None, *, handle: object = None) -> None:
        self.calls: list[Sequence[str]] = []
        self._then = then
        self._handle = handle

    def __call__(self, argv: Sequence[str]) -> object:
        self.calls.append(list(argv))
        if callable(self._then):
            self._then(argv)
        return self._handle


class Exited:
    """A console process that has ended. ``poll`` is ``subprocess.Popen``'s."""

    def __init__(self, code: int = 1) -> None:
        self._code = code

    def poll(self) -> int | None:
        return self._code


class Running:
    """A console process that is still up, which is what a slow reader looks like."""

    def poll(self) -> int | None:
        return None


class Clock:
    """A monotonic clock a test moves by hand, and a sleep that moves it."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


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
    timeout: float = 45.0,
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
    clock = Clock()
    made = mcp_server.Tools(
        environ,
        session="sess0001",
        spawner=spawner or Spawner(),
        clock=clock,
        sleep=clock.sleep,
        approval_timeout=timeout,
        platform=platform,
    )
    made.clock = clock  # type: ignore[attr-defined]
    return made


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


def test_approve_opens_the_console_and_believes_only_its_report(tmp_path: Path) -> None:
    """Criterion 7. The server performs no write of any kind: it spawns, and it
    reads what the console filed."""
    spawner = Spawner()
    made = tools(tmp_path, spawner=spawner)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id = str(proposed["proposal_id"])

    def answer(_: Sequence[str]) -> None:
        made._store().write_report(proposal_id, {"outcome": "declined"})

    spawner._then = answer
    outcome = made.approve(proposal_id, str(proposed["approval_digest"]))

    assert spawner.calls, "the console was never opened, so nobody was asked"
    assert proposal_id in spawner.calls[0]
    assert outcome["outcome"] == "declined"


def test_a_second_approve_is_refused_whatever_the_console_answered(tmp_path: Path) -> None:
    """Criterion 6, at the tool boundary."""
    made = tools(tmp_path)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id, digest = str(proposed["proposal_id"]), str(proposed["approval_digest"])
    made.approve(proposal_id, digest)

    with pytest.raises(proposals.ProposalNotFound):
        made.approve(proposal_id, digest)


# ---------------------------------------------------------------------------
# ⭐ The timeout -- the sharp one
# ---------------------------------------------------------------------------


def test_a_timeout_leaves_no_proposal_that_a_later_call_could_write(tmp_path: Path) -> None:
    """⚠️ **The ruling's hard requirement: a timeout must NEVER leave a proposal
    in a state where a later call writes it.**

    ``approve`` blocks on a human at a console, and a client may give up while
    the owner is still reading. What that must not do is leave anything a retry
    can act on. It does not, and the reason is structural rather than careful:
    the proposal was consumed at the claim, before the console was even opened.
    """
    made = tools(tmp_path, timeout=45.0)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id, digest = str(proposed["proposal_id"]), str(proposed["approval_digest"])

    outcome = made.approve(proposal_id, digest)

    assert outcome["outcome"] == "still_open"
    assert made.clock.now >= 45.0, "it waited"  # type: ignore[attr-defined]
    with pytest.raises(proposals.ProposalNotFound):
        made.approve(proposal_id, digest)


def test_a_timeout_tells_the_agent_not_to_retry_and_where_to_look(tmp_path: Path) -> None:
    """The acceptable answer the amendment names: the write may still proceed
    and is reported as an outcome to relay, never as one to retry. What is not
    acceptable is that the window be undefined, so it is spelled out."""
    made = tools(tmp_path, timeout=1.0)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    outcome = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    message = str(outcome["error"])
    assert "not retry" in message.lower()
    assert proposals.PROPOSAL_DIRECTORY in message, "where the answer will appear"
    assert "has not reported back" in message, (
        "the message says what is actually known: the console has not reported. It is "
        "now known to be ALIVE as well -- a dead one takes the branch above and never "
        "reaches this message -- but reaching an answer and having reached one are "
        "still different facts, and this one is the second"
    )


def test_a_console_that_died_before_answering_is_not_still_open_forever(tmp_path: Path) -> None:
    """L7, and ``still_open`` was the only answer this could ever give.

    Console death **before** the owner answers files no report -- the window is
    closed, the machine is shut down, the process is killed -- and nothing in
    the console can file one, because nothing in it runs. So the server waited
    out its whole timeout, said ``still_open``, and ``outcome_of`` said
    ``still_open`` for as long as anybody asked. **The state never resolved.**

    ⚠️ **What discriminates is process liveness, and only that.** A window still
    open with a slow reader in front of it and a window that is gone look
    identical from the report directory, which is exactly why the message could
    only ever say *has not reported back*. The server spawned the process; it
    can ask. It could not before, because ``new_console`` threw the handle away.

    ``unknown`` rather than ``failed``: killed before the answer nothing was
    written, killed after ``y`` a note may be in the tree, and this cannot tell
    which -- which is precisely what ``APPROVE_DESCRIPTION`` defines the word to
    mean.
    """
    made = tools(tmp_path, spawner=Spawner(handle=Exited()), timeout=45.0)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")

    outcome = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    assert outcome["outcome"] == "unknown"
    assert made.clock.now < 45.0, (  # type: ignore[attr-defined]
        "it waited out a timeout for a console that had already ended"
    )
    assert "exited" in str(outcome["error"]), "the message says what is actually known"
    assert proposals.PROPOSAL_DIRECTORY in str(outcome["error"]), "where to look"


def test_a_console_that_files_its_report_and_then_exits_is_believed(tmp_path: Path) -> None:
    """The race the liveness check must not lose, and it is the ordinary case.

    Every console that answers exits immediately afterwards. Reading the report
    *before* observing the exit is not enough on its own -- the process can end
    between the two -- so the exit branch re-reads before it concludes anything.
    Getting this wrong would report ``unknown`` over every successful approval.
    """
    exited = Exited(code=0)
    made = tools(tmp_path, timeout=45.0)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id = str(proposed["proposal_id"])

    def answer_then_die(_: Sequence[str]) -> None:
        made._store().write_report(proposal_id, {"outcome": "declined"})

    made._spawn = Spawner(answer_then_die, handle=exited)  # type: ignore[attr-defined]
    outcome = made.approve(proposal_id, str(proposed["approval_digest"]))

    assert outcome["outcome"] == "declined"


def test_a_console_still_running_is_still_reported_as_still_open(tmp_path: Path) -> None:
    """The direction that must NOT move: a slow reader is not a dead console.

    ``still_open`` is the correct answer while the window is up, and the whole
    of ``docs/slice2-mcp.md``'s timeout table rests on it -- the owner typing
    ``y`` after the call returned still writes the note.
    """
    made = tools(tmp_path, spawner=Spawner(handle=Running()), timeout=1.0)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")

    outcome = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    assert outcome["outcome"] == "still_open"
    assert "not retry" in str(outcome["error"]).lower()


def test_a_console_that_answers_late_still_writes_and_the_report_says_so(
    tmp_path: Path,
) -> None:
    """The other half of the same window, and it is the half that must not be
    a surprise: the owner typing ``y`` after the tool call already returned is a
    real sequence, and the write proceeds. Nothing about that is a retry."""
    made = tools(tmp_path, timeout=1.0)
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a note")
    proposal_id = str(proposed["proposal_id"])
    timed_out = made.approve(proposal_id, str(proposed["approval_digest"]))
    assert timed_out["outcome"] == "still_open"

    # The owner, some seconds later, types y in the window that is still open.
    made._store().write_report(proposal_id, {"outcome": "written", "note_gramps_id": "N0021"})

    assert made.outcome_of(proposal_id)["outcome"] == "written"


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

    clock = Clock()
    answers = mcp_server.Tools(
        environ,
        session="sess0001",
        spawner=Spawner(lambda _: store.write_report(proposal_id, {"outcome": "declined"})),
        clock=clock,
        sleep=clock.sleep,
        platform="win32",
    )
    assert answers.approve(proposal_id, digest)["outcome"] == "declined"


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
    the Gramps boundary -- and the note's identifier back in the transcript.

    ⚠️ **This is criterion 8 read as the owner ruled it**: unit-tested through
    the MCP path with an injected runner up to the process boundary, and
    demo-verified beyond it. It does not prove the sentinel, the lock, the undo
    record or the read-back hold inside Gramps. CI has no Gramps, no ``gi`` and
    no tree, and a criterion reading as *CI-proven* is the false claim
    ``docs/using.md`` exists to avoid.
    """
    copy, environ = equipment(tmp_path)
    runner = Recorder(*written_and_read_back())

    def console(argv: Sequence[str]) -> None:
        cli.main(
            ("approve", argv[-1]),
            environ=environ,
            stdin=io.StringIO("y\n\n"),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            runner=runner,
        )

    made = mcp_server.Tools(environ, session="sess0001", spawner=Spawner(console), platform="win32")
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "Ashenmoor deed, volume two.")
    outcome = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    assert outcome["outcome"] == "written"
    assert outcome["note_gramps_id"] == "N0021"
    assert len(runner.runs) == 2, "the write, and the read-back in a fresh process"
    argv, environment = runner.runs[0]
    assert "-u" not in argv and "--force-unlock" not in argv, "Gramps keeps its lock"
    assert environment[invocation.ENV_APPROVED_DIGEST] == str(proposed["approval_digest"])
    assert Path(copy, apply.SENTINEL_NAME).is_file(), "the token was over a blessed copy"


def test_the_environment_cap_is_inherited_and_relayed_rather_than_hidden(
    tmp_path: Path,
) -> None:
    """#66 is OUT, so the MCP path inherits the Windows environment-block cap.

    It fails closed -- Gramps does not launch and nothing is written -- and the
    tool must return an error an agent can relay, which means the underlying
    message travels rather than a paraphrase of it.
    """
    _, environ = equipment(tmp_path)
    refusal = "OSError: [WinError 206] The filename or extension is too long"

    def console(argv: Sequence[str]) -> None:
        cli.main(
            ("approve", argv[-1]),
            environ=environ,
            stdin=io.StringIO("y\n\n"),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            runner=Recorder(marker(ok=False, error=refusal)),
        )

    made = mcp_server.Tools(environ, session="sess0001", spawner=Spawner(console), platform="win32")
    proposed = made.propose_note(PUBLIC[1], PUBLIC[0], "research", "a very long note")
    outcome = made.approve(str(proposed["proposal_id"]), str(proposed["approval_digest"]))

    assert outcome["outcome"] == "failed"
    assert outcome["error"] == refusal


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
