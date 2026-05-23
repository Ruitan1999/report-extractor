# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Automatically extracts daily KPI data from McDonald's franchise store report PDFs (delivered via Gmail every day by store managers) and writes the extracted data into the correct row and sheet of a Google Sheets scorecard. Triggered every morning via GitHub Actions. Zero manual input once deployed.

Owner: Ruitan Huang — 7 franchise stores in Perth, WA.

---

## Development commands

```bash
# Install dependencies
pip install -r requirements.txt

# Test PDF extraction against sample PDFs (primary development task)
python pdf_extractor.py

# Test Sheets writer against a copy of the scorecard
python sheets_writer.py

# Run the full pipeline manually (requires secrets in env)
python main.py

# Run GitHub Actions workflow manually (once deployed)
gh workflow run daily_run.yml
```

---

## Architecture

Five modules wired together by `main.py`:

| File | Role |
|------|------|
| `gmail_fetch.py` | Gmail API (OAuth2) — fetches emails by sender, downloads PDF attachments |
| `pdf_extractor.py` | pypdf text extraction → Claude API (Haiku) → structured JSON |
| `sheets_writer.py` | Google Sheets API v4 — finds the right row by date, writes data |
| `alerter.py` | Sends alert email if any store/report fails; never aborts the whole run |
| `config.py` | Store config, sender emails, field→column mappings |

**PDF extraction pattern:** Extract raw text with pypdf/pdfplumber first, then pass text (not base64) to Claude API with a strict JSON-only prompt. This is cheaper and more reliable than sending the raw PDF.

**Store identification:** Each store's emails come from a unique sender address. `config.py` maps sender → store name → sheet tab name.

**Row targeting in Sheets:** The date column is **Excel column B** (column A is always blank). Search column B of the relevant sheet for a cell matching today's date (`D/M/YY` or `DD/MM/YY`). Overwrite if found; if not found, insert a new row within the correct month block (before the "Monthend: [Month]" row).

---

## Daily vs Weekly — key design decisions

The scorecard was originally weekly (one row per week-ending Sunday). It is being redesigned to **daily granularity**:

- **Reports:** The DDCR is a **weekly-format PDF** (Mon–Sun columns + Week Total). The same file is sent by managers every day; only the current day's column has data — prior days accumulate as the week progresses.
- **Scorecard rows:** Each day gets its own row. The week-ending Sunday row doubles as the weekly summary (all 7 day columns and the Week Total are all populated). The existing "Monthend" row stays as a monthly aggregate.
- **Schedule:** The script runs **every morning** to process the previous day's report.
- **Daily extraction:** To extract a specific day's data from the DDCR, match the date column header (format `DD/MM/YYYY` e.g. `13/04/2026`). Do not use the "Week Total" column for daily rows.

---

## Report types and confirmed PDF structure

### DDCR (Daily Detail Consultant Report) — `DDCR Weekly.pdf`

**1 page.** Confirmed from sample PDFs.

Layout: header rows then a table with columns `Monday DD/MM/YYYY | Tuesday DD/MM/YYYY | ... | Sunday DD/MM/YYYY | Week Total`.

Each row is a metric. Confirmed field names (exact text as it appears in the PDF):

| PDF field name | Scorecard field | Notes |
|---|---|---|
| `Actual Product Sales` | Actual Sales | Dollar value |
| `Projected Sales` | Projected Sales | Dollar value |
| `% Sales Difference` | Sales Proj Opp | Percentage shown as `10.01%` |
| `Sales Comp %` | Sales Comp % | Percentage shown as `7.54%` → store as decimal 0.0754 |
| `Guest Count Comp %` | GC Comp | Decimal; negative shown as `(2.07)%` |
| `Actual Guest Count` | CPM | Integer count |
| `Actual Crew Hours` | Actual Hours | e.g. `103.27` |
| `Projected Crew Hours` | Ros Mgr Hours | ⚠ confirm — this is total crew hours, not mgr-only |
| `Actual Crew AHR` | AHR | Dollar value |
| `Actual Total Labour %` | Labour Actual | Decimal |
| `Projected Total Labour %` | Labour Proj | Decimal |
| `Actual Crew SPCH` | SPCH | Dollar value |
| `Actual GCPCH` | ACPM | Numeric |
| `Proj GCPCH` | QCPM | Numeric — confirm this mapping |
| `Total Waste %` | Waste combined | Decimal e.g. `0.50%` → 0.005 |
| `Cash + / -` | Cash + / - | Dollar value; negative shown as `($25.14)` |
| `SOC Percent` | STA % | e.g. `100.00%` |

