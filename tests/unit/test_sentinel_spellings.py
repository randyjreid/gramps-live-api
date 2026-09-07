"""The blessing is spelled in three places, and nothing checked they agreed.

⛔ **This is the highest-severity finding of the rename probe, and it is not
about the rename.** The sentinel that arms every write path is declared
independently in three modules: ``core/apply``, ``host/document``, and the
writer inside ``gramps_plugin``. The third is inlined deliberately, because
Gramps ``exec``s a plugin module rather than importing it, so it cannot reach
the package's constant.

⚠️ **A partial rename of that value was measured GREEN on all six CI jobs.**
Changing the writer's spelling alone, leaving the other two as they were, left
the whole suite passing:

    MUTANT: the writer's SENTINEL only, one value changed
    1072 passed, 17 skipped        <- core leg: MUTANT SURVIVES

(The value is not written out here. It is on the constant's own line in each of
the three sources, and repeating it in prose is how a fourth spelling starts.)

The one guard that exists is in ``tests/integration/test_round_trip.py``, which
skips twice over -- once where the MCP extra is absent and once where no Gramps
runtime is installed -- and its own skip text says that is expected on CI.

⭐ **Freezing the value makes this pin MORE necessary, not less.** After the
rename to AgentDataEntry the three constants hold a name that no longer matches
the project, which is exactly the shape a future tidying pass fixes in one place
and not the other two. What that ships is ``document`` and ``apply`` answering
*this tree is blessed* while the writer inside Gramps answers *it is not*, from
three constants whose entire purpose is to be one answer.

This test runs on the **core** leg: it parses source and imports neither Gramps
nor the MCP SDK, so it is a measurement on all six jobs rather than a reading.

The precedent for the shape is
``tests/unit/test_cli.py:test_the_source_check_matches_what_the_host_actually_does``,
which reads the plugin's source and fails when two spellings of one rule stop
agreeing. Its docstring calls that this project's most-recorded defect class.
This is another instance of it.
"""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.host_sources import PLUGIN_DIRECTORY, REPOSITORY_ROOT, assigned_constant

SPELLINGS: tuple[tuple[Path, str], ...] = (
    (REPOSITORY_ROOT / "src" / "gramps_agent_data_entry" / "core" / "apply.py", "SENTINEL_NAME"),
    (REPOSITORY_ROOT / "src" / "gramps_agent_data_entry" / "host" / "document.py", "SENTINEL"),
    (PLUGIN_DIRECTORY / "AgentDataEntry_writer.py", "SENTINEL"),
)


def test_every_source_that_spells_the_sentinel_spells_it_the_same_way() -> None:
    """⛔ Three declarations of one value, pinned to each other."""
    found = {}
    for path, name in SPELLINGS:
        value = assigned_constant(path, name)
        # ⚠️ Asserted BEFORE the comparison, and it is load bearing: three
        # ``None``s compare equal, so a pin that only compared them would pass
        # by construction the day one of these constants moved or was renamed.
        assert isinstance(value, str) and value, (
            f"{path.relative_to(REPOSITORY_ROOT)} no longer declares {name} as a "
            "module-level string constant, so this pin cannot see it at all"
        )
        found[f"{path.relative_to(REPOSITORY_ROOT)}:{name}"] = value

    assert len(set(found.values())) == 1, (
        "the sentinel is spelled differently in different places, so one half of "
        f"the write path would call a tree blessed and the other half would not: {found}"
    )


def test_the_pin_covers_every_place_the_sentinel_is_declared() -> None:
    """⚠️ A pin over a hand-written list goes stale when a fourth spelling arrives.

    So the list above is checked against the tree: every module-level constant
    named ``SENTINEL`` or ``SENTINEL_NAME`` anywhere in the package or the plugin
    directory must be one this pin already compares.
    """
    declared = set()
    trees = (REPOSITORY_ROOT / "src", PLUGIN_DIRECTORY)
    for tree in trees:
        for path in sorted(tree.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for name in ("SENTINEL", "SENTINEL_NAME"):
                if assigned_constant(path, name) is not None:
                    declared.add((path, name))

    assert declared == set(SPELLINGS), (
        "the set of sources declaring the sentinel changed, so SPELLINGS above is "
        f"no longer the whole of it: {sorted((str(p), n) for p, n in declared)}"
    )
