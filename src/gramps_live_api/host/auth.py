"""Who is allowed to ask. Two functions, both deliberately small.

⚠️ **``token_matches`` is small because a test reads it.**
``tests/unit/test_host_auth.py`` parses this file and refuses an equality
operator inside that function -- a source-level rule, because no behavioural
test can tell ``==`` from ``hmac.compare_digest``: they return the same answers,
and the difference is that ``==`` stops at the first differing byte and hands the
token to anything that can time a request. A comparison moved out of this
function is a comparison that rule does not see, which is the whole reason to
keep the function one line long.

⚠️ **The values are encoded before they are compared, and that is not tidiness.**
``hmac.compare_digest`` raises ``TypeError`` on a ``str`` carrying anything
outside ASCII. A header is attacker-controlled text, so the ``str`` spelling
turns a wrong token into an exception out of a request handler -- a 500 where a
401 belongs, and a different response to a wrong token than to a differently
wrong one.
"""

from __future__ import annotations

import hmac

BEARER = "bearer"


def presented_token(authorization: str | None) -> str | None:
    """The token out of an ``Authorization`` header, or ``None`` if there is not one.

    ``None`` rather than ``""`` for an absent or malformed header. An empty
    string would go on to be compared against the real token and fail -- but only
    because the real token is never empty, which is a property of the generator
    rather than of this check.
    """
    if not authorization:
        return None

    scheme, separator, value = authorization.partition(" ")
    if not separator or scheme.lower() != BEARER:
        return None

    return value.strip() or None


def token_matches(presented: str, expected: str) -> bool:
    """Constant-time, and total over anything a header can carry."""
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
