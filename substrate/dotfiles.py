from __future__ import annotations

# Backward-compatible aliases for the legacy "dotfiles" naming.
# New code should import from substrate.config_sync.
from .config_sync import (  # noqa: F401
    CONFIG_SYNC_TARGET_ENVS as DOTFILE_TARGET_ENVS,
)
