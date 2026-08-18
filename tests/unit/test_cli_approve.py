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
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from gramps_live_api import cli, config, invocation
from gramps_live_api.core import apply, proposals, schema
from tests.fixtures.trees import blessed
from tests.unit.test_cli import OPERATION, equipped, marker, run


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


class Unavailable(io.StringIO):
    """A console stream that stops working partway through, the way one does.

    ⚠️ **``OSError`` on write is the enumerated failure, not an invented one.**
    A console the server spawned can go away while its process is still running
    -- the window is closed, the pipe behind it breaks -- and ``write`` then
    raises ``OSError``, which is one of the four exceptions the post-commit
    handler already names. So this is the bounded claim being tested where it
    says it holds, not a new claim about arbitrary exceptions.

    Failing on a **substring** is what lets a test say *which* statement broke
    the console, which is the whole of C2-1: the same exception is a different
    defect depending on whether the read-back had already run.
    """

    def __init__(self, failing_on: str) -> None:
        super().__init__()
        self._failing_on = failing_on

    def write(self, s: str) -> int:
        if self._failing_on in s:
            raise OSError(9, "the console stream is no longer available")
        return super().write(s)


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
    out: io.StringIO | None = None,
    err: io.StringIO | None = None,
) -> tuple[int, str, str]:
    out = io.StringIO() if out is None else out
    err = io.StringIO() if err is None else err
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


def test_the_consumed_proposal_is_still_the_reason_no_second_note_can_arrive(
    tmp_path: Path,
) -> None:
    """L6's control, and it is the half that must NOT move.

    The shared post-commit message is being made path-specific rather than
    softened: on ``apply`` there is no proposal and a re-run can write a second
    note, and on this path the strong claim is simply true -- the proposal was
    consumed before Gramps was launched and a retried ``approve`` meets
    ``ProposalNotFound``. A fix that weakened this sentence to one true of both
    callers would have papered over exactly the seam the finding is about.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    wrote, _ = written_and_read_back()
    silent = invocation.Completed(stdout="Gramps says nothing\n", stderr="", returncode=0)

    approve(proposal_id, tmp_path, copy, runner=Recorder(wrote, silent))

    error = str(report_of(directory, proposal_id)["error"])
    assert "proposal is consumed" in error
    assert "second note" in error
    assert "SECOND note on the person" not in error, "that is the other caller's sentence"


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


def test_a_console_that_fails_after_the_read_back_is_not_reported_as_a_refusal(
    tmp_path: Path,
) -> None:
    """C2-1, and it is inside C1-1's repair rather than beside it.

    Both markers said ok and the read-back agreed, so the note is in the tree
    and confirmed. Then the success line cannot print. That statement sat
    *after* the post-commit ``try`` ended, so the ``OSError`` reached
    ``_approve``'s pre-commit handler and filed ``failed`` -- the word
    ``APPROVE_DESCRIPTION`` defines as *it was refused* -- without the handles,
    for the most successful run this program has.

    ⚠️ **A console that broke is not an outcome.** The outcome describes what
    is in the tree, and printing is how the operator is told about it; a report
    that downgraded itself because the telling failed would assert something
    untrue in the other direction.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    out = Unavailable(failing_on="read back from a fresh process")

    code, _, err = approve(
        proposal_id, tmp_path, copy, runner=Recorder(*written_and_read_back()), out=out
    )

    assert code == 0, err
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "written", "a committed and verified note may not read as refused"
    assert report["note_gramps_id"] == "N0021", "the identifiers an undo by hand needs survive"


