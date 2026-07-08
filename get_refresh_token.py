"""
One-time LOCAL script - run this once on your own machine, not on GitHub
Actions. It does the interactive Google consent (the one unavoidable manual
step) and prints out a refresh token you save as a GitHub Secret. After
this, the actual agent runs entirely headless on GitHub's servers.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")

if __name__ == "__main__":
    if not os.path.exists(CREDS_PATH):
        print(f"credentials.json not found at {CREDS_PATH}")
        print("Download it from Google Cloud Console first (see README).")
        exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)  # opens a browser once, for this one approval

    print("\n" + "=" * 60)
    print("SAVE THESE AS GITHUB SECRETS (Settings -> Secrets and variables -> Actions):")
    print("=" * 60)
    print(f"GMAIL_CLIENT_ID = {creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET = {creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN = {creds.refresh_token}")
    print("=" * 60)
    print("\nDo NOT commit these to the repo - only add them as GitHub Secrets.")
    print("This script (get_refresh_token.py) and credentials.json should also")
    print("NOT be committed - they're only needed for this one local run.")
