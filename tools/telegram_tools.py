"""Shared Telegram send helper."""
import os
import requests

TELEGRAM_MAX_LEN = 4096  # Telegram's hard limit per message


def send_telegram(text: str):
    """
    Sends a message via Telegram. If text exceeds Telegram's 4096-char limit,
    splits it into multiple messages rather than silently failing/truncating.
    Logs (doesn't raise) on send failure, so a Telegram outage doesn't crash
    the whole poll/summary run - the classification/labeling already happened
    successfully by this point, only the notification would be lost.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - message not sent]")
        print(text)
        return None

    chunks = [text[i:i + TELEGRAM_MAX_LEN] for i in range(0, len(text), TELEGRAM_MAX_LEN)] or [text]

    responses = []
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            chunk = f"[{i + 1}/{len(chunks)}]\n{chunk}"
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": chunk},
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[telegram send failed: {resp.status_code} - {resp.text[:200]}]")
            responses.append(resp)
        except requests.RequestException as e:
            print(f"[telegram send failed: {e}]")
            responses.append(None)

    return responses