def test_a_disagreement_that_cannot_be_printed_is_still_reported_as_unverified(
    tmp_path: Path,
) -> None:
    """C2-1's other statement, and the finding named it: *printing a
    disagreement has the same routing.*

    The read-back ran and disagreed, which is ``unverified``. The console then
    fails while saying so, and the exception took the report from *the note is
    in the tree and does not match* to *the write was refused*.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    wrote, _ = written_and_read_back()
    disagrees = marker(ok=True, text_matches=False, attached=True, text="something else")
    err = Unavailable(failing_on="the read-back disagrees")

    code, _, _ = approve(proposal_id, tmp_path, copy, runner=Recorder(wrote, disagrees), err=err)

    assert code != 0
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "unverified", "a committed note may not be reported as refused"
    assert report["note_handle"] == "f00d1e5f00d1e5", "the handles survive the failed printing"
    assert "read-back disagrees" in str(report["error"]), "the report says what actually happened"


def test_a_post_commit_failure_reports_even_when_its_own_message_cannot_print(
    tmp_path: Path,
) -> None:
    """⚠️ **The repair's own diagnostic is a post-commit statement too.**

    C1-1's handler catches the read-back's ``OSError`` and prints an
    explanation. If the console is *why* we are here, that print raises inside
    the ``except`` block, and an exception raised there propagates exactly like
    the original -- so the handler that exists to prevent ``failed`` produces
    it. Widening the ``try`` around the statements the finding named would not
    have touched this, because it is not one of them.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    wrote, _ = written_and_read_back()
    runner = Recorder(wrote, OSError(7, "the environment block is too small"))
    err = Unavailable(failing_on="THE NOTE WAS WRITTEN")

    code, _, _ = approve(proposal_id, tmp_path, copy, runner=runner, err=err)

    assert code != 0
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "unverified", "a committed note may not be reported as refused"
    assert report["note_gramps_id"] == "N0021", "the identifiers an undo by hand needs survive"
    assert apply.UNDO_DIRECTORY in str(report["error"]), "the operator is still told where to look"


def test_a_console_that_fails_before_the_read_back_reports_unverified_not_written(
    tmp_path: Path,
) -> None:
    """The direction that must NOT move, and it is why printing is not uniformly
    best-effort.

    Here the handles line is what cannot print, so the read-back never launches.
    ``unverified`` is then literally true -- the note is in the tree and nothing
    read it back -- and the handler's own words say exactly that. Swallowing
    this one to keep the outcome ``written`` would claim a read-back that never
    happened, which is C2-1 pointing the other way.
    """
    copy, directory, proposal_id = prepared(tmp_path)
    runner = Recorder(*written_and_read_back())
    out = Unavailable(failing_on="note handle")

    code, _, _ = approve(proposal_id, tmp_path, copy, runner=runner, out=out)

    assert code != 0
    assert len(runner.runs) == 1, "the read-back did not run, which is what unverified means"
    report = report_of(directory, proposal_id)
    assert report["outcome"] == "unverified"
    assert report["note_gramps_id"] == "N0021"


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
    """It is reported, and it does NOT fail the doctor. See the test below."""
    copy = blessed(tmp_path / "tree")

    checks = cli.inspect(
        None, equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: ""})
    )
    line = next(check for check in checks if check.label == "export")

    assert line.ok
    assert "export_path" in line.detail, "the remedy is named, not just the condition"
    assert "list_people" in line.detail, "what is unavailable is named, not just the setting"


def test_a_copy_path_only_install_is_ready_the_way_docs_using_shows_it(tmp_path: Path) -> None:
    """L5, and it is a REGRESSION AGAINST A DEMO THAT PASSED, not merely a defect.

    ``docs/using.md``'s own sample report ends ``ready`` over a setup whose
    config file holds one key, ``copy_path`` -- which is the setup the owner
    performed on demo day. Slice 1's three commands need no export; only slice
    2's tools read one. So *not configured* is reported and is not a failure,
    and the sentence that says which tools cannot run is what carries the fact.

    ⚠️ **A CONFIGURED export that is stale or unreadable still fails**, and the
    two tests below are the pair. Absence is a feature nobody has set up;
    staleness is a privacy oracle that is lying, which is ``docs/slice2-mcp.md``'s
    recorded ruling and does not move.
    """
    copy = blessed(tmp_path / "tree")
    environ = equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: ""})

    code, out, _ = run("check", environ=environ)

    assert code == 0, f"a copy-path-only install is what docs/using.md shows ending ready; {out}"
    assert out.strip().endswith("ready")
    assert "not ready" not in out


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


