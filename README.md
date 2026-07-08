# Daily Inbox Triage Agent — final v1

## Folder structure

```
inbox-agent/
├── .github/
│   └── workflows/
│       ├── poll.yml              # runs every 5 min - real-time classification
│       └── daily_summary.yml     # runs once daily - rollup report
├── .gitignore                    # excludes credentials.json, token.json, __pycache__
├── get_refresh_token.py          # ONE-TIME local script only - never deployed
├── poll_and_classify.py          # main real-time script (runs on GitHub Actions)
├── daily_summary.py              # daily rollup script (runs on GitHub Actions)
├── state/
│   └── .gitkeep                  # daily state files (YYYY-MM-DD.json) land here,
│                                  # committed back to the repo automatically by poll.yml
└── tools/
    ├── gmail_tools.py            # Gmail OAuth (interactive + headless) + fetch/star/label
    ├── state.py                  # persistent processed-email tracking
    └── telegram_tools.py         # Telegram send helper (chunking, failure logging)
```

Two files are LOCAL-ONLY and must never be committed (already in .gitignore):
- `credentials.json` — downloaded from Google Cloud Console
- `token.json` — only created if you ever run the interactive auth path locally

## What it does

**poll_and_classify.py** (every ~5 min via GitHub Actions):
1. Fetches today's emails, filters to only ones not yet processed (tracked in `state/`)
2. Sends new ones to Groq (Llama 3.3 70B) for classification, reading full body text
   (not just Gmail's short snippet) - avoids misreading based on truncated context
3. For each email, decides:
   - **important**: Tanmay needs to DO something (respond/schedule/attend), OR a human is
     personally reaching out, OR a genuinely confirmed scheduled event verified in the body
   - **junk**: promotional emails, algorithmic job-alert/job-matching notifications
     (LinkedIn, Indeed, Instahyre, etc.) regardless of single-job or digest format
   - **uncertain**: informational/FYI content needing no action but not spam either (e.g.
     application acknowledgments with no next step) - genuinely ambiguous cases also land here
4. Applies actions: stars important, labels junk with a custom "Spam-Agent" label (never
   deletes, never moves out of inbox - fully recoverable), leaves uncertain untouched
5. Sends ONE batched Telegram message per run for anything important (not one ping per
   email), including when the email was actually received (Gmail's own timestamp, not the
   spoofable Date header)

**daily_summary.py** (once daily via GitHub Actions):
- Reads everything the poller logged that day from `state/`
- Does NOT re-fetch or re-classify anything - purely reports
- Sends one rollup Telegram message grouped by important/junk/uncertain

## Guardrails built in (worth knowing for explaining this project)
- Every email fetched must get a classification decision - code rejects incomplete submissions
- No phantom email IDs allowed in decisions (hallucination guard)
- "uncertain" is a genuine third option, not a fallback - the agent can choose not to act
  when unsure, which matters more than usual since a false-positive during an active job
  search (wrongly burying a real opportunity) is worse than a slower manual glance
- Telegram messages over 4096 chars are split into numbered chunks instead of failing silently
- Telegram send failures are logged, not silently swallowed, and don't crash the run since
  classification/labeling already succeeded by that point

## One-time setup (if starting fresh)

### 1. Groq API key
console.groq.com/keys → free key

### 2. Telegram bot
@BotFather on Telegram → /newbot → get token. Message your bot once, then visit
`https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat ID.

### 3. Gmail API
1. console.cloud.google.com → new project → enable Gmail API
2. Google Auth Platform → Audience → add yourself as a Test User (required while
   the app is in Testing mode)
3. Clients → Create Client → Desktop app → download as `credentials.json`,
   place in this folder locally

### 4. Get your refresh token (the one unavoidable local/manual step)
```
pip3 install google-auth google-auth-oauthlib google-api-python-client
python3 get_refresh_token.py
```
Opens a browser once for consent, then prints three values to save as GitHub Secrets.

### 5. Push to GitHub (public repo recommended - see below for why)
```
git init
git add .
git commit -m "Inbox triage agent"
git remote add origin <your-repo-url>
git branch -M main
git push -u origin main
```

### 6. Add 6 GitHub Secrets
Repo → Settings → Secrets and variables → Actions → New repository secret:
`GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GMAIL_CLIENT_ID`,
`GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`

### 7. Test manually before trusting the schedule
Actions tab → "Poll and Classify Inbox" → Run workflow → check the logs

## Why public repo for Actions minutes
Private repos get 2000 free Actions minutes/month. Polling every 5 minutes uses
roughly 4,300 min/month - over that limit. Public repos get unlimited free minutes,
and nothing sensitive ever lives in the code itself (only GitHub Secrets, which stay
encrypted regardless of repo visibility). If you'd rather keep it private, reduce the
poll frequency in `.github/workflows/poll.yml` (e.g. `*/15 * * * *` instead of `*/5`).

## Known limitations, stated honestly
- GitHub's cron schedule isn't precise - can lag a few minutes under platform load
- If Gmail/Groq has an outage during a scheduled run, that cycle is skipped with no
  retry - the next scheduled run picks up whatever was missed
- Refresh tokens can be revoked by Google after 6 months of inactivity, or if you
  change your Google account password - if polling stops working, re-run
  get_refresh_token.py and update the GitHub Secret
- A previous wrong classification (e.g. a star from before a prompt fix) isn't
  automatically corrected by a later, better classification - stars only get added,
  never removed, in the current version
