"""
pdf_extractor.py

Extracts KPI data from the three report PDFs using pdfplumber + regex.
No external API required.

Usage (standalone test):
    python pdf_extractor.py
"""

import re
import os
from pathlib import Path
import pdfplumber


# ---------------------------------------------------------------------------
# Value parsing utilities
# ---------------------------------------------------------------------------

# Matches every numeric token that can appear in these PDFs:
#   ($25.14)   ($1,234.56)   $128,825.17   -$410.09
#   (2.07)%    11.28%        100.00        738.04   1,337
_VALUE_TOKEN = re.compile(
    r'\(\$[\d,]+\.?\d*\)'   # ($1,234.56)
    r'|-\$[\d,]+\.?\d*'     # -$410.09
    r'|\$[\d,]+\.?\d*'      # $128,825.17
    r'|\([\d,]+\.?\d*\)%'   # (2.07)%
    r'|[\d,]+\.?\d*%'       # 11.28%
    r'|\([\d,]+\.?\d*\)'    # (10)
    r'|[\d,]+\.?\d*'        # 738.04  or  1,337
)


def _parse_token(token: str) -> float | None:
    """Convert a raw value token to a Python float. Returns None if blank."""
    if token is None:
        return None
    s = token.strip()
    is_pct = s.endswith('%')
    if is_pct:
        s = s[:-1]
    negative = s.startswith('(') and s.endswith(')')
    s = s.strip('()').replace('$', '').replace(',', '')
    if s in ('', '-'):
        return None
    try:
        val = float(s)
        val = -val if negative else val
        return val / 100 if is_pct else val
    except ValueError:
        return None


def _extract_tokens(text_after_field: str) -> list[str]:
    """Return all value tokens found after the field name."""
    return _VALUE_TOKEN.findall(text_after_field)


