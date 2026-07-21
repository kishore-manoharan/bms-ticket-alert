"""Telegram delivery with explicit error handling."""
from __future__ import annotations

import logging
import requests


class NotificationError(RuntimeError):
    pass


def send_telegram(bot_token: str, chat_id: str, message: str) -> None:
    """Send one Telegram message, raising when Telegram does not accept it."""
    if not bot_token or not chat_id:
        raise NotificationError("BOT_TOKEN and CHAT_ID must both be configured")
    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=20,
    )
    try:
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NotificationError(f"Telegram request failed: {exc}") from exc
    if not payload.get("ok"):
        raise NotificationError(f"Telegram rejected the message: {payload}")
    logging.info("Telegram accepted notification (message_id=%s)", payload["result"].get("message_id"))
