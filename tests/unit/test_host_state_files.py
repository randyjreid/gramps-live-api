"""The three files the host leaves on disk, and what each one is for.

``token``  what a client must present. Written with the tightest protection the
           platform offers, and the protection actually achieved is REPORTED
           rather than assumed.
``port``   where to reach it. Written only after a successful bind, and removed
           before every start -- so its presence is a claim, not a leftover.
``host.log``
           R8's accepted risk 2. ``load_on_reg`` swallows exceptions and the AIO
           has no console, so a failed start is otherwise invisible; this file is
           the only place it can be seen, and it is what lets a client tell
           "host unreachable" from "host errored".

Both platform layouts are exercised on whichever platform is running, by passing
``platform`` in -- ``config.py``'s rule, for its reason: a branch only its own
operating system can reach is a branch CI proves nothing about. That is also
what lets the Windows ACL decision be tested on a runner that has no ``icacls``.
"""

from __future__ import annotations

from pathlib import Path

from gramps_live_api import config
from gramps_live_api.host import log, paths, tokens


def test_the_state_directory_is_the_one_the_configuration_already_uses(tmp_path: Path) -> None:
    """One directory, resolved one way. A second answer here is a second directory."""
    where = paths.state_directory({"APPDATA": str(tmp_path)}, platform="win32")

    assert where == tmp_path / config.DIRECTORY_NAME
    assert where == config.user_config_path({"APPDATA": str(tmp_path)}, platform="win32").parent


def test_the_other_layout_follows_the_same_rule(tmp_path: Path) -> None:
    where = paths.state_directory({"XDG_CONFIG_HOME": str(tmp_path)}, platform="linux")

    assert where == tmp_path / config.DIRECTORY_NAME


def test_the_port_is_written_beside_the_token(tmp_path: Path) -> None:
    """R8's shape: a client reads both from one place, or neither."""
    directory = paths.state_directory({"APPDATA": str(tmp_path)}, platform="win32")

    assert paths.token_path(directory).parent == paths.port_path(directory).parent == directory
    assert paths.log_path(directory).parent == directory


def test_writing_a_token_leaves_exactly_the_token_in_the_file(tmp_path: Path) -> None:
    path = tmp_path / "token"
    minted = tokens.new_token()

    tokens.write_token(path, minted, platform="linux", environ={}, run=refuse_to_run)

    assert path.read_text(encoding="utf-8") == minted


def refuse_to_run(argv: list[str]) -> tokens.CommandResult:
    raise AssertionError(f"nothing should have been run here, but this was: {argv[0]}")


def test_off_windows_the_mode_bits_are_the_protection(tmp_path: Path) -> None:
    """No subprocess is spawned where the filesystem already answers the question."""
    path = tmp_path / "token"

    protection = tokens.write_token(
        path, tokens.new_token(), platform="linux", environ={}, run=refuse_to_run
    )

    assert protection.kind == tokens.OWNER_ONLY_MODE


def test_on_windows_the_access_list_is_rewritten_for_the_current_account(
    tmp_path: Path,
) -> None:
    """Mode bits do not carry an ACL on Windows, so the ACL is set explicitly.

    ⚠️ **The command is asserted, not just its success.** ``/inheritance:r``
    without ``/grant:r`` leaves a file nobody can read including the owner, and
    ``/grant:r`` without ``/inheritance:r`` adds the owner to an inherited list
    that already grants others -- which is a no-op dressed as a protection. Both
    have to be there.
    """
    path = tmp_path / "token"
    ran: list[list[str]] = []

    def record(argv: list[str]) -> tokens.CommandResult:
        ran.append(argv)
        return tokens.CommandResult(returncode=0, detail="")

    protection = tokens.write_token(
        path,
        tokens.new_token(),
        platform="win32",
        environ={"USERNAME": "an-account", "USERDOMAIN": "a-machine"},
        run=record,
    )

    assert protection.kind == tokens.OWNER_ONLY_ACL
    assert len(ran) == 1
    argv = ran[0]
    assert argv[0] == "icacls"
    assert str(path) in argv
    assert "/inheritance:r" in argv
    assert any(part.startswith("/grant:r") or part == "/grant:r" for part in argv)


def test_the_account_name_never_reaches_the_reported_protection(tmp_path: Path) -> None:
    """A Windows account name is personal data and the log is not the place for it.

    The protection is reported into ``host.log``, which is a file the owner may
    well paste into an issue. What it says is which mechanism succeeded; who the
    owner is stays out of it.
    """
    protection = tokens.write_token(
        tmp_path / "token",
        tokens.new_token(),
        platform="win32",
        environ={"USERNAME": "an-account", "USERDOMAIN": "a-machine"},
        run=lambda argv: tokens.CommandResult(returncode=0, detail=""),
    )

    assert "an-account" not in protection.detail
    assert "a-machine" not in protection.detail


def test_a_failed_access_list_is_reported_rather_than_hidden(tmp_path: Path) -> None:
    """Fail-open, said out loud.

    The host still starts: ``%APPDATA%`` is already owner-and-administrators on
    Windows, and R8 accepts that any process running as the owner can read the
    token anyway. What is not acceptable is a host that claims a protection it
    did not get, so the outcome goes in the log either way.
    """
    protection = tokens.write_token(
        tmp_path / "token",
        tokens.new_token(),
        platform="win32",
        environ={"USERNAME": "an-account"},
        run=lambda argv: tokens.CommandResult(returncode=1, detail="icacls said no"),
    )

    assert protection.kind == tokens.INHERITED_ONLY
    assert "icacls said no" in protection.detail


def test_windows_without_an_account_name_does_not_guess_one(tmp_path: Path) -> None:
    """No name, no command. A grant to a guessed principal is worse than none."""
    protection = tokens.write_token(
        tmp_path / "token",
        tokens.new_token(),
        platform="win32",
        environ={},
        run=refuse_to_run,
    )

    assert protection.kind == tokens.INHERITED_ONLY


def test_the_log_line_carries_a_level_a_time_and_the_message(tmp_path: Path) -> None:
    path = tmp_path / "host.log"

    log.record(path, log.INFO, "listening")

    line = path.read_text(encoding="utf-8").splitlines()[-1]
    assert line.endswith(" listening")
    assert f" {log.INFO} " in line
    assert line.split(" ")[0], "the line begins with no timestamp, so nothing orders two starts"


def test_the_log_appends_rather_than_replacing(tmp_path: Path) -> None:
    """Yesterday's failed start is the thing the owner needs when today's works."""
    path = tmp_path / "host.log"

    log.record(path, log.INFO, "the first start")
    log.record(path, log.ERROR, "the second start")

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_the_log_creates_its_directory(tmp_path: Path) -> None:
    """First run on a machine that has never had this configured is the ordinary case."""
    path = tmp_path / "not-there-yet" / "host.log"

    log.record(path, log.INFO, "listening")

    assert path.is_file()


def test_a_log_that_cannot_be_written_does_not_stop_the_host(tmp_path: Path) -> None:
    """The log exists to make a failed start visible; it must not cause one.

    A directory where the file should be is the cheapest way to make writing
    fail on every platform. The call reports that it failed and returns.
    """
    path = tmp_path / "host.log"
    path.mkdir()

    assert log.record(path, log.INFO, "listening") is False
