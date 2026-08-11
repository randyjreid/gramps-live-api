"""Decision 2 -- no entry point may put a sensitive value on stdout or stderr.

Three consecutive rounds leaked, and every fix patched a *call site*. There is
always another call site: round 3's were a scan target printed in the summary
regardless of ``--redact``, and a repository root embedded in an exception.

So this is a property over output, not a checklist of places. The scan target
lives inside a directory whose **name contains a canary**, which makes the path
sensitive by construction -- the test cannot pass vacuously, because there is
no arrangement in which the canary is absent from what the code handles.

Error and metadata paths are driven too. The exception leak would have survived
any number of happy-path tests.
"""

from __future__ import annotations

import copy
import pickle
from collections.abc import Callable
from pathlib import Path

import pytest

from gramps_live_api.core import pii_guard
from gramps_live_api.core.pii_guard import Secret, main
from tests.fixtures.repositories import commit_all, init_repository
from tests.fixtures.synthetic import posix_path

CANARY = "quorvane-ashenmoor"


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """A scan target whose own path carries the canary."""
    root = tmp_path / f"{CANARY}-workspace"
    root.mkdir()
    return root


EXPLICIT_REVEAL = "--show-matches"


def invocations(root: Path, *, including_explicit_reveal: bool) -> list[list[str]]:
    """Every way in, including the ones no happy path reaches.

    ``--show-matches`` is the one deliberate reveal, so it is excluded when the
    property under test is about *values*. Excluding it is not a softening: it
    is the difference between "never discloses" and "never discloses by
    accident", and the second is the property this design actually claims. That
    the flag does reveal is asserted separately, in the reporting tests.
    """
    ways = [
        [str(root)],
        ["--redact", str(root)],
        ["--range", "does-not-exist..HEAD", str(root)],
        ["--range", "HEAD..HEAD", str(root)],
        ["--range", str(root)],
        ["--range=", str(root)],
        [str(root / "no-such-file.md")],
    ]
    if including_explicit_reveal:
        ways.append([EXPLICIT_REVEAL, str(root)])
    return ways


def drive(
    root: Path, capsys: pytest.CaptureFixture[str], *, including_explicit_reveal: bool = True
) -> str:
    captured = []
    for argv in invocations(root, including_explicit_reveal=including_explicit_reveal):
        try:
            main(argv)
        except SystemExit:  # pragma: no cover - defensive
            pass
        except Exception as error:  # noqa: BLE001 - an escaping message is a leak too
            captured.append(f"{type(error).__name__}: {error}")
        streams = capsys.readouterr()
        captured.append(streams.out)
        captured.append(streams.err)
    return "\n".join(captured)


