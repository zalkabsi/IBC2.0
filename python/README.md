# ibc2

**One command to keep Interactive Brokers Gateway / TWS logged in, always on.**

`ibc2` wraps [IBC](https://github.com/IbcAlpha/IBC) (the Java tool that logs in to TWS / IB Gateway and
clicks through its dialogs; retired upstream in September 2026) and adds what unattended
algo-trading setups actually need:

- a guided **`ibc2 setup`** (finds your install, stores your password in the OS keyring, never in a file you edit),
- a **watchdog** that checks the API with a real handshake and restarts a frozen Gateway,
- **alerts** (Telegram, Discord, e-mail, any webhook) the moment IBKR wants your **2FA approval**, a login fails,
  or Gateway shows a pop-up nobody has taught it to dismiss,
- a **weekly re-login reminder**, because IBKR forces a fresh 2FA login every week,
- **`ibc2 install-service`** to start at login (Windows Task Scheduler / systemd / launchd),
- a ready-made **Docker image** for headless servers.

```
pip install ibc2
ibc2 setup
ibc2 start
```

## What it can and cannot do

IBKR requires a fresh, fully authenticated login (with second factor) about once a week - the first
login after **Sunday 01:00 New York time**. **No tool can remove that**, and `ibc2` does not try to
bypass it. What `ibc2` does is make sure the nightly restarts and every disconnect recover by
themselves, and that the weekly approval is a 30-second tap on your phone, with an alert telling you
exactly when, instead of a silent outage.

## Requirements

- Python 3.10+
- An **offline (standalone)** IB Gateway or TWS from Interactive Brokers. IBC does **not** work with the
  self-updating TWS. (Gateway is recommended for always-on use.)
- Java: the one bundled with Gateway/TWS is used automatically.

## Commands

| Command | What it does |
|---|---|
| `ibc2 setup` | Guided setup: finds Gateway/TWS, asks mode (paper/live), username, password (keyring), alerts |
| `ibc2 doctor` | Checks everything and says how to fix each problem |
| `ibc2 start` / `stop` | Run in the background / close Gateway cleanly |
| `ibc2 run` | Run in the foreground (what services use) |
| `ibc2 restart` | Restart Gateway in place without a new 2FA |
| `ibc2 status [--json]` | Is it running, is the API answering, when is the next forced re-login |
| `ibc2 logs [-f]` | Show / follow the IBC log |
| `ibc2 install-service` | Start automatically at login (`uninstall-service` to remove) |
| `ibc2 test-alert` | Send a test alert |

## Alerts

`ibc2 setup` asks for one channel; you can add more in `~/.ibc2/ibc2.toml` (or the environment):

```toml
[alerts]
telegram_token = "123:ABC"       # from @BotFather
telegram_chat_id = "123456789"
discord_webhook = "https://discord.com/api/webhooks/..."
webhook_url = "https://example.com/hook"        # receives {"title","message","level","time"}
email_to = "you@example.com"
smtp_host = "smtp.gmail.com"
smtp_user = "you@gmail.com"
smtp_password = "app password"
```

You are alerted when: second-factor approval is needed, login fails, Gateway shows an unrecognised window,
the API stops answering, IBC crashes, and a few hours before the weekly forced re-login.

## When Gateway shows a new pop-up

Interactive Brokers occasionally adds a dialog IBC does not know. `ibc2` tells you the window's title and
text. Add a rule to `~/.ibc2/dialogrules.txt` - no recompiling:

```
title=^Gateway$ ; text=Prediction Markets ; click=Close
```

Rules only apply to windows IBC does not already handle.

## Docker / headless servers

See [`docker/README.md`](../docker/README.md) in the repository: `docker compose up` gives you a headless
Gateway under Xvfb with the watchdog and alerts, configured by environment variables / secrets.

## Security notes

- The password is stored in your OS keyring (Windows Credential Manager, macOS Keychain, Secret Service).
  For containers use `IBC2_PASSWORD_FILE` (a Docker/Kubernetes secret).
- While running, `ibc2` writes a private (owner-only) `runtime/config.ini` for IBC to read; it is deleted
  when `ibc2` stops.
- IBC's command server listens on `127.0.0.1` only.
- Start with **paper** trading. `ibc2 setup` asks you to type `live` to confirm live mode.

## License

GPL-3.0-or-later, like IBC. This is an independent fork; see the repository for upstream credits.
