"""Small shared helpers for asserting on guard findings."""

from __future__ import annotations

from collections.abc import Iterable

from gramps_live_api.core.pii_guard import Finding


def rules(findings: Iterable[Finding]) -> list[str]:
    """The distinct property identifiers reported, sorted."""
    return sorted({finding.rule for finding in findings})
