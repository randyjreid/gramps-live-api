"""The operation registry is closed, and the provenance partition is total.

These tests are asserted **over the registry**, never against a hand-written
list of types. That is deliberate and it is the criterion: an enumeration fails
on the case nobody listed, so a tenth operation type must extend this file's
coverage without this file being edited.
"""

from __future__ import annotations

import pytest

from gramps_live_api.core import schema


def test_the_registry_cannot_be_added_to_from_outside() -> None:
    with pytest.raises(TypeError):
        schema.REGISTRY["add_anything"] = None  # type: ignore[index]


def test_the_module_exposes_no_public_registration_function() -> None:
    exported = [
        name for name in dir(schema) if not name.startswith("_") and "register" in name.lower()
    ]

    assert exported == [], (
        "the registry is CLOSED: a public registration function makes the set "
        f"open, and an open set makes the provenance partition unfalsifiable; got {exported}"
    )
