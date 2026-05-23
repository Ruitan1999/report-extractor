"""
Central configuration: store definitions, column mappings, field names.
"""

# ---------------------------------------------------------------------------
# Store configuration
# Each store maps: sender email → store name → Google Sheet tab name
# Sender emails are TBC — update before deploying gmail_fetch.py
# ---------------------------------------------------------------------------

STORES = [
    {
        "name": "William St",
        "tab": "William St",
        "sender": "williamst@mcdonalds.example.com",  # TBC
    },
    {
        "name": "Hay St",
        "tab": "Hay St",
        "sender": "hayst@mcdonalds.example.com",  # TBC
    },
    {
        "name": "Ascot Waters",
        "tab": "Ascot Waters",
        "sender": "ascotwaters@mcdonalds.example.com",  # TBC
    },
    {
        "name": "Crown",
        "tab": "Crown",
        "sender": "crown@mcdonalds.example.com",  # TBC
    },
    {
        "name": "Duncraig",
        "tab": "Duncraig",
        "sender": "duncraig@mcdonalds.example.com",  # TBC
    },
    {
        "name": "Whitfords",
        "tab": "Whitfords",
        "sender": "whitfords@mcdonalds.example.com",  # TBC
    },
    {
        "name": "New Store",
        "tab": "New Store",
        "sender": "newstore@mcdonalds.example.com",  # TBC
    },
]

SENDER_TO_STORE = {s["sender"]: s for s in STORES}

# ---------------------------------------------------------------------------
# Report filename patterns (for identifying which PDF is which)
# ---------------------------------------------------------------------------

REPORT_PATTERNS = {
    "ddcr":           "DDCR",           # matches DDCR Weekly.pdf, DDCR Daily.pdf, etc.
    "sales_ledger":   "Sales Ledger",
    "qcr_daily":      "QCR Daily",
    "qcr_progressive":"QCR Progressive",
    "ops_snapshot":   "Operations Snapshot",
}

# ---------------------------------------------------------------------------
# Scorecard column mapping
#
# Each entry maps a scorecard field name to:
#   col_letter : Excel column letter (for Sheets API range strings)
#   col_index  : 0-based pandas column index
#   source     : which report the value comes from
#   pdf_field  : exact field name as it appears in the PDF text
#   notes      : any extraction caveats
#
# Column A (index 0) is always blank — never written to.
# Column B (index 1) is the W/End date — written separately.
# KPI data starts at column C (index 2).
# ---------------------------------------------------------------------------

