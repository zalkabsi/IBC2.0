"""``ibc2 doctor``: check everything that commonly goes wrong, and say how to fix it."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from . import credentials, health, launcher, paths, reauth
from .detect import find_installs, find_java, pick_install

OK, WARN, FAIL = "ok", "warn", "FAIL"


@dataclass
class Check:
    status: str
    name: str
    detail: str


def run_checks(settings: dict[str, Any]) -> list[Check]:
    g = settings["gateway"]
    checks: list[Check] = []

    def add(status: str, name: str, detail: str) -> None:
        checks.append(Check(status, name, detail))

    add(OK if sys.version_info >= (3, 10) else FAIL, "Python", sys.version.split()[0])

    ibc_dir = paths.bundled_ibc_dir()
    jar = ibc_dir / "IBC.jar"
    scripts_ok = (ibc_dir / "scripts").is_dir()
    if jar.exists() and scripts_ok:
        add(OK, "IBC engine", f"{jar}")
    else:
        add(FAIL, "IBC engine", f"IBC.jar or scripts missing in {ibc_dir}. Reinstall: pip install --force-reinstall ibc2")

    roots = [__import__("pathlib").Path(g["tws_path"])] if g["tws_path"] else None
    installs = find_installs(roots)
    install = pick_install(installs, g["app"], g["version"])
    if install:
        add(OK, "TWS / Gateway", f"{install.app} {install.version} in {install.root}")
    elif pick_install(installs, "", g["version"]):
        other = pick_install(installs, "", g["version"])
        add(WARN, "TWS / Gateway",
            f"No {g['app']} found, but {other.app} {other.version} is installed. "
            f"Gateway is more reliable for unattended use; install the offline IB Gateway, "
            f"or run 'ibc2 setup --app {other.app}' to use what you have.")
        install = other
    else:
        add(FAIL, "TWS / Gateway",
            "No offline installation found. Install the OFFLINE (standalone) IB Gateway from Interactive "
            "Brokers - IBC does not work with the self-updating TWS. Searched: "
            + (", ".join(str(r) for r in (roots or [])) or "default locations"))

    java = find_java(install)
    add(OK if java else FAIL, "Java", str(java) if java else "No Java found (TWS/Gateway normally bundles one).")

    if settings["gateway"]["username"]:
        has = credentials.has_password(g["username"])
        add(OK if has else FAIL, "Credentials",
            f"user '{g['username']}', password stored" if has else "no password stored: run 'ibc2 setup'")
    else:
        add(FAIL, "Credentials", "no username configured: run 'ibc2 setup'")

    add(OK if paths.settings_file().exists() else WARN, "Settings file", str(paths.settings_file()))

    port = launcher.effective_port(settings)
    if health.api_handshake("127.0.0.1", port, timeout=2.0):
        add(OK, f"API port {port}", "answering (an API session is available)")
    elif health.port_open("127.0.0.1", port):
        add(WARN, f"API port {port}", "open but not answering the API handshake (still logging in, or frozen)")
    else:
        add(WARN, f"API port {port}", "closed (fine if Gateway is not running yet; enable the API in Gateway otherwise)")

    from .alerts import Alerter

    channels = Alerter(settings["alerts"]).channels()
    add(OK if channels else WARN, "Alerts",
        ", ".join(channels) if channels else "none configured: you will not be told when a 2FA approval is needed. "
                                            "Run 'ibc2 setup' or edit " + str(paths.settings_file()))

    restart = g["auto_restart_time"] or reauth.default_auto_restart_time()
    add(OK, "Nightly restart", f"{restart} local time"
        + ("" if g["auto_restart_time"] else " (01:30 New York time)"))
    add(OK, "Next forced weekly re-login", reauth.format_local(reauth.next_weekly_reauth()))
    return checks


def format_checks(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    return "\n".join(f"[{c.status:>4}] {c.name:<{width}}  {c.detail}" for c in checks)


def has_failures(checks: list[Check]) -> bool:
    return any(c.status == FAIL for c in checks)
