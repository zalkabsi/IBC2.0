"""The watchdog: starts IBC, reads its events, checks the API, restarts and alerts."""

from __future__ import annotations

import json
import os
import signal
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import config as config_mod
from . import credentials, health, launcher, paths, reauth
from .alerts import Alerter
from .detect import Install, find_installs, pick_install

EXIT_2FA_TIMEOUT = 1111
EXIT_LOGIN_DIALOG_TIMEOUT = 1112

STARTING, WAITING_2FA, RUNNING, BACKOFF, STOPPED = "starting", "waiting_2fa", "running", "backoff", "stopped"


class EventTail:
    """Yields new JSON-lines events appended to a file since the last poll."""

    def __init__(self, path: Path):
        self.path = path
        self._pos = path.stat().st_size if path.exists() else 0
        self._partial = ""

    def poll(self) -> list[dict[str, Any]]:
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self._pos:  # truncated or replaced
            self._pos, self._partial = 0, ""
        if size == self._pos:
            return []
        with open(self.path, "rb") as f:
            f.seek(self._pos)
            chunk = f.read()
        self._pos += len(chunk)
        text = self._partial + chunk.decode("utf-8", errors="replace")
        *lines, self._partial = text.split("\n")
        events = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events


class LogPump(threading.Thread):
    """Copies IBC's output to a daily log file and remembers the last lines."""

    def __init__(self, stream, logs_dir: Path):
        super().__init__(daemon=True, name="ibc2-logpump")
        self.stream = stream
        self.logs_dir = logs_dir
        self.tail: deque[str] = deque(maxlen=40)

    def run(self) -> None:
        current, fh = None, None
        try:
            for line in self.stream:
                day = time.strftime("%Y%m%d")
                if day != current:
                    if fh:
                        fh.close()
                    fh = open(self.logs_dir / f"ibc-{day}.log", "a", encoding="utf-8")
                    current = day
                fh.write(line)
                fh.flush()
                self.tail.append(line.rstrip())
        except (OSError, ValueError):
            pass
        finally:
            if fh:
                fh.close()


