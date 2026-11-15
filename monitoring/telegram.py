from __future__ import annotations

import json
import os
from urllib.error import HTTPError
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
    for attempt in range(2):
        request = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urlencode(data).encode("utf-8"),
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            with error:
                try:
                    body = json.loads(error.read(4096))
                except (ValueError, OSError):
                    body = {}
            if not isinstance(body, dict):
                body = {}
            parameters = body.get("parameters")
            migrated_id = parameters.get("migrate_to_chat_id") if isinstance(parameters, dict) else None
            if error.code == 400 and attempt == 0 and type(migrated_id) is int and migrated_id < 0 and str(migrated_id) != chat_id:
                print(f"[TELEGRAM] {chat_id_env} migrated to a supergroup; retrying delivery")
                data["chat_id"] = str(migrated_id)
                continue
            description = body.get("description")
            if not isinstance(description, str):
                description = ""
            for secret in {token, chat_id, data["chat_id"]}:
                description = description.replace(secret, "[redacted]")
            description = " ".join(description.split())
            reason = f" — {description[:240]}" if description else ""
            raise RuntimeError(f"Telegram sendMessage to {chat_id_env} failed (HTTP {error.code}){reason}") from None
        if not result.get("ok"):
            raise RuntimeError(f"Telegram sendMessage to {chat_id_env} failed")
        return True


def send_telegram(message: str) -> bool:
    return _send(message, chat_id_env="TELEGRAM_HEALTH_CHAT_ID")


def send_digest(message: str) -> bool:
    return _send(
        message,
        chat_id_env="TELEGRAM_DIGEST_CHAT_ID",
        parse_mode="HTML",
    )
