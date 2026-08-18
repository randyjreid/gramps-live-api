"""``approve`` -- the console the owner types ``y`` at, and the doctor's export line.

⚠️ **This console is the approval, and everything else in slice 2 is transport.**
The agent owns the transcript; it does not own this window. What is printed here
is rendered from the operation stored on disk by the same ``full_display`` the
digest covers -- never from anything the agent sent -- so what the owner read and
what the tree receives are the same object.

Covered here up to the process boundary and no further, exactly as ``test_cli``
covers ``apply``: the runner is injected. Whether a note reaches a tree is
observable only where Gramps is, and the demo is what observes it.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from gramps_live_api import cli, config, invocation
from gramps_live_api.core import apply, proposals, schema
from tests.fixtures.trees import blessed
from tests.unit.test_cli import OPERATION, equipped, marker


class Recorder:
    """A runner that starts no process, remembers, and can look around first.

    A reply may be an **exception**, which this raises instead of returning.
    That is how a run that never launches is expressed: ``subprocess`` raises
    rather than handing back a completed process, and which of the two runs it
    happens on is exactly what C1-1 is about.
    """

    def __init__(self, *replies: invocation.Completed | Exception, watching: object = None) -> None:
        self._replies = list(replies)
        self._watching = watching
        self.runs: list[tuple[Sequence[str], Mapping[str, str]]] = []
        self.seen: list[list[str]] = []

    def __call__(self, argv: Sequence[str], environ: Mapping[str, str]) -> invocation.Completed:
        if self._watching is not None:
            self.seen.append(sorted(path.name for path in Path(str(self._watching)).iterdir()))
        self.runs.append((argv, environ))
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def written_and_read_back() -> tuple[invocation.Completed, invocation.Completed]:
    return (
        marker(
            ok=True,
            note_handle="f00d1e5f00d1e5",
            note_gramps_id="N0021",
            person_handle="a1b2c3d4e5f607",
            record="a-record",
            record_error=None,
        ),
        marker(ok=True, text_matches=True, attached=True, text=OPERATION.text),
    )


def prepared(tmp_path: Path, operation: schema.Operation = OPERATION) -> tuple[str, str, str]:
    """A blessed copy holding one claimed proposal. Returns copy, store dir, id."""
    copy = blessed(tmp_path / "tree")
    directory = proposals.store_directory(copy.tree_dir)
    store = proposals.Store(directory, session="sess0001")
    proposal = store.mint(operation)
    store.claim(proposal.id, proposal.approval_digest)
    return copy.tree_dir, directory, proposal.id


def approve(
    proposal_id: str,
    tmp_path: Path,
    copy: str,
    *,
    answer: str = "y",
    runner: Recorder | None = None,
    extra: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    environ = equipped(tmp_path, **{config.ENV_COPY: copy, **(extra or {})})
    code = cli.main(
        ("approve", proposal_id),
        environ=environ,
        # Two lines: the answer, and the Enter that closes the window.
        stdin=io.StringIO(f"{answer}\n\n"),
        stdout=out,
        stderr=err,
        runner=runner,
    )
    return code, out.getvalue(), err.getvalue()


def report_of(directory: str, proposal_id: str) -> dict[str, object]:
    return proposals.Store(directory, session="anything").read_report(proposal_id) or {}


# ---------------------------------------------------------------------------
# The console is the approval
# ---------------------------------------------------------------------------


def test_the_whole_note_is_shown_before_the_prompt(tmp_path: Path) -> None:
    copy, _, proposal_id = prepared(tmp_path)
    runner = Recorder(*written_and_read_back())

    code, out, err = approve(proposal_id, tmp_path, copy, runner=runner)

    assert code == 0, err
    assert schema.full_display(OPERATION) in out, "nothing is written that was not shown"
    assert f"write this into {copy}? [y/N]" in out


def test_what_is_shown_is_rendered_from_the_stored_operation(tmp_path: Path) -> None:
    """⚠️ **Not from the stored sentence**, and the difference is the design.

    ``ProposalCorrupt`` binds the stored *operation* to the digest. The stored
    sentence is a convenience beside it and nothing binds it, so a console that
    printed it would show whatever an editor last put there while writing what
    the operation says.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    path = Path(directory) / f"{proposal_id}.pending.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["full_display"] = "add a research note to person I0001: “something else entirely”"
    path.write_text(json.dumps(record), encoding="utf-8")

    _, out, _ = approve(proposal_id, tmp_path, copy, answer="n")

    assert "something else entirely" not in out
    assert schema.full_display(OPERATION) in out


def test_a_declined_proposal_writes_nothing_at_all(tmp_path: Path) -> None:
    """Criterion 7: the console is the only writer, and it did not write."""
    copy, directory, proposal_id = prepared(tmp_path)
    runner = Recorder()

    code, out, _ = approve(proposal_id, tmp_path, copy, answer="n", runner=runner)

    assert code != 0
    assert runner.runs == [], "a declined proposal started a Gramps process"
    assert "nothing was written" in out
    assert report_of(directory, proposal_id)["outcome"] == "declined"


