from __future__ import annotations

import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from monitoring.health import HealthResult


def format_transition(result: HealthResult, transition: str) -> str:
    if transition == "recovered":
        return (
            f"🟢 {result.source} RECOVERED\n"
            f"Status: {result.status}\n"
            f"Items: {result.count}\n"
            f"Checked: {result.checked_at}"
        )
    return (
        f"🔴 {result.source} HEALTH ALERT\n"
        f"Status: {result.status}\n"
        f"Items: {result.count}\n"
        f"Problem: {result.message}\n"
        f"Checked: {result.checked_at}"
    )


def _send(message: str, *, chat_id_env: str, parse_mode: str | None = None) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv(chat_id_env)
    if not token or not chat_id:
        print(f"[TELEGRAM] {chat_id_env} or bot token not configured; notification skipped")
        return False

    data = {"chat_id": chat_id, "text": message}
    if parse_mode:
        data["parse_mode"] = parse_mode
    payload = urlencode(data).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        if response.status >= 400:
            raise RuntimeError(f"Telegram HTTP {response.status}")
        result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")
    return True


def send_telegram(message: str) -> bool:
    return _send(message, chat_id_env="TELEGRAM_HEALTH_CHAT_ID")


def send_digest(message: str) -> bool:
    return _send(
        message,
        chat_id_env="TELEGRAM_DIGEST_CHAT_ID",
        parse_mode="HTML",
    )
