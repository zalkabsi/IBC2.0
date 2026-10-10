"""Alert delivery: console always; Telegram, Discord, e-mail and generic webhooks when configured."""

from __future__ import annotations

import json
import smtplib
import ssl
import sys
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Any, Callable


def _post(url: str, data: bytes, content_type: str, timeout: float = 15.0) -> None:
    req = urllib.request.Request(url, data=data, headers={"Content-Type": content_type, "User-Agent": "ibc2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL comes from the user's own config
        resp.read()


class Alerter:
    """Sends alerts to every configured channel. Never raises: alerting must not break supervision."""

    def __init__(self, cfg: dict[str, Any], *, min_interval: float = 300.0,
                 clock: Callable[[], float] = time.monotonic, out=None):
        self.cfg = cfg
        self.min_interval = min_interval
        self._clock = clock
        self._last: dict[str, float] = {}
        self._out = out or sys.stderr

    def channels(self) -> list[str]:
        c = self.cfg
        names = []
        if c.get("telegram_token") and c.get("telegram_chat_id"):
            names.append("telegram")
        if c.get("discord_webhook"):
            names.append("discord")
        if c.get("webhook_url"):
            names.append("webhook")
        if c.get("email_to") and c.get("smtp_host"):
            names.append("email")
        return names

    def send(self, title: str, message: str, *, level: str = "warning", key: str | None = None) -> bool:
        """Deliver an alert. If *key* is given, repeats of the same key within ``min_interval`` are dropped."""
        if key is not None:
            now = self._clock()
            last = self._last.get(key)
            if last is not None and now - last < self.min_interval:
                return False
            self._last[key] = now
        print(f"[ibc2 {level.upper()}] {title}: {message}", file=self._out, flush=True)
        for name in self.channels():
            try:
                getattr(self, f"_send_{name}")(title, message, level)
            except Exception as e:  # noqa: BLE001 - delivery problems must never propagate
                print(f"[ibc2] could not deliver alert via {name}: {e}", file=self._out, flush=True)
        return True

    def _send_telegram(self, title: str, message: str, level: str) -> None:
        c = self.cfg
        body = urllib.parse.urlencode({"chat_id": c["telegram_chat_id"], "text": f"{title}\n{message}"}).encode()
        _post(f"https://api.telegram.org/bot{c['telegram_token']}/sendMessage", body,
              "application/x-www-form-urlencoded")

    def _send_discord(self, title: str, message: str, level: str) -> None:
        body = json.dumps({"content": f"**{title}**\n{message}"[:1900]}).encode()
        _post(self.cfg["discord_webhook"], body, "application/json")

    def _send_webhook(self, title: str, message: str, level: str) -> None:
        body = json.dumps({"title": title, "message": message, "level": level,
                           "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}).encode()
        _post(self.cfg["webhook_url"], body, "application/json")

    def _send_email(self, title: str, message: str, level: str) -> None:
        c = self.cfg
        msg = EmailMessage()
        msg["Subject"] = f"[ibc2] {title}"
        msg["From"] = c.get("email_from") or c.get("smtp_user") or c["email_to"]
        msg["To"] = c["email_to"]
        msg.set_content(message)
        host, port = c["smtp_host"], int(c.get("smtp_port") or 587)
        security = (c.get("smtp_security") or "starttls").lower()
        context = ssl.create_default_context()
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as s:
                self._smtp_finish(s, msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                if security == "starttls":
                    s.starttls(context=context)
                self._smtp_finish(s, msg)

    def _smtp_finish(self, s: smtplib.SMTP, msg: EmailMessage) -> None:
        if self.cfg.get("smtp_user"):
            s.login(self.cfg["smtp_user"], self.cfg.get("smtp_password", ""))
        s.send_message(msg)
