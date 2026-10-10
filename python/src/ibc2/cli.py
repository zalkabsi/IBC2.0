"""Command line interface: ``ibc2 <command>``."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__, credentials, doctor, health, launcher, paths, reauth, service, settings as settings_mod
from .alerts import Alerter
from .detect import find_installs, pick_install


# ---- helpers ---------------------------------------------------------------------------------------
def _ask(prompt: str, default: str = "", *, interactive: bool = True) -> str:
    if not interactive:
        return default
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                             check=False).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _supervisor_pid() -> int | None:
    try:
        pid = int(paths.pid_file().read_text().strip())
    except (OSError, ValueError):
        return None
    # A pid file can outlive its process (crash, docker kill, reboot) and the number can then be reused
    # by something unrelated. A live supervisor refreshes its state file every few seconds.
    try:
        newest = max(paths.state_file().stat().st_mtime if paths.state_file().exists() else 0,
                     paths.pid_file().stat().st_mtime)
    except OSError:
        return None
    if time.time() - newest > 120:
        return None
    return pid if _pid_alive(pid) else None


def _read_state() -> dict[str, Any]:
    try:
        return json.loads(paths.state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---- commands --------------------------------------------------------------------------------------
def cmd_setup(args: argparse.Namespace) -> int:
    interactive = not args.non_interactive
    s = settings_mod.load()
    g, a = s["gateway"], s["alerts"]

    installs = find_installs()
    if installs:
        print("Found: " + ", ".join(f"{i.app} {i.version}" for i in installs))
    else:
        print("No offline TWS / IB Gateway installation found.\n"
              "Install the OFFLINE (standalone) IB Gateway from Interactive Brokers first "
              "(Gateway is best for always-on use), then re-run 'ibc2 setup'.")
    wanted = args.app or g["app"]
    if not args.app and installs and not pick_install(installs, wanted):
        wanted = installs[0].app
        print(f"No {g['app']} found; using {wanted}.")
    g["app"] = _ask("Application (gateway/tws)", wanted, interactive=interactive and not args.app)
    install = pick_install(installs, g["app"])
    if install:
        g["version"], g["tws_path"] = install.version, str(install.root)

    g["mode"] = args.mode or _ask("Trading mode (paper/live)", g["mode"], interactive=interactive)
    if g["mode"] not in ("paper", "live"):
        print("Mode must be 'paper' or 'live'.", file=sys.stderr)
        return 2
    if g["mode"] == "live" and interactive and not args.mode:
        if _ask("LIVE mode places real orders. Type 'live' to confirm", "", interactive=True) != "live":
            g["mode"] = "paper"
            print("Staying in paper mode.")
    g["username"] = args.username or _ask("IBKR username", g["username"], interactive=interactive)
    if not g["username"]:
        print("A username is required.", file=sys.stderr)
        return 2

    password = None
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    elif interactive and (not credentials.has_password(g["username"]) or
                          _ask("A password is already stored. Replace it? (y/N)", "n").lower().startswith("y")):
        password = getpass.getpass("IBKR password (stored in your OS keyring, not shown): ")
    if password:
        try:
            credentials.set_password(g["username"], password)
            print("Password saved to the OS keyring.")
        except credentials.CredentialError as e:
            print(f"warning: {e}", file=sys.stderr)

    if interactive and not Alerter(a).channels():
        choice = _ask("Alerts for 2FA / problems: telegram, discord, email, webhook or skip", "skip").lower()
        if choice == "telegram":
            a["telegram_token"] = _ask("Telegram bot token (from @BotFather)")
            a["telegram_chat_id"] = _ask("Telegram chat id")
        elif choice == "discord":
            a["discord_webhook"] = _ask("Discord webhook URL")
        elif choice == "webhook":
            a["webhook_url"] = _ask("Webhook URL (receives JSON)")
        elif choice == "email":
            a["email_to"] = _ask("Send alerts to")
            a["smtp_host"] = _ask("SMTP host", "smtp.gmail.com")
            a["smtp_port"] = int(_ask("SMTP port", "587"))
            a["smtp_user"] = _ask("SMTP user name", a["email_to"])
            a["smtp_password"] = getpass.getpass("SMTP password / app password: ")
            a["email_from"] = _ask("From address", a["smtp_user"])

    settings_mod.save(s)
    print(f"\nSettings saved to {paths.settings_file()}\n")
    checks = doctor.run_checks(settings_mod.load())
    print(doctor.format_checks(checks))
    print("\nNext: 'ibc2 start' to run in the background, 'ibc2 install-service' to start at every login.")
    return 1 if doctor.has_failures(checks) else 0


def cmd_doctor(_: argparse.Namespace) -> int:
    checks = doctor.run_checks(settings_mod.load())
    print(doctor.format_checks(checks))
    return 1 if doctor.has_failures(checks) else 0


def _prepare_logging(force: bool) -> None:
    """Send our own messages to a file when there is no console to show them (pythonw, a detached
    process, a scheduled task). Under Docker or systemd stderr is already collected, so leave it alone."""
    if force or sys.stderr is None:
        log = open(paths.logs_dir() / "ibc2.log", "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout = log


def cmd_run(args: argparse.Namespace) -> int:
    from .supervisor import Supervisor

    _prepare_logging(args.log_file)
    if _supervisor_pid() not in (None, os.getpid()):
        print("ibc2 is already running (see 'ibc2 status').", file=sys.stderr)
        return 1
    s = settings_mod.load()
    return Supervisor(s, Alerter(s["alerts"])).run()


def cmd_start(_: argparse.Namespace) -> int:
    if _supervisor_pid():
        print("ibc2 is already running. See 'ibc2 status'.")
        return 0
    checks = doctor.run_checks(settings_mod.load())
    if doctor.has_failures(checks):
        print(doctor.format_checks(checks))
        print("\nFix the FAIL items above (try 'ibc2 setup'), then start again.", file=sys.stderr)
        return 1
    kwargs: dict[str, Any] = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([launcher.python_executable(), "-m", "ibc2", "run", "--log-file"], **kwargs)  # noqa: S603
    for _i in range(20):
        time.sleep(0.5)
        if _supervisor_pid():
            print("ibc2 started in the background. 'ibc2 status' shows progress; 'ibc2 logs -f' follows the log.")
            return 0
    print("ibc2 did not start; see " + str(paths.logs_dir() / "ibc2.log"), file=sys.stderr)
    return 1


def cmd_stop(_: argparse.Namespace) -> int:
    pid = _supervisor_pid()
    if pid is None:
        print("ibc2 is not running.")
        return 0
    paths.stop_flag().write_text("stop")
    print("Stopping (Gateway is closed cleanly; this can take up to 40 seconds)...")
    for _i in range(90):
        if not _pid_alive(pid):
            print("Stopped.")
            return 0
        time.sleep(0.5)
    print("Supervisor did not exit in time; terminating it.", file=sys.stderr)
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False)
    else:
        os.kill(pid, 15)
    return 1


def cmd_restart(_: argparse.Namespace) -> int:
    """Ask IBC to restart Gateway/TWS in place (no new 2FA needed, unlike stop + start)."""
    s = settings_mod.load()
    port = s["supervisor"]["command_port"]
    if not port or _supervisor_pid() is None:
        print("ibc2 is not running (or the command port is disabled).", file=sys.stderr)
        return 1
    try:
        print(health.send_command(port, "RESTART") or "Restart requested.")
    except OSError as e:
        print(f"Could not reach IBC's command server on port {port}: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    s = settings_mod.load()
    pid = _supervisor_pid()
    st = _read_state()
    port = launcher.effective_port(s)
    api = health.api_handshake("127.0.0.1", port, timeout=3.0)
    nxt = reauth.next_weekly_reauth()
    info = {
        "supervisor": "running" if pid else "not running",
        "phase": st.get("phase", "unknown") if pid else "stopped",
        "api_port": port,
        "api_responding": api,
        "last_event": st.get("last_event", ""),
        "next_weekly_reauth": reauth.format_local(nxt),
        "alert_channels": Alerter(s["alerts"]).channels(),
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        for k, v in info.items():
            print(f"{k.replace('_', ' '):<20} {v}")
    return 0 if (pid and api) else 1


def cmd_logs(args: argparse.Namespace) -> int:
    files = sorted(paths.logs_dir().glob("ibc-*.log"))
    if not files:
        print("No logs yet.")
        return 0
    latest = files[-1]
    lines = latest.read_text(encoding="utf-8", errors="replace").splitlines()[-args.lines:]
    print("\n".join(lines))
    if args.follow:
        with open(latest, encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            try:
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                pass
    return 0


def cmd_install_service(_: argparse.Namespace) -> int:
    try:
        print(service.install())
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def cmd_uninstall_service(_: argparse.Namespace) -> int:
    print(service.uninstall())
    return 0


def cmd_test_alert(_: argparse.Namespace) -> int:
    s = settings_mod.load()
    alerter = Alerter(s["alerts"])
    if not alerter.channels():
        print("No alert channel is configured. Run 'ibc2 setup' or edit " + str(paths.settings_file()))
        return 1
    alerter.send("ibc2 test alert", "If you can read this, alerts work.", level="info")
    return 0


def cmd_paths(_: argparse.Namespace) -> int:
    print(f"home      {paths.home()}\nsettings  {paths.settings_file()}\nlogs      {paths.logs_dir()}\n"
          f"rules     {paths.dialog_rules_file()}\nibc       {paths.bundled_ibc_dir()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ibc2", description="Keep Interactive Brokers TWS / IB Gateway logged in, always on.")
    p.add_argument("--version", action="version", version=f"ibc2 {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("setup", help="guided first-time setup")
    sp.add_argument("--app", choices=["gateway", "tws"])
    sp.add_argument("--mode", choices=["paper", "live"])
    sp.add_argument("--username")
    sp.add_argument("--password-stdin", action="store_true", help="read the password from stdin (for scripts)")
    sp.add_argument("--non-interactive", action="store_true")
    sp.set_defaults(func=cmd_setup)

    for name, func, helptext in [
        ("doctor", cmd_doctor, "check your installation and explain any problem"),
        ("start", cmd_start, "run the supervisor in the background"),
        ("stop", cmd_stop, "stop the supervisor and close Gateway/TWS cleanly"),
        ("restart", cmd_restart, "restart Gateway/TWS in place (keeps the session, no new 2FA)"),
        ("install-service", cmd_install_service, "start ibc2 automatically at login / boot"),
        ("uninstall-service", cmd_uninstall_service, "remove the automatic start"),
        ("test-alert", cmd_test_alert, "send a test alert to your configured channels"),
        ("paths", cmd_paths, "show where ibc2 keeps its files"),
    ]:
        sub.add_parser(name, help=helptext).set_defaults(func=func)

    rn = sub.add_parser("run", help="run the supervisor in the foreground")
    rn.add_argument("--log-file", action="store_true", help="write ibc2's own messages to logs/ibc2.log")
    rn.set_defaults(func=cmd_run)

    st = sub.add_parser("status", help="show whether everything is running")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    lg = sub.add_parser("logs", help="show the latest IBC log")
    lg.add_argument("-n", "--lines", type=int, default=50)
    lg.add_argument("-f", "--follow", action="store_true")
    lg.set_defaults(func=cmd_logs)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
