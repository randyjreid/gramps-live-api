"""Where the copy's real path lives: a user directory, never the checkout.

⚠️ **This is a privacy rail as much as an ergonomic one.** The one value this
project cannot commit is where the owner's tree actually is, so the loader
resolves the **user configuration directory only**. A ``config.json`` sitting in
the working directory is not read -- which is what stops a real path being
picked up from inside a clone of a public repository, and it is asserted below
rather than left to the shape of the code.

Both platform layouts are exercised on whichever platform is running, by
passing the platform in. A branch that only its own operating system can reach
is a branch CI proves nothing about.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gramps_live_api import config


def written(directory: Path, settings: dict[str, object]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / config.CONFIG_FILE
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def test_the_windows_layout_is_under_the_roaming_profile(tmp_path: Path) -> None:
    where = config.user_config_path({"APPDATA": str(tmp_path)}, platform="win32")

    assert where == tmp_path / config.DIRECTORY_NAME / config.CONFIG_FILE


def test_the_other_layout_follows_the_freedesktop_variable(tmp_path: Path) -> None:
    where = config.user_config_path({"XDG_CONFIG_HOME": str(tmp_path)}, platform="linux")

    assert where == tmp_path / config.DIRECTORY_NAME / config.CONFIG_FILE


def test_the_other_layout_falls_back_to_the_documented_default(tmp_path: Path) -> None:
    where = config.user_config_path({"HOME": str(tmp_path)}, platform="linux")

    assert where == tmp_path / ".config" / config.DIRECTORY_NAME / config.CONFIG_FILE


def test_the_file_supplies_the_copy_when_nothing_overrides_it(tmp_path: Path) -> None:
    written(tmp_path / config.DIRECTORY_NAME, {"copy_path": "a-copy-directory"})

    settings = config.load({"APPDATA": str(tmp_path)}, platform="win32")

    assert settings.copy_path == "a-copy-directory"


def test_the_environment_overrides_the_file(tmp_path: Path) -> None:
    # The override exists so a run can be pointed somewhere else without
    # editing a file -- which is what the integration test needs, and what the
    # owner needs the first time he tries a second copy.
    written(tmp_path / config.DIRECTORY_NAME, {"copy_path": "from-the-file"})

    settings = config.load(
        {"APPDATA": str(tmp_path), config.ENV_COPY: "from-the-environment"}, platform="win32"
    )

    assert settings.copy_path == "from-the-environment"


def test_a_missing_file_is_no_configuration_rather_than_a_failure(tmp_path: Path) -> None:
    settings = config.load({"APPDATA": str(tmp_path)}, platform="win32")

    assert settings.copy_path is None
    assert settings.runtime is None


def test_a_configuration_file_in_the_working_directory_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rail: a real path can never be picked up from inside a checkout.

    A loader that also looked beside the current directory would make a
    ``config.json`` committed by accident into a working configuration -- in a
    public repository whose whole previous phase exists to keep exactly that
    out.
    """
    here = tmp_path / "checkout"
    here.mkdir()
    (here / config.CONFIG_FILE).write_text(
        json.dumps({"copy_path": "from-the-checkout"}), encoding="utf-8"
    )
    monkeypatch.chdir(here)

    settings = config.load({"APPDATA": str(tmp_path / "roaming")}, platform="win32")

    assert settings.copy_path is None, (
        "a config.json beside the current directory was read, so a file "
        "committed by accident becomes live configuration in a public checkout"
    )


def test_a_file_that_is_not_readable_json_is_refused(tmp_path: Path) -> None:
    # Fail closed. Ignoring it would run against whatever the default is while
    # the owner believes the file he edited is in force.
    directory = tmp_path / config.DIRECTORY_NAME
    directory.mkdir()
    (directory / config.CONFIG_FILE).write_text("{not json", encoding="utf-8")

    with pytest.raises(config.ConfigError):
        config.load({"APPDATA": str(tmp_path)}, platform="win32")


def test_a_key_nobody_declared_is_refused_rather_than_dropped(tmp_path: Path) -> None:
    # The same reading ``schema.from_dict`` takes of an unknown field: a
    # misspelled key silently ignored means the configuration in force is not
    # the one that was written, and nothing anywhere says so.
    written(tmp_path / config.DIRECTORY_NAME, {"copy-path": "a-copy-directory"})

    with pytest.raises(config.ConfigError) as refusal:
        config.load({"APPDATA": str(tmp_path)}, platform="win32")

    assert "copy-path" in str(refusal.value)


def test_a_value_that_is_not_a_string_is_refused(tmp_path: Path) -> None:
    written(tmp_path / config.DIRECTORY_NAME, {"copy_path": 7})

    with pytest.raises(config.ConfigError):
        config.load({"APPDATA": str(tmp_path)}, platform="win32")


def installed(root: Path, version: str) -> Path:
    install = root / f"GrampsAIO64-{version}"
    install.mkdir(parents=True)
    (install / config.RUNTIME_NAME).write_text("", encoding="utf-8")
    return install


def test_the_runtime_is_discovered_when_exactly_one_is_installed(tmp_path: Path) -> None:
    install = installed(tmp_path, "6.0.8")

    found = config.discover_runtime({"ProgramFiles": str(tmp_path)}, platform="win32")

    assert found == str(install / config.RUNTIME_NAME)


def test_two_installations_are_refused_rather_than_guessed_between(tmp_path: Path) -> None:
    """Fail closed, because the alternative is a version comparison.

    ⚠️ **A plain sort would pick 6.0.9 over 6.0.11**, because "9" sorts after
    "1". The repair is a version comparison, which is a thing this project would
    then own and get wrong on the first four-part or pre-release version it met.
    Refusing costs the owner one line in a configuration file, once, and it is
    the only answer that cannot silently write a tree with the wrong Gramps.
    """
    installed(tmp_path, "6.0.9")
    installed(tmp_path, "6.0.11")

    with pytest.raises(config.ConfigError) as refusal:
        config.discover_runtime({"ProgramFiles": str(tmp_path)}, platform="win32")

    assert config.CONFIG_FILE in str(refusal.value), (
        "a refusal that does not say how to resolve it is a dead end; the owner "
        f"needs to be told to name one, got {refusal.value}"
    )


def test_discovery_finding_nothing_is_not_an_error(tmp_path: Path) -> None:
    # Nothing found is a question for the caller -- `check` reports it as a
    # missing runtime, which reads better than a traceback at a terminal.
    assert config.discover_runtime({"ProgramFiles": str(tmp_path)}, platform="win32") is None


def test_discovery_says_nothing_off_the_platform_it_knows(tmp_path: Path) -> None:
    # The AIO layout is a Windows fact. Elsewhere Gramps is installed a dozen
    # ways, and a guess would be a guess -- so the configuration key answers it.
    installed(tmp_path, "6.0.8")

    assert config.discover_runtime({"ProgramFiles": str(tmp_path)}, platform="linux") is None


def test_a_named_runtime_is_never_second_guessed(tmp_path: Path) -> None:
    settings = config.load(
        {"APPDATA": str(tmp_path), config.ENV_RUNTIME: "a-named-runtime"}, platform="win32"
    )

    assert settings.runtime == "a-named-runtime"
