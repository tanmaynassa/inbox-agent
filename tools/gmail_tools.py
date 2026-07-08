"""
Gmail API tools: auth, fetch today's emails, star important ones,
label likely-junk ones with a custom "Spam-Agent" label.

Deliberately does NOT delete or move anything out of the inbox - labeling
only. This is a safety choice: a wrongly-deleted or wrongly-archived
important email (e.g. a recruiter reply, mid job search) is a much worse
failure than a junk email that sits labeled but still visible.

One-time setup required (see README):
1. Google Cloud Console -> enable Gmail API -> OAuth client (Desktop app)
2. Download credentials.json, place in this project's root folder
3. First run opens a browser for one-time auth, then caches token.json
   locally so future runs don't need to re-auth
"""
import os
import base64
from datetime import datetime, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # read + label/star, NOT delete permission
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CREDS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
SPAM_LABEL_NAME = "Spam-Agent"


def get_gmail_service():
    """Interactive auth - for local runs only. Opens a browser if no cached token."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise RuntimeError(
                    f"credentials.json not found at {CREDS_PATH}. "
                    "Download it from Google Cloud Console (OAuth client, Desktop app) first."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)  # opens browser once for consent
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_gmail_service_headless():
    """
    Non-interactive auth for CI/CD (GitHub Actions) - builds credentials
    directly from a stored refresh token, no browser needed. The refresh
    token is obtained once via get_refresh_token.py run locally, then
    stored as a GitHub Secret and passed in as env vars here.
    """
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN not set. "
            "Run get_refresh_token.py locally once to obtain these."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())  # exchange refresh token for a fresh access token
    return build("gmail", "v1", credentials=creds)


def _get_or_create_spam_label(service) -> str:
    """Returns the label ID for Spam-Agent, creating it if it doesn't exist yet."""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"] == SPAM_LABEL_NAME:
            return label["id"]
    new_label = service.users().labels().create(
        userId="me",
        body={"name": SPAM_LABEL_NAME, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    ).execute()
    return new_label["id"]


def _extract_body(payload) -> str:
    """Pulls plain text body out of Gmail's nested MIME structure."""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
            # recurse into nested multipart (common with multipart/alternative)
            if "parts" in part:
                result = _extract_body(part)
                if result:
                    return result
    elif "body" in payload and "data" in payload["body"]:
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    return ""


def fetch_todays_emails(service) -> list:
    """Fetches emails received since midnight today (in local time)."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    query_date = today_start.strftime("%Y/%m/%d")
    results = service.users().messages().list(
        userId="me", q=f"after:{query_date}", maxResults=50
    ).execute()
    message_refs = results.get("messages", [])

    emails = []
    for ref in message_refs:
        msg = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        body = _extract_body(msg["payload"])

        # internalDate is Gmail's own record of when the message was received,
        # in epoch milliseconds - more reliable than parsing the email's own
        # "Date" header, which senders can set to anything
        received_dt = datetime.fromtimestamp(int(msg["internalDate"]) / 1000)

        emails.append({
            "id": msg["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "sender": headers.get("From", "(unknown sender)"),
            "snippet": msg.get("snippet", ""),
            "body": body[:1500],  # cap length - plenty for classification, keeps prompt small
            "received_at": received_dt.strftime("%b %d, %I:%M %p"),  # e.g. "Jul 08, 03:23 PM"
        })
    return emails


def star_email(service, msg_id: str):
    service.users().messages().modify(
        userId="me", id=msg_id, body={"addLabelIds": ["STARRED"]}
    ).execute()


def label_as_spam(service, msg_id: str):
    label_id = _get_or_create_spam_label(service)
    service.users().messages().modify(
        userId="me", id=msg_id, body={"addLabelIds": [label_id]}
    ).execute()
