"""⛔ The MCP seam: the layer nothing was testing.

The README says so publicly — *"No test invokes ``propose_document``,
``approve_document``, or any of the live-read tools at the MCP layer — their logic
is exercised one layer down, against fakes."* This file closes that.

⭐ **No tree, no Gramps, no ``gi``.** ``Tools`` already takes its environment,
session, spawner and platform by injection, and reaches the host over loopback
HTTP. So the host is replaced by a recorder and the whole surface is exercised
without a client, a transport or an event loop — the same way the note flow is
already tested one file over.

⚠️ **What this covers is the WIRING, not the tree.** That a route is called with
the right parameters says nothing about what Gramps would answer. The parts that
can only be proved against a real tree are named in the README and stay named.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

# ⛔ ``find_spec``, not ``pytest.importorskip`` — the same guard the other MCP
# test modules use. It asks one question, *is the optional extra installed?*, and
# skips only on that answer; every other import error still fails collection.
if importlib.util.find_spec("mcp") is None:  # pragma: no cover - installed in dev
    pytest.skip(
        "the MCP server is an optional extra and it is not installed, so there is "
        "nothing to cover here -- gramps_live_api_mcp.server cannot be imported at "
        "all. CI's mcp leg installs '.[mcp]' and asserts these tests actually ran.",
        allow_module_level=True,
    )

from gramps_live_api.host import paths  # noqa: E402
from gramps_live_api_mcp import server as mcp_server  # noqa: E402
from tests.unit.test_cli import equipped  # noqa: E402

PORT = "55555"
TOKEN = "a-token-the-host-minted"


class Answer:
    """What ``urlopen`` returns: a body, and a context manager around it."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Answer:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class Host:
    """A recorder standing in for the loopback host.

    ⭐ It records the URL, the method, the headers and the body of every request,
    so a test can assert **which route was called with what** rather than only
    that something happened.
    """

    def __init__(self, reply: Any = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._reply = reply if reply is not None else {"ok": True, "results": []}
        self.raises: BaseException | None = None

    def __call__(self, request: Any, timeout: float | None = None) -> Answer:
        body = request.data.decode("utf-8") if request.data else ""
        self.calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "auth": request.get_header("Authorization"),
                "body": json.loads(body) if body else None,
            }
        )
        if self.raises is not None:
            raise self.raises
        return Answer(self._reply)

    @property
    def last(self) -> dict[str, Any]:
        assert self.calls, "the host was never called"
        return self.calls[-1]