def test_the_proposal_is_consumed_before_gramps_is_launched(tmp_path: Path) -> None:
    """#69, and the ordering is the whole of the fix.

    An agent retries on an ambiguous result without being asked. By the time
    anything can crash and be retried, the proposal is already gone -- so the
    retry meets ``ProposalNotFound`` instead of writing a second note.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    runner = Recorder(*written_and_read_back(), watching=directory)

    approve(proposal_id, tmp_path, copy, runner=runner)

    assert runner.seen, "the runner was never called, so the ordering was not observed"
    at_launch = runner.seen[0]
    assert f"{proposal_id}.json" not in at_launch
    assert f"{proposal_id}.pending.json" not in at_launch
    assert f"{proposal_id}.approved.json" in at_launch


def test_a_second_approve_of_the_same_proposal_is_refused(tmp_path: Path) -> None:
    copy, directory, proposal_id = prepared(tmp_path)
    approve(proposal_id, tmp_path, copy, runner=Recorder(*written_and_read_back()))

    code, _, err = approve(proposal_id, tmp_path, copy, runner=Recorder())

    assert code != 0
    assert proposal_id in err


def test_the_lock_is_never_broken(tmp_path: Path) -> None:
    """Criterion 8's rail, through the new path: Gramps refuses a locked tree
    and we never hand that back with ``-u`` or ``--force-unlock``."""
    copy, _, proposal_id = prepared(tmp_path)
    runner = Recorder(*written_and_read_back())

    approve(proposal_id, tmp_path, copy, runner=runner)

    for argv, _ in runner.runs:
        assert "-u" not in argv and "--force-unlock" not in argv


def test_the_approved_digest_travels_with_every_run(tmp_path: Path) -> None:
    """The binding slice 1 built, unchanged by an agent standing in front of it."""
    copy, _, proposal_id = prepared(tmp_path)
    runner = Recorder(*written_and_read_back())

    approve(proposal_id, tmp_path, copy, runner=runner)

    assert len(runner.runs) == 2, "an apply run and a read-back in a fresh process"
    for _, environ in runner.runs:
        assert environ[invocation.ENV_APPROVED_DIGEST] == apply.approval_digest(OPERATION)


# ---------------------------------------------------------------------------
# What the server is told afterwards
# ---------------------------------------------------------------------------


def test_a_completed_write_reports_the_note_the_agent_will_relay(tmp_path: Path) -> None:
    copy, directory, proposal_id = prepared(tmp_path)

    code, out, err = approve(proposal_id, tmp_path, copy, runner=Recorder(*written_and_read_back()))

    assert code == 0, err
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "written"
    assert report["note_gramps_id"] == "N0021"
    assert "read back from a fresh process" in out


def test_an_ambiguous_run_is_reported_rather_than_left_to_be_retried(tmp_path: Path) -> None:
    """#69's other half: the vocabulary the result marker lacks.

    A run that printed no marker may or may not have committed. The proposal is
    already consumed, so a retry cannot write a second note -- and the agent has
    to be told that in words rather than handed a failure it will read as
    *try again*.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    silent = invocation.Completed(stdout="Gramps says nothing\n", stderr="", returncode=0)

    code, _, err = approve(proposal_id, tmp_path, copy, runner=Recorder(silent))

    assert code != 0
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "unknown"
    assert apply.UNDO_DIRECTORY in str(report["error"])
    assert "will not be retried" in str(report["error"])
    assert invocation.MARKER in err, "the underlying message is relayed, not paraphrased"


def test_a_refusal_from_inside_gramps_reaches_the_report_verbatim(tmp_path: Path) -> None:
    """#62 is not fixed here and it is now worse, because the message reaches an
    agent that will paraphrase it. So it is relayed word for word."""
    copy, directory, proposal_id = prepared(tmp_path)
    refusal = "UnblessedTree: this tree has not been blessed for writing"

    code, _, err = approve(
        proposal_id, tmp_path, copy, runner=Recorder(marker(ok=False, error=refusal))
    )

    assert code != 0
    assert refusal in err
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "failed"
    assert report["error"] == refusal


