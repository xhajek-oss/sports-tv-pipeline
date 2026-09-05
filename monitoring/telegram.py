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


def send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[TELEGRAM] secrets not configured; notification skipped")
        return False

    payload = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        if response.status >= 400:
            raise RuntimeError(f"Telegram HTTP {response.status}")
        data = json.loads(response.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
    return True
