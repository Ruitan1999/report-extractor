"""
sheets_writer.py

Finds the correct row in the scorecard for a given store and date,
then writes the extracted KPI data to it.

Two backends:
  - LOCAL (default): reads/writes the .xlsx file directly using openpyxl.
    Used for development and testing without Google credentials.
  - GOOGLE: uses the Google Sheets API v4.
    Activated when GOOGLE_SHEETS_SERVICE_ACCOUNT env var is set.

Usage (standalone test):
    python sheets_writer.py
"""

import os
import re
import copy
import json
from datetime import date, datetime
from pathlib import Path

import openpyxl

import config

# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SHEETS_SERVICE_ACCOUNT")
_SHEET_ID             = os.environ.get("SCORECARD_SHEET_ID")
USE_GOOGLE = bool(_SERVICE_ACCOUNT_JSON and _SHEET_ID)

if USE_GOOGLE:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    _creds = service_account.Credentials.from_service_account_info(
        json.loads(_SERVICE_ACCOUNT_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    _sheets_service = build("sheets", "v4", credentials=_creds).spreadsheets()

# Local fallback workbook path
LOCAL_XLSX = Path(__file__).parent / "Weekly Scorecard tracker Q2 2026.xlsx"


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------

def normalise_date(d: date) -> str:
    """Return date as 'D/M/YY' string matching the scorecard format."""
    return f"{d.day}/{d.month}/{str(d.year)[2:]}"


# Label used in column B for the weekly summary row that follows each Sunday
WEEKLY_LABEL_PREFIX = "Week ending "


def _is_weekly_summary_row(cell_value) -> bool:
    """True if this cell is the 'Week ending D/M/YY' summary row label."""
    if cell_value is None:
        return False
    return str(cell_value).strip().startswith(WEEKLY_LABEL_PREFIX)


def _cell_matches_date(cell_value, target: date) -> bool:
    """
    Return True if the cell value represents the same date as target.
    Handles:
      - Python date / datetime objects (from openpyxl)
      - Text strings: 'D/M/YY', 'DD/MM/YY', 'D/M/YYYY'

    'Week ending D/M/YY' rows are NEVER matched here — they have a separate
    finder so daily writes don't accidentally overwrite weekly summary rows.
    """
    if cell_value is None:
        return False

    # Skip the weekly summary rows — they have their own date but represent
    # weekly totals, not a daily row
    if _is_weekly_summary_row(cell_value):
        return False

    if isinstance(cell_value, (datetime, date)):
        d = cell_value.date() if isinstance(cell_value, datetime) else cell_value
        if d == target:
            return True
        # Some cells have month/day swapped (AU dates entered on US-locale Excel).
        # Try the swapped interpretation when both values are valid month numbers.
        try:
            return date(d.year, d.day, d.month) == target
        except ValueError:
            return False

    s = str(cell_value).strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%-d/%-m/%y", "%-d/%-m/%Y"):
        try:
            return datetime.strptime(s, fmt).date() == target
        except ValueError:
            pass

    # Try splitting manually for short formats like "19/4/26"
    parts = s.split("/")
    if len(parts) == 3:
        try:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            year = year + 2000 if year < 100 else year
            return date(year, month, day) == target
        except (ValueError, TypeError):
            pass

    return False


def _is_month_end_row(cell_value) -> bool:
    """True if this cell is the monthly aggregate row."""
    if cell_value is None:
        return False
    s = str(cell_value).strip().lower()
    return s.startswith("monthend:") or s.startswith("month end:")


def _is_target_row(cell_value) -> bool:
    """True if this is a [Month] Target label row (skip when searching)."""
    if cell_value is None:
        return False
    s = str(cell_value).strip().lower()
    return s.endswith("target") or s.startswith("quarter")


# ---------------------------------------------------------------------------
# Row finder — shared logic
# ---------------------------------------------------------------------------

def _find_or_plan_row(date_col_values: list, target: date) -> dict:
    """
    Given a list of (row_index_0based, cell_value) tuples from column B,
    determine what action to take.

    Returns:
      {"action": "overwrite", "row_index": int}   — row exists, overwrite it
      {"action": "insert",    "row_index": int}   — insert before this row index
      {"action": "append",    "row_index": int}   — append at this row index
    """
    monthend_row = None
    for idx, val in date_col_values:
        if _cell_matches_date(val, target):
            return {"action": "overwrite", "row_index": idx}
        if _is_month_end_row(val):
            monthend_row = idx  # keep updating — want the one in the right month

    # No existing row — insert before the Monthend row of the right month
    if monthend_row is not None:
        return {"action": "insert", "row_index": monthend_row}

    # Fallback: append after last non-empty row
    last_data = max(
        (idx for idx, val in date_col_values if val is not None and not _is_target_row(val)),
        default=config.DATA_START_ROW - 1,
    )
    return {"action": "append", "row_index": last_data + 1}


# ---------------------------------------------------------------------------
# Local (openpyxl) backend
# ---------------------------------------------------------------------------

def _row_data_to_list(row_data: dict, date_str: str) -> list:
    """
    Convert scorecard field dict → ordered list of values for the full row.
    Index 0 = col A (blank), index 1 = col B (date), index 2+ = KPI fields.
    """
    n_cols = max(c["col_index"] for c in config.COLUMN_MAP) + 1
    values = [None] * (n_cols + 1)   # +1 for col A
    values[0] = None                  # col A always blank
    values[1] = date_str             # col B = date
    for col in config.COLUMN_MAP:
        if col["source"] == "manual":
            continue
        values[col["col_index"]] = row_data.get(col["field"])
    return values


def write_row_local(
    store_tab: str,
    target_date: date,
    row_data: dict,
    xlsx_path: Path = LOCAL_XLSX,
    output_path: Path = None,
) -> str:
    """
    Write a row of KPI data to the local xlsx file.

    store_tab   : sheet tab name e.g. 'William St'
    target_date : the date this row represents
    row_data    : dict of {field_name: value} matching config.COLUMN_MAP
    xlsx_path   : source workbook (default: the reference scorecard)
    output_path : where to save the result (default: overwrites xlsx_path)

    Returns a description of the action taken.
    """
    if output_path is None:
        output_path = xlsx_path

    wb = openpyxl.load_workbook(xlsx_path)

    if store_tab not in wb.sheetnames:
        raise ValueError(f"Sheet tab '{store_tab}' not found. Available: {wb.sheetnames}")

    ws = wb[store_tab]
    date_col = config.DATE_COL_INDEX + 1  # openpyxl is 1-based

    # Collect column B values with their 0-based row index
    date_col_values = []
    for row in ws.iter_rows(
        min_row=config.DATA_START_ROW,
        max_row=ws.max_row,
        min_col=date_col,
        max_col=date_col,
    ):
        cell = row[0]
        date_col_values.append((cell.row - 1, cell.value))  # store 0-based

    plan = _find_or_plan_row(date_col_values, target_date)
    date_str = normalise_date(target_date)
    values = _row_data_to_list(row_data, date_str)

    if plan["action"] == "overwrite":
        excel_row = plan["row_index"] + 1  # back to 1-based
        for col_idx, val in enumerate(values, start=1):
            ws.cell(row=excel_row, column=col_idx, value=val)
        action_desc = f"Overwrote row {excel_row}"

    elif plan["action"] in ("insert", "append"):
        excel_row = plan["row_index"] + 1
        if plan["action"] == "insert":
            ws.insert_rows(excel_row)
        for col_idx, val in enumerate(values, start=1):
            ws.cell(row=excel_row, column=col_idx, value=val)
        action_desc = f"{'Inserted' if plan['action'] == 'insert' else 'Appended'} row at {excel_row}"

    wb.save(output_path)
    return action_desc


# ---------------------------------------------------------------------------
# Google Sheets backend
# ---------------------------------------------------------------------------

def write_row_google(store_tab: str, target_date: date, row_data: dict) -> str:
    """
    Write a row of KPI data via Google Sheets API.
    Only available when GOOGLE_SHEETS_SERVICE_ACCOUNT and SCORECARD_SHEET_ID are set.
    """
    if not USE_GOOGLE:
        raise RuntimeError("Google credentials not configured.")

    date_col_letter = "B"
    date_str = normalise_date(target_date)

    # Read column B to find the right row
    range_name = f"'{store_tab}'!B:B"
    result = _sheets_service.values().get(
        spreadsheetId=_SHEET_ID,
        range=range_name,
    ).execute()
    col_b = result.get("values", [])

    date_col_values = []
    for i, row in enumerate(col_b):
        val = row[0] if row else None
        date_col_values.append((i, val))

    plan = _find_or_plan_row(date_col_values, target_date)
    values = _row_data_to_list(row_data, date_str)
    values_2d = [values]

    if plan["action"] == "overwrite":
        excel_row = plan["row_index"] + 1
        range_str = f"'{store_tab}'!A{excel_row}"
        _sheets_service.values().update(
            spreadsheetId=_SHEET_ID,
            range=range_str,
            valueInputOption="USER_ENTERED",
            body={"values": values_2d},
        ).execute()
        action_desc = f"Overwrote row {excel_row}"

    else:
        # Insert requires batchUpdate for inserting a blank row, then update
        excel_row = plan["row_index"] + 1
        sheet_id = _get_sheet_id_by_name(store_tab)

        if plan["action"] == "insert":
            _sheets_service.batchUpdate(
                spreadsheetId=_SHEET_ID,
                body={
                    "requests": [{
                        "insertDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": excel_row - 1,
                                "endIndex": excel_row,
                            },
                            "inheritFromBefore": True,
                        }
                    }]
                },
            ).execute()

        range_str = f"'{store_tab}'!A{excel_row}"
        _sheets_service.values().update(
            spreadsheetId=_SHEET_ID,
            range=range_str,
            valueInputOption="USER_ENTERED",
            body={"values": values_2d},
        ).execute()
        action_desc = f"{'Inserted' if plan['action'] == 'insert' else 'Appended'} row at {excel_row}"

    return action_desc


