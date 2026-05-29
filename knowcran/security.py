"""Security path validation for KnowCran."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_allowed_path(requested: str | None, default_name: str, env_var: str) -> Path:
    """Resolve and validate requested path against a whitelist boundary.

    Prevents traversal attacks ('..'), absolute path overrides, and symlink escapes
    by resolving all paths absolutely and verifying they lie within the allowed root.
    """
    env_val = os.getenv(env_var)
    if env_val:
        allowed_root = Path(env_val).resolve()
    else:
        # Default to relative path in the current working directory, resolved absolutely
        allowed_root = Path(default_name).resolve()

    if requested is None:
        return allowed_root

    requested_path = Path(requested).resolve()

    try:
        # is_relative_to requires Python 3.9+
        if not requested_path.is_relative_to(allowed_root):
            raise ValueError(
                f"Security Error: Path '{requested}' (resolved to '{requested_path}') "
                f"is outside the allowed directory boundary '{allowed_root}'"
            )
    except ValueError as e:
        # If is_relative_to raises ValueError (e.g. different drives on Windows), raise our own security error
        raise ValueError(
            f"Security Error: Path '{requested}' (resolved to '{requested_path}') "
            f"is outside the allowed directory boundary '{allowed_root}'"
        ) from e

    return requested_path


def resolve_allowed_data_dir(data_dir: str | None) -> Path:
    """Resolve and validate the data directory path."""
    return resolve_allowed_path(data_dir, "data", "KNOWCRAN_DATA_DIR")


def resolve_allowed_vault_dir(vault_dir: str | None) -> Path:
    """Resolve and validate the vault directory path."""
    return resolve_allowed_path(vault_dir, "vault", "KNOWCRAN_VAULT_DIR")