COLUMN_MAP = [
    # ── DDCR fields ──────────────────────────────────────────────────────────
    {
        "field":      "projected_sales",
        "col_letter": "C",
        "col_index":  2,
        "source":     "ddcr",
        "pdf_field":  "Projected Sales",
        "notes":      "Dollar value",
    },
    {
        "field":      "actual_sales",
        "col_letter": "D",
        "col_index":  3,
        "source":     "ddcr",
        "pdf_field":  "Actual Product Sales",
        "notes":      "Dollar value",
    },
    {
        "field":      "sales_comp_pct",
        "col_letter": "E",
        "col_index":  4,
        "source":     "ddcr",
        "pdf_field":  "Sales Comp %",
        "notes":      "Store as decimal e.g. 0.1128",
    },
    {
        "field":      "sales_proj_opp",
        "col_letter": "F",
        "col_index":  5,
        "source":     "ddcr",
        "pdf_field":  "% Sales Difference",
        "notes":      "Store as decimal",
    },
    {
        "field":      "gc_comp",
        "col_letter": "G",
        "col_index":  6,
        "source":     "ddcr",
        "pdf_field":  "Guest Count Comp %",
        "notes":      "Decimal; negatives shown as (2.07)% in PDF",
    },
    {
        "field":      "cash_plus_minus",
        "col_letter": "H",
        "col_index":  7,
        "source":     "ddcr",
        "pdf_field":  "Cash + / -",
        "notes":      "Dollar value; negatives shown as ($25.14) in PDF",
    },
    {
        "field":      "waste_combined",
        "col_letter": "I",
        "col_index":  8,
        "source":     "ddcr",
        "pdf_field":  "Total Waste %",
        "notes":      "Decimal e.g. 0.0028",
    },
    {
        "field":      "labour_proj",
        "col_letter": "J",
        "col_index":  9,
        "source":     "ddcr",
        "pdf_field":  "Projected Total Labour %",
        "notes":      "Decimal",
    },
    {
        "field":      "spch",
        "col_letter": "K",
        "col_index":  10,
        "source":     "ddcr",
        "pdf_field":  "Actual Crew SPCH",
        "notes":      "Dollar value",
    },
    {
        "field":      "ahr",
        "col_letter": "L",
        "col_index":  11,
        "source":     "ddcr",
        "pdf_field":  "Actual Crew AHR",
        "notes":      "Dollar value",
    },
    {
        "field":      "actual_hours",
        "col_letter": "M",
        "col_index":  12,
        "source":     "ddcr",
        "pdf_field":  "Actual Crew Hours",
        "notes":      "",
    },
    {
        "field":      "labour_actual",
        "col_letter": "N",
        "col_index":  13,
        "source":     "ddcr",
        "pdf_field":  "Actual Total Labour %",
        "notes":      "Decimal",
    },
    {
        "field":      "training_hours",
        "col_letter": "O",
        "col_index":  14,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE — leave null until confirmed",
    },
    {
        "field":      "sta_pct",
        "col_letter": "P",
        "col_index":  15,
        "source":     "ddcr",
        "pdf_field":  "SOC Percent",
        "notes":      "e.g. 100.00",
    },
    {
        "field":      "acpm",
        "col_letter": "Q",
        "col_index":  16,
        "source":     "ddcr",
        "pdf_field":  "Actual GCPCH",
        "notes":      "",
    },
    {
        "field":      "qcpm",
        "col_letter": "R",
        "col_index":  17,
        "source":     "ddcr",
        "pdf_field":  "Proj GCPCH",
        "notes":      "Confirm this mapping is correct",
    },
    # ── Unknown / TBC ────────────────────────────────────────────────────────
    {
        "field":      "kvs_peak",
        "col_letter": "S",
        "col_index":  18,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "kvs_shift",
        "col_letter": "T",
        "col_index":  19,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "r2p_peak",
        "col_letter": "U",
        "col_index":  20,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "r2p_shift",
        "col_letter": "V",
        "col_index":  21,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "side2_peak",
        "col_letter": "W",
        "col_index":  22,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "side2_shift",
        "col_letter": "X",
        "col_index":  23,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "delivery_time",
        "col_letter": "Y",
        "col_index":  24,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    # ── Sales Ledger fields ───────────────────────────────────────────────────
    {
        "field":      "refund",
        "col_letter": "Z",
        "col_index":  25,
        "source":     "sales_ledger",
        "pdf_field":  "EFT Refunds",
        "notes":      "Page 1 of Sales Ledger; Amt column of the EFT Refunds pair",
    },
    {
        "field":      "promo",
        "col_letter": "AA",
        "col_index":  26,
        "source":     "sales_ledger",
        "pdf_field":  "Promo Sales Amt",
        "notes":      "Page 3 of Sales Ledger",
    },
    {
        "field":      "manager_meal",
        "col_letter": "AB",
        "col_index":  27,
        "source":     "sales_ledger",
        "pdf_field":  "Mgr Meals Amt",
        "notes":      "Page 3 of Sales Ledger",
    },
    # ── DDCR continued ────────────────────────────────────────────────────────
    {
        "field":      "ros_mgr_hours",
        "col_letter": "AC",
        "col_index":  28,
        "source":     "ddcr",
        "pdf_field":  "Projected Crew Hours",
        "notes":      "Confirm: total crew hours or mgr-only?",
    },
    {
        "field":      "actual_mgr_hrs",
        "col_letter": "AD",
        "col_index":  29,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "sick_mgr_hr",
        "col_letter": "AE",
        "col_index":  30,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "sick_crew_hrs",
        "col_letter": "AF",
        "col_index":  31,
        "source":     None,
        "pdf_field":  None,
        "notes":      "UNKNOWN SOURCE",
    },
    {
        "field":      "cpm",
        "col_letter": "AG",
        "col_index":  32,
        "source":     "ddcr",
        "pdf_field":  "Actual Guest Count",
        "notes":      "Integer",
    },
    # ── QCR field ────────────────────────────────────────────────────────────
    {
        "field":      "qcr",
        "col_letter": "AH",
        "col_index":  33,
        "source":     "qcr_daily",
        "pdf_field":  "QCR % of Product Sold",
        "notes":      "Last page of QCR Daily PDF; food % only (not paper); store as decimal",
    },
    # ── Manual ───────────────────────────────────────────────────────────────
    {
        "field":      "events",
        "col_letter": "AI",
        "col_index":  34,
        "source":     "manual",
        "pdf_field":  None,
        "notes":      "Entered manually by Ruitan — always leave blank",
    },
]

# Convenience lookups
FIELD_BY_NAME   = {c["field"]: c for c in COLUMN_MAP}
FIELDS_BY_SOURCE = {}
for c in COLUMN_MAP:
    src = c["source"] or "unknown"
    FIELDS_BY_SOURCE.setdefault(src, []).append(c)

# ---------------------------------------------------------------------------
# Scorecard sheet layout constants
# ---------------------------------------------------------------------------

DATE_COL_INDEX   = 1    # pandas / 0-based: column B holds W/End dates
DATA_START_ROW   = 4    # 1-based Excel row where data begins (row 4 = first data row)
HEADER_ROW       = 3    # 1-based: row 3 holds column labels
TARGETS_ROW      = 2    # 1-based: row 2 holds target values

# Row labels used to navigate the month structure
MONTH_END_PREFIX  = "Monthend:"           # e.g. "Monthend: April"
MONTH_END_PREFIX2 = "Month End:"          # alternate capitalisation seen in file
TARGET_SUFFIX     = "Target"              # e.g. "April Target"
QUARTER_PREFIX    = "Quarter"             # e.g. "Quarter 3"
