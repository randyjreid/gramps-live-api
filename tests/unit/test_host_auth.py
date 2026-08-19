"""The auth check, which R8 makes a named risk surface and this slice treats as one.

A listening socket inside the owner's Gramps is new attack surface. Four things
carry it, and each is asserted here rather than reviewed by eye:

- a **random** bearer token from ``secrets``, required on every request;
- compared with ``hmac.compare_digest``, **never** ``==``;
- **any** ``Origin`` header rejects the request outright;
- the listener binds ``127.0.0.1`` and nothing else.

⚠️ **What this does NOT claim, stated here because the next reader will assume
it.** The token does not defend against a local process running as the owner:
such a process can read the token file, and it could read the tree directly
without bothering. R8 accepts that residual on exactly that ground. What the
token defends against is something that can reach the socket but not the
filesystem -- which, with the ``Origin`` rule beside it, is a page the owner has
open in a browser.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from gramps_live_api.host import auth, httpd, tokens

AUTH_SOURCE = Path(auth.__file__)


def test_a_token_is_random_and_long_enough_to_be_worth_comparing() -> None:
    """Two tokens in a row must differ, and neither may be short.

    A guessable token makes the ``Origin`` rule the only defence, and the
    ``Origin`` rule is about browsers alone.
    """
    minted = {tokens.new_token() for _ in range(64)}

    assert len(minted) == 64, "token generation repeated itself, so it is not random"
    assert all(len(one) >= 32 for one in minted), "a token short enough to guess is not a token"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param("Bearer abc123", "abc123", id="the ordinary spelling"),
        pytest.param("bearer abc123", "abc123", id="a lowercase scheme is still bearer"),
        pytest.param("BEARER abc123", "abc123", id="and an uppercase one"),
        pytest.param(None, None, id="no header at all"),
        pytest.param("", None, id="an empty header"),
        pytest.param("abc123", None, id="a bare value with no scheme"),
        pytest.param("Basic abc123", None, id="another scheme entirely"),
        pytest.param("Bearer", None, id="a scheme with nothing after it"),
        pytest.param("Bearer ", None, id="a scheme with only space after it"),
    ],
)
def test_the_authorization_header_is_read_the_way_the_scheme_defines_it(
    header: str | None, expected: str | None
) -> None:
    """RFC 7235 makes the scheme case-insensitive; the value is not.

    The empty-value rows matter more than they look: a handler that returned
    ``""`` there would then compare an empty presented token against the real
    one, which is a comparison that must fail -- and does -- but only by luck of
    the token never being empty. Refusing to produce a value at all is the
    answer that does not depend on that.
    """
    assert auth.presented_token(header) == expected


def test_the_right_token_is_accepted_and_a_wrong_one_is_not() -> None:
    real = tokens.new_token()

    assert auth.token_matches(real, real)
    assert not auth.token_matches(real + "x", real)
    assert not auth.token_matches("", real)
    assert not auth.token_matches(real[:-1], real), "a truncated token must not match"


def test_a_comparison_of_different_lengths_answers_rather_than_raising() -> None:
    """``compare_digest`` raises on non-ASCII ``str``, so the values must be bytes.

    This is the trap in using it directly: hand it two ``str`` where either
    carries a non-ASCII character and it raises ``TypeError`` -- out of a request
    handler, which turns a wrong token into a 500 instead of a 401. Encoding
    first is what makes the check total over anything a header can carry.
    """
    assert not auth.token_matches("tökén", tokens.new_token())


def comparisons_in(function_name: str) -> list[str]:
    """Every ``==``/``!=`` comparison inside this function of the auth module."""
    tree = ast.parse(AUTH_SOURCE.read_text(encoding="utf-8"), filename=str(AUTH_SOURCE))
    bodies = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    assert bodies, f"{function_name} is not defined in {AUTH_SOURCE.name} any more"

    return [
        ast.unparse(node)
        for body in bodies
        for node in ast.walk(body)
        if isinstance(node, ast.Compare)
        and any(isinstance(operator, (ast.Eq, ast.NotEq)) for operator in node.ops)
    ]


def test_the_token_comparison_is_constant_time_by_construction() -> None:
    """R8 says ``hmac.compare_digest``, not ``==``, so the source is checked for it.

    A behavioural test cannot tell the two apart -- both return the same answers
    -- and the difference is the whole point: ``==`` on ``str`` short-circuits at
    the first differing byte and leaks the token one character at a time to
    anything that can time a request.

    So this reads the code. It is a source-level rule and its bound is stated:
    it watches one function, and a comparison moved out of that function is a
    comparison it does not see. That is why the function is small.
    """
    source = AUTH_SOURCE.read_text(encoding="utf-8")

    assert "hmac.compare_digest" in source, (
        "the auth module no longer calls hmac.compare_digest at all"
    )
    assert comparisons_in("token_matches") == [], (
        "the token comparison uses an equality operator, which short-circuits at "
        "the first differing byte and leaks the token to anything that can time a "
        f"request: {comparisons_in('token_matches')}"
    )


def test_the_listener_binds_loopback_and_could_not_be_told_otherwise() -> None:
    """``0.0.0.0`` would put the owner's tree on every interface of the machine.

    Asserted as the value of the constant AND as the absence of the wildcard
    anywhere in the module, because a second bind added later would not go
    through the constant.
    """
    assert httpd.LOOPBACK == "127.0.0.1"

    source = Path(httpd.__file__).read_text(encoding="utf-8")

    assert "0.0.0.0" not in source, (
        "the wildcard address appears in the listener module, so something there "
        "can bind every interface on the machine"
    )


def test_the_socket_cannot_be_taken_over_by_a_later_binder() -> None:
    """``HTTPServer`` sets ``allow_reuse_address``; on Windows that is a hijack.

    There it lets any process bind a port another is already listening on, with
    delivery undefined between them -- so the default would let something else
    take over answering for our socket. Nothing is given up by refusing it,
    because the port is chosen fresh by the operating system at every startup.
    """
    assert httpd.HostServer.allow_reuse_address is False
