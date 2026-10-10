import json
import socket
import struct
import threading
import xml.dom.minidom
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from ibc2 import config, credentials, detect, health, paths, reauth, service, settings, tomlio
from ibc2.alerts import Alerter

NY = ZoneInfo("America/New_York")


# ---- config rendering --------------------------------------------------------------------------
TEMPLATE = "# Foo=ignored\r\nIbLoginId=edemo\r\nIbPassword=demouser\r\nAutoRestartTime=\r\nTradingMode=live\r\n"


def test_set_key_replaces_first_uncommented_line_and_keeps_crlf():
    out = config.set_key(TEMPLATE, "TradingMode", "paper")
    assert "TradingMode=paper\r\n" in out
    assert "# Foo=ignored" in out
    assert out.count("TradingMode=") == 1


def test_set_key_appends_missing_key():
    out = config.set_key("A=1\n", "B", "2")
    assert out.endswith("B=2\n")


def test_set_key_does_not_touch_commented_default():
    out = config.set_key("#TradingMode=live\nTradingMode=\n", "TradingMode", "paper")
    assert out == "#TradingMode=live\nTradingMode=paper\n"


def test_render_applies_unattended_defaults_and_credentials():
    s = settings.load()
    s["gateway"]["mode"] = "paper"
    out = config.render(TEMPLATE, s, username="u1", password="p@ss&word%1")
    assert "IbLoginId=u1" in out
    assert "IbPassword=p@ss&word%1" in out  # passwords with shell metacharacters pass through untouched
    assert "ExistingSessionDetectedAction=primary" in out
    assert "ReloginAfterSecondFactorAuthenticationTimeout=yes" in out
    assert "AllowLocalhostOnly=yes" in out
    assert "TradingMode=paper" in out


def test_allow_remote_clients_for_docker():
    s = settings.load()
    s["gateway"]["allow_remote_clients"] = True
    assert "AllowLocalhostOnly=no" in config.render(TEMPLATE, s)


def test_escape_value_for_java_properties():
    # Windows paths and passwords with backslashes must survive Properties.load
    assert config.escape_value(r"C:\Users\me\events.jsonl") == r"C:\\Users\\me\\events.jsonl"
    assert config.escape_value(" lead") == r"\ lead"
    assert config.escape_value("pw=a:b#c!d") == "pw=a:b#c!d"  # these are fine after the first '='
    assert config.escape_value("pässword") == r"p\u00e4ssword"
    assert config.escape_value("a\nb") == r"a\nb"


def test_set_key_escapes_value_in_file():
    out = config.set_key("EventLogFile=\n", "EventLogFile", r"C:\Users\x")
    assert out == "EventLogFile=C:\\\\Users\\\\x\n"


def test_runtime_config_is_ascii_and_roundtrips_as_properties(tmp_path, monkeypatch):
    ibc = tmp_path / "ibc"
    ibc.mkdir()
    (ibc / "config.ini").write_text("IbLoginId=\nIbPassword=\n")
    monkeypatch.setenv("IBC2_IBC_DIR", str(ibc))
    path = config.write_runtime_config(settings.load(), "usér", "pa\\ss wörd")
    raw = path.read_bytes()
    assert all(b < 0x80 for b in raw)
    assert b"IbPassword=pa\\\\ss w\\u00f6rd" in raw


# ---- settings / toml ---------------------------------------------------------------------------
def test_toml_roundtrip_with_awkward_strings(tmp_path):
    data = {"gateway": {"username": 'a "quoted" \\ name', "api_port": 4002, "x": True},
            "supervisor": {"backoff": [1, 2, 3]}}
    p = tmp_path / "t.toml"
    tomlio.save(p, data)
    assert tomlio.load(p) == data


def test_toml_control_characters_stay_valid(tmp_path):
    nl, tab, cr = chr(10), chr(9), chr(13)
    data = {"alerts": {"webhook_url": "https://x/y" + nl, "smtp_password": "a" + tab + "b" + cr + "c" + chr(1)}}
    p = tmp_path / "t.toml"
    tomlio.save(p, data)
    assert tomlio.load(p) == data


def test_escape_value_astral_characters_use_surrogate_pairs():
    bs = chr(92)
    assert config.escape_value(chr(0x1F600)) == bs + "ud83d" + bs + "ude00"


