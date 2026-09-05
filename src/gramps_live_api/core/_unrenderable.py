"""The characters ``preview`` refuses, derived from the published UCD.

⚠️ **MACHINE-GENERATED. DO NOT HAND-EDIT.** Regenerate it with
``scripts/derive_unrenderable.py`` over artifacts matching the digests below,
and see the derivation note in ``docs`` for where each one comes from.

⚠️ **This module IS the class**, and ``core/render_guard.py`` imports it. That is
a stated deviation from the precedent this table follows, whose generated module
nothing imports: there the table was a checklist beside a hand-written weighting,
and duplicating it by hand was tractable. Here a hand-maintained copy would be
the thing the derivation exists to remove.

⚠️ **No fetch date is recorded here.** Verification is re-fetch, compare digest,
re-run, and diff against this file; a timestamp would make every such run differ
from the file it is checking. Dates belong to the note.
"""

from __future__ import annotations

SOURCE_DIGESTS: tuple[tuple[str, str], ...] = (
    ("general-category", "d62e5bab70ca74f099343f71224fa051cb1fdd61a1ab45c0488c44cfc0b6102e"),
    ("core-properties", "24c7fed1195c482faaefd5c1e7eb821c5ee1fb6de07ecdbaa64b56a99da22c08"),
)
"""Each source artifact and the SHA-256 it was read from."""

UNICODE_VERSION: str = "17.0.0"
"""The Unicode version both artifacts declare in their own first line.

The class is a fact about THIS version of the standard and does not track a
later one until somebody re-derives it. That is the cost of determinism, and
it is recorded in the costs block the guard carries.
"""

UNRENDERABLE_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0000, 0x001F, "Cc"),
    (0x007F, 0x009F, "Cc"),
    (0x00AD, 0x00AD, "Cf"),
    (0x034F, 0x034F, "Default_Ignorable_Code_Point"),
    (0x0600, 0x0605, "Cf"),
    (0x061C, 0x061C, "Cf"),
    (0x06DD, 0x06DD, "Cf"),
    (0x070F, 0x070F, "Cf"),
    (0x0890, 0x0891, "Cf"),
    (0x08E2, 0x08E2, "Cf"),
    (0x115F, 0x1160, "Default_Ignorable_Code_Point"),
    (0x17B4, 0x17B5, "Default_Ignorable_Code_Point"),
    (0x180B, 0x180D, "Default_Ignorable_Code_Point"),
    (0x180E, 0x180E, "Cf"),
    (0x180F, 0x180F, "Default_Ignorable_Code_Point"),
    (0x200B, 0x200F, "Cf"),
    (0x202A, 0x202E, "Cf"),
    (0x2060, 0x2064, "Cf"),
    (0x2065, 0x2065, "Default_Ignorable_Code_Point"),
    (0x2066, 0x206F, "Cf"),
    (0x3164, 0x3164, "Default_Ignorable_Code_Point"),
    (0xD800, 0xDFFF, "Cs"),
    (0xE000, 0xF8FF, "Co"),
    (0xFE00, 0xFE0F, "Default_Ignorable_Code_Point"),
    (0xFEFF, 0xFEFF, "Cf"),
    (0xFFA0, 0xFFA0, "Default_Ignorable_Code_Point"),
    (0xFFF0, 0xFFF8, "Default_Ignorable_Code_Point"),
    (0xFFF9, 0xFFFB, "Cf"),
    (0x110BD, 0x110BD, "Cf"),
    (0x110CD, 0x110CD, "Cf"),
    (0x13430, 0x1343F, "Cf"),
    (0x1BCA0, 0x1BCA3, "Cf"),
    (0x1D173, 0x1D17A, "Cf"),
    (0xE0000, 0xE0000, "Default_Ignorable_Code_Point"),
    (0xE0001, 0xE0001, "Cf"),
    (0xE0002, 0xE001F, "Default_Ignorable_Code_Point"),
    (0xE0020, 0xE007F, "Cf"),
    (0xE0080, 0xE0FFF, "Default_Ignorable_Code_Point"),
    (0xF0000, 0xFFFFD, "Co"),
    (0x100000, 0x10FFFD, "Co"),
)
"""Every inclusive range of the class, sorted, with what put it there.

Non-overlapping, and no two adjacent ranges share a label -- which is what
says the coalesce ran. The label is a General_Category value or the derived
core property, and it is what a refusal message names.
"""