def _get_sheet_id_by_name(tab_name: str) -> int:
    """Return the numeric sheetId for a named tab."""
    meta = _sheets_service.get(spreadsheetId=_SHEET_ID).execute()
    for sheet in meta["sheets"]:
        if sheet["properties"]["title"] == tab_name:
            return sheet["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_name}' not found in spreadsheet.")


# ---------------------------------------------------------------------------
# Unified write entry point
# ---------------------------------------------------------------------------

def write_row(store_tab: str, target_date: date, row_data: dict, output_path: Path = None) -> str:
    """
    Write to Google Sheets if credentials available, otherwise local xlsx.
    """
    if USE_GOOGLE:
        return write_row_google(store_tab, target_date, row_data)
    else:
        return write_row_local(store_tab, target_date, row_data, output_path=output_path)


# ---------------------------------------------------------------------------
# Weekly summary row — inserts/overwrites a "Week ending D/M/YY" row
# immediately after the matching Sunday daily row.
# ---------------------------------------------------------------------------

def _weekly_label(sunday_date: date) -> str:
    return f"{WEEKLY_LABEL_PREFIX}{normalise_date(sunday_date)}"


def _plan_weekly_row(date_col_values: list, sunday_date: date) -> dict:
    """
    Decide where the 'Week ending D/M/YY' row should go.

    Strategy:
      1. If a matching weekly summary row already exists → overwrite it.
      2. Otherwise find the Sunday daily row → insert immediately after it.
      3. If no Sunday daily row exists → fall back to insert-before-Monthend.
    """
    target_label = _weekly_label(sunday_date)
    sunday_row = None
    monthend_row = None

    for idx, val in date_col_values:
        # Already present? Overwrite it.
        if val is not None and str(val).strip() == target_label:
            return {"action": "overwrite", "row_index": idx}
        # Track the Sunday daily row (needed for insert-after position)
        if _cell_matches_date(val, sunday_date):
            sunday_row = idx
        if _is_month_end_row(val):
            monthend_row = idx

    if sunday_row is not None:
        # Insert immediately AFTER the Sunday daily row
        return {"action": "insert", "row_index": sunday_row + 1}

    if monthend_row is not None:
        return {"action": "insert", "row_index": monthend_row}

    last_data = max(
        (idx for idx, val in date_col_values if val is not None and not _is_target_row(val)),
        default=config.DATA_START_ROW - 1,
    )
    return {"action": "append", "row_index": last_data + 1}