def test_an_unreadable_copy_fails_the_export_check_rather_than_passing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1-2, and ``_export_check``'s own docstring is what it breaks.

    An ACL can permit access to known files while denying the directory listing,
    and then ``os.scandir`` -- or an entry's ``stat`` -- raises. Freshness is
    then unknown, and the docstring says which way unknown has to be wrong:
    *toward re-export, never toward the flag you are reading is current.*
    """
    copy = blessed(tmp_path / "tree")
    export = tmp_path / "tree.gramps"
    export.write_text("<database/>", encoding="utf-8")
    listing = os.scandir
    denied = os.path.realpath(copy.tree_dir)

    def refuse(path: object = ".") -> object:
        if os.path.realpath(str(path)) == denied:
            raise PermissionError(13, "the directory may not be listed")
        return listing(str(path))

    monkeypatch.setattr(os, "scandir", refuse)

    checks = cli.inspect(
        None, equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: str(export)})
    )
    line = next(check for check in checks if check.label == "export")

    assert not line.ok, "freshness that could not be read may not report as current"
    assert "could not be established" in line.detail
    assert "older than the copy" not in line.detail, "unreadable and stale are not one state"


def a_tree_at(directory: Path) -> Path:
    """A directory that looks enough like a tree for ``check <tree>`` to report."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / apply.NAME_FILE).write_text("Another Invented Tree\n", encoding="utf-8")
    return directory


def test_the_export_is_compared_against_the_configured_copy_not_the_named_tree(
    tmp_path: Path,
) -> None:
    """L4, direction one: a FALSE staleness failure.

    ``docs/using.md`` documents ``check <live tree>`` and tells the owner to run
    it -- it is how he watches the blessing refusal happen. That argument became
    ``resolved``, and ``_export_check``'s parameter is named ``copy`` and
    received it. So the export was compared against whatever tree was named on
    the command line, and pointing the doctor at a tree touched more recently
    than the export reported the export stale when it speaks for the copy
    perfectly well.
    """
    copy = blessed(tmp_path / "copy")
    export = tmp_path / "tree.gramps"
    export.write_text("<database/>", encoding="utf-8")
    aged(export, seconds=60)
    aged(Path(copy.tree_dir) / apply.NAME_FILE, seconds=120)
    aged(Path(copy.tree_dir) / apply.SENTINEL_NAME, seconds=120)
    named = a_tree_at(tmp_path / "somewhere-else")  # touched just now, after the export

    checks = cli.inspect(
        str(named),
        equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: str(export)}),
    )
    line = next(check for check in checks if check.label == "export")

    assert line.ok, f"the export is newer than the COPY, which is what it speaks for; {line.detail}"


def test_a_named_tree_older_than_the_export_cannot_make_a_stale_export_look_current(
    tmp_path: Path,
) -> None:
    """L4, direction two, and it is **the fail-open the check exists to forbid**.

    The same parameter mix-up read the other way: point the doctor at an old
    scratch tree and the comparison it makes is *export versus that*, which
    passes -- while the configured copy has moved on since the export was taken.
    ``_export_check``'s own docstring says which way unknown or wrong has to
    err: *toward re-export, never toward the flag you are reading is current.*
    A person marked private since the export would still be listed, and the one
    place that says so would be printing ``ok``.
    """
    named = a_tree_at(tmp_path / "old-scratch")
    export = tmp_path / "tree.gramps"
    export.write_text("<database/>", encoding="utf-8")
    aged(export, seconds=60)
    aged(named / apply.NAME_FILE, seconds=120)
    copy = blessed(tmp_path / "copy")  # written last, so the export is stale against it

    checks = cli.inspect(
        str(named),
        equipped(tmp_path, **{config.ENV_COPY: copy.tree_dir, config.ENV_EXPORT: str(export)}),
    )
    line = next(check for check in checks if check.label == "export")

    assert not line.ok, "a stale export reported current is the fail-open, not a nuisance"
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
