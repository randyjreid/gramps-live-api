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
    """An environment whose state directory holds a port and token, or does not."""
    environ = equipped(tmp_path)
    directory = paths.state_directory(environ)
    directory.mkdir(parents=True, exist_ok=True)
    if running:
        (directory / "port").write_text(PORT, encoding="utf-8")
        (directory / "token").write_text(TOKEN, encoding="utf-8")
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
# ---------------------------------------------------------------------------

# ⭐ (tool name, keyword arguments, the route it must reach, the query it must send)
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
)


@pytest.mark.parametrize("tool, kwargs, route, query", LIVE_READS)
def test_a_live_read_reaches_its_own_route_with_its_own_parameters(
    tmp_path: Path, tool: str, kwargs: dict[str, Any], route: str, query: dict[str, str]
) -> None:
    """⛔ The wiring, per tool.

    ⚠️ Asserting only *"a request happened"* would pass against a server that sent
    every tool to the same route with the wrong argument — which is exactly the
    class of defect an untested seam hides.
    """
    host = Host()
    tools = _tools(tmp_path, host)

    getattr(tools, tool)(**kwargs)

    assert route in host.last["url"], f"{tool} did not reach {route}: {host.last['url']}"
    for key, value in query.items():
        assert f"{key}=" in host.last["url"], f"{tool} sent no {key}: {host.last['url']}"
        assert value.replace(" ", "+") in host.last["url"] or value in host.last["url"], (
            f"{tool} sent the wrong {key}: {host.last['url']}"
        )


def test_every_live_read_carries_the_bearer_token(tmp_path: Path) -> None:
    """⛔ The host refuses an unauthenticated request before it looks at the route.

    ⭐ So a tool that forgot the header would fail against the real host and pass
    against any test that only checked the URL.
    """
    host = Host()
    tools = _tools(tmp_path, host)

    for tool, kwargs, _route, _query in LIVE_READS:
        getattr(tools, tool)(**kwargs)
        assert host.last["auth"] == f"Bearer {TOKEN}", (
            f"{tool} sent {host.last['auth']!r} rather than the minted token"
        )


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
        f"the host's own reason did not reach the caller: {refused.value}"
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