def write_weekly_summary_row_local(
    store_tab: str,
    sunday_date: date,
    row_data: dict,
    xlsx_path: Path = LOCAL_XLSX,
    output_path: Path = None,
) -> str:
    if output_path is None:
        output_path = xlsx_path

    wb = openpyxl.load_workbook(xlsx_path)
    if store_tab not in wb.sheetnames:
        raise ValueError(f"Sheet tab '{store_tab}' not found. Available: {wb.sheetnames}")

    ws = wb[store_tab]
    date_col = config.DATE_COL_INDEX + 1

    date_col_values = []
    for row in ws.iter_rows(
        min_row=config.DATA_START_ROW,
        max_row=ws.max_row,
        min_col=date_col,
        max_col=date_col,
    ):
        cell = row[0]
        date_col_values.append((cell.row - 1, cell.value))

    plan = _plan_weekly_row(date_col_values, sunday_date)
    label = _weekly_label(sunday_date)
    values = _row_data_to_list(row_data, label)

    excel_row = plan["row_index"] + 1

    if plan["action"] == "overwrite":
        for col_idx, val in enumerate(values, start=1):
            ws.cell(row=excel_row, column=col_idx, value=val)
        action_desc = f"Overwrote weekly row {excel_row}"
    else:
        if plan["action"] == "insert":
            ws.insert_rows(excel_row)
        for col_idx, val in enumerate(values, start=1):
            ws.cell(row=excel_row, column=col_idx, value=val)
        action_desc = f"{'Inserted' if plan['action'] == 'insert' else 'Appended'} weekly row at {excel_row}"

    wb.save(output_path)
    return action_desc