**Fields confirmed NOT in the DDCR:** Training Hours, KVS, R2P, Side 2, Delivery Time, Sick hours, Refund, Promo, Manager Meal.

Also present in DDCR but not mapped to scorecard: `Projected Guest Count`, `Guest Count Difference`, `Actual Crew Labour %`, `Proj Crew Labour %`, `Projected Crew AHR`, `Projected Crew SPCH`, `Raw Waste %`, `Completed Waste %`, `Average Check`, `Cash Deposits`, `Drive Thru Sales %`, `McCafe Sales %`, `Breakfast Sales %`, `Kiosk Sales %`, `CYT %`, `Eftpos Sales`, `Eftpos Cashout`, `Eftpos %`, `Stat Variance`.

---

### Sales Ledger — `Sales Ledger Month Apr 26.pdf`

**4 pages.** Monthly cumulative report; rows are individual calendar days.

- **Page 1:** Each day row contains: `ORing`, `Refund` (qty + amt), `EFT Refunds` (qty + amt), `Other Receipts`, `GC Sold`, `Gross Sales`, tax columns, `Guest Count`, `Ave Chk`
- **Page 2:** Cash/Eftpos reconciliation columns per day
- **Page 3:** Promo/meals breakdown per day — columns include `Disc Sales`, `Promo Sales Amt`, `Emp Meals Amt`, `Mgr Meals Amt`, `Other Net Sales`
- **Page 4:** (continuation)

**Extraction targets (per day row, matched by day number e.g. `13 Mon`):**

| PDF location | PDF field | Scorecard field |
|---|---|---|
| Page 1, `EFT Refunds` Amt column | e.g. `21.50` | Refund |
| Page 3, `Promo Sales Amt` column | e.g. `838.05` | Promo |
| Page 3, `Mgr Meals Amt` column | e.g. `160.68` | Manager Meal |

> ⚠️ The user indicated Refund/Promo/Manager Meal come from the daily DDCR. However in the sample PDFs these fields appear only in the Sales Ledger (page 3). Confirm exact source once daily PDFs are available. For now, extract from Sales Ledger.

---

### QCR Daily — `QCR Daily 19Apr26.pdf`

**13 pages.** Pages 1–12 are item-level food/paper cost detail (one row per menu item). **Page 13 (last page) is the summary** — this is the only page needed.

Key fields on the summary page:

```
QCR % of Product Sold    25.99%    2.00%
                         (Food)   (Paper)
```

Extract `QCR % of Product Sold` food % → scorecard field **QCR** (decimal, e.g. 0.2599).

> ⚠️ The sample DDCR known value says QCR = 26.64% but this QCR Daily (for Sunday only) shows 25.99%. The weekly QCR figure may come from the QCR Progressive report instead. Confirm which report and which date range is used for the weekly/daily scorecard row.

---

## Scorecard structure (confirmed from file)

File: `Weekly Scorecard tracker Q2 2026.xlsx` — one tab per store plus `Template` and `Instructions`.

**Row layout within each store tab:**

| Row | Content |
|-----|---------|
| 1 | Category headers (Sales / Profit / OPS / Register Controls / Notes) |
| 2 | Target values per column |
| 3 | Column headers (W/End, Projected Sales, …) |
| 4+ | Data rows — see pattern below |

**Data row pattern per month block (rows 4+):**
```
[Month] Target          ← monthly target label row (no data)
[Mon date]              ← daily data row
[Tue date]              ← daily data row
[Wed date]              ← daily data row
[Thu date]              ← daily data row
[Fri date]              ← daily data row
[Sat date]              ← daily data row
[Sun/week-end date]     ← daily data row (doubles as weekly summary)
... (repeat for next week)
Monthend: [Month]       ← monthly aggregate row
                        ← blank separator
```

**Date format in column B:** Mixed — some stored as Excel date objects (pandas reads as `YYYY-DD-MM HH:MM:SS`), some as text strings (`D/M/YY` e.g. `19/4/26`). Sheets writer must handle both when searching for a row. Write new rows as text `D/M/YY`.

