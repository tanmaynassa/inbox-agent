"""
Runs frequently (e.g. every 5 min via cron) - checks for NEW emails since
the last run, classifies only those (already-processed ones are skipped,
tracked via tools/state.py), applies star/label actions immediately, and
sends an INSTANT Telegram ping for anything classified important.

This is the "real-time" half of the system. The daily summary (separate
script, daily_summary.py) reads what this script logged throughout the day
and sends one rollup - it does NOT re-classify anything.
"""
import json
import os
import time
from datetime import datetime
from groq import Groq
from groq import BadRequestError
from tools.gmail_tools import get_gmail_service_headless, fetch_todays_emails, star_email, label_as_spam
from tools.state import get_processed_ids, mark_processed
from tools.telegram_tools import send_telegram

MODEL = "llama-3.3-70b-versatile"
MAX_API_RETRIES = 3

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "classify_and_act",
            "description": "Submit your classification decision for EVERY new email given to "
                            "you. Every email ID provided must appear exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decisions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "action": {"type": "string", "enum": ["important", "junk", "uncertain"]},
                                "reason": {"type": "string", "description": "One sentence why"}
                            },
                            "required": ["id", "action", "reason"]
                        }
                    }
                },
                "required": ["decisions"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are Tanmay's inbox triage agent, running frequently throughout the day
(not just once). He is actively job hunting (Product Analyst / Business Analyst roles) alongside
his regular work and personal email.

You'll be given a batch of NEW emails (subject, sender, and body text - READ THE BODY, don't
just pattern-match on the subject line or sender name). For each one, decide:

- "important": Tanmay needs to DO something soon - respond, schedule, attend, submit something -
  OR a human is personally reaching out to him (not an automated system) - OR it's a confirmed,
  scheduled event (an interview/call with an actual date/time stated IN THE BODY, verified by
  you reading the body, not assumed from the subject line).

- "junk": promotional emails, newsletters, algorithmic job-alert/job-matching notifications
  (LinkedIn Job Alerts, Indeed job matches, Instahyre, Naukri, etc.) - these are unsolicited
  system-generated suggestions, NOT responses to anything Tanmay did, regardless of whether
  the subject mentions one job or ten. A single-job alert from an automated job board is just
  as much junk as a "10 jobs matching your profile" digest - the FORMAT doesn't matter, only
  whether a human is asking him to do something.

- "uncertain": informational/FYI content that needs no action but isn't spam either - e.g. an
  automated "we received your application" acknowledgment with NO next step mentioned, a LinkedIn
  connection notification, or anything genuinely ambiguous. This is NOT a lower-confidence version
  of "important" - it's specifically for things that don't need a star (no action pending) but
  also don't belong being labeled junk (they're legitimate, just not urgent).

Critical distinction that matters most: an application ACKNOWLEDGMENT (e.g. "thank you for
applying", no next step stated) is "uncertain", NOT "important" - Tanmay doesn't need to do
anything in response to it. Only mark something "important" if there's a real pending action
or a genuinely scheduled event you can verify in the body text.

When you're not sure, choose "uncertain" rather than guessing "junk" or "important".

Call classify_and_act with a decision for every email given - no skipping any.
"""


def classify_batch(client, emails: list) -> list:
    """Returns list of {id, action, reason} for the given emails."""
    compact = [{"id": e["id"], "subject": e["subject"], "sender": e["sender"], "body": e["body"][:800]} for e in emails]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"New emails to classify:\n{json.dumps(compact, indent=2)}"}
    ]

    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOLS,
                tool_choice={"type": "function", "function": {"name": "classify_and_act"}},
                temperature=0.3,
            )
            break
        except BadRequestError as e:
            bad_gen = (getattr(e, "body", None) or {}).get("error", {}).get("failed_generation", "")
            print(f"[api retry {attempt}/{MAX_API_RETRIES}: {bad_gen[:80]}...]")
            if attempt == MAX_API_RETRIES:
                return []
            time.sleep(1)

    msg = response.choices[0].message
    if not msg.tool_calls:
        return []
    fn_args = json.loads(msg.tool_calls[0].function.arguments or "{}")
    decisions = fn_args.get("decisions", [])

    # GUARDRAIL: every given email must be covered, no phantom IDs
    given_ids = {e["id"] for e in emails}
    decided_ids = {d["id"] for d in decisions}
    if given_ids - decided_ids:
        print(f"[guardrail warning: {len(given_ids - decided_ids)} emails not classified - "
              f"leaving them uncertain by default]")
        for missing_id in given_ids - decided_ids:
            decisions.append({"id": missing_id, "action": "uncertain", "reason": "not classified by model"})
    decisions = [d for d in decisions if d["id"] in given_ids]  # drop any phantom IDs
    return decisions


def run_poll():
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    service = get_gmail_service_headless()

    today = datetime.now().strftime("%Y-%m-%d")
    processed_ids = get_processed_ids(today)

    all_emails = fetch_todays_emails(service)
    new_emails = [e for e in all_emails if e["id"] not in processed_ids]

    if not new_emails:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] No new emails since last check.")
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(new_emails)} new email(s) - classifying...")
    decisions = classify_batch(client, new_emails)
    emails_by_id = {e["id"]: e for e in new_emails}

    important_this_run = []  # collected and sent as ONE message, not one ping per email

    for d in decisions:
        email = emails_by_id[d["id"]]
        if d["action"] == "important":
            star_email(service, d["id"])
            important_this_run.append((email, d["reason"]))
        elif d["action"] == "junk":
            label_as_spam(service, d["id"])
        # uncertain -> no action

        mark_processed({
            "id": d["id"],
            "subject": email["subject"],
            "sender": email["sender"],
            "action": d["action"],
            "reason": d["reason"],
            "received_at": email["received_at"],
            "timestamp": datetime.now().isoformat(),
        }, today)

    if important_this_run:
        if len(important_this_run) == 1:
            email, reason = important_this_run[0]
            msg = (f"⚠️ Important email:\n\n"
                   f"From: {email['sender']}\n"
                   f"Subject: {email['subject']}\n"
                   f"Received: {email['received_at']}\n"
                   f"Why: {reason}")
        else:
            lines = [f"⚠️ {len(important_this_run)} important emails:\n"]
            for email, reason in important_this_run:
                lines.append(f"• {email['sender']}\n  {email['subject']}\n  Received: {email['received_at']}\n  {reason}")
            msg = "\n\n".join(lines)
        send_telegram(msg)

    print(f"Processed {len(decisions)} email(s).")


if __name__ == "__main__":
    if not os.environ.get("GROQ_API_KEY"):
        print("ERROR: set GROQ_API_KEY first.")
    else:
        run_poll()