def write_weekly_summary_row_google(store_tab: str, sunday_date: date, row_data: dict) -> str:
    if not USE_GOOGLE:
        raise RuntimeError("Google credentials not configured.")

    label = _weekly_label(sunday_date)

    # Read column B
    result = _sheets_service.values().get(
        spreadsheetId=_SHEET_ID,
        range=f"'{store_tab}'!B:B",
    ).execute()
    col_b = result.get("values", [])

    date_col_values = [(i, (row[0] if row else None)) for i, row in enumerate(col_b)]

    plan = _plan_weekly_row(date_col_values, sunday_date)
    values = _row_data_to_list(row_data, label)
    values_2d = [values]
    excel_row = plan["row_index"] + 1

    if plan["action"] == "overwrite":
        _sheets_service.values().update(
            spreadsheetId=_SHEET_ID,
            range=f"'{store_tab}'!A{excel_row}",
            valueInputOption="USER_ENTERED",
            body={"values": values_2d},
        ).execute()
        return f"Overwrote weekly row {excel_row}"

    sheet_id = _get_sheet_id_by_name(store_tab)
    if plan["action"] == "insert":
        _sheets_service.batchUpdate(
            spreadsheetId=_SHEET_ID,
            body={
                "requests": [{
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": excel_row - 1,
                            "endIndex": excel_row,
                        },
                        "inheritFromBefore": True,
                    }
                }]
            },
        ).execute()

    _sheets_service.values().update(
        spreadsheetId=_SHEET_ID,
        range=f"'{store_tab}'!A{excel_row}",
        valueInputOption="USER_ENTERED",
        body={"values": values_2d},
    ).execute()
    return f"{'Inserted' if plan['action'] == 'insert' else 'Appended'} weekly row at {excel_row}"


def write_weekly_summary_row(store_tab: str, sunday_date: date, row_data: dict, output_path: Path = None) -> str:
    """
    Insert/overwrite a 'Week ending D/M/YY' summary row immediately after
    the corresponding Sunday daily row. Uses the same column layout as a
    daily row — only column B differs (label instead of date string).
    """
    if USE_GOOGLE:
        return write_weekly_summary_row_google(store_tab, sunday_date, row_data)
    else:
        return write_weekly_summary_row_local(store_tab, sunday_date, row_data, output_path=output_path)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import date as dt

    output = Path(__file__).parent / "test_output.xlsx"

    # Fake row data matching the William St week-ending 19/4/26 known values
    test_row = {
        "projected_sales":  118417.00,
        "actual_sales":     128825.17,
        "sales_comp_pct":   0.1128,
        "sales_proj_opp":   0.0879,
        "gc_comp":          0.1103,
        "cash_plus_minus":  -17.49,
        "waste_combined":   0.0028,
        "labour_proj":      0.2508,
        "spch":             174.55,
        "ahr":              28.22,
        "actual_hours":     738.04,
        "labour_actual":    0.2031,
        "training_hours":   None,
        "sta_pct":          100.00,
        "acpm":             14.86,
        "qcpm":             10.37,
        "kvs_peak":         None,
        "kvs_shift":        None,
        "r2p_peak":         None,
        "r2p_shift":        None,
        "side2_peak":       None,
        "side2_shift":      None,
        "delivery_time":    None,
        "refund":           140.95,
        "promo":            6422.12,
        "manager_meal":     625.09,
        "ros_mgr_hours":    847.00,
        "actual_mgr_hrs":   None,
        "sick_mgr_hr":      None,
        "sick_crew_hrs":    None,
        "cpm":              10968,
        "qcr":              0.2599,
        "events":           None,
    }

    target = dt(2026, 4, 19)  # Sunday 19 April 2026

    print(f"Writing test row for William St | {normalise_date(target)}")
    print(f"Backend: {'Google Sheets' if USE_GOOGLE else 'Local xlsx'}")
    print(f"Output:  {output if not USE_GOOGLE else _SHEET_ID}")

    action = write_row("William St", target, test_row, output_path=output)
    print(f"Result:  {action}")

    if not USE_GOOGLE:
        # Verify by reading back
        wb = openpyxl.load_workbook(output)
        ws = wb["William St"]
        print("\nVerification — reading back written values:")
        for row in ws.iter_rows(min_row=4, max_row=ws.max_row):
            b_val = row[1].value  # column B
            if b_val is not None and "19" in str(b_val) and "4" in str(b_val):
                print(f"  Row {row[0].row}: date={b_val}")
                # Print a few key cells
                for col in config.COLUMN_MAP[:6]:
                    cell_val = row[col["col_index"]].value
                    print(f"    {col['field']:<22} = {cell_val}")
                break
