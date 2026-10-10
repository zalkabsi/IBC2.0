"""Where ibc2 keeps its files.

Everything lives under one directory (``~/.ibc2`` unless ``IBC2_HOME`` is set)
so that it is easy to find, back up, or mount into a container.
"""

from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    base = os.environ.get("IBC2_HOME")
    path = Path(base).expanduser() if base else Path.home() / ".ibc2"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return home() / "ibc2.toml"


def runtime_dir() -> Path:
    d = home() / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def runtime_config() -> Path:
    """The generated IBC config.ini (may contain the password; kept private)."""
    return runtime_dir() / "config.ini"


def events_file() -> Path:
    return runtime_dir() / "events.jsonl"


def state_file() -> Path:
    return runtime_dir() / "state.json"


def pid_file() -> Path:
    return runtime_dir() / "supervisor.pid"


def stop_flag() -> Path:
    return runtime_dir() / "stop.flag"


def dialog_rules_file() -> Path:
    return home() / "dialogrules.txt"


def logs_dir() -> Path:
    d = home() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundled_ibc_dir() -> Path:
    """Directory holding IBC.jar and the launch scripts shipped in the wheel."""
    override = os.environ.get("IBC2_IBC_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "_ibc"


def restrict_to_owner(path: Path) -> None:
    """Make a file readable only by the current user (best effort)."""
    try:
        if os.name == "nt":
            import subprocess

            user = os.environ.get("USERNAME", "")
            if user:
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                    capture_output=True,
                    check=False,
                )
        else:
            os.chmod(path, 0o600)
    except OSError:
        pass
