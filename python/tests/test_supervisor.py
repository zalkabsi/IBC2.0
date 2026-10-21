import json
from datetime import datetime
from zoneinfo import ZoneInfo

from ibc2 import paths, settings
from ibc2 import supervisor as sup_mod
from ibc2.alerts import Alerter
from ibc2.supervisor import EventTail, RUNNING, STARTING, WAITING_2FA, Supervisor


class Recorder(Alerter):
    def __init__(self):
        super().__init__({}, out=open("nul" if __import__("os").name == "nt" else "/dev/null", "w"))
        self.sent = []

    def send(self, title, message, *, level="warning", key=None):
        if key is not None and any(k == key for _, _, _, k in self.sent):
            return False
        self.sent.append((title, message, level, key))
        return True

    def titles(self):
        return [t for t, *_ in self.sent]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def make(handshake=lambda h, p: True, **overrides):
    s = settings.load()
    s["supervisor"].update(overrides)
    clock = Clock()
    rec = Recorder()
    sv = Supervisor(s, rec, now=clock, handshake=handshake, sleep=clock.sleep,
                    wall=lambda: datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("America/New_York")))
    sv.proc = None
    return sv, rec, clock


# ---- events -------------------------------------------------------------------------------------
def test_two_fa_event_alerts_user_once():
    sv, rec, _ = make()
    sv.handle_event({"type": "TWO_FA_REQUIRED", "detail": "x"})
    sv.handle_event({"type": "TWO_FA_REQUIRED", "detail": "x"})
    assert sv.phase == WAITING_2FA
    assert rec.titles() == ["Approve the IBKR login now"]


def test_logged_in_after_problem_sends_recovery():
    sv, rec, _ = make()
    sv.handle_event({"type": "LOGIN_FAILED", "detail": "bad password"})
    sv.handle_event({"type": "LOGGED_IN", "detail": ""})
    assert sv.phase == RUNNING
    assert rec.titles() == ["IBKR login failed", "IBKR session recovered"]


def test_normal_login_sends_no_recovery_noise():
    sv, rec, _ = make()
    sv.handle_event({"type": "LOGGED_IN", "detail": ""})
    assert rec.sent == []


def test_unknown_window_alert_mentions_rules_file():
    sv, rec, _ = make()
    sv.handle_event({"type": "UNKNOWN_WINDOW", "detail": "Gateway: Trade Prediction Markets"})
    title, message, level, _ = rec.sent[0]
    assert "does not recognise" in title and "Prediction Markets" in message and "dialogrules" in message
    assert level == "error"


# ---- timeouts and health -----------------------------------------------------------------------
def test_login_timeout_alert_fires_once():
    sv, rec, clock = make(login_timeout=600)
    sv._set_phase(STARTING)
    clock.t += 601
    sv.tick()
    sv.tick()
    assert rec.titles().count("Login has not completed") == 1


def test_health_grace_prevents_restart_during_nightly_restart(monkeypatch):
    healthy = [False]
    sv, rec, clock = make(handshake=lambda h, p: healthy[0], health_grace=600)
    killed = []
    sv.proc = type("FakeProc", (), {"pid": 1, "poll": lambda self: None})()
    monkeypatch.setattr(sup_mod.launcher, "kill_tree", lambda p, **k: killed.append(p))
    sv._set_phase(RUNNING)
    clock.t += 120  # gateway is restarting itself: API down for 2 minutes
    assert sv.check_health() is False
    assert killed == [] and rec.sent == []
    clock.t += 600  # now it has been down far too long
    sv.check_health()
    assert killed and rec.titles() == ["IBKR API is not responding"]


def test_health_recovery_resets_alert():
    ok = [False]
    sv, rec, clock = make(handshake=lambda h, p: ok[0], health_grace=60, restart_on_unhealthy=False)
    sv._set_phase(RUNNING)
    clock.t += 100
    sv.check_health()
    ok[0] = True
    assert sv.check_health() is True
    assert sv._unhealthy_alerted is False


# ---- reauth reminder ---------------------------------------------------------------------------
def test_reauth_reminder_sent_once_inside_window():
    s = settings.load()
    s["supervisor"]["reauth_reminder_hours"] = 24 * 7  # always inside the window for this test
    rec = Recorder()
    sv = Supervisor(s, rec, handshake=lambda *_: True, sleep=lambda _: None,
                    wall=lambda: datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("America/New_York")))
    sv.check_reauth_reminder()
    sv.check_reauth_reminder()
    assert rec.titles() == ["Weekly IBKR re-login coming up"]


def test_reauth_reminder_disabled_with_zero():
    sv, rec, _ = make(reauth_reminder_hours=0)
    sv.check_reauth_reminder()
    assert rec.sent == []


