# Setup & Operations

What's done, what's left, and how to do it.

---

## ✅ What's already working

- **GitHub Actions workflow** — `.github/workflows/daily_run.yml`
  - Auto-runs daily at **6:00 AM Perth time** (22:00 UTC previous day) on `main`
  - Manual trigger any time: [Actions tab](https://github.com/Ruitan1999/report-extractor/actions) → "Daily Report Extractor" → Run workflow (optional `target_date` input as `YYYY-MM-DD`)
- **Gmail integration** — reads PDFs from `ruitan1520@gmail.com` via OAuth
- **Google Sheets writes** — service account writes to scorecard ID `1LaMHjhLXQ8m-4Kke0TFOH9q5u58sz8z3Dm-mBZ0kLso`
- **Sunday handling** — writes BOTH the daily Sunday row AND a `Week ending D/M/YY` summary row
- **William St** — fully configured with test sender (`ruitanhuang@outlook.com`) and verified end-to-end against the test sheet

---

## 🔴 Remaining setup

### 1. Sender emails for the other 6 stores (BLOCKER for full production)

Currently `config.py` has placeholder emails for everything except William St. Until these are filled in, only William St will be processed; the other 6 will show as alerts every run.

**To do:** Get the sender email address each store manager emails reports from, and update `config.py`:

```python
STORES = [
    {"name": "William St",   "tab": "William St",   "sender": "ruitanhuang@outlook.com"},  # ← currently the test sender; swap for real William St sender when ready
    {"name": "Hay St",       "tab": "Hay St",       "sender": "TBC"},
    {"name": "Ascot Waters", "tab": "Ascot Waters", "sender": "TBC"},
    {"name": "Crown",        "tab": "Crown",        "sender": "TBC"},
    {"name": "Duncraig",     "tab": "Duncraig",     "sender": "TBC"},
    {"name": "Whitfords",    "tab": "Whitfords",    "sender": "TBC"},
    {"name": "New Store",    "tab": "New Store",    "sender": "TBC"},
]
```

After updating, commit and push to `main` — the next scheduled (or manual) run will pick them up immediately.

**Important constraints:**
- All 7 stores must email the **same inbox** — `ruitan1520@gmail.com` (the inbox the GMAIL_TOKEN was minted for)
- The `tab` name in `config.py` must match the Google Sheet tab name **character-for-character** (case, spaces, punctuation)
- The Gmail search uses `from:<sender>` — if a manager sometimes emails from a different address (personal forwarding, etc.), it won't match. Add multi-sender support later if needed.

---

### 2. Production sheet ID (when ready to leave test mode)

Currently writes to the **test** sheet:
`1LaMHjhLXQ8m-4Kke0TFOH9q5u58sz8z3Dm-mBZ0kLso`

To switch to the real production sheet:

1. Share the real sheet with the service account email:
   `report-extractor-sheets@report-extractor-497204.iam.gserviceaccount.com` (Editor)
2. Copy the production sheet ID from its URL (`/spreadsheets/d/<SHEET_ID>/edit`)
3. Update the `SCORECARD_SHEET_ID` GitHub secret: [Settings → Secrets](https://github.com/Ruitan1999/report-extractor/settings/secrets/actions)
4. Verify tab names in production sheet match `config.py` exactly

---

### 3. Daily digest email (optional — alerts/data currently only in Actions logs)

When SMTP secrets are configured, after every run the script sends ONE email containing:
- **KPI summary table** — one row per store, columns: Projected Sales, Actual Sales, Sales Comp, Sales Proj Opp, GC Comp, Cash +/-, Waste, Labour Proj, SPCH, AHR
- **Issues list** — any stores that failed to extract or write

Subject line: `Daily Store Report — 2026-04-13 (1 OK, 6 issues)`

Without SMTP secrets, this same digest is printed to the Actions run log only.

To enable email, add 3 GitHub secrets:

| Secret | Value |
|---|---|
| `ALERT_EMAIL` | Address to send alerts to (e.g. `ruitan1520@gmail.com`) |
| `SMTP_USER` | Gmail address to send FROM |
| `SMTP_PASS` | **App password** (not your Google password) — generate at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |

Add at: [Settings → Secrets](https://github.com/Ruitan1999/report-extractor/settings/secrets/actions)

If only some are set, alerts silently fall back to console-only.

---

### 4. Unknown columns — source TBD

These scorecard columns currently leave blank because the source report isn't confirmed:

| Excel col | Field | Status |
|---|---|---|
| O | Training Hours | Not in DDCR — what report? |
| S, T | KVS Peak / Shift | Not in any sample report |
| U, V | R2P Peak / Shift | Not in any sample report |
| W, X | Side 2 Peak / Shift | Not in any sample report |
| Y | Delivery Time | Not in any sample report |
| AD | Actual Mgr Hours | Not confirmed in DDCR |
| AE | Sick Mgr Hours | Not in any sample report |
| AF | Sick Crew Hours | Not in any sample report |

Also worth confirming:
- **Refund / Promo / Manager Meal** (cols Z/AA/AB) — currently pulled from Sales Ledger, but you mentioned they might be in the daily DDCR. Confirm from a real daily PDF.
- **QCR** — daily uses `QCR Daily` (single day, 25.99%). Should it use `QCR Progressive` (period-to-date) instead?
- **Ros Mgr Hours** (col AC) — currently `Projected Crew Hours` from DDCR. Is this total crew or mgr-only?

For each missing source, once identified:
- Add the extraction logic to `pdf_extractor.py`
- Wire it into `extract_all()` and the main pipeline
- Update the column mapping in `config.py`

---

### 5. Gmail token re-auth (every ~7 days while OAuth app is in Testing mode)

⚠ **This is the most important ongoing operation.**

Because the OAuth consent screen is in **Testing** status (correct for non-public app), Google expires `refresh_token`s after 7 days. The workflow will fail with `invalid_grant` errors when this happens.

**To re-auth:**

```bash
cd /Users/Ruitan/Documents/report-extractor
python3 auth_gmail.py "/Users/Ruitan/Downloads/client_secret_166143871550-98rp7j69tts61aat9vqsc2du8icfpshe.apps.googleusercontent.com.json"
# A browser opens — sign in as ruitan1520@gmail.com → approve
# This produces a new gmail_token.json
cat gmail_token.json
# Copy the entire JSON output → paste into GMAIL_TOKEN secret on GitHub
```

Update the secret at: [Settings → Secrets → GMAIL_TOKEN](https://github.com/Ruitan1999/report-extractor/settings/secrets/actions)

**Set a recurring calendar reminder** every 6 days to re-auth before it expires.

**Permanent fix:** Submit the OAuth app for Google verification ([apps.google.com/console](https://console.cloud.google.com/apis/credentials/consent?project=report-extractor-497204) → Publish app → Submit for verification). Takes a few days to a few weeks for `gmail.readonly` scope. Once verified, tokens last indefinitely. Worth doing if the weekly re-auth gets annoying.

---

## 🛠 Operations runbook

### Manually trigger a run for a specific date

Via web UI:
1. [Actions tab](https://github.com/Ruitan1999/report-extractor/actions) → Daily Report Extractor → Run workflow
2. Optional: enter `target_date` as `YYYY-MM-DD` (leave blank for yesterday)

Via CLI:
```bash
gh workflow run daily_run.yml -R Ruitan1999/report-extractor -f target_date=2026-04-19
```

### Backfill a missed day

Same as manual trigger — just pick the date. The pipeline is idempotent (re-running the same date overwrites the existing row, doesn't duplicate).

### Run locally (for debugging)

```bash
# Set the same env vars the workflow uses
export GMAIL_OAUTH_CREDENTIALS="$(cat ~/Downloads/client_secret_166143871550-98rp7j69tts61aat9vqsc2du8icfpshe.apps.googleusercontent.com.json)"
export GMAIL_TOKEN="$(cat gmail_token.json)"
export GOOGLE_SHEETS_SERVICE_ACCOUNT="$(cat ~/Downloads/report-extractor-497204-df0f6906df9f.json)"
export SCORECARD_SHEET_ID="1LaMHjhLXQ8m-4Kke0TFOH9q5u58sz8z3Dm-mBZ0kLso"

# Run for a specific date
python3 main.py 2026-04-19

# Or just the previous day (default)
python3 main.py
```

If env vars are NOT set, each module falls back to local mode:
- Gmail → reads `Sample report/` folder
- Sheets → writes to local `Weekly Scorecard tracker Q2 2026.xlsx`
- Alerter → prints to stdout

### Check what an extraction returns without writing

```bash
python3 pdf_extractor.py     # runs the built-in test suite
```

### Adding a new store

1. Add an entry to `STORES` list in `config.py` with `name`, `tab`, `sender`
2. Confirm the matching tab exists in the Google Sheet (and is shared with the service account)
3. Commit, push, done

### Removing or renaming a store

1. Either delete the entry from `STORES` (script will stop processing it)
2. Or change the `tab` name — make sure the sheet tab is renamed too

---

## 📅 Tracked technical debt

- **Action versions** — GitHub flagged that `actions/checkout@v4` and `actions/setup-python@v5` will be forced to Node 24 in September 2026. Bump to newer versions before then.
- **Single-sender per store** — if managers sometimes email from alternate addresses, current code won't match. Easy fix: turn `sender` into a list.
- **Hardcoded "William St gets all sample PDFs" in local mode** — `fetch_reports_local()` attributes every PDF in `Sample report/` to William St. Fine for dev; if you ever organise samples by store, update accordingly.
- **Test sender email in config** — `config.py` currently has `ruitanhuang@outlook.com` as William St's sender. Swap to the real William St sender when ready for production.

---

## 🔐 Where each secret lives

| Secret name | Lives in | Source |
|---|---|---|
| `GMAIL_OAUTH_CREDENTIALS` | GitHub Actions secrets | `~/Downloads/client_secret_166143871550-*.json` |
| `GMAIL_TOKEN` | GitHub Actions secrets | `gmail_token.json` (produced by `auth_gmail.py`) |
| `GOOGLE_SHEETS_SERVICE_ACCOUNT` | GitHub Actions secrets | `~/Downloads/report-extractor-497204-*.json` |
| `SCORECARD_SHEET_ID` | GitHub Actions secrets | Sheet URL between `/d/` and `/edit` |
| `ALERT_EMAIL` (optional) | GitHub Actions secrets | Plain email address |
| `SMTP_USER` (optional) | GitHub Actions secrets | Gmail to send alerts from |
| `SMTP_PASS` (optional) | GitHub Actions secrets | App password (not Google password) |

Never commit any of these files to git — `.gitignore` already covers `gmail_token.json`, `client_secret_*.json`, `report-extractor-*.json`.

---

## 🆘 If the workflow fails

1. Open the [Actions tab](https://github.com/Ruitan1999/report-extractor/actions) and click the red run
2. Common failures:
   - **`invalid_grant`** → Gmail token expired (7-day Testing-mode limit). Re-auth — see section 5 above.
   - **`No PDFs found in email`** → Either the store didn't email yet, or the sender address in `config.py` is wrong.
   - **`Sheet tab 'X' not found`** → Tab in `config.py` doesn't match the Google Sheet exactly.
   - **`PERMISSION_DENIED` on Sheets** → Sheet wasn't shared with the service account email.
   - **Date not found in DDCR header** → The DDCR doesn't have the target date's column. Are you backfilling a date outside this week's report?
3. Fix and either re-trigger manually (Actions tab → Run workflow) or wait for the next 6 AM cycle.
