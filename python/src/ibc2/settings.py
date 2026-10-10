"""User settings (ibc2.toml) and their defaults."""

from __future__ import annotations

import copy
import os
from typing import Any

from . import paths, tomlio

DEFAULTS: dict[str, Any] = {
    "gateway": {
        "app": "gateway",  # "gateway" or "tws"
        "version": "",  # TWS/Gateway major version, e.g. "1043"; detected if empty
        "tws_path": "",  # install root (the folder containing the version folder); detected if empty
        "settings_path": "",  # where TWS/Gateway keep their settings; empty = the install root (Docker mounts a volume here)
        "mode": "paper",  # "paper" or "live"
        "username": "",  # IBKR user name (the password lives in the OS keyring)
        "api_port": 0,  # 0 = leave TWS/Gateway's own port; otherwise force this port
        "host": "127.0.0.1",
        "allow_remote_clients": False,  # True = also accept API clients from other machines/containers
        "auto_restart_time": "",  # e.g. "01:30 AM"; empty = computed (01:30 New York time, in local time)
        "second_factor_device": "",  # name of the 2FA device if you have several
        "read_only_api": False,
    },
    "supervisor": {
        "health_interval": 30,  # seconds between API handshakes
        "health_grace": 600,  # seconds the API may be down (e.g. during the nightly restart) before acting
        "login_timeout": 900,  # alert if login has not completed this long after start
        "restart_on_unhealthy": True,
        "backoff": [15, 60, 300, 900],  # seconds to wait between consecutive crash restarts
        "command_port": 7462,  # IBC command server (localhost only); 0 disables stop/restart commands
        "reauth_reminder_hours": 8,  # remind this long before the weekly forced re-login
    },
    "alerts": {
        "telegram_token": "",
        "telegram_chat_id": "",
        "discord_webhook": "",
        "webhook_url": "",
        "email_to": "",
        "email_from": "",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_security": "starttls",  # "starttls", "ssl" or "none"
    },
}

_ENV = {
    "IBC2_MODE": ("gateway", "mode"),
    "IBC2_APP": ("gateway", "app"),
    "IBC2_USERNAME": ("gateway", "username"),
    "IBC2_TWS_VERSION": ("gateway", "version"),
    "IBC2_TWS_PATH": ("gateway", "tws_path"),
    "IBC2_TWS_SETTINGS_PATH": ("gateway", "settings_path"),
    "IBC2_API_PORT": ("gateway", "api_port"),
    "IBC2_TELEGRAM_TOKEN": ("alerts", "telegram_token"),
    "IBC2_TELEGRAM_CHAT_ID": ("alerts", "telegram_chat_id"),
    "IBC2_DISCORD_WEBHOOK": ("alerts", "discord_webhook"),
    "IBC2_WEBHOOK_URL": ("alerts", "webhook_url"),
    "IBC2_SMTP_PASSWORD": ("alerts", "smtp_password"),
}


def load() -> dict[str, Any]:
    data = copy.deepcopy(DEFAULTS)
    user = tomlio.load(paths.settings_file())
    for table, values in user.items():
        if isinstance(values, dict) and table in data:
            data[table].update(values)
        else:
            data[table] = values
    apply_env(data)
    return data


def apply_env(data: dict[str, Any]) -> None:
    """Environment variables win, which is what containers and CI want."""
    for env, (table, key) in _ENV.items():
        value = os.environ.get(env)
        if value:
            default = DEFAULTS[table][key]
            is_int = isinstance(default, int) and not isinstance(default, bool)
            data[table][key] = int(value) if is_int else value
    if os.environ.get("IBC2_ALLOW_REMOTE_CLIENTS", "").lower() in ("1", "true", "yes"):
        data["gateway"]["allow_remote_clients"] = True


def save(data: dict[str, Any]) -> None:
    tomlio.save(paths.settings_file(), data)
    paths.restrict_to_owner(paths.settings_file())
