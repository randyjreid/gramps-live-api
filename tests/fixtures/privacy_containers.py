"""Which Gramps calls reach which ``priv``-carrying container.

⭐ **This is the ratchet's one hand-written input, and it is its fail-open.** The
published DTD names *containers*; it does not name Python methods. So the
container **list** is derived and re-derivable — see
``core/_specified_containers.py`` and its recorded digests — while the **mapping
below is written by hand and cannot be re-derived from anything.**

⛔ **A getter nobody lists makes its container read as unreachable.** That is the
whole weakness, stated here rather than discovered later, and
``test_privacy_container_ratchet.py`` carries a companion assertion that fails
when the accessor calls a container-shaped getter this map does not know.

⚠️ **Two kinds of getter, and the distinction is load-bearing.**

``YIELDS_OBJECT``
    the call hands back the container itself (or an iterator of them), so the
    thing it hands back is what must be gated.
``YIELDS_HANDLE``
    the call hands back opaque handles. **Gating the handle would be
    meaningless** -- the gate belongs on whatever fetch turns it into an object,
    which is its own entry in ``YIELDS_OBJECT``. These entries establish
    *reachability* only.

**Round 4 is why that split exists.** ``get_parent_family_handle_list()`` returns
handles, so a container can be reached with no reference anywhere on the path --
and a rule phrased as *"every ``.ref`` is gated"* cannot see it.
"""

from __future__ import annotations

YIELDS_OBJECT: dict[str, tuple[str, ...]] = {
    "person": (
        "iter_people",
        "get_person_from_handle",
        "get_person_from_gramps_id",
    ),
    "family": (
        "iter_families",
        "get_family_from_handle",
        "get_family_from_gramps_id",
    ),
    "event": (
        "iter_events",
        "get_event_from_handle",
        "get_event_from_gramps_id",
    ),
    "placeobj": (
        "iter_places",
        "get_place_from_handle",
        "get_place_from_gramps_id",
    ),
    "source": (
        "iter_sources",
        "get_source_from_handle",
        "get_source_from_gramps_id",
    ),
    "citation": (
        "iter_citations",
        "get_citation_from_handle",
        "get_citation_from_gramps_id",
    ),
    "note": (
        "iter_notes",
        "get_note_from_handle",
        "get_note_from_gramps_id",
    ),
    "repository": (
        "iter_repositories",
        "get_repository_from_handle",
        "get_repository_from_gramps_id",
    ),
    "object": (
        "iter_media",
        "get_media_from_handle",
        "get_media_from_gramps_id",
    ),
    "childref": ("get_child_ref_list",),
    "eventref": ("get_event_ref_list", "get_birth_ref", "get_death_ref"),
    "personref": ("get_person_ref_list",),
    "objref": ("get_media_list",),
    "reporef": ("get_reporef_list",),
    "name": ("get_primary_name", "get_alternate_names"),
    "address": ("get_address_list",),
    "attribute": ("get_attribute_list",),
    "srcattribute": ("get_attribute_list",),
    "url": ("get_url_list",),
    "lds_ord": ("get_lds_ord_list",),
}
"""Container -> the calls that hand back the container itself."""

YIELDS_HANDLE: dict[str, tuple[str, ...]] = {
    "family": ("get_family_handle_list", "get_parent_family_handle_list"),
    "note": ("get_note_list",),
    "event": ("get_event_handles",),
    "person": ("get_person_handles",),
    "placeobj": ("get_place_handles", "get_placeref_list"),
}
"""Container -> calls that hand back handles. ⛔ Reachability only, never a gate
site: the handle is opaque and gating it would assert nothing."""


def every_mapped_getter() -> set[str]:
    """Every getter name this map knows, in either direction."""
    names: set[str] = set()
    for table in (YIELDS_OBJECT, YIELDS_HANDLE):
        for getters in table.values():
            names.update(getters)
    return names
