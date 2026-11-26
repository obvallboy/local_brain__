"""Tests for pibench — profile loading, rendering, and the safety gating.

Everything runs in --dry-run, so no hardware, flashrom, or Pi is needed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pibench  # noqa: E402

ALL_PROFILES = pibench.list_profiles()


def test_profiles_exist():
    assert {"spi-bios", "i2c-eeprom", "uart-console"} <= set(ALL_PROFILES)


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_every_profile_loads_and_has_actions(name):
    prof = pibench.load_profile(name)
    assert prof["title"]
    assert prof["actions"], "a profile needs at least one action"
    for key, act in prof["actions"].items():
        assert pibench.action_commands(prof, key), f"{name}:{key} has no commands"


@pytest.mark.parametrize("name", ALL_PROFILES)
def test_commands_fully_render_with_defaults(name):
    """No {token} may survive rendering with the profile's default vars."""
    prof = pibench.load_profile(name)
    vars_ = pibench.resolve_vars(prof, [])
    for key in prof["actions"]:
        for cmd in pibench.action_commands(prof, key):
            rendered = pibench.render(cmd, vars_)
            assert "{" not in rendered and "}" not in rendered, f"unrendered token in {name}:{key}: {rendered}"


def test_list_shows_titles(capsys):
    assert pibench.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "spi-bios" in out and "SPI NOR flash" in out


def test_show_includes_wiring_and_actions(capsys):
    assert pibench.main(["show", "spi-bios"]) == 0
    out = capsys.readouterr().out
    assert "Wiring" in out and "CS#" in out and "MISO" in out
    assert "read" in out and "write" in out


def test_dry_run_prints_commands_runs_nothing(capsys):
    rc = pibench.main(["run", "spi-bios", "read", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "flashrom -p linux_spi:dev=/dev/spidev0.0" in out
    assert "dry-run" in out


def test_set_overrides_a_variable(capsys):
    pibench.main(["run", "spi-bios", "read", "--dry-run", "--set", "image=aw15r2.bin", "--set", "spispeed=256"])
    out = capsys.readouterr().out
    assert "aw15r2.bin" in out and "spispeed=256" in out
    assert "bios.bin" not in out


def test_destructive_action_refuses_without_yes(capsys):
    # Not dry-run and no --yes → must refuse and run nothing (exit 2).
    rc = pibench.main(["run", "spi-bios", "write", "--set", "image=x.bin"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "DESTRUCTIVE" in out and "--yes" in out


def test_destructive_action_dry_run_is_allowed(capsys):
    rc = pibench.main(["run", "spi-bios", "write", "--dry-run"])
    assert rc == 0
    assert "flashrom" in capsys.readouterr().out


def test_unknown_profile_errors(capsys):
    assert pibench.main(["show", "nope"]) == 1
    assert "no profile" in capsys.readouterr().err


def test_unknown_action_errors(capsys):
    assert pibench.main(["run", "spi-bios", "frobnicate", "--dry-run"]) == 1
    assert "no action" in capsys.readouterr().err
