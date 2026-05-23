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

# Test PDF extraction against sample PDFs — runs two assertions (Week Total + Mon 13/04)
python pdf_extractor.py

# Test Sheets writer against a copy of the scorecard (writes test_output.xlsx)
python sheets_writer.py

# Run the full pipeline for yesterday (default) or a specific date (backfill)
python main.py
python main.py 2026-04-13

# Run GitHub Actions workflow manually (once deployed)
gh workflow run daily_run.yml
```

Each module (`gmail_fetch.py`, `sheets_writer.py`, `alerter.py`) also has a `__main__` block for standalone testing.

---

## Architecture

Five modules wired together by `main.py`:

| File | Role |
|------|------|
| `gmail_fetch.py` | Gmail API (OAuth2) — fetches emails by sender, downloads PDF attachments |
| `pdf_extractor.py` | pdfplumber text extraction → regex parsing → structured dict |
| `sheets_writer.py` | Google Sheets API v4 — finds the right row by date, writes data |
| `alerter.py` | Collects issues throughout the run, sends one digest email at the end |
| `config.py` | Store config, sender emails, field→column mappings, scorecard layout constants |

**PDF extraction pattern:** Extract raw text with pdfplumber (0-based page indices), then parse with regex. No external API call — extraction is pure Python regex. `extract_all()` in `pdf_extractor.py` is the top-level function that merges DDCR + Sales Ledger + QCR Daily into a single scorecard row dict.

**Dual-backend pattern (all three I/O modules):** Backend is auto-selected from env vars at import time — there is no CLI flag to switch.

| Module | Local/dev mode | Production mode trigger |
|--------|---------------|------------------------|
| `gmail_fetch.py` | Returns paths from `Sample report/` dir; all PDFs mapped to William St only | `GMAIL_OAUTH_CREDENTIALS` + `GMAIL_TOKEN` both set |
| `sheets_writer.py` | Reads/writes `Weekly Scorecard tracker Q2 2026.xlsx` directly via openpyxl | `GOOGLE_SHEETS_SERVICE_ACCOUNT` + `SCORECARD_SHEET_ID` both set |
| `alerter.py` | Prints digest to stdout | `ALERT_EMAIL` + `SMTP_USER` + `SMTP_PASS` all set |

**Store identification:** Each store's emails come from a unique sender address. `config.py` maps sender → store name → sheet tab name.

**Row targeting in Sheets:** The date column is **Excel column B** (column A is always blank). Search column B of the relevant sheet for a cell matching the target date. Overwrite if found; insert before the "Monthend: [Month]" row if not found; append after the last non-empty row as a fallback.

---

## Daily vs Weekly — key design decisions

The scorecard was originally weekly (one row per week-ending Sunday). It is being redesigned to **daily granularity**:

- **Reports:** The DDCR is a **weekly-format PDF** (Mon–Sun columns + Week Total). The same file is sent by managers every day; only the current day's column has data — prior days accumulate as the week progresses.
- **Scorecard rows:** Each day gets its own row containing that day's daily values. The existing "Monthend" row stays as a monthly aggregate.
- **Sunday rows + Week Total summary:** On Sundays, the script writes TWO rows:
    1. The Sunday daily row (same as any weekday) — column B = `19/4/26`
    2. A `Week ending 19/4/26` summary row immediately after, populated from the DDCR **Week Total column** + Sales Ledger **Week Tot** row + QCR — column B = literal text `"Week ending D/M/YY"`
  This is implemented by `sheets_writer.write_weekly_summary_row()` and triggered in `main.py` when `target_date.weekday() == 6`.
- **Schedule:** The script runs **every morning** to process the previous day's report.
- **Daily extraction:** To extract a specific day's data from the DDCR, match the date column header (format `DD/MM/YYYY` e.g. `13/04/2026`). The "Week Total" column is reserved for the weekly summary row.
- **Weekly-row finder caveat:** `_cell_matches_date()` in `sheets_writer.py` explicitly **skips** rows whose column B starts with `"Week ending "`. This prevents a future daily run from accidentally overwriting the weekly summary row. Any new row-finder logic must respect this.

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
| `SOC Percent` | STA % | Stored in PDF as plain `100.00` (no `%`); extractor normalises to decimal by ÷100 |

**Fields confirmed NOT in the DDCR:** Training Hours, KVS, R2P, Side 2, Delivery Time, Sick hours, Refund, Promo, Manager Meal.

Also present in DDCR but not mapped to scorecard: `Projected Guest Count`, `Guest Count Difference`, `Actual Crew Labour %`, `Proj Crew Labour %`, `Projected Crew AHR`, `Projected Crew SPCH`, `Raw Waste %`, `Completed Waste %`, `Average Check`, `Cash Deposits`, `Drive Thru Sales %`, `McCafe Sales %`, `Breakfast Sales %`, `Kiosk Sales %`, `CYT %`, `Eftpos Sales`, `Eftpos Cashout`, `Eftpos %`, `Stat Variance`.

---

### Sales Ledger — `Sales Ledger Month Apr 26.pdf`

**4 pages** (pdfplumber page indices 0–3). Monthly cumulative report; rows are individual calendar days.

- **Page 0 (PDF p.1):** Each day row contains: `ORing`, `Refund` (qty + amt), `EFT Refunds` (qty + amt), `Other Receipts`, `GC Sold`, `Gross Sales`, tax columns, `Guest Count`, `Ave Chk`
- **Page 1 (PDF p.2):** Cash/Eftpos reconciliation columns per day
- **Page 2 (PDF p.3):** Promo/meals breakdown per day — columns include `Disc Sales`, `Promo Sales Amt`, `Emp Meals Amt`, `Mgr Meals Amt`, `Other Net Sales`
- **Page 3 (PDF p.4):** (continuation)

**Extraction targets (per day row, matched by day number e.g. `13 Mon`):**

| pdfplumber page | Token index | PDF field | Scorecard field |
|---|---|---|---|
| 0 | [8] | `EFT Refunds` Amt | Refund |
| 2 | [3] | `Promo Sales Amt` | Promo |
| 2 | [9] | `Mgr Meals Amt` | Manager Meal |

Week-total rows (`Week Tot`) use different token offsets — see comments in `extract_sales_ledger()`.

> ⚠️ The user indicated Refund/Promo/Manager Meal come from the daily DDCR. However in the sample PDFs these fields appear only in the Sales Ledger. Confirm exact source once daily PDFs are available. For now, extract from Sales Ledger.

---

### QCR Daily — `QCR Daily 19Apr26.pdf`

**13 pages.** Pages 1–12 are item-level food/paper cost detail (one row per menu item). **Last page (index -1) is the summary** — this is the only page needed.

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

**Date format in column B:** Mixed — some cells are Excel date objects (openpyxl returns `datetime`), some are text strings (`D/M/YY` e.g. `19/4/26`). Some dates were entered in a US-locale Excel and have day/month swapped; `_cell_matches_date()` in `sheets_writer.py` handles all these cases. Write new rows as text `D/M/YY`.

---

## Scorecard column mapping

**⚠️ Column A in Excel is always blank.** W/End dates are in **column B**. KPI data starts at **column C**.

| Excel Col | col_index | Field | Source | Notes |
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
| P | 15 | STA % | DDCR | `SOC Percent` — stored as 100.00, written as decimal 1.00 |
| Q | 16 | ACPM | DDCR | `Actual GCPCH` |
| R | 17 | QCPM | DDCR | `Proj GCPCH` — confirm this mapping |
| S | 18 | KVS Peak | ⚠ UNKNOWN | Not in any sample report |
| T | 19 | KVS Shift | ⚠ UNKNOWN | Not in any sample report |
| U | 20 | R2P Peak | ⚠ UNKNOWN | Not in any sample report |
| V | 21 | R2P Shift | ⚠ UNKNOWN | Not in any sample report |
| W | 22 | Side 2 Peak | ⚠ UNKNOWN | Not in any sample report |
| X | 23 | Side 2 Shift | ⚠ UNKNOWN | Not in any sample report |
| Y | 24 | Delivery Time | ⚠ UNKNOWN | Not in any sample report |
| Z | 25 | Refund | Sales Ledger p0 | `EFT Refunds` Amt per day row |
| AA | 26 | Promo | Sales Ledger p2 | `Promo Sales Amt` per day row |
| AB | 27 | Manager Meal | Sales Ledger p2 | `Mgr Meals Amt` per day row |
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

**Extra columns:** The store tabs have 37 columns total (2 unlabelled beyond AI, col_index 35–36). Do not overwrite these.

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

Running `python pdf_extractor.py` checks both scenarios automatically and prints PASS/FAIL per field.

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
| SOC Percent | 100.00 → stored as 1.00 |

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

**Sales Ledger — week of 13–19 Apr:**

| Field | Weekly total | Source |
|-------|-------------|--------|
| EFT Refunds Amt | $140.95 | Page 0 (PDF p.1) Week Tot |
| Promo Sales Amt | $6,422.12 | Page 2 (PDF p.3) Week Tot |
| Mgr Meals Amt | $625.09 | Page 2 (PDF p.3) Week Tot |

**QCR Daily (Sunday 19 Apr only):** QCR % of Product Sold = **25.99%** (0.2599)

> Note: 26.64% may be from the weekly QCR Progressive report, not the single-day QCR Daily. Clarify which is correct for the scorecard.

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
ALERT_EMAIL                   # Address to send failure alerts to
SMTP_USER                     # Gmail address for sending alert emails
SMTP_PASS                     # App password for SMTP_USER
```

Optional overrides (defaults to Gmail SMTP):
```
SMTP_HOST   # default: smtp.gmail.com
SMTP_PORT   # default: 587
```

---

## Development sequence

1. Confirm 7 sender email addresses with Ruitan → update `config.py`
2. Confirm exact filename patterns for daily reports (DDCR, Sales Ledger, QCR Daily)
3. Confirm source for: Training Hours (col O), KVS/R2P/Side 2/Delivery Time (cols S–Y), Actual Mgr hrs (col AD), Sick hours (cols AE–AF)
4. Confirm whether Refund/Promo/Manager Meal are in the daily DDCR or daily Sales Ledger (sample PDFs show Sales Ledger; confirm with actual daily PDF)
5. Confirm whether QCR % for daily scorecard uses QCR Daily (single day) or QCR Progressive (period-to-date)
6. Verify `pdf_extractor.py` passes against sample PDFs: `python pdf_extractor.py`
7. Verify `sheets_writer.py` produces correct `test_output.xlsx`: `python sheets_writer.py`
8. Confirm Gmail auth works: set env vars and run `python gmail_fetch.py`
9. Set up GitHub Actions and secrets
10. First live test via `workflow_dispatch`
11. Confirm daily auto-trigger