def test_stale_pid_file_is_not_treated_as_running(monkeypatch):
    import os
    import time

    from ibc2 import cli

    paths.pid_file().write_text(str(os.getpid()))  # a live PID (ours), but nothing refreshes the state
    assert cli._supervisor_pid() == os.getpid()  # fresh pid file
    old = time.time() - 3600
    os.utime(paths.pid_file(), (old, old))
    assert cli._supervisor_pid() is None  # stale: the number may have been reused by something else
    paths.state_file().write_text("{}")  # a supervisor that is really alive keeps refreshing this
    assert cli._supervisor_pid() == os.getpid()


def test_settings_user_file_and_env_override(monkeypatch):
    s = settings.load()
    s["gateway"]["username"] = "fromfile"
    settings.save(s)
    assert settings.load()["gateway"]["username"] == "fromfile"
    monkeypatch.setenv("IBC2_USERNAME", "fromenv")
    monkeypatch.setenv("IBC2_API_PORT", "4001")
    loaded = settings.load()
    assert loaded["gateway"]["username"] == "fromenv"
    assert loaded["gateway"]["api_port"] == 4001


def test_runtime_config_is_written_and_contains_secret(tmp_path, monkeypatch):
    ibc = tmp_path / "ibc"
    ibc.mkdir()
    (ibc / "config.ini").write_text("IbLoginId=\nIbPassword=\nTradingMode=live\n")
    monkeypatch.setenv("IBC2_IBC_DIR", str(ibc))
    path = config.write_runtime_config(settings.load(), "me", "secret")
    text = path.read_text()
    assert "IbPassword=secret" in text
    assert f"EventLogFile={config.escape_value(str(paths.events_file()))}" in text


# ---- credentials -------------------------------------------------------------------------------
def test_password_from_env_and_file(monkeypatch, tmp_path):
    monkeypatch.setenv("IBC2_PASSWORD", "envpw")
    assert credentials.get_password("x") == "envpw"
    monkeypatch.delenv("IBC2_PASSWORD")
    f = tmp_path / "pw"
    f.write_text("filepw\n")
    monkeypatch.setenv("IBC2_PASSWORD_FILE", str(f))
    assert credentials.get_password("x") == "filepw"


def test_missing_password_raises(monkeypatch):
    class Fake:
        @staticmethod
        def get_password(*_):
            return None

    monkeypatch.setitem(__import__("sys").modules, "keyring", Fake)
    with pytest.raises(credentials.CredentialError):
        credentials.get_password("nobody")


# ---- weekly re-authentication --------------------------------------------------------------------
def test_next_weekly_reauth_is_next_sunday_1am_new_york():
    # Wednesday 2026-10-14 12:00 New York
    nxt = reauth.next_weekly_reauth(datetime(2026, 10, 14, 12, 0, tzinfo=NY))
    assert (nxt.year, nxt.month, nxt.day, nxt.hour, nxt.weekday()) == (2026, 10, 18, 1, 6)


def test_reauth_on_sunday_after_1am_rolls_to_next_week():
    nxt = reauth.next_weekly_reauth(datetime(2026, 10, 18, 2, 0, tzinfo=NY))
    assert nxt.day == 25


def test_reauth_on_sunday_before_1am_is_same_day():
    nxt = reauth.next_weekly_reauth(datetime(2026, 10, 18, 0, 30, tzinfo=NY))
    assert nxt.day == 18


def test_default_restart_is_0130_new_york_in_local_time():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Asia/Singapore"))
    got = reauth.default_auto_restart_time(now)
    ny = datetime.strptime(got, "%I:%M %p")
    # 01:30 New York (EDT, UTC-4) = 05:30 UTC = 13:30 Singapore
    assert (ny.hour, ny.minute) == (13, 30)


# ---- alerts ------------------------------------------------------------------------------------
class Sink:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def flush(self):
        pass


def test_alert_rate_limit_by_key():
    t = [0.0]
    a = Alerter({}, min_interval=300, clock=lambda: t[0], out=Sink())
    assert a.send("x", "y", key="k") is True
    assert a.send("x", "y", key="k") is False
    t[0] = 301
    assert a.send("x", "y", key="k") is True
    assert a.send("x", "y") is True  # unkeyed alerts are never dropped


