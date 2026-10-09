from datetime import UTC, datetime

import pytest

from tools.sim import access

FIXED_NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
def fixed_clock(monkeypatch):
    """Freeze the simulator clock and make the default scenario explicit."""
    monkeypatch.setattr(access, "clock", lambda: FIXED_NOW)
    monkeypatch.setenv("SIM_SCENARIO_ID", "healthy")
    return FIXED_NOW