def _equipped(tmp_path: Path, *, running: bool = True) -> Mapping[str, str]:
    """An environment whose state directory holds a port and token, or does not.

    ⛔ **``APPDATA`` answers this on Windows ONLY**, and that is why this helper
    sets two more variables it looks like it does not need.

    ⚠️ Off Windows the directory comes from ``XDG_CONFIG_HOME``, or from
    ``HOME/.config``. With neither set, ``config.user_config_path`` builds
    ``Path("") / ".config"`` -- a **relative** path, shared by every test in the
    session and living in the checkout. The parametrised cases below then left a
    ``port`` and a ``token`` in it, ``running=False`` did not remove them, and
    the *no host at all* test connected to port 55555 and got **"not answering"**
    where it asserts **"not running"**. Every MCP job on the Linux matrix failed;
    every local run on Windows passed. **The isolation depended on the platform,
    and nothing said so.**

    ⭐ So the directory is now asserted to be inside ``tmp_path`` rather than
    assumed to be. A platform where that stops holding fails here, loudly, at the
    line that says why -- instead of somewhere else, three tests later.
    """
    environ = dict(equipped(tmp_path))
    environ["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    environ["HOME"] = str(tmp_path / "home")

    directory = paths.state_directory(environ)
    assert tmp_path in directory.parents, (
        f"the state directory resolved to {directory}, which is not under this "
        f"test's tmp_path -- state leaks between cases and the failure surfaces "
        f"somewhere else entirely"
    )
    directory.mkdir(parents=True, exist_ok=True)
    # ⛔ Written when running, REMOVED when not. An absent file and a stale one
    # are different states, and only one of them is what this asks for.
    for name, value in (("port", PORT), ("token", TOKEN)):
        path = directory / name
        if running:
            path.write_text(value, encoding="utf-8")
        elif path.exists():
            path.unlink()
    return environ


def _tools(tmp_path: Path, host: Host | None, *, running: bool = True) -> Any:
    tools = mcp_server.Tools(_equipped(tmp_path, running=running), session="sess0001")
    if host is not None:
        # ⚠️ Patched on the module the server imports, not globally.
        mcp_server.urllib.request.urlopen = host  # type: ignore[assignment]
    return tools


@pytest.fixture(autouse=True)
def _restore_urlopen() -> Any:
    """⛔ Leave no stub armed. Restored whatever the test did."""
    import urllib.request

    original = urllib.request.urlopen
    yield
    urllib.request.urlopen = original
    mcp_server.urllib.request.urlopen = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Every live-read tool reaches its route, with its parameters
# ⭐ All THIRTEEN of them, through the registered MCP wrappers -- not six,
#    and not by calling Tools directly. Both were true of the first version.
# ---------------------------------------------------------------------------

# ⭐ (tool name, keyword arguments, the route it must reach, the query it must send)
#
# ⛔ **All thirteen live reads, not the six this started with.** The first
# version covered six and a section heading above it said *every live read*,
# which was false in the file that exists to stop exactly that kind of claim.
# A regression in any of the other seven passed the suite untouched.
LIVE_READS: tuple[tuple[str, dict[str, Any], str, dict[str, str]], ...] = (
    ("find_people", {"name": "Ashenmoor"}, "/find/people", {"q": "Ashenmoor"}),
    ("find_place", {"text": "Invented"}, "/find/place", {"q": "Invented"}),
    ("find_source", {"text": "Register"}, "/find/source", {"q": "Register"}),
    ("find_families", {"gramps_id": "X0001"}, "/find/families", {"gramps_id": "X0001"}),
    ("list_events", {"gramps_id": "X0001"}, "/find/events", {"gramps_id": "X0001"}),
    (
        "list_family_events",
        {"gramps_id": "X0001"},
        "/find/family-events",
        {"gramps_id": "X0001"},
    ),
    # ⭐ **Two arguments, and both are asserted.** A tool that dropped its second
    # one reached the right route with half the question, which is the shape a
    # single-argument table cannot see.
    (
        "find_citation",
        {"source": "Register", "page": "12"},
        "/find/citation",
        {"source": "Register", "page": "12"},
    ),
    (
        "list_notes",
        {"gramps_id": "X0001", "kind": "family"},
        "/find/notes",
        {"gramps_id": "X0001", "kind": "family"},
    ),
    (
        "list_associations",
        {"gramps_id": "X0001"},
        "/find/associations",
        {"gramps_id": "X0001"},
    ),
    (
        "list_citations",
        {"gramps_id": "X0001", "kind": "event"},
        "/find/citations",
        {"gramps_id": "X0001", "kind": "event"},
    ),
    ("find_orphans", {"kind": "people"}, "/find/orphans", {"kind": "people"}),
    (
        "changed_since",
        {"since": "2026-08-01", "kind": "families"},
        "/find/changed",
        {"since": "2026-08-01", "kind": "families"},
    ),
    # ⚠️ The one read with no search term, and the only way to ask the size.
    ("tree_totals", {}, "/totals", {}),
    # ⚠️ The other argument-free read. It rides the route that already carried
    # the name, so what is asserted here is the WIRING, not a new capability.
    ("tree_name", {}, "/health", {}),
)

# ⛔ Tools whose DEFAULT for a second argument is what a caller usually gets, so
# the default itself is part of the wiring and is asserted separately.
LIVE_READ_DEFAULTS: tuple[tuple[str, dict[str, Any], str, dict[str, str]], ...] = (
    ("find_citation", {"source": "Register"}, "/find/citation", {"page": ""}),
    ("list_notes", {"gramps_id": "X0001"}, "/find/notes", {"kind": "person"}),
    ("list_citations", {"gramps_id": "X0001"}, "/find/citations", {"kind": "person"}),
    ("changed_since", {"since": "2026-08-01"}, "/find/changed", {"kind": "people"}),
)


def _assert_it_asked(tool: str, url: str, route: str, query: dict[str, str]) -> None:
    """⛔ The route, and **each key bound to its own value**.

    ⚠️ Searching for every key and every value independently anywhere in the URL
    passes for a wrapper that **swaps its arguments**: with
    ``since=families&kind=2026-08-01`` both keys and both values are present, so
    every assertion holds while the host is asked an entirely different
    question. Two of the tools here take two arguments of the same shape, which
    is exactly where that swap is possible.

    ⭐ So the query is parsed and compared as a mapping. ``urlsplit`` also means
    the route is matched against the **path**, not found as a substring of a
    query value.
    """
    from urllib.parse import parse_qs, urlsplit

    parts = urlsplit(url)
    assert parts.path == route, f"{tool} did not reach {route}: {url}"

    asked = {
        key: values[0] for key, values in parse_qs(parts.query, keep_blank_values=True).items()
    }
    for key, value in query.items():
        assert key in asked, f"{tool} sent no {key}: {url}"
        assert asked[key] == value, (
            f"{tool} bound {key}={asked[key]!r}, expected {value!r} -- the keys and "
            f"values can all be present and still be paired wrongly: {url}"
        )


def _refusal_reaching_an_mcp_caller(tools: Any, tool: str, kwargs: dict[str, Any]) -> str:
    """What a client actually receives when a registered wrapper refuses.

    ⛔ **Not the internal exception text.** Calling ``Tools`` directly proves what
    ``ToolRefusal`` says; it says nothing about what survives the SDK's own
    handling at the registered boundary. A change that replaced or truncated the
    host's detail there would keep every direct-call assertion green while real
    callers received something else.

    ⛔ **What the SDK does with that refusal is VERSION-DEPENDENT, measured.**
    On ``mcp`` 2.0.0 the message is ``Error executing tool find_people: <the
    reason>``. On 2.1.1 -- which CI resolves, because nothing pins it -- it is
    ``Error executing tool find_people`` and **the reason is gone entirely**.

    ⚠️ So callers assert only what holds on both: that the wrapper refuses, and
    that it names the tool. **Whether the host's reason survives is asserted one
    layer down, against ``Tools``**, where it is this project's own contract
    rather than the SDK's. The gap is real -- the newer SDK silently discards
    every refusal reason a user would act on -- and it is filed.
    """
    import asyncio

    server = mcp_server.build_server(tools)
    try:
        asyncio.run(server.call_tool(tool, kwargs))
    except Exception as reached:  # noqa: BLE001 - the SDK's wrapper type is its own
        return str(reached)
    raise AssertionError(f"{tool} did not refuse at all; the caller got a result")


def _through_the_registered_wrapper(tools: Any, tool: str, kwargs: dict[str, Any]) -> Any:
    """⛔ Call the tool the way an MCP client would, not the way we would.

    ⚠️ **Invoking ``Tools`` directly leaves ``build_server`` untested**, and
    ``build_server`` is the seam. A registered wrapper that delegated to the
    wrong method -- ``find_place`` calling ``tools.find_people`` -- kept every
    route assertion green while real MCP callers reached the wrong route.

    ⭐ ``call_tool`` is the server's own public entry point and needs no
    transport and no client, so the whole registered surface is reachable from a
    unit test.
    """
    import asyncio

    server = mcp_server.build_server(tools)
    return asyncio.run(server.call_tool(tool, kwargs))


@pytest.mark.parametrize("tool, kwargs, route, query", LIVE_READS)
def test_a_live_read_reaches_its_own_route_with_its_own_parameters(
    tmp_path: Path, tool: str, kwargs: dict[str, Any], route: str, query: dict[str, str]
) -> None:
    """⛔ The wiring, per tool.

    ⚠️ Asserting only *"a request happened"* would pass against a server that sent
    every tool to the same route with the wrong argument — which is exactly the
    class of defect an untested seam hides.
    """
    # ⭐ A payload only this call could have produced, so the result assertion
    # below cannot be satisfied by a wrapper that returned something else.
    host = Host({"ok": True, "results": [], "echo": f"{tool}-answered"})
    tools = _tools(tmp_path, host)

    returned = _through_the_registered_wrapper(tools, tool, kwargs)

    _assert_it_asked(tool, host.last["url"], route, query)

    # ⛔ **The host's answer has to come BACK, not just go out.** A wrapper that
    # called the right method and then returned ``{}`` -- or another tool's
    # result -- satisfied every route, query and token assertion here while an
    # MCP client received nothing. The outbound half was tested and the return
    # half was discarded.
    assert returned.structured_content == {
        "ok": True,
        "results": [],
        "echo": f"{tool}-answered",
    }, (
        f"{tool} reached its route but the host's answer did not reach the "
        f"caller: {returned.structured_content}"
    )

    # ⛔ **GET, asserted rather than merely recorded.** The recorder captures the
    # method and nothing looked at it. The fake accepts every verb; the real
    # host's ``do_POST`` serves one route and 404s every live read, so a change
    # that attached data -- turning these into POSTs -- would keep every test
    # here green and 404 against Gramps.
    assert host.last["method"] == "GET", (
        f"{tool} used {host.last['method']}; the real host 404s live reads on anything but GET"
    )


def test_every_live_read_carries_the_bearer_token(tmp_path: Path) -> None:
    """⛔ The host refuses an unauthenticated request before it looks at the route.

    ⭐ So a tool that forgot the header would fail against the real host and pass
    against any test that only checked the URL.
    """
    host = Host()
    tools = _tools(tmp_path, host)

    for tool, kwargs, _route, _query in LIVE_READS:
        _through_the_registered_wrapper(tools, tool, kwargs)
        assert host.last["auth"] == f"Bearer {TOKEN}", (
            f"{tool} sent {host.last['auth']!r} rather than the minted token"
        )


def test_tree_name_returns_the_name_the_host_reported(tmp_path: Path) -> None:
    """⛔ The point of the tool is the NAME, so assert the name, not the call.

    ⚠️ A test that only checked the route would pass for a wrapper that reached
    ``/health`` and threw the answer away -- which is exactly the state this
    tool was built to end, since ``/health`` has always carried the name and
    nothing could ask it.
    """
    # ⛔ **The REAL envelope.** ``/health`` answers ``{"ok": ..., "tree": {...}}``
    # -- ``_answer(HEALTH_ROUTE, "tree", ...)`` in the listener, and
    # ``test_host_over_loopback`` asserts through ``body["tree"]``. A fake that
    # put the fields at the top level made these tests pass against a shape no
    # caller ever receives, which is a fake proving something about itself.
    host = Host({"ok": True, "tree": {"open": True, "name": "Some Tree", "people": 3}})
    tools = _tools(tmp_path, host)

    answer = tools.tree_name()

    assert "/health" in host.last["url"], host.last["url"]
    assert answer["tree"]["name"] == "Some Tree"
    assert answer["tree"]["people"] == 3


def test_tree_name_reports_a_closed_tree_as_an_ordinary_answer(tmp_path: Path) -> None:
    """⚠️ Closed is the state the host STARTS in, not a fault.

    ``load_on_reg`` fires with no tree open, so a wrapper that treated the
    closed shape as an error would be broken at every launch. The host sends
    ``open: false`` and no other key; nothing here may invent one.
    """
    host = Host({"ok": True, "tree": {"open": False}})
    tools = _tools(tmp_path, host)

    answer = tools.tree_name()

    assert answer["tree"]["open"] is False
    assert "name" not in answer["tree"]
    assert "people" not in answer["tree"]


def test_tree_totals_needs_no_argument_and_still_reaches_the_host(tmp_path: Path) -> None:
    """⚠️ The one read with no search term. It is also the only way to ask the size."""
    host = Host({"ok": True, "totals": {"people": 1}})
    tools = _tools(tmp_path, host)

    answer = tools.tree_totals()

    assert "/totals" in host.last["url"], host.last["url"]
    assert answer["totals"] == {"people": 1}


# ---------------------------------------------------------------------------
# What happens when the host is absent, refusing, or unreachable
# ---------------------------------------------------------------------------


def test_no_host_at_all_refuses_by_naming_the_remedy(tmp_path: Path) -> None:
    """⛔ No port file and no token file: Gramps is not running.

    ⚠️ The refusal must say what to do. A caller that is told only *"failed"*
    cannot tell a closed Gramps from a broken tool.
    """
    tools = _tools(tmp_path, None, running=False)

    with pytest.raises(mcp_server.ToolRefusal) as refused:
        tools.find_people(name="anybody")
    assert "not running" in str(refused.value), str(refused.value)
    assert "Gramps" in str(refused.value), str(refused.value)

    assert "find_people" in _refusal_reaching_an_mcp_caller(
        tools, "find_people", {"name": "anybody"}
    )


def test_a_host_that_REFUSES_surfaces_its_own_detail(tmp_path: Path) -> None:
    """⭐ The host's reason must reach the caller, not be replaced by a generic one.

    ⚠️ The host refuses a private target BY NAME rather than reporting it absent,
    and that distinction is ruling 1's whole point. It is worth nothing if the
    MCP layer swallows the detail on the way back.
    """
    host = Host()
    detail = "X0001 is marked private in this tree"
    host.raises = urllib.error.HTTPError(
        url="http://127.0.0.1/find/people",
        code=403,
        msg="Forbidden",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    host.raises.read = lambda: json.dumps({"detail": detail}).encode("utf-8")  # type: ignore[method-assign]
    tools = _tools(tmp_path, host)

    with pytest.raises(mcp_server.ToolRefusal) as refused:
        tools.find_people(name="anybody")
    assert detail in str(refused.value), (
        f"the host's own reason did not reach the tool layer: {refused.value}"
    )

    assert "find_people" in _refusal_reaching_an_mcp_caller(
        tools, "find_people", {"name": "anybody"}
    )


def test_a_host_that_is_UNREACHABLE_asks_whether_gramps_is_open(tmp_path: Path) -> None:
    """⚠️ A port file can outlive the process that wrote it.

    ⭐ So a connection error is the likeliest real-world failure, and the refusal
    has to point at the cause rather than at the socket.
    """
    host = Host()
    host.raises = OSError("connection refused")
    tools = _tools(tmp_path, host)

    with pytest.raises(mcp_server.ToolRefusal) as refused:
        tools.find_people(name="anybody")
    assert "Gramps" in str(refused.value), f"the refusal does not point at Gramps: {refused.value}"

    assert "find_people" in _refusal_reaching_an_mcp_caller(
        tools, "find_people", {"name": "anybody"}
    )


@pytest.mark.parametrize("tool, kwargs, route, query", LIVE_READ_DEFAULTS)
def test_a_live_read_sends_its_DEFAULT_for_an_argument_the_caller_omitted(
    tmp_path: Path, tool: str, kwargs: dict[str, Any], route: str, query: dict[str, str]
) -> None:
    """⛔ The default is part of the wiring, and it is what most callers get.

    ⚠️ ``list_notes`` defaults ``kind`` to ``person``; a wrapper that dropped the
    argument, or passed a different default than ``Tools`` does, reaches the right
    route and asks a different question. The full-argument cases above cannot see
    that, because they never omit anything.
    """
    host = Host()
    tools = _tools(tmp_path, host)

    _through_the_registered_wrapper(tools, tool, kwargs)

    _assert_it_asked(tool, host.last["url"], route, query)


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_the_fixture_isolates_its_state_on_EVERY_platform(tmp_path: Path, platform: str) -> None:
    """⛔ The bug that turned the whole MCP matrix red, pinned where it happened.

    ⚠️ ``equipped`` supplies ``APPDATA``, which answers this **on Windows only**.
    Off Windows the directory comes from ``XDG_CONFIG_HOME`` or ``HOME/.config``,
    and with neither set ``config.user_config_path`` builds ``Path("") /
    ".config"`` -- **relative**, in the checkout, and shared by every test in the
    session. Measured before the fix: ``win32`` landed under ``tmp_path``,
    ``linux`` and ``darwin`` both landed on ``.config/gramps-live-api``.

    ⭐ **This is why the check is parametrised over the platform rather than run
    on this one.** A test that only ever asks ``sys.platform`` is a check whose
    definition comes from where it runs, and it passed on Windows through six red
    Linux jobs.
    """
    directory = paths.state_directory(_equipped(tmp_path), platform=platform)

    assert tmp_path in directory.parents, (
        f"on {platform} the state directory resolves to {directory}, outside this "
        f"test's tmp_path -- state leaks between cases and the failure surfaces "
        f"somewhere else entirely"
    )


def test_a_refusals_REASON_reaches_an_mcp_caller(tmp_path: Path) -> None:
    """⛔ **The property the SDK pin exists to hold, asserted so it cannot lapse.**

    ⚠️ ``TargetIsPrivate`` refuses a private target **by name** rather than
    reporting it absent, and that distinction is ruling 1's whole point. It is
    worth nothing if the reason is discarded on the way back to the caller.

    ⭐ **Measured across both SDK versions, isolated environments, same probe:**

    ===========  =========================================================
    ``2.0.0``    ``Error executing tool ...: source ... is marked private``
    ``2.1.1``    ``Error executing tool ...``
    ===========  =========================================================

    On 2.1.1 a caller cannot tell **private** from **not found**, which inverts
    the distinction this project is built to make. ``pyproject.toml`` pins
    ``mcp<2.1`` for exactly that, as a stopgap -- issue #173 holds the design
    call the owner still owes.

    ⛔ **This test is what makes that pin honest.** Relaxing the bound without
    the design change fails here, naming the property. A pin with no test is a
    pin someone relaxes.

    ⚠️ It is deliberately NOT the layer-split the other failure-path cases use.
    Those assert what holds on **any** SDK, because a suite must not go red on a
    dependency's behaviour; this one asserts what the **pinned** SDK must do, and
    going red is precisely its job when the pin stops being true.
    """
    host = Host()
    reason = "source X0001 is marked private in this tree"
    host.raises = urllib.error.HTTPError(
        url="http://127.0.0.1/find/source",
        code=403,
        msg="Forbidden",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    host.raises.read = lambda: json.dumps({"detail": reason}).encode("utf-8")  # type: ignore[method-assign]
    tools = _tools(tmp_path, host)

    reached = _refusal_reaching_an_mcp_caller(tools, "find_source", {"text": "Register"})

    assert reason in reached, (
        "the reason did not reach the MCP caller, so a private record is "
        "indistinguishable from a missing one. Either the mcp pin in "
        "pyproject.toml has been relaxed past 2.1, or the SDK changed again -- "
        f"see issue #173. What the caller got: {reached}"
    )
