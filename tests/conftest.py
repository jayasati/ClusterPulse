"""Shared pytest fixtures for ClusterPulse tests."""

import pytest


@pytest.fixture
def buffer_path(tmp_path):
    """A throwaway path for a ``FileBuffer`` under test."""
    return tmp_path / "buffer.jsonl"