def extract_text_all_pages(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def extract_text_last_page(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return pdf.pages[-1].extract_text() or ""


def extract_text_pages(pdf_path: str, page_numbers: list) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(
            pdf.pages[i].extract_text() or ""
            for i in page_numbers
            if i < len(pdf.pages)
        )


# ---------------------------------------------------------------------------
# DDCR extraction — pure regex
# ---------------------------------------------------------------------------

# Exact field names as they appear in the PDF, mapped to scorecard keys
_DDCR_FIELD_MAP = {
    "Actual Product Sales":   "actual_sales",
    "Projected Sales":        "projected_sales",
    "% Sales Difference":     "sales_proj_opp",
    "Sales Comp %":           "sales_comp_pct",
    "Guest Count Comp %":     "gc_comp",
    "Actual Guest Count":     "cpm",
    "Actual Crew Hours":      "actual_hours",
    "Projected Crew Hours":   "ros_mgr_hours",
    "Actual Crew AHR":        "ahr",
    "Actual Total Labour %":  "labour_actual",
    "Projected Total Labour %": "labour_proj",
    "Actual Crew SPCH":       "spch",
    "Actual GCPCH":           "acpm",
    "Proj GCPCH":             "qcpm",
    "Total Waste %":          "waste_combined",
    "Cash + / -":             "cash_plus_minus",
    "SOC Percent":            "sta_pct",
}

# Fields where the raw value is already in decimal (percentages pre-divided)
# vs fields that need no conversion (already absolute)
# Note: _parse_token handles % conversion automatically


def _get_ddcr_column_index(text: str, target_date: str) -> int:
    """
    Find which column index (0=Mon … 6=Sun, 7=Week Total) corresponds
    to target_date ('DD/MM/YYYY') or 'Week Total'.
    """
    # Line 6 contains the date headers: "13/04/2026 14/04/2026 ... Total"
    for line in text.split('\n'):
        tokens = line.split()
        # Date header line: all tokens are either DD/MM/YYYY or 'Total'
        date_pattern = re.compile(r'^\d{2}/\d{2}/\d{4}$')
        date_tokens = [t for t in tokens if date_pattern.match(t) or t == 'Total']
        if len(date_tokens) >= 7:  # found the header
            if target_date == 'Week Total':
                return len(date_tokens) - 1  # last column
            for i, dt in enumerate(date_tokens):
                if dt == target_date:
                    return i
            # Try matching by day number only (handles format differences)
            target_day = target_date.split('/')[0] if '/' in target_date else None
            if target_day:
                for i, dt in enumerate(date_tokens):
                    if dt.startswith(target_day + '/'):
                        return i
            raise ValueError(
                f"Date '{target_date}' not found in DDCR header. "
                f"Available: {date_tokens}"
            )
    raise ValueError("Could not find date header row in DDCR PDF text.")


def extract_ddcr(pdf_path: str, target_date: str = 'Week Total') -> dict:
    """
    Extract DDCR fields for a specific day column or the Week Total.

    target_date: 'DD/MM/YYYY' (e.g. '13/04/2026') or 'Week Total'
    Returns dict keyed by scorecard field names.
    """
    print(f"  Extracting DDCR: {Path(pdf_path).name} | column: {target_date}")
    text = extract_text_all_pages(pdf_path)
    col_idx = _get_ddcr_column_index(text, target_date)

    result = {}
    for field_name, scorecard_key in _DDCR_FIELD_MAP.items():
        result[scorecard_key] = None
        for line in text.split('\n'):
            if line.startswith(field_name):
                after = line[len(field_name):]
                tokens = _extract_tokens(after)
                if col_idx < len(tokens):
                    result[scorecard_key] = _parse_token(tokens[col_idx])
                break

    # SOC Percent: PDF stores as plain "100.00" (no % sign), so _parse_token
    # returns 100.0. Normalise to decimal fraction (0.0–1.0) here.
    if result.get("sta_pct") is not None and result["sta_pct"] > 1:
        result["sta_pct"] = result["sta_pct"] / 100

    return result


def ddcr_to_scorecard_row(ddcr: dict) -> dict:
    """Pass-through — extract_ddcr already returns scorecard-keyed dict."""
    row = dict(ddcr)
    # Fill unknowns with None so the writer always gets a complete row
    unknown_fields = [
        "training_hours", "kvs_peak", "kvs_shift", "r2p_peak", "r2p_shift",
        "side2_peak", "side2_shift", "delivery_time", "actual_mgr_hrs",
        "sick_mgr_hr", "sick_crew_hrs", "events",
    ]
    for f in unknown_fields:
        row.setdefault(f, None)
    return row


# ---------------------------------------------------------------------------
# Sales Ledger extraction — pure regex
# ---------------------------------------------------------------------------
#
# Page 1 column layout (values after "DD Mon"):
#   [0] Opening  [1] Closing  [2] Diff
#   [3] ORing Qty  [4] ORing Amt
#   [5] Refund Qty  [6] Refund Amt   ← day row
#   [7] EFT Refunds Qty  [8] EFT Refunds Amt
#
# Page 1 "Week Tot" column layout (Opening/Closing/Diff columns absent):
#   [0] ORing Qty  [1] ORing Amt
#   [2] Refund Qty  [3] Refund Amt   ← week-total row
#   [4] EFT Refunds Qty  [5] EFT Refunds Amt
#
# Page 3 column layout (same indices for both day and Week Tot rows):
#   [0] Disc Qty  [1] Disc Amt
#   [2] Promo Qty  [3] Promo Amt     ← we want this
#   [4] Voucher Amt  [5] Promo Short/Over (negative)
#   [6] Emp Meals Qty  [7] Emp Meals Amt
#   [8] Mgr Meals Qty  [9] Mgr Meals Amt  ← we want this


def _find_day_line(text: str, day: int) -> str | None:
    """
    Find the line for a specific day number in Sales Ledger page text.
    Matches e.g. "13 Mon ..." or "13 Sat ..." at the start of a line.
    """
    pattern = re.compile(rf'^{day}\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    start = match.start()
    end = text.find('\n', start)
    return text[start:end] if end != -1 else text[start:]


def _find_week_tot_line(text: str, after_day: int) -> str | None:
    """
    Find the 'Week Tot' line immediately following the given day number.
    Scans line-by-line: once we find the day row, the next 'Week Tot' is ours.
    """
    lines = text.split('\n')
    day_pattern = re.compile(rf'^{after_day}\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s')
    found_day = False
    for line in lines:
        if found_day and line.startswith('Week Tot'):
            return line
        if day_pattern.match(line):
            found_day = True
    return None


def extract_sales_ledger(pdf_path: str, target_day: int,
                         week_total: bool = False) -> dict:
    """
    Extract Refund, Promo, Manager Meal for a specific calendar day
    (week_total=False) or the week-total row following that day
    (week_total=True).

    target_day: integer day-of-month (1–31), i.e. the last day of the week
                when week_total=True.
    """
    label = "week-total" if week_total else f"day {target_day}"
    print(f"  Extracting Sales Ledger: {Path(pdf_path).name} | {label}")

    result = {"refund": None, "promo": None, "manager_meal": None}

    # Page 1 — Refund
    p1_text = extract_text_pages(pdf_path, [0])
    if week_total:
        line1 = _find_week_tot_line(p1_text, target_day)
        if line1:
            after = re.sub(r'^Week Tot\s+', '', line1)
            tokens = _extract_tokens(after)
            # Week Tot layout: [0] ORing Qty [1] ORing Amt [2] Refund Qty [3] Refund Amt
            if len(tokens) > 3:
                result["refund"] = _parse_token(tokens[3])
        else:
            print(f"  [WARN] Week Tot after day {target_day} not found in Sales Ledger page 1")
    else:
        line1 = _find_day_line(p1_text, target_day)
        if line1:
            after = re.sub(rf'^{target_day}\s+\w+\s+', '', line1)
            tokens = _extract_tokens(after)
            # Day row: [5] Refund Qty  [6] Refund Amt
            if len(tokens) > 6:
                result["refund"] = _parse_token(tokens[6])
        else:
            print(f"  [WARN] Day {target_day} not found in Sales Ledger page 1")

    # Page 3 — Promo + Manager Meal (indices 3 and 9 same for both day and Week Tot)
    p3_text = extract_text_pages(pdf_path, [2])
    if week_total:
        line3 = _find_week_tot_line(p3_text, target_day)
        prefix_pat = r'^Week Tot\s+'
    else:
        line3 = _find_day_line(p3_text, target_day)
        prefix_pat = rf'^{target_day}\s+\w+\s+'

    if line3:
        after = re.sub(prefix_pat, '', line3)
        tokens = _extract_tokens(after)
        # [2] Promo Qty  [3] Promo Amt  [8] Mgr Meals Qty  [9] Mgr Meals Amt
        if len(tokens) > 3:
            result["promo"] = _parse_token(tokens[3])
        if len(tokens) > 9:
            result["manager_meal"] = _parse_token(tokens[9])
    else:
        src = "Week Tot" if week_total else f"Day {target_day}"
        print(f"  [WARN] {src} not found in Sales Ledger page 3")

    return result


# ---------------------------------------------------------------------------
# QCR Daily extraction — regex (last page only)
# ---------------------------------------------------------------------------

def extract_qcr_daily(pdf_path: str) -> dict:
    """
    Extract QCR % of Product Sold (food %) from the last page summary.
    Returns dict with key: qcr
    """
    print(f"  Extracting QCR: {Path(pdf_path).name}")
    text = extract_text_last_page(pdf_path)

    match = re.search(
        r'QCR\s*%\s*of\s*Product\s*Sold\s+([\d.]+)%',
        text,
        re.IGNORECASE,
    )
    if match:
        val = float(match.group(1)) / 100
        print(f"  QCR % of Product Sold = {val:.4f}")
        return {"qcr": val}

    print("  [WARN] QCR % of Product Sold not found on last page")
    return {"qcr": None}


# ---------------------------------------------------------------------------
# Top-level: extract all fields for one store/day
# ---------------------------------------------------------------------------

def extract_all(
    ddcr_path: str,
    qcr_daily_path: str,
    sales_ledger_path: str,
    target_date: str,   # 'DD/MM/YYYY' or 'Week Total'
    target_day: int,    # calendar day-of-month
) -> dict:
    """Merge all three extractors into a single scorecard row dict."""
    ddcr_raw = extract_ddcr(ddcr_path, target_date)
    row = ddcr_to_scorecard_row(ddcr_raw)
    is_week = (target_date == 'Week Total')
    row.update(extract_sales_ledger(sales_ledger_path, target_day, week_total=is_week))
    row.update(extract_qcr_daily(qcr_daily_path))
    return row


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base       = Path(__file__).parent / "Sample report"
    ddcr_pdf   = base / "DDCR Weekly.pdf"
    qcr_pdf    = base / "QCR Daily 19Apr26.pdf"
    ledger_pdf = base / "Sales Ledger Month Apr 26.pdf"

    EXPECTED_WEEKLY = {
        "actual_sales":    128825.17,
        "projected_sales": 118417.00,
        "sales_comp_pct":  0.1128,
        "sales_proj_opp":  0.0879,
        "gc_comp":         0.1103,
        "actual_hours":    738.04,
        "cash_plus_minus": -17.49,
        "waste_combined":  0.0028,
        "spch":            174.55,
        "ahr":             28.22,
        "labour_actual":   0.2031,
        "labour_proj":     0.2508,
        "sta_pct":         1.00,    # 100.00% -> 1.00 after pct conversion
        "acpm":            14.86,
        "qcpm":            10.37,
        "cpm":             10968,
        "qcr":             0.2599,
        "refund":          140.95,
        "promo":           6422.12,
        "manager_meal":    625.09,
    }

    EXPECTED_MONDAY = {
        "actual_sales":    15168.70,
        "projected_sales": 13788.00,
        "sales_comp_pct":  0.0754,
        "actual_hours":    103.27,
        "cash_plus_minus": 11.50,
        "waste_combined":  0.005,
        "spch":            146.88,
        "ahr":             27.10,
        "refund":          0.00,
        "promo":           895.23,
        "manager_meal":    62.55,
    }

    def check(label, row, expected):
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        print(f"  {'Field':<22}  {'Expected':>12}  {'Got':>12}  {'':>6}")
        print("  " + "-" * 56)
        all_ok = True
        for field, exp in expected.items():
            got = row.get(field)
            if got is None:
                status = "MISSING"
                all_ok = False
            elif abs(got - exp) < 0.015:
                status = "OK"
            else:
                status = f"FAIL (diff={got-exp:+.4f})"
                all_ok = False
            print(f"  {field:<22}  {exp:>12.4f}  {str(round(got,4)) if got is not None else 'None':>12}  {status}")
        print(f"\n  Result: {'PASS' if all_ok else 'FAIL'}")

    print("\nRunning extraction tests (no API key required)...")

    row_weekly = extract_all(
        str(ddcr_pdf), str(qcr_pdf), str(ledger_pdf),
        target_date="Week Total", target_day=19,
    )
    check("TEST 1: Week Total column", row_weekly, EXPECTED_WEEKLY)

    row_monday = extract_all(
        str(ddcr_pdf), str(qcr_pdf), str(ledger_pdf),
        target_date="13/04/2026", target_day=13,
    )
    check("TEST 2: Monday 13/04/2026", row_monday, EXPECTED_MONDAY)
