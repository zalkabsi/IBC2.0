from ibc2 import cli


def test_bare_command_runs_setup_and_starts(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_supervisor_pid", lambda: None)
    monkeypatch.setattr(cli.settings_mod, "load", lambda: {"gateway": {"username": ""}})
    monkeypatch.setattr(cli, "cmd_setup", lambda args: calls.append(("setup", args)) or 0)
    monkeypatch.setattr(cli, "_ask", lambda *_args, **_kwargs: "y")
    monkeypatch.setattr(cli.service, "install", lambda: calls.append(("service",)) or "installed")
    monkeypatch.setattr(cli, "cmd_start", lambda args: calls.append(("start", args)) or 0)

    assert cli.main([]) == 0
    assert [call[0] for call in calls] == ["setup", "service", "start"]
    assert calls[0][1].start_after_setup is True


def test_bare_command_starts_existing_configuration_without_setup(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_supervisor_pid", lambda: None)
    monkeypatch.setattr(cli.settings_mod, "load", lambda: {"gateway": {"username": "alice"}})
    monkeypatch.setattr(cli.credentials, "has_password", lambda username: username == "alice")
    monkeypatch.setattr(cli, "cmd_setup", lambda _args: calls.append("setup") or 0)
    monkeypatch.setattr(cli, "cmd_start", lambda _args: calls.append("start") or 0)

    assert cli.main([]) == 0
    assert calls == ["start"]


def test_bare_command_does_not_start_if_setup_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_supervisor_pid", lambda: None)
    monkeypatch.setattr(cli.settings_mod, "load", lambda: {"gateway": {"username": ""}})
    monkeypatch.setattr(cli, "cmd_setup", lambda _args: calls.append("setup") or 1)
    monkeypatch.setattr(cli, "cmd_start", lambda _args: calls.append("start") or 0)

    assert cli.main([]) == 1
    assert calls == ["setup"]


def test_bare_command_reports_when_already_running(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_supervisor_pid", lambda: 123)

    assert cli.main([]) == 0
    assert "already running" in capsys.readouterr().out


def test_bare_command_parser_is_allowed():
    assert cli.build_parser().parse_args([]).command is None


def test_startup_prompt_can_skip_automatic_service(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_supervisor_pid", lambda: None)
    monkeypatch.setattr(cli.settings_mod, "load", lambda: {"gateway": {"username": ""}})
    monkeypatch.setattr(cli, "cmd_setup", lambda _args: 0)
    monkeypatch.setattr(cli, "_ask", lambda *_args, **_kwargs: "n")
    monkeypatch.setattr(cli.service, "install", lambda: calls.append("service"))
    monkeypatch.setattr(cli, "cmd_start", lambda _args: calls.append("start") or 0)

    assert cli.main([]) == 0
    assert calls == ["start"]


def test_stop_command_requests_clean_shutdown(monkeypatch, tmp_path, capsys):
    stop_flag = tmp_path / "stop.flag"
    monkeypatch.setattr(cli, "_supervisor_pid", lambda: 123)
    monkeypatch.setattr(cli, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(cli.paths, "stop_flag", lambda: stop_flag)

    assert cli.main(["stop"]) == 0
    assert stop_flag.read_text() == "stop"
    output = capsys.readouterr().out
    assert "Stopping" in output and "Stopped." in output
