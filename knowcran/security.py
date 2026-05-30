"""Path boundary validation for local MCP access."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_allowed_path(requested: str | None, default_name: str, env_var: str) -> Path:
    """Resolve a requested path and ensure it stays under the configured root."""
    env_value = os.getenv(env_var)
    allowed_root = Path(env_value or default_name).resolve()
    if requested is None:
        return allowed_root

    requested_path = Path(requested).resolve()
    try:
        is_allowed = requested_path == allowed_root or requested_path.is_relative_to(allowed_root)
    except ValueError:
        is_allowed = False
    if not is_allowed:
        raise ValueError(
            f"Security Error: path '{requested}' resolves to '{requested_path}', "
            f"outside allowed root '{allowed_root}'"
        )
    return requested_path


def resolve_allowed_data_dir(data_dir: str | None) -> Path:
    """Resolve and validate a data directory."""
    return resolve_allowed_path(data_dir, "data", "KNOWCRAN_DATA_DIR")


def resolve_allowed_vault_dir(vault_dir: str | None) -> Path:
    """Resolve and validate a vault directory."""
    return resolve_allowed_path(vault_dir, "vault", "KNOWCRAN_VAULT_DIR")