---

## Scorecard column mapping

**⚠️ Column A in Excel is always blank.** W/End dates are in **column B**. KPI data starts at **column C**.

| Excel Col | pandas idx | Field | Source | Notes |
|-----------|-----------|-------|--------|-------|
| A | 0 | *(blank)* | — | Always empty — do not write here |
| B | 1 | W/End date | — | `D/M/YY` e.g. `19/4/26` |
| C | 2 | Projected Sales | DDCR | `Projected Sales` |
| D | 3 | Actual Sales | DDCR | `Actual Product Sales` |
| E | 4 | Sales Comp % | DDCR | `Sales Comp %` — decimal |
| F | 5 | Sales Proj Opp | DDCR | `% Sales Difference` |
| G | 6 | GC Comp | DDCR | `Guest Count Comp %` — decimal |
| H | 7 | Cash + / - | DDCR | `Cash + / -` — dollar value |
| I | 8 | Waste combined | DDCR | `Total Waste %` — decimal |
| J | 9 | Labour Proj | DDCR | `Projected Total Labour %` — decimal |
| K | 10 | SPCH | DDCR | `Actual Crew SPCH` |
| L | 11 | AHR | DDCR | `Actual Crew AHR` |
| M | 12 | Actual Hours | DDCR | `Actual Crew Hours` |
| N | 13 | Labour Actual | DDCR | `Actual Total Labour %` — decimal |
| O | 14 | Training Hours | ⚠ UNKNOWN | Not in sample DDCR — confirm source |
| P | 15 | STA % | DDCR | `SOC Percent` |
| Q | 16 | ACPM | DDCR | `Actual GCPCH` |
| R | 17 | QCPM | DDCR | `Proj GCPCH` — confirm this mapping |
| S | 18 | KVS Peak | ⚠ UNKNOWN | Not in any sample report |
| T | 19 | KVS Shift | ⚠ UNKNOWN | Not in any sample report |
| U | 20 | R2P Peak | ⚠ UNKNOWN | Not in any sample report |
| V | 21 | R2P Shift | ⚠ UNKNOWN | Not in any sample report |
| W | 22 | Side 2 Peak | ⚠ UNKNOWN | Not in any sample report |
| X | 23 | Side 2 Shift | ⚠ UNKNOWN | Not in any sample report |
| Y | 24 | Delivery Time | ⚠ UNKNOWN | Not in any sample report |
| Z | 25 | Refund | Sales Ledger p1 | `EFT Refunds` Amt per day row |
| AA | 26 | Promo | Sales Ledger p3 | `Promo Sales Amt` per day row |
| AB | 27 | Manager Meal | Sales Ledger p3 | `Mgr Meals Amt` per day row |
| AC | 28 | Ros Mgr Hours | DDCR | `Projected Crew Hours` ⚠ confirm if crew or mgr-only |
| AD | 29 | Actual Mgr hrs | ⚠ UNKNOWN | Not confirmed in sample reports |
| AE | 30 | Sick Mgr Hr | ⚠ UNKNOWN | Not in any sample report |
| AF | 31 | Sick Crew Hrs | ⚠ UNKNOWN | Not in any sample report |
| AG | 32 | CPM | DDCR | `Actual Guest Count` |
| AH | 33 | QCR | QCR Daily | `QCR % of Product Sold` on last page — decimal |
| AI | 34 | Events | Manual | Leave blank — entered manually by Ruitan |

**Open unknowns (cannot be populated until source confirmed):**
- Col O: Training Hours
- Cols S–Y: KVS Peak/Shift, R2P Peak/Shift, Side 2 Peak/Shift, Delivery Time
- Col AD: Actual Mgr hrs
- Cols AE–AF: Sick Mgr Hr, Sick Crew Hrs

**Extra columns:** The store tabs have 37 columns total (2 unlabelled beyond AI, pandas idx 35–36). Do not overwrite these.

---

## Store sender emails (TBC — confirm with Ruitan before building gmail_fetch.py)