def test_alert_delivery_failure_never_raises():
    cfg = {"webhook_url": "http://127.0.0.1:1/nope"}
    sink = Sink()
    Alerter(cfg, out=sink).send("t", "m")
    assert "could not deliver" in sink.text


def test_alert_webhook_payload():
    received = []
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        c, _ = srv.accept()
        data = b""
        while b"\r\n\r\n" not in data:
            data += c.recv(4096)
        head, _, body = data.partition(b"\r\n\r\n")
        n = int([h for h in head.split(b"\r\n") if h.lower().startswith(b"content-length")][0].split(b":")[1])
        while len(body) < n:
            body += c.recv(4096)
        received.append(json.loads(body))
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        c.close()

    th = threading.Thread(target=serve)
    th.start()
    Alerter({"webhook_url": f"http://127.0.0.1:{port}/"}, out=Sink()).send("Title", "Body", level="error")
    th.join(5)
    srv.close()
    assert received[0]["title"] == "Title" and received[0]["level"] == "error"


# ---- API handshake -----------------------------------------------------------------------------
def _fake_gateway(reply: bytes | None):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        try:
            c, _ = srv.accept()
            c.recv(4096)
            if reply is not None:
                c.sendall(reply)
                c.close()
            else:
                threading.Event().wait(1.5)  # accept but never answer: a frozen gateway
                c.close()
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()
    return srv


def test_handshake_ok():
    body = b"176\x0020261010 12:00:00 EST\x00"
    srv = _fake_gateway(struct.pack(">I", len(body)) + body)
    assert health.api_handshake("127.0.0.1", srv.getsockname()[1], timeout=2) is True
    srv.close()


def test_handshake_fails_when_port_open_but_silent():
    srv = _fake_gateway(None)
    assert health.api_handshake("127.0.0.1", srv.getsockname()[1], timeout=0.5) is False
    srv.close()


def test_handshake_fails_when_closed():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert health.api_handshake("127.0.0.1", port, timeout=0.5) is False


def test_send_command_skips_greeting_and_prompt():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got = []

    def serve():
        c, _ = srv.accept()
        c.sendall(b"INFO IBC Command Server\n> ")
        data = b""
        while b"\n" not in data:
            data += c.recv(4096)
        got.append(data.split(b"\n")[0])
        c.sendall(b"OK Stopping\n> ")
        c.close()

    th = threading.Thread(target=serve)
    th.start()
    reply = health.send_command(srv.getsockname()[1], "STOP", timeout=3)
    th.join(5)
    srv.close()
    assert got == [b"STOP"] and reply == "OK Stopping"


# ---- install detection -----------------------------------------------------------------------------
def test_find_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(detect.platform, "system", lambda: "Linux")  # this test describes the Linux/Windows layout
    (tmp_path / "1043" / "jars").mkdir(parents=True)
    (tmp_path / "ibgateway" / "1045" / "jars").mkdir(parents=True)
    (tmp_path / "1030").mkdir()  # no jars: the self-updating layout, must be ignored
    found = detect.find_installs([tmp_path])
    assert [(i.app, i.version) for i in found] == [("gateway", "1045"), ("tws", "1043")]
    assert detect.pick_install(found, "tws").version == "1043"
    assert detect.pick_install(found, "", "1045").app == "gateway"
    assert detect.pick_install(found, "gateway", "9999") is None


# ---- service definitions -------------------------------------------------------------------------
def test_windows_task_xml_is_valid_and_escaped(tmp_path):
    xml_text = service.windows_task_xml(r"C:\Python\pythonw.exe", tmp_path, r"PC\me & co")
    doc = xml.dom.minidom.parseString(xml_text.replace('encoding="UTF-16"', "").strip().encode("utf-8"))
    assert doc.getElementsByTagName("RestartOnFailure")
    assert "me &amp; co" in xml_text


def test_systemd_unit_restarts_always(tmp_path):
    unit = service.systemd_unit("/usr/bin/python3", tmp_path)
    assert "Restart=always" in unit and "-m ibc2 run" in unit


def test_find_installs_macos_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(detect.platform, "system", lambda: "Darwin")
    (tmp_path / "IB Gateway 1050").mkdir()
    (tmp_path / "Trader Workstation 1043").mkdir()
    found = detect.find_installs([tmp_path])
    assert [(i.app, i.version) for i in found] == [("gateway", "1050"), ("tws", "1043")]
