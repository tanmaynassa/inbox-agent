# Daily Inbox Triage Agent — v3 (deployed on GitHub Actions, free)

## The one manual step that can't be automated away
Google's OAuth requires a human to click "approve" in a browser at least
once - there's no way around this for any Gmail integration, by design
(it's a security feature, not a limitation of this project). Everything
AFTER that one click runs entirely on GitHub's servers, not your machine.

## Be honest about GitHub Actions minutes (read before picking repo visibility)
- **Private repo**: 2000 free Actions minutes/month
- **Public repo**: unlimited free Actions minutes
- Polling every 5 minutes ≈ 288 runs/day × ~30 sec each ≈ 144 min/day ≈
  **4,300 min/month** - this EXCEEDS the private repo free tier.

Two honest options:
1. **Use a public repo.** No personal data or secrets are ever in the code
   itself - only referenced as GitHub Secrets (encrypted, never exposed in
   logs or to anyone browsing the repo). This is the simplest way to keep
   true 5-minute polling for $0.
2. **Keep it private, reduce polling to every 15 min instead** (edit the
   cron in `.github/workflows/poll.yml` to `*/15 * * * *`) - fits
   comfortably in the 2000 free minutes. Less real-time, still much
   better than once a day.

Your call - I'd lean public repo since there's genuinely nothing sensitive
in the code, but it's your inbox automation, your choice.

## One-time setup

### 1. Get Gmail OAuth credentials
1. console.cloud.google.com -> enable Gmail API -> OAuth client ID
   (Desktop app) -> download as `credentials.json`
2. Place it in this folder LOCALLY (do not commit it - .gitignore already
   excludes it)

### 2. Get your refresh token (the one local run needed)
```
pip install google-auth google-auth-oauthlib google-api-python-client
python3 get_refresh_token.py
```
This opens a browser once for you to approve access, then prints three
values - copy them, you'll need them in step 4.

### 3. Create a GitHub repo and push this code
```
git init
git add .
git commit -m "Inbox triage agent"
git remote add origin <your-new-repo-url>
git push -u origin main
```
(credentials.json and token.json are gitignored - they won't be pushed,
which is correct, they're not needed on GitHub at all)

### 4. Add GitHub Secrets
Repo -> Settings -> Secrets and variables -> Actions -> New repository secret.
Add each of these:
- `GROQ_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GMAIL_CLIENT_ID` (from step 2's output)
- `GMAIL_CLIENT_SECRET` (from step 2's output)
- `GMAIL_REFRESH_TOKEN` (from step 2's output)

### 5. Enable Actions and test manually first
Repo -> Actions tab -> you'll see both workflows listed. Click "Poll and
Classify Inbox" -> "Run workflow" to trigger it manually once and check
the logs before letting it run on schedule - same principle as testing
locally, just done through GitHub's UI instead of your terminal.

## What runs automatically after this
- `poll.yml` — every 5 (or 15) minutes, classifies new emails, stars/labels,
  instant Telegram ping for anything important
- `daily_summary.yml` — once daily (default 8:30pm IST, edit the cron in
  the file to change), sends the rollup

Both commit their results back to the repo's `state/` folder automatically
- that's how the two workflows share state without a database.

## Files
- `poll_and_classify.py` / `daily_summary.py` — same logic as before, now
  using headless auth (no browser needed at runtime)
- `get_refresh_token.py` — the ONE local script, run once, never deployed
- `tools/gmail_tools.py` — now has both interactive (local) and headless
  (CI) auth paths
- `.github/workflows/` — the two scheduled jobs
- `state/` — daily classification logs, now living in the repo itself

## Known limitations to be upfront about
- GitHub's schedule isn't millisecond-precise - can lag several minutes
  under platform load, especially for 5-min intervals
- If Gmail's API or Groq's API has an outage during a scheduled run, that
  cycle is just skipped (no retry-later logic yet) - the next scheduled
  run will pick up anything missed
- Refresh tokens can be revoked by Google if unused for 6 months, or if
  you change your Google account password - if polling suddenly stops
  working, re-run get_refresh_token.py locally and update the GitHub Secret