| Store | Sheet tab | Sender email |
|-------|-----------|--------------|
| William St | William St | TBC |
| Hay St | Hay St | TBC |
| Ascot Waters | Ascot Waters | TBC |
| Crown | Crown | TBC |
| Duncraig | Duncraig | TBC |
| Whitfords | Whitfords | TBC |
| New Store | New Store | TBC |

---

## Sample PDFs and known test values

Real PDFs for William St in `Sample report/`. The DDCR covers the full week 13–19 Apr 2026. Use the **Week Total column** values to validate weekly extraction; use individual **day columns** to validate daily extraction.

**DDCR — Week Total column (week ending 19/4/26):**

| PDF field | Expected value |
|-----------|---------------|
| Actual Product Sales | $128,825.17 |
| Projected Sales | $118,417.00 |
| Sales Comp % | 11.28% (0.1128) |
| % Sales Difference | 8.79% |
| Guest Count Comp % | 11.03% |
| Actual Guest Count | 10,968 |
| Actual Crew Hours | 738.04 |
| Actual Crew AHR | $28.22 |
| Actual Total Labour % | 20.31% |
| Projected Total Labour % | 25.08% |
| Actual Crew SPCH | $174.55 |
| Actual GCPCH | 14.86 |
| Proj GCPCH | 10.37 |
| Total Waste % | 0.28% |
| Cash + / - | ($17.49) |
| SOC Percent | 100.00 |

**DDCR — Monday 13/04/2026 column (daily example):**

| PDF field | Expected value |
|-----------|---------------|
| Actual Product Sales | $15,168.70 |
| Projected Sales | $13,788.00 |
| Sales Comp % | 7.54% |
| Actual Crew Hours | 103.27 |
| Actual Crew AHR | $27.10 |
| Cash + / - | $11.50 |
| Total Waste % | 0.50% |
| Actual Crew SPCH | $146.88 |

**Sales Ledger — week of 13–19 Apr (page 3):**

| Field | Weekly total | Source |
|-------|-------------|--------|
| EFT Refunds Amt | $140.95 | Page 1 Week Tot |
| Promo Sales Amt | $6,422.12 | Page 3 Week Tot |
| Mgr Meals Amt | $625.09 | Page 3 Week Tot |

**QCR Daily (Sunday 19 Apr only):** QCR % of Product Sold = **25.99%** (0.2599)

> Note: CLAUDE.md previously listed QCR = 26.64% — that figure may be from the weekly QCR Progressive report, not the single-day QCR Daily. Clarify which is correct for the scorecard.

---

## GitHub Actions

```yaml
# .github/workflows/daily_run.yml
# Runs every morning at 6:00 AM Perth time (UTC+8 → 22:00 UTC previous day)
schedule:
  - cron: '0 22 * * *'
```

Also include `workflow_dispatch` for manual testing.

**Required secrets:**

```
GMAIL_OAUTH_CREDENTIALS       # OAuth2 client credentials JSON
GMAIL_TOKEN                   # OAuth2 token JSON (after first auth)
GOOGLE_SHEETS_SERVICE_ACCOUNT # Service account JSON
SCORECARD_SHEET_ID            # Sheet ID from the URL
ANTHROPIC_API_KEY             # Claude API key
ALERT_EMAIL                   # Address to send failure alerts to
```

---

## Development sequence

1. Confirm 7 sender email addresses with Ruitan → update `config.py`
2. Confirm exact filename patterns for daily reports (DDCR, Sales Ledger, QCR Daily)
3. Confirm source for: Training Hours (col O), KVS/R2P/Side 2/Delivery Time (cols S–Y), Actual Mgr hrs (col AD), Sick hours (cols AE–AF)
4. Confirm whether Refund/Promo/Manager Meal are in the daily DDCR or daily Sales Ledger (sample PDFs show Sales Ledger; confirm with actual daily PDF)
5. Confirm whether QCR % for daily scorecard uses QCR Daily (single day) or QCR Progressive (period-to-date)
6. Build and test `pdf_extractor.py` against sample PDFs — verify against known values above
7. Build and test `sheets_writer.py` against a copy of the scorecard (daily row insertion logic)
8. Build `gmail_fetch.py` — test Gmail auth and PDF download
9. Wire together in `main.py`
10. Build `alerter.py`
11. Set up GitHub Actions and secrets
12. First live test via `workflow_dispatch`
13. Confirm daily auto-trigger