def test_no_entry_point_prints_the_scan_target(
    target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (target / "notes.md").write_text("nothing to see\n", encoding="utf-8")

    output = drive(target, capsys)

    assert CANARY not in output, (
        "the scan target is an absolute path on somebody's machine, and a "
        "build log is public. Some entry point printed it"
    )


def test_no_entry_point_prints_a_matched_value(
    target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted = posix_path("home", CANARY, "trees")
    (target / "notes.md").write_text(f"stored in {planted}\n", encoding="utf-8")

    output = drive(target, capsys, including_explicit_reveal=False)

    assert planted not in output, "a matched path reached the output"
    assert CANARY not in output, "the canary reached the output by any route"


def test_a_git_failure_does_not_print_the_repository_root(
    target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    init_repository(target)
    (target / "notes.md").write_text("nothing\n", encoding="utf-8")
    commit_all(target, "base")

    main(["--range", "no-such-revision..HEAD", str(target)])
    output = capsys.readouterr().out + capsys.readouterr().err

    assert CANARY not in output, (
        "round 3's second leak was an exception message; the root was "
        "interpolated into it and printed"
    )


# ---------------------------------------------------------------------------
# The wrapper itself: leaking must be impossible, not merely absent.
# ---------------------------------------------------------------------------


def test_a_secret_cannot_be_interpolated() -> None:
    secret = Secret("private-user")  # pii-guard: not-a-secret -- an invented test literal

    assert "private-user" not in str(secret)
    assert "private-user" not in repr(secret)
    assert "private-user" not in f"{secret}"
    assert "private-user" not in f"{secret!r}"
    assert "private-user" not in f"{secret!s}"
    assert "private-user" not in "{}".format(secret)  # noqa: UP032 - exercising __format__
    assert "private-user" not in f"{[secret]}"
    assert "private-user" not in str({"k": secret})
    assert "private-user" not in f"{secret:>40}"


def test_no_route_off_a_secret_yields_cleartext() -> None:
    """Enumerate the routes; do not list them.

    The previous version listed the ones somebody had thought of, which is why
    it stayed green while the value sat on a public attribute and
    ``__getstate__`` handed back a printable dict. A walk fails when a new
    route appears, without anyone remembering to extend it.
    """
    cleartext = "private-user"
    secret = Secret(cleartext)

    seen: list[tuple[str, object]] = [
        ("str", str(secret)),
        ("repr", repr(secret)),
        ("format", f"{secret}"),
        ("vars", getattr(secret, "__dict__", None)),
        ("copy", _attempt(lambda: copy.copy(secret))),
        ("deepcopy", _attempt(lambda: copy.deepcopy(secret))),
        ("pickle", _attempt(lambda: pickle.dumps(secret))),
    ]

    for name in dir(secret):
        if name == "reveal":
            continue  # the one audited route, asserted separately
        attribute = getattr(secret, name, None)
        seen.append((name, attribute))
        if callable(attribute):
            seen.append((f"{name}()", _attempt(attribute)))

    leaks = [name for name, value in seen if cleartext in _render(value)]

    assert leaks == [], f"these routes yield the cleartext without reveal(): {leaks}"


def test_the_side_table_is_module_private_and_not_reachable_from_a_secret() -> None:
    """The achievable half of "one audited route", and the honest boundary.

    The values have to live somewhere in the process, and *any* store can be
    dumped by code that goes looking: module globals are reachable from any
    object through its class, so no storage strategy -- attribute, side table
    or closure -- can make cleartext unreachable to deliberate introspection.

    What the wrapper does guarantee is that no ORDINARY use of the object --
    formatting it, printing it, serialising it, reading its attributes --
    yields the value. That is what the walk above enforces. Here we pin the
    two structural facts that keep it true: the store is module-private, and
    it is not an attribute of the wrapper.
    """
    secret = Secret("private-user")  # pii-guard: not-a-secret -- an invented test literal

    assert not hasattr(secret, "__dict__"), "a per-instance dict would be a route"
    assert [slot for slot in Secret.__slots__ if slot != "__weakref__"] == [], (
        "the value must not live in a slot; a slot is a readable attribute"
    )
    stores = [name for name in vars(pii_guard) if name.endswith("_SECRET_VALUES")]
    assert stores == ["_SECRET_VALUES"], f"one module-private store, named as such; found {stores}"


def _attempt(route: Callable[[], object]) -> object:
    """The result of a route, or nothing when it refuses. A refusal leaks nothing."""
    try:
        return route()
    except Exception as error:  # noqa: BLE001 - the message is inspected too
        return error


def _render(value: object) -> str:
    """Everything a route's result could be turned into, as text."""
    try:
        return f"{value!r} {value!s} {getattr(value, '__dict__', '')}"
    except Exception:  # noqa: BLE001
        return ""


def test_a_secret_reveals_only_when_asked() -> None:
    assert Secret("private-user").reveal() == "private-user"


def test_a_secret_reports_its_length_without_its_content() -> None:
    assert "12" in str(Secret("private-user")), "the length is useful and is not the value"


def test_reveal_is_called_in_exactly_one_place() -> None:
    """The wrapper's whole value is that leaking is impossible by construction.

    A second call site quietly restores the old regime, where safety depended
    on remembering. If a second one is ever genuinely needed, that is a design
    decision to be taken deliberately, not a line to be added.
    """
    source = Path(__import__("gramps_live_api.core.pii_guard", fromlist=["_"]).__file__)
    text = source.read_text(encoding="utf-8")
    call_sites = [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if ".reveal()" in line and "def reveal" not in line
    ]

    assert len(call_sites) == 1, f"expected exactly one reveal() call site, found {call_sites}"


def test_a_source_is_rendered_in_full_from_exactly_one_place() -> None:
    """The other half of the same guarantee, and it was true by inspection only.

    Five rounds of redaction fixes held only once the source became a type
    whose every text route is redacted, leaving one deliberate way to produce
    the cleartext. That way must stay single: "true by inspection" is precisely
    what the four fixes that did not hold were.
    """
    source = Path(__import__("gramps_live_api.core.pii_guard", fromlist=["_"]).__file__)
    text = source.read_text(encoding="utf-8")
    call_sites = [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if ".rendered(" in line and "def rendered" not in line
    ]

    assert len(call_sites) == 1, (
        f"the full path must be produced in one place only, found {call_sites}"
    )
