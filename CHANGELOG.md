# Changelog

## 0.1.0 / IBC 3.25.0 - first release of this fork

### New: `ibc2` (Python, `pip install ibc2`)
- `ibc2 setup`, `doctor`, `start`, `stop`, `restart`, `status`, `logs`, `run`, `install-service`, `test-alert`
- Watchdog with a real API handshake; restarts a frozen Gateway with growing back-off
- Alerts: Telegram, Discord, e-mail (SMTP), generic webhook; rate-limited
- Reminder before the weekly forced re-login; default nightly restart time computed from 01:30 New York
- Password stored in the OS keyring (or `IBC2_PASSWORD` / `IBC2_PASSWORD_FILE` for containers)
- Service installation: Windows Task Scheduler, systemd (user), launchd
- Docker image for headless Gateway (Xvfb, optional VNC, Docker secrets)
- CI on Linux/Windows/macOS; tagged releases publish to PyPI via trusted publishing

### IBC (Java) 3.25.0
- New `EventLogFile` setting: JSON-lines event log for supervisors
- New `DialogRulesFile` setting: user-defined rules for unrecognised dialogs
- New `AllowLocalhostOnly` setting
- `AutoRestartTime` / `AutoLogoffTime` accept `2:00 PM`, `02:00 pm` and `14:00`; invalid values are reported
  (a single-digit hour used to be silently ignored)
- Second factor device matched case-insensitively / by unambiguous partial name; available devices are listed
  when nothing matches
- AM/PM handling no longer depends on the JVM's default language
- Launch scripts keep JVM stderr in the log; `StartIBC.bat` finds Java reliably
- Shipped `config.ini` no longer contains demonstration credentials
- Dependency-free unit tests (`ant test`)

### Not yet verified against a live account
2FA alert flow, dialog rules on a real IBKR pop-up, and delivery on each alert channel.
