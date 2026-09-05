from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from monitoring.telegram import send_telegram

PRAGUE = ZoneInfo("Europe/Prague")
ALERT_DAYS = {30, 14, 7, 3, 1, 0}


def parse_expiry(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("CRON_PAT_EXPIRES_AT must use YYYY-MM-DD format") from exc


def days_until_expiry(expiry: date, *, today: date | None = None) -> int:
    local_today = today or datetime.now(PRAGUE).date()
    return (expiry - local_today).days


def _days_text(days: int) -> str:
    if days == 1:
        return "1 den"
    if 2 <= days <= 4:
        return f"{days} dny"
    return f"{days} dní"


def build_expiry_alert(expiry: date, days_left: int) -> str | None:
    formatted = expiry.strftime("%d.%m.%Y")
    if days_left < 0:
        overdue = abs(days_left)
        return (
            "🚨 GitHub token je po expiraci\n"
            f"PAT pro cron-job.org expiroval před {_days_text(overdue)}.\n"
            f"Expirace: {formatted}\n"
            "Vytvoř nový PAT, nahraď ho na cron-job.org a aktualizuj secret CRON_PAT_EXPIRES_AT."
        )
    if days_left not in ALERT_DAYS:
        return None
    if days_left == 0:
        return (
            "🚨 GitHub token expiruje dnes\n"
            "PAT pro cron-job.org expiruje dnes.\n"
            f"Expirace: {formatted}\n"
            "Vytvoř nový PAT a nahraď ho na cron-job.org."
        )
    return (
        "⚠️ GitHub token brzy expiruje\n"
        f"PAT pro cron-job.org vyprší za {_days_text(days_left)}.\n"
        f"Expirace: {formatted}\n"
        "Vytvoř nový PAT a nahraď ho na cron-job.org."
    )


def main() -> int:
    raw_expiry = os.getenv("CRON_PAT_EXPIRES_AT", "").strip()
    if not raw_expiry:
        print("[TOKEN-EXPIRY] CRON_PAT_EXPIRES_AT not configured; check skipped")
        return 0

    expiry = parse_expiry(raw_expiry)
    days_left = days_until_expiry(expiry)
    print(f"[TOKEN-EXPIRY] expiry={expiry.isoformat()} days_left={days_left}")

    message = build_expiry_alert(expiry, days_left)
    if not message:
        print("[TOKEN-EXPIRY] no alert threshold reached")
        return 0

    if not send_telegram(message):
        print("[TOKEN-EXPIRY] Telegram not configured; alert skipped")
        return 0

    print("[TOKEN-EXPIRY] Telegram alert sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
