"""Shared Telegram send helper."""
import os
import requests


def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - message not sent]")
        print(text)
        return None
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text}
    )
    return resp
