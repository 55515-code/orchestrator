from __future__ import annotations

# Backward-compatible aliases for the legacy "dotfiles" naming.
# New code should import from substrate.config_sync.
from .config_sync import (  # noqa: F401
    CONFIG_SYNC_TARGET_ENVS as DOTFILE_TARGET_ENVS,
    backup_config_sync as backup_dotfiles,
    config_sync_payload as dotfiles_payload,
    deploy_config_sync as deploy_dotfiles,
    discover_dotfiles,
    plan_config_sync as plan_dotfiles,
    scan_config_sync as scan_dotfiles,
)