def test_a_read_back_that_cannot_launch_is_not_reported_as_a_refusal(tmp_path: Path) -> None:
    """C1-1, and the exact input that makes an agent propose again.

    The apply run committed; the read-back could not start. On Windows that is
    reachable because ``_one_run`` adds ``ENV_HANDLES`` to the verification
    environment, so it can cross the block limit the apply run sat under -- but
    the cause does not matter and the cap is #66, filed and out of scope. What
    matters is that ``failed`` is what ``APPROVE_DESCRIPTION`` calls a refusal,
    and a committed note reported as refused is the duplicate-write path slice 2
    claims to have closed.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    wrote, _ = written_and_read_back()
    runner = Recorder(wrote, OSError(7, "the environment block is too small"))

    code, _, err = approve(proposal_id, tmp_path, copy, runner=runner)

    assert code != 0
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "unverified", "a committed note may not be reported as refused"
    assert report["note_gramps_id"] == "N0021", "the identifiers an undo by hand needs survive"
    assert apply.UNDO_DIRECTORY in str(report["error"]), "the operator is told where to look"
    assert "environment block" in err, "the underlying failure is relayed, not paraphrased"


def test_a_read_back_that_prints_no_marker_still_files_a_report(tmp_path: Path) -> None:
    """The same boundary, reached by the other post-commit failure.

    ``NoResultMarker`` from the read-back is not in the set ``_approve``
    catches, so it escaped past the report entirely: the note was committed, the
    console printed a traceback-free message and exited, and **no report was
    filed at all** -- leaving the server to wait out its whole timeout and tell
    the agent *still_open* about a run that had ended.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    wrote, _ = written_and_read_back()
    silent = invocation.Completed(stdout="Gramps says nothing\n", stderr="", returncode=0)

    code, _, _ = approve(proposal_id, tmp_path, copy, runner=Recorder(wrote, silent))

    assert code != 0
    report = report_of(directory, proposal_id)
    assert report.get("outcome") == "unverified", "a post-commit failure files a report"
    assert report["note_handle"] == "f00d1e5f00d1e5"


def test_a_write_that_never_launched_is_still_reported_as_a_refusal(tmp_path: Path) -> None:
    """The other side of C1-1's distinction, and it must not move.

    Nothing committed here, so ``failed`` is the true word and the agent may act
    on it. A fix that reported every launch failure as *committed but
    unverified* would have widened the claim it was asked to narrow.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    runner = Recorder(OSError(7, "the environment block is too small"))

    code, _, _ = approve(proposal_id, tmp_path, copy, runner=runner)

    assert code != 0
    assert report_of(directory, proposal_id)["outcome"] == "failed"


def test_a_read_back_that_disagrees_is_not_reported_as_written(tmp_path: Path) -> None:
    copy, directory, proposal_id = prepared(tmp_path)
    wrote, _ = written_and_read_back()
    disagrees = marker(ok=True, text_matches=False, attached=True, text="something else")

    code, _, _ = approve(proposal_id, tmp_path, copy, runner=Recorder(wrote, disagrees))

    assert code != 0
    assert report_of(directory, proposal_id)["outcome"] == "unverified"


def test_a_proposal_nobody_claimed_is_refused_by_name(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree").tree_dir

    code, _, err = approve("0" * 16, tmp_path, copy, runner=Recorder())

    assert code != 0
    assert err.strip()


# ---------------------------------------------------------------------------
# The doctor's export line -- and the staleness that is a PRIVACY question
# ---------------------------------------------------------------------------


def aged(path: Path, *, seconds: float) -> None:
    """Move ``path``'s timestamp back, so an ordering is asserted not raced."""
    import os

    when = path.stat().st_mtime - seconds
    os.utime(path, (when, when))


def test_check_reports_the_export(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")
    export = tmp_path / "tree.gramps"
    export.write_text("<database/>", encoding="utf-8")

    checks = cli.inspect(
        None, equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: str(export)})
    )
    line = next(check for check in checks if check.label == "export")

    assert line.ok, line.detail
    assert str(export) in line.detail


def test_check_says_when_no_export_is_configured(tmp_path: Path) -> None:
    copy = blessed(tmp_path / "tree")

    checks = cli.inspect(
        None, equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: ""})
    )
    line = next(check for check in checks if check.label == "export")

    assert not line.ok
    assert "export_path" in line.detail, "the remedy is named, not just the condition"


def test_check_reports_an_export_older_than_the_copy_as_stale(tmp_path: Path) -> None:
    """⚠️ **A privacy question, not an ergonomic one.**

    A stale handle fails CLOSED at the write -- ``TargetNotFound`` or
    ``TargetDisagrees``. A stale ``priv`` flag fails OPEN: somebody marked
    private after the export was taken is still listed and still targetable.
    Of the two directions this one has to be visible, so it fails the doctor
    rather than warning inside a passing report.
    """
    copy = blessed(tmp_path / "tree")
    export = tmp_path / "tree.gramps"
    export.write_text("<database/>", encoding="utf-8")
    aged(export, seconds=60)

    checks = cli.inspect(
        None, equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: str(export)})
    )
    line = next(check for check in checks if check.label == "export")

    assert not line.ok
    assert "export" in line.detail.lower()
    assert "again" in line.detail, "the remedy is named"


def test_our_own_directories_inside_the_copy_do_not_make_the_export_stale(
    tmp_path: Path,
) -> None:
    """The store and the undo records live inside the copy, and they are ours.

    A comparison that counted them would report stale the moment a proposal was
    minted -- a check that fires on its own side effects is a check people learn
    to ignore.
    """
    copy = blessed(tmp_path / "tree")
    export = tmp_path / "tree.gramps"
    export.write_text("<database/>", encoding="utf-8")
    store = proposals.Store(proposals.store_directory(copy.tree_dir), session="sess0001")
    store.mint(OPERATION)

    checks = cli.inspect(
        None, equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: str(export)})
    )
    line = next(check for check in checks if check.label == "export")

    assert line.ok, line.detail
