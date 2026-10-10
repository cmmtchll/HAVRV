"""Test fixtures for HAVRV."""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: Generator[None],
) -> Generator[None]:
    """Enable custom integrations for each test."""
    yield
