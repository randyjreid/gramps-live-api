"""A2 — R3's precondition P2, implemented in ``host/`` and asserted here.

⚠️ **This is the blocking criterion.** R3 is ruled and its only egress bound is
the ``priv`` exclusion, the required search term and the result cap. Those live
in ``core/people.py``, the export reader; **nothing in
``src/gramps_live_api/host/`` implemented any of them**, so a live read surface
built without this ships R3's bound with nothing behind it.

⛔ **The three bounds answer different questions**, and the third is the one that
gets lost: a private person must be in **neither the results nor the count**.
*42 matched, 25 shown* over a set that included people it will never show leaks
the existence of the excluded ones by arithmetic -- ruling 1's first enforcement
point, which is about counting rather than about text.
"""

from __future__ import annotations

import pytest

from gramps_live_api.host import reads


def row(gramps_id: str, display: str, *, private: bool) -> tuple[bool, reads.Match]:
    return private, reads.Match(gramps_id=gramps_id, display=display)


# ---------------------------------------------------------------------------
# A2, bound 1: excluded from results, and excluded from the count
# ---------------------------------------------------------------------------


def test_a2_a_private_person_is_in_neither_the_results_nor_the_count() -> None:
    """⛔ The arithmetic must not be runnable backwards."""
    found = reads.bound(
        [
            row("I0001", "Public, Anne", private=False),
            row("I0002", "Hidden, Brian", private=True),
            row("I0003", "Public, Clara", private=False),
        ]
    )

    ids = [match.gramps_id for match in found.matches]
    assert ids == ["I0001", "I0003"], "a private person appeared in the results"
    assert found.matched == 2, (
        "matched counted a private person -- '3 matched, 2 shown' tells the caller "
        "somebody exists that they may not see, which is the leak by arithmetic"
    )
    assert found.withheld == 0
    assert found.capped is False


def test_a2_the_cap_reports_withheld_over_visible_rows_only() -> None:
    """The cap and the privacy filter compose without the filter leaking."""
    rows = [row(f"I{n:04d}", f"Person, {n}", private=False) for n in range(30)]
    rows += [row("I9001", "Hidden, One", private=True)]

    found = reads.bound(rows, cap=25)

    assert found.shown == 25
    assert found.matched == 30, "the private row must not be in the total either"
    assert found.withheld == 5, "withheld is over visible rows, not over everything"
    assert found.capped is True


def test_a2_a_wholly_private_result_set_is_indistinguishable_from_no_matches() -> None:
    """⭐ The strongest form: nothing distinguishes *all private* from *none*."""
    all_private = reads.bound([row("I0002", "Hidden", private=True)])
    nothing = reads.bound([])

    assert all_private == nothing


# ---------------------------------------------------------------------------
# A2, bound 2: a search term is required
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_a2_a_listing_without_a_term_is_refused(empty: str | None) -> None:
    """⛔ There is no *list everybody*. A privacy control, not an ergonomic one."""
    with pytest.raises(reads.SearchTermRequired):
        reads.require_term(empty)


def test_a2_the_refusal_says_it_is_a_privacy_control() -> None:
    """A caller told only *invalid input* narrows and retries; this one is told why."""
    with pytest.raises(reads.SearchTermRequired) as refusal:
        reads.require_term("")
    assert "privacy" in str(refusal.value)


# ---------------------------------------------------------------------------
# A2, bound 3: refused BY NAME when named directly
# ---------------------------------------------------------------------------


def test_a2_private_and_absent_are_different_exceptions() -> None:
    """⛔ Ruling 1's second enforcement point.

    Silence would leave the caller unable to tell *no such person* from *that
    person is private*. A listing hides them; a direct target refuses **by name**.
    """
    assert issubclass(reads.TargetIsPrivate, reads.ReadRefused)
    assert not issubclass(reads.SearchTermRequired, reads.TargetIsPrivate)

    refusal = reads.TargetIsPrivate("I0002 is marked private in this tree")
    assert "private" in str(refusal), (
        "the refusal must say WHY, or it is indistinguishable from not-found"
    )


# ---------------------------------------------------------------------------
# The alternate-name walk, which is what a duplicate mother turned on
# ---------------------------------------------------------------------------


def test_folding_matches_across_an_accent_but_not_across_a_transliteration() -> None:
    """⭐ Unicode normalisation, and deliberately nothing more.

    Folding makes an accented spelling match its unaccented form. It does **not**
    make the German ``ue`` spelling match the umlaut -- that is orthography, not
    a Unicode property, and inventing language rules is how a search starts
    guessing. The alternate-name walk is what catches that case, because the
    tree records the ``ue`` spelling as an actual name.
    """
    umlaut = "Künkele"

    assert reads.matches_term("Kunkele", umlaut), "folding should ignore the accent"
    assert reads.matches_term("kunkele", umlaut), "and case"
    assert not reads.matches_term("Kuenkele", umlaut), (
        "ue -> umlaut is a transliteration rule, not a Unicode one; the "
        "alternate-name walk covers it instead"
    )


# ---------------------------------------------------------------------------
# Private must not be distinguishable from absent, ON THE WIRE
# ---------------------------------------------------------------------------


def test_a_private_node_appears_in_missing_just_like_an_absent_one() -> None:
    """⛔ Otherwise the caller reads the difference back as *this record exists*.

    A private node answers ``found: false``. Leaving it out of ``missing`` made
    it the one id that is neither found nor missing — and comparing those two
    fields recovers exactly the fact the privacy flag was hiding.
    """
    from gramps_live_api.host import document

    absent = document.Resolved("p1", "I9999", "person", found=False)
    private = document.Resolved("p2", "I0001", "person", found=False, private=True)
    resolution = document.Resolution(nodes=(absent, private))

    on_the_wire = [node.gramps_id for node in resolution.missing]
    assert on_the_wire == ["I9999", "I0001"], (
        "a private id must be indistinguishable from an absent one in the read "
        f"projection, got {on_the_wire}"
    )


def test_the_write_path_can_still_tell_them_apart() -> None:
    """⭐ The two enforcement points are kept apart by ORDERING, not by lying.

    ``missing`` is deliberately undiscriminating; ``refused`` carries the
    difference, and the write path checks it first — so a private target is
    still refused BY NAME there rather than reported absent.
    """
    from gramps_live_api.host import document

    resolution = document.Resolution(
        nodes=(
            document.Resolved("p1", "I9999", "person", found=False),
            document.Resolved("p2", "I0001", "person", found=False, private=True),
        )
    )
    assert [n.gramps_id for n in resolution.refused] == ["I0001"]
