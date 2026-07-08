"""
Runs once daily (e.g. 9pm via cron) - reads everything poll_and_classify.py
logged today and sends ONE rollup summary via Telegram. Does NOT re-fetch
or re-classify anything - purely reports on what already happened.
"""
import json
import os
from datetime import datetime
from groq import Groq
from tools.state import get_todays_entries
from tools.telegram_tools import send_telegram

MODEL = "llama-3.3-70b-versatile"

SUMMARY_PROMPT = """Write a short, friendly daily email summary for Tanmay based ONLY on
the classified emails given below - do not invent or generalize about any email not listed.
Group by important / junk / uncertain. For important emails, list sender + subject + when it
was received (received_at field, if present) + why. For junk, just give a count. For uncertain,
list sender + subject briefly so he can glance at them himself. Keep it tight - this is a
Telegram message, not a report. Plain text only.
"""


def build_summary(entries: list) -> str:
    if not entries:
        return "No emails processed today."

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": json.dumps(entries, indent=2)},
        ],
        temperature=0.4,
    )
    summary = response.choices[0].message.content

    # GUARDRAIL: cheap faithfulness check - every entry's sender should be
    # traceable in the summary text somewhere, catches gross omission/invention
    missing = [e["sender"] for e in entries if e["action"] == "important" and e["sender"] not in summary]
    if missing:
        summary += f"\n\n(Note: {len(missing)} important sender(s) may not be fully reflected above - check Gmail directly.)"

    return summary


if __name__ == "__main__":
    if not os.environ.get("GROQ_API_KEY"):
        print("ERROR: set GROQ_API_KEY first.")
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        entries = get_todays_entries(today)
        summary = build_summary(entries)

        header = f"📬 Daily inbox summary — {today}\n\n"
        full_message = header + summary

        print(full_message)
        send_telegram(full_message)
