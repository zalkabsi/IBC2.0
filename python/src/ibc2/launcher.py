"""Building and running the IBC command line, and killing it cleanly."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import paths
from .detect import Install, find_java

# default API ports of TWS / IB Gateway
DEFAULT_PORTS = {("gateway", "live"): 4001, ("gateway", "paper"): 4002,
                 ("tws", "live"): 7496, ("tws", "paper"): 7497}


def effective_port(settings: dict[str, Any]) -> int:
    g = settings["gateway"]
    if g["api_port"]:
        return int(g["api_port"])
    return DEFAULT_PORTS.get((g["app"], g["mode"]), 4002)


def build_command(settings: dict[str, Any], install: Install, config: Path,
                  ibc_dir: Path | None = None) -> list[str]:
    g = settings["gateway"]
    ibc_dir = ibc_dir or paths.bundled_ibc_dir()
    java = find_java(install)
    if os.name == "nt":
        cmd = [str(ibc_dir / "scripts" / "StartIBC.bat"), install.version]
        if install.app == "gateway":
            cmd.append("/G")
        cmd += [f"/TwsPath:{install.root}", f"/IbcPath:{ibc_dir}", f"/Config:{config}", f"/Mode:{g['mode']}"]
        if g["settings_path"]:
            cmd.append(f"/TwsSettingsPath:{g['settings_path']}")
        if java is not None:
            cmd.append(f"/JavaPath:{java.parent}")
        return cmd
    bash = shutil.which("bash") or "/bin/bash"
    cmd = [bash, str(ibc_dir / "scripts" / "ibcstart.sh"), install.version]
    if install.app == "gateway":
        cmd.append("--gateway")
    cmd += [f"--tws-path={install.root}", f"--ibc-path={ibc_dir}", f"--ibc-ini={config}", f"--mode={g['mode']}"]
    if g["settings_path"]:
        cmd.append(f"--tws-settings-path={g['settings_path']}")
    if java is not None:
        cmd.append(f"--java-path={java.parent}")
    return cmd


def popen(cmd: list[str]) -> subprocess.Popen:
    kwargs: dict[str, Any] = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  text=True, encoding="utf-8", errors="replace", bufsize=1)
    if os.name == "nt":
        # no console window for the .bat when ibc2 runs under pythonw (TWS/Gateway's own window still shows)
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)  # noqa: S603 - fixed argv, no shell


def kill_tree(proc: subprocess.Popen, *, grace: float = 10.0) -> None:
    """Terminate the launch script *and* the Java processes it started."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL,
                           capture_output=True, check=False)
        else:
            import signal

            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


def python_executable() -> str:
    return sys.executable
