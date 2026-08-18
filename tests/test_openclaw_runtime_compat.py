from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

import pytest


def test_sitecustomize_restores_legacy_cmdop_timeout_alias() -> None:
    try:
        openclaw = import_module("openclaw")
    except ModuleNotFoundError:
        pytest.skip("openclaw package not installed")

    if not getattr(openclaw, "_CMDOP_AVAILABLE", False):
        pytest.skip("cmdop not installed")

    exceptions = import_module("cmdop.exceptions")

    assert hasattr(exceptions, "TimeoutError")
    assert exceptions.TimeoutError is exceptions.ConnectionTimeoutError


def test_openclaw_imports_with_compatible_cmdop_line() -> None:
    try:
        openclaw = import_module("openclaw")
    except ModuleNotFoundError:
        pytest.skip("openclaw package not installed")

    if not getattr(openclaw, "_CMDOP_AVAILABLE", False):
        pytest.skip("cmdop not installed")

    assert getattr(openclaw, "__version__", "")
    try:
        assert version("cmdop").startswith("2026.3.")
    except PackageNotFoundError:
        pytest.skip("cmdop package not found")
