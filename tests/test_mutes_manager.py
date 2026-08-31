"""Unit tests for MutesManager and dynamic noise suppression."""

import os
import pytest
from src.services.mutes_manager import MutesManager


@pytest.fixture
def temp_mutes_manager(tmp_path):
    test_file = str(tmp_path / "test_mutes.json")
    return MutesManager(persistence_file=test_file)


def test_mute_and_is_muted(temp_mutes_manager):
    mgr = temp_mutes_manager

    # Mute WordPress
    mgr.mute("wordpress", duration_minutes=60, reason="Test sourdine")

    assert mgr.is_muted("association-nonvitcha-wordpress-4dlu8o") is True
    assert mgr.is_muted("savanes-du-continent-wordpress") is True
    assert mgr.is_muted("bestlens-app") is False


def test_unmute(temp_mutes_manager):
    mgr = temp_mutes_manager

    mgr.mute("bestlens-app", duration_minutes=120)
    assert mgr.is_muted("bestlens-app") is True

    # Lever la sourdine
    unmuted = mgr.unmute("bestlens-app")
    assert unmuted is True
    assert mgr.is_muted("bestlens-app") is False


def test_mute_wildcard_all(temp_mutes_manager):
    mgr = temp_mutes_manager

    mgr.mute("all", duration_minutes=30)
    assert mgr.is_muted("any-container-name") is True
    assert mgr.is_muted("wordpress-1") is True


def test_mutes_persistence(tmp_path):
    test_file = str(tmp_path / "persist_mutes.json")
    mgr1 = MutesManager(persistence_file=test_file)
    mgr1.mute("kanbio24", duration_minutes=120, reason="Test persistence")

    # Nouveau gestionnaire lisant le même fichier
    mgr2 = MutesManager(persistence_file=test_file)
    assert mgr2.is_muted("kanbio24-wordpress-rwxkae") is True
    assert len(mgr2.get_active_mutes()) == 1