# ---- exit handling -----------------------------------------------------------------------------
def test_exit_2fa_timeout_message_and_backoff_grows():
    sv, rec, _ = make(backoff=[1, 2, 4])
    sv.pump = None
    sv.on_ibc_exit(sup_mod.EXIT_2FA_TIMEOUT, 30)
    sv.on_ibc_exit(sup_mod.EXIT_2FA_TIMEOUT, 30)
    assert "second-factor approval timed out" in rec.sent[0][1]
    assert sv._consecutive_failures == 2
    sv.phase = RUNNING
    sv.on_ibc_exit(1, 4000)
    assert sv._consecutive_failures == 0


def test_backoff_starts_at_first_step_and_grows():
    sv, rec, _ = make(backoff=[1, 2, 4])
    sv.pump = None
    for expected in ("1s", "2s", "4s", "4s"):
        sv.on_ibc_exit(1, 30)
        assert f"Restarting in {expected}." in rec.sent[-1][1]
        rec.sent.clear()


def test_watchdog_kill_does_not_reset_backoff():
    """A Gateway that logs in but never answers must not be re-logged-in at a fixed short interval."""
    healthy = [False]
    sv, rec, clock = make(handshake=lambda h, p: healthy[0], backoff=[1, 2, 4], health_grace=60)
    sv.pump = None
    sv.proc = type("FakeProc", (), {"pid": 1, "poll": lambda self: None})()
    waits = []
    for _ in range(3):
        sv._set_phase(RUNNING)
        sv.handle_event({"type": "LOGGED_IN", "detail": ""})  # login succeeds each time...
        clock.t += 100
        sup_mod.launcher.kill_tree = lambda p, **k: None
        sv.check_health()  # ...but the API never answers, so the watchdog kills it
        sv.on_ibc_exit(1, 4000)  # long run, yet it was killed by the watchdog
        waits.append(rec.sent[-1][1].split("Restarting in ")[1].split(".")[0])
        rec.sent.clear()
    assert waits == ["1s", "2s", "4s"]


def test_healthy_api_resets_backoff():
    sv, rec, _ = make(backoff=[1, 2, 4])
    sv.pump = None
    sv.on_ibc_exit(1, 30)
    sv.on_ibc_exit(1, 30)
    assert sv._consecutive_failures == 2
    sv._set_phase(RUNNING)
    sv.check_health()
    assert sv._consecutive_failures == 0


def test_run_reports_oserror_instead_of_dying_silently(monkeypatch):
    sv, rec, _ = make()
    monkeypatch.setattr(sv, "resolve_install", lambda: (_ for _ in ()).throw(FileNotFoundError("bash")))
    assert sv.run() == 2
    assert rec.titles() == ["ibc2 cannot start"]


# ---- event tail --------------------------------------------------------------------------------
def test_event_tail_reads_only_new_complete_lines():
    path = paths.events_file()
    path.write_text(json.dumps({"type": "OLD"}) + "\n")
    tail = EventTail(path)
    assert tail.poll() == []  # history is ignored
    with open(path, "a") as f:
        f.write(json.dumps({"type": "A"}) + "\n" + '{"type": "B"')
    assert [e["type"] for e in tail.poll()] == ["A"]  # the partial line waits
    with open(path, "a") as f:
        f.write("}\nnot json\n")
    assert [e["type"] for e in tail.poll()] == ["B"]  # garbage is skipped


def test_event_tail_survives_missing_and_truncated_file():
    path = paths.events_file()
    tail = EventTail(path)
    assert tail.poll() == []
    path.write_text(json.dumps({"type": "X"}) + "\n")
    assert [e["type"] for e in tail.poll()] == ["X"]
    path.write_text("")
    assert tail.poll() == []  # truncation is noticed
    path.write_text(json.dumps({"type": "Y"}) + "\n")
    assert [e["type"] for e in tail.poll()] == ["Y"]


def test_alerter_scrubs_registered_secret_from_title_and_message():
    import io

    out = io.StringIO()
    alerter = Alerter({}, out=out)
    delivered = []
    alerter.channels = lambda: ["fake"]
    alerter._send_fake = lambda title, message, level: delivered.append((title, message))
    alerter.add_secret("hunter2pass")
    alerter.send("window hunter2pass", "Login\nhunter2pass\nOK")
    assert delivered == [("window ***", "Login\n***\nOK")]
    assert "hunter2pass" not in out.getvalue()


def test_start_ibc_registers_password_with_alerter(monkeypatch):
    sv, rec, _ = make()
    monkeypatch.setattr(sup_mod.credentials, "get_password", lambda user: "s3cret-pw")
    monkeypatch.setattr(sup_mod.config_mod, "write_runtime_config", lambda *a, **k: paths.runtime_config())
    monkeypatch.setattr(sup_mod.launcher, "build_command", lambda *a, **k: ["true"])

    class FakeProc:
        stdout = iter(())
        pid = 0

        def poll(self):
            return None

    monkeypatch.setattr(sup_mod.launcher, "popen", lambda cmd: FakeProc())
    monkeypatch.setattr(sup_mod, "LogPump", lambda stream, logs: type("P", (), {"start": lambda self: None})())
    sv.start_ibc(install=None)
    assert rec.scrub("detail s3cret-pw") == "detail ***"
