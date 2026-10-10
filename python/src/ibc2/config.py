"""Generation of the IBC ``config.ini`` from ibc2 settings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import paths, reauth

_BOOL = {True: "yes", False: "no"}


def escape_value(value: str) -> str:
    """Escape a value for ``java.util.Properties.load`` - which is how IBC reads its config.

    Properties treats a backslash as an escape character (so ``C:\\Users`` would lose its
    separators), trims leading blanks, and reads the file as ISO-8859-1.
    """
    out = []
    for i, ch in enumerate(value):
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == " " and i == 0:
            out.append("\\ ")
        elif ord(ch) > 0x7E or ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def set_key(text: str, key: str, value: str) -> str:
    """Set ``key=value`` in IBC ini text, replacing the first ``key=`` line (comments start with #).

    *value* is the logical value; it is escaped for Java Properties here. If the key is
    absent it is appended. Line endings of the template are kept.
    """
    value = escape_value(value)
    pattern = re.compile(rf"^{re.escape(key)}=.*?(\r?)$", re.MULTILINE)
    match = pattern.search(text)
    if match:
        eol = match.group(1)
        return text[: match.start()] + f"{key}={value}{eol}" + text[match.end():]
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}{key}={value}\n"


def overrides(settings: dict[str, Any], *, events_file: Path | None, rules_file: Path | None) -> dict[str, str]:
    g, s = settings["gateway"], settings["supervisor"]
    o: dict[str, str] = {
        "TradingMode": g["mode"],
        # unattended defaults: see the comments in config.ini for each setting
        "ExistingSessionDetectedAction": "primary",
        "AcceptIncomingConnectionAction": "accept",
        "AcceptNonBrokerageAccountWarning": "yes",
        "ReloginAfterSecondFactorAuthenticationTimeout": "yes",
        "ExitAfterSecondFactorAuthenticationTimeout": "no",
        "AutoRestartTime": g["auto_restart_time"] or reauth.default_auto_restart_time(),
        "ReadOnlyApi": _BOOL[bool(g["read_only_api"])],
        # make unknown dialogs easy to diagnose
        "LogStructureScope": "unknown",
        "LogStructureWhen": "open",
        "AllowLocalhostOnly": "no" if g["allow_remote_clients"] else "yes",
    }
    if g["api_port"]:
        o["OverrideTwsApiPort"] = str(g["api_port"])
    if g["second_factor_device"]:
        o["SecondFactorDevice"] = g["second_factor_device"]
    if s["command_port"]:
        o["CommandServerPort"] = str(s["command_port"])
        o["ControlFrom"] = "127.0.0.1"
        o["BindAddress"] = "127.0.0.1"
    if events_file:
        o["EventLogFile"] = str(events_file)
    if rules_file:
        o["DialogRulesFile"] = str(rules_file)
    return o


def render(template: str, settings: dict[str, Any], *, username: str = "", password: str = "",
           events_file: Path | None = None, rules_file: Path | None = None) -> str:
    text = template
    for key, value in overrides(settings, events_file=events_file, rules_file=rules_file).items():
        text = set_key(text, key, value)
    text = set_key(text, "IbLoginId", username)
    text = set_key(text, "IbPassword", password)
    return text


def template_text() -> str:
    return (paths.bundled_ibc_dir() / "config.ini").read_text(encoding="utf-8", errors="replace")


def write_runtime_config(settings: dict[str, Any], username: str, password: str) -> Path:
    """Write the config IBC will actually read. It may contain the password, so it is private."""
    rules = paths.dialog_rules_file()
    if not rules.exists():
        bundled = paths.bundled_ibc_dir() / "dialogrules.txt"
        if bundled.exists():
            rules.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
    text = render(template_text(), settings, username=username, password=password,
                  events_file=paths.events_file(), rules_file=rules)
    target = paths.runtime_config()
    target.write_text("", encoding="utf-8")  # create, then lock down BEFORE writing the secret
    paths.restrict_to_owner(target)
    target.write_text(text, encoding="latin-1", errors="replace")  # Properties.load reads ISO-8859-1
    return target
