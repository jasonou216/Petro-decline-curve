"""Smoke test confirming the src package imports and pytest is wired up correctly."""

from petro_decline import data, decline, eur, economics  # noqa: F401


def test_imports():
    assert True
