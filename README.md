# IBC2.0 - always-on Interactive Brokers, one command

[![PyPI](https://img.shields.io/pypi/v/ibc2)](https://pypi.org/project/ibc2/)
[![CI](https://github.com/zalkabsi/IBC2.0/actions/workflows/ci.yml/badge.svg)](https://github.com/zalkabsi/IBC2.0/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE.txt)

**IBC2.0 keeps Interactive Brokers TWS / IB Gateway logged in without you.** It is a maintained fork of
[IBC](https://github.com/IbcAlpha/IBC) (the Java tool that logs in to TWS/Gateway and clicks through its dialogs;
retired upstream on 1 September 2026) plus **`ibc2`**, a pip-installable supervisor that adds a watchdog, alerts,
service installation and a Docker image.

```bash
pip install ibc2
ibc2                # first run: guided setup, then starts the watchdog in the background
ibc2 stop           # stop the watchdog and close TWS/Gateway
```

The first run finds an offline TWS / Gateway installation, asks for your trading mode and IBKR login,
stores the password in the OS keyring, and offers to start ibc2 automatically when you sign in. Later,
running `ibc2` starts the configured watchdog. Use `ibc2 setup` to change settings or `ibc2 status` to
check the session. `ibc2 uninstall-service` removes the automatic sign-in startup.

On a headless server or VPS use Docker instead:

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

See [python/README.md](python/README.md) for the full `ibc2` command reference and
[docker/README.md](docker/README.md) for the container.

> **Start with a paper-trading account.** `ibc2 setup` asks you to type `live` before it will use live mode.

## What it fixes

| Problem algo traders hit | What this project does |
|---|---|
| The weekly forced 2FA login arrives while you are away | Alerts (Telegram, Discord, e-mail, any webhook) the moment approval is needed, and a reminder hours before it is due |
| Gateway stalls on a new pop-up IBC has never seen | Detects and reports the window; fix it with a one-line rule in `dialogrules.txt`, no recompiling |
| `AutoRestartTime=2:00 PM` silently ignored, causing a mid-session logoff | Lenient time parsing, and a default restart time computed for your time zone (01:30 New York) |
| Wrong 2FA device or passkey chosen | Device matched by name (case-insensitive, partial if unambiguous); lists the available devices when none match |
| Gateway frozen but its port still open | Watchdog performs a real API handshake and restarts it, backing off if restarts do not help |
| Config errors disappeared into `/dev/null` | JVM errors now reach the log |
| Fiddly install, version mismatches, plaintext passwords | `ibc2 setup` / `ibc2 doctor`, OS keyring, Docker image |
| API client in another container cannot connect | New `AllowLocalhostOnly` setting |

### What no tool can do

Interactive Brokers requires a fresh, fully authenticated login (including second factor) about once a week -
the first login after **Sunday 01:00 New York time**. **That cannot be removed, and this project does not try.**
What it does is make sure every other disconnect and the nightly restart recover by themselves, and that the
weekly approval is a 30-second tap on your phone with an alert telling you when, instead of a silent outage.

## Requirements

- An **offline (standalone)** TWS or IB Gateway from Interactive Brokers. IBC does **not** work with the
  self-updating TWS. (There is no self-updating Gateway, so the normal Gateway installer is fine.)
  Gateway is recommended for always-on use.
- Python 3.10+ for `ibc2` (or just Docker). Java is not needed separately: the one bundled with TWS/Gateway is used.
- Windows, Linux or macOS.

## How it fits together

```
 ibc2 (Python)          watchdog, alerts, config, service       pip install ibc2
   |  writes config.ini, launches, reads events.jsonl
 IBC (Java, this repo)  logs in, handles dialogs, auto-restart  resources/IBC.jar
   |  runs inside the same JVM as
 TWS / IB Gateway       your bot talks to its API port          4001/4002 (Gateway), 7496/7497 (TWS)
```

The Java side was extended to write machine-readable **events** (2FA needed, login ok/failed, unrecognised
window, exit) to `EventLogFile`; `ibc2` reads them to alert you.

## Project status

- Java: builds on JDK 17; unit tests run with `ant test`.
- `ibc2`: 54 automated tests on Linux, Windows and macOS (CI). Verified manually against a real TWS 1043 on
  Windows and a real IB Gateway 1050 in Docker, in both cases up to the login window, using blank credentials.
- **Not yet verified against a live account:** the 2FA alert flow, dialog rules on a real IBKR pop-up, and
  alert delivery on each channel. Treat the first week as a trial on a paper account.
- Release notes: [CHANGELOG.md](CHANGELOG.md).

## Classic IBC usage (without ibc2)

Everything IBC did before still works: the start scripts in [resources](resources), `config.ini`, the
command server, and so on. See the [IBC User Guide](userguide.md). The settings added in this fork
(`EventLogFile`, `DialogRulesFile`, `AllowLocalhostOnly`, lenient `AutoRestartTime`) are documented there and
in [resources/config.ini](resources/config.ini). Existing configurations keep behaving as before.

IBC's original feature list:

* Automatically fills in your username and password in the Login dialog and clicks Login
* Ensures that, while a session is running, logins from another computer or device do not succeed
* Participates in Two Factor Authentication using IBKR Mobile, re-prompting so that a missed alert is not fatal
* Handles the various dialog boxes TWS sometimes displays, to keep things running with no user involvement
* Allows TWS and Gateway to be auto-restarted each day without re-authenticating
* Allows TWS and Gateway to be shut down at a specified time every day (or TWS on a given day of the week)
* Can be remotely told to shut down or restart TWS/Gateway (the command server)

> IBC cannot complete a login by itself if Interactive Brokers have given you a card or device you must use.
> It can still enter your username and password, but you must supply the code or use the IBKR Mobile app.
>
> If you are moving from IBController, see the last section of the [User Guide](userguide.md).
>
> No guarantee is given that this repository is in a fully self-consistent state at every commit. If you build
> `IBC.jar` yourself, test thoroughly before deploying it (for example in a Docker image).

## Building from source

```bash
export IBC_BIN=/path/to/Jts/<version>/jars     # any TWS/Gateway jars folder; only needed to compile
ant test jar                                   # Java tests, then resources/IBC.jar
cd python && python build_assets.py && pip install -e ".[test]" && pytest
```

Details are in [CONTRIBUTING.md](CONTRIBUTING.md); releases are described in
[python/RELEASING.md](python/RELEASING.md).

## Support

Please open an issue on [this repository](https://github.com/zalkabsi/IBC2.0/issues). Attach the IBC log
(`ibc2 logs`, or `~/.ibc2/logs`), and say which IBC/`ibc2` and TWS/Gateway versions you use and what you
expected to happen. The original project's archive remains at [IbcAlpha/IBC](https://github.com/IbcAlpha/IBC),
and its [user group](https://groups.io/g/ibcalpha) is still a useful resource for general IBC questions.

## Contributing

Pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License and credits

IBC is licensed under the [GNU General Public License](LICENSE.txt) version 3 or later, and so is this fork.
It is an independent fork and is not affiliated with or endorsed by Interactive Brokers.

Credit to everyone who built what this stands on: Richard L King and the IBC contributors, and the
predecessor [IBController](https://github.com/ib-controller/ib-controller) (Richard King, Steven Kearns,
Ken Geis, Ben Alex and Shane Castle).

### History

IBC is a fork of IBController, created in early 2018 by Richard L King, who had been that project's
primary maintainer since 2004. IBC was retired upstream on 1 September 2026 with the wish that others
could carry it forward; this repository does so.
