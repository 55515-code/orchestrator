"""Workspace-local OpenClaw compatibility shim.

This shadows the broken third-party wheel when running from this repo and
restores the legacy exception export that newer CMDOP releases removed.
"""

from __future__ import annotations

try:
    from cmdop import AsyncCMDOPClient, CMDOPClient
    from cmdop import exceptions as _cmdop_exceptions

    CMDOPError = _cmdop_exceptions.CMDOPError
    ConnectionError = _cmdop_exceptions.ConnectionError
    AuthenticationError = _cmdop_exceptions.AuthenticationError
    TimeoutError = getattr(
        _cmdop_exceptions,
        "TimeoutError",
        _cmdop_exceptions.ConnectionTimeoutError,
    )

    if not hasattr(_cmdop_exceptions, "TimeoutError"):
        _cmdop_exceptions.TimeoutError = TimeoutError

    _CMDOP_AVAILABLE = True
except ImportError:
    # cmdop is not installed — provide stub classes for compatibility
    _CMDOP_AVAILABLE = False
    
    class CMDOPClient:
        """Stub client when cmdop is not available."""
        pass
    
    class AsyncCMDOPClient:
        """Stub async client when cmdop is not available."""
        pass
    
    CMDOPError = Exception
    ConnectionError = Exception
    AuthenticationError = Exception
    TimeoutError = Exception

__version__ = "2026.3.20"
__all__ = [
    "OpenClaw",
    "AsyncOpenClaw",
    "CMDOPClient",
    "AsyncCMDOPClient",
    "CMDOPError",
    "ConnectionError",
    "AuthenticationError",
    "TimeoutError",
]


class OpenClaw(CMDOPClient):
    """Compatibility wrapper around CMDOPClient."""


class AsyncOpenClaw(AsyncCMDOPClient):
    """Compatibility wrapper around AsyncCMDOPClient."""