def prune_logs(logs_dir: Path, keep_days: int = 30) -> None:
    cutoff = time.time() - keep_days * 86400
    for p in logs_dir.glob("ibc-*.log"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


class Supervisor:
    def __init__(self, settings: dict[str, Any], alerter: Alerter, *,
                 now: Callable[[], float] = time.monotonic,
                 wall: Callable[[], datetime] = lambda: datetime.now().astimezone(),
                 sleep: Callable[[float], None] = time.sleep,
                 handshake: Callable[[str, int], bool] = health.api_handshake):
        self.settings = settings
        self.alerter = alerter
        self._now, self._wall, self._sleep, self._handshake = now, wall, sleep, handshake
        self.sup = settings["supervisor"]
        self.phase = STOPPED
        self.stop_requested = False
        self.proc = None
        self.pump: LogPump | None = None
        self.tail: EventTail | None = None
        self.last_event = ""
        self._phase_since = now()
        self._last_ok = now()
        self._last_check = 0.0
        self._problem_alerted = False
        self._unhealthy_alerted = False
        self._login_alerted = False
        self._reminded_for: datetime | None = None
        self._consecutive_failures = 0
        self._killed_unhealthy = False
        self.port = launcher.effective_port(settings)

    # ---- state ---------------------------------------------------------------------------------
    def _set_phase(self, phase: str) -> None:
        if phase != self.phase:
            self.phase = phase
            self._phase_since = self._now()
        self.write_state()

    def write_state(self) -> None:
        nxt = reauth.next_weekly_reauth()
        data = {
            "phase": self.phase,
            "supervisor_pid": os.getpid(),
            "ibc_pid": self.proc.pid if self.proc and self.proc.poll() is None else None,
            "in_phase_seconds": int(self._now() - self._phase_since),
            "seconds_since_api_ok": int(self._now() - self._last_ok) if self.phase == RUNNING else None,
            "last_event": self.last_event,
            "api_port": self.port,
            "next_weekly_reauth": nxt.isoformat(),
            "updated": datetime.now().astimezone().isoformat(),
        }
        try:
            paths.state_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ---- events --------------------------------------------------------------------------------
    def handle_event(self, ev: dict[str, Any]) -> None:
        kind, detail = ev.get("type", ""), ev.get("detail", "")
        self.last_event = f"{kind}: {detail}"[:300]
        if kind == "TWO_FA_REQUIRED":
            self._set_phase(WAITING_2FA)
            self.alerter.send("Approve the IBKR login now",
                              "Interactive Brokers is waiting for your second-factor approval. "
                              "Open the IBKR Mobile app and approve the login request.",
                              level="action", key="2fa")
        elif kind == "LOGGED_IN":
            if self._problem_alerted:
                self.alerter.send("IBKR session recovered", "Login completed; the session is running again.",
                                  level="info")
            self._problem_alerted = self._unhealthy_alerted = self._login_alerted = False
            self._last_ok = self._now()
            self._set_phase(RUNNING)
        elif kind == "LOGIN_FAILED":
            self._problem_alerted = True
            self.alerter.send("IBKR login failed", detail[:500] or "Login failed.", level="error", key="login-failed")
        elif kind == "UNKNOWN_WINDOW":
            self._problem_alerted = True
            self.alerter.send("Gateway is showing a window ibc2 does not recognise",
                              f"{detail[:500]}\nIf this blocks the login, add a rule to "
                              f"{paths.dialog_rules_file()} (see the comments in that file).",
                              level="error", key="unknown-window:" + detail.split(":", 1)[0][:60])
        elif kind == "EXIT":
            self.write_state()

    # ---- periodic checks -----------------------------------------------------------------------
    def tick(self) -> None:
        """One iteration of monitoring. Called about once a second while IBC runs."""
        if self.tail:
            for ev in self.tail.poll():
                self.handle_event(ev)
        now = self._now()
        if self.phase in (STARTING, WAITING_2FA) and not self._login_alerted \
                and now - self._phase_since > self.sup["login_timeout"]:
            self._login_alerted = True
            self._problem_alerted = True
            self.alerter.send("Login has not completed",
                              f"Still waiting for login after {self.sup['login_timeout'] // 60} minutes "
                              f"(state: {self.phase}). Last event: {self.last_event or 'none'}.",
                              level="error", key="login-timeout")
        if self.phase == RUNNING and now - self._last_check >= self.sup["health_interval"]:
            self._last_check = now
            self.check_health()
        self.check_reauth_reminder()
        self.write_state()

    def check_health(self) -> bool:
        ok = self._handshake(self._host(), self.port)
        now = self._now()
        if ok:
            self._last_ok = now
            self._unhealthy_alerted = False
            self._consecutive_failures = 0  # a working API is the only real proof the last start succeeded
            return True
        down_for = now - self._last_ok
        if down_for > self.sup["health_grace"]:
            if not self._unhealthy_alerted:
                self._unhealthy_alerted = self._problem_alerted = True
                self.alerter.send("IBKR API is not responding",
                                  f"No answer on port {self.port} for {int(down_for // 60)} minutes."
                                  + (" Restarting." if self.sup["restart_on_unhealthy"] else ""),
                                  level="error", key="api-down")
            if self.sup["restart_on_unhealthy"] and self.proc is not None:
                self._killed_unhealthy = True
                launcher.kill_tree(self.proc)
        return False

    def _host(self) -> str:
        return "127.0.0.1"

    def check_reauth_reminder(self) -> None:
        hours = self.sup["reauth_reminder_hours"]
        if not hours:
            return
        wall = self._wall()
        nxt = reauth.next_weekly_reauth(wall)
        if nxt - wall <= timedelta(hours=hours) and self._reminded_for != nxt:
            self._reminded_for = nxt
            self.alerter.send("Weekly IBKR re-login coming up",
                              f"IBKR will require a fresh login with second-factor approval after "
                              f"{reauth.format_local(nxt)}. Keep your phone handy; ibc2 will alert you when the "
                              f"request appears.", level="info", key="reauth-reminder")

    # ---- process lifecycle ---------------------------------------------------------------------
    def request_stop(self, *_: Any) -> None:
        self.stop_requested = True

    def resolve_install(self) -> Install:
        g = self.settings["gateway"]
        roots = [Path(g["tws_path"])] if g["tws_path"] else None
        installs = find_installs(roots)
        install = pick_install(installs, g["app"], g["version"]) or pick_install(installs, "", g["version"])
        if install is None:
            raise RuntimeError(
                "No offline TWS/Gateway installation found. Install IB Gateway (the standalone/offline build, "
                "not the self-updating one), or set tws_path in " + str(paths.settings_file()))
        return install

    def start_ibc(self, install: Install) -> None:
        g = self.settings["gateway"]
        password = credentials.get_password(g["username"])
        cfg = config_mod.write_runtime_config(self.settings, g["username"], password)
        cmd = launcher.build_command(self.settings, install, cfg)
        self.tail = EventTail(paths.events_file())
        self.proc = launcher.popen(cmd)
        self.pump = LogPump(self.proc.stdout, paths.logs_dir())
        self.pump.start()
        self._last_ok = self._now()
        self._set_phase(STARTING)

    def run(self) -> int:
        prune_logs(paths.logs_dir())
        events = paths.events_file()
        if events.exists() and events.stat().st_size > 1_000_000:
            events.unlink()  # the event log is only read live; keep it from growing without bound
        paths.pid_file().write_text(str(os.getpid()))
        paths.stop_flag().unlink(missing_ok=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self.request_stop)
            except (ValueError, OSError):
                pass
        try:
            install = self.resolve_install()
            self.alerter.send("ibc2 started",
                              f"Supervising {install.app} {install.version} ({self.settings['gateway']['mode']}). "
                              f"Next weekly re-login: {reauth.format_local(reauth.next_weekly_reauth())}.",
                              level="info")
            while not self.stop_requested and not paths.stop_flag().exists():
                started = self._now()
                self.start_ibc(install)
                while self.proc.poll() is None and not self.stop_requested and not paths.stop_flag().exists():
                    self.tick()
                    self._sleep(1)
                if self.stop_requested or paths.stop_flag().exists():
                    break
                self.on_ibc_exit(self.proc.returncode, self._now() - started)
            self.shutdown()
            return 0
        except (RuntimeError, OSError, credentials.CredentialError) as e:
            self.alerter.send("ibc2 cannot start", str(e), level="error")
            return 2
        finally:
            for p in (paths.pid_file(), paths.runtime_config()):
                p.unlink(missing_ok=True)  # never leave the generated password-bearing config behind
            self._set_phase(STOPPED)

    def on_ibc_exit(self, code: int | None, ran_for: float) -> None:
        reason = {EXIT_2FA_TIMEOUT: "the second-factor approval timed out",
                  EXIT_LOGIN_DIALOG_TIMEOUT: "the login window never appeared"}.get(code or 0, f"exit code {code}")
        # A long run only counts as healthy if the watchdog did not have to kill it: a Gateway that logs
        # in but never answers must back off, not re-login every few minutes (login throttling).
        ran_ok = ran_for > 600 and not self._killed_unhealthy
        self._killed_unhealthy = False
        self._consecutive_failures = 0 if ran_ok else self._consecutive_failures + 1
        backoff = self.sup["backoff"]
        wait = backoff[min(max(self._consecutive_failures, 1) - 1, len(backoff) - 1)]
        tail = "\n".join(list(self.pump.tail)[-8:]) if self.pump else ""
        self.alerter.send("IBC exited; restarting", f"Reason: {reason}. Restarting in {wait}s.\n{tail}"[:1500],
                          level="error" if code else "warning", key=f"exit:{code}")
        self._set_phase(BACKOFF)
        end = self._now() + wait
        while self._now() < end and not self.stop_requested and not paths.stop_flag().exists():
            self.write_state()  # keeps the state file fresh: 'ibc2 start' treats a stale one as "not running"
            self._sleep(1)

    def shutdown(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            port = self.sup["command_port"]
            if port:
                try:
                    health.send_command(port, "STOP")
                except OSError:
                    pass
                deadline = self._now() + 30
                while self.proc.poll() is None and self._now() < deadline:
                    self._sleep(1)
            launcher.kill_tree(self.proc)
