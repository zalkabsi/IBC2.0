"""Storage of the IBKR password in the operating system's keyring."""

from __future__ import annotations

import os

SERVICE = "ibc2"


class CredentialError(RuntimeError):
    pass


def get_password(username: str) -> str:
    """Password from ``IBC2_PASSWORD`` / ``IBC2_PASSWORD_FILE`` (containers, CI) or the OS keyring."""
    env = os.environ.get("IBC2_PASSWORD")
    if env:
        return env
    file_path = os.environ.get("IBC2_PASSWORD_FILE")  # Docker / Kubernetes secrets
    if file_path:
        try:
            with open(file_path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            raise CredentialError(f"cannot read IBC2_PASSWORD_FILE: {e}") from e
    try:
        import keyring

        value = keyring.get_password(SERVICE, username)
    except Exception as e:  # no usable keyring backend (e.g. headless Linux)
        raise CredentialError(
            f"no usable OS keyring ({e}). Set IBC2_PASSWORD or IBC2_PASSWORD_FILE instead."
        ) from e
    if not value:
        raise CredentialError(f"no password stored for '{username}'. Run: ibc2 setup")
    return value


def set_password(username: str, password: str) -> None:
    try:
        import keyring

        keyring.set_password(SERVICE, username, password)
    except Exception as e:
        raise CredentialError(f"could not store the password in the OS keyring: {e}") from e


def has_password(username: str) -> bool:
    try:
        return bool(get_password(username))
    except CredentialError:
        return False
