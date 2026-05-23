"""
main.py

Orchestrates the full daily pipeline:
  1. Fetch PDFs from Gmail (or local sample dir)
  2. Extract KPI data from each PDF
  3. Write to the scorecard (Google Sheets or local xlsx)
  4. Send alert digest if anything failed

Run manually:
    python main.py

Run for a specific date (useful for backfilling):
    python main.py 2026-04-13
"""

import sys
from datetime import date, datetime

import config
import gmail_fetch
import pdf_extractor
import sheets_writer
import alerter


def run(target_date: date = None):
    if target_date is None:
        target_date = date.today() - __import__("datetime").timedelta(days=1)

    print(f"\n{'='*60}")
    print(f"Store Report Automation — {target_date}")
    print(f"  Extractor: Pure regex (no API key required)")
    print(f"  Gmail:     {'LIVE' if gmail_fetch.USE_GMAIL else 'LOCAL'}")
    print(f"  Sheets:    {'Google Sheets' if sheets_writer.USE_GOOGLE else 'Local xlsx'}")
    print(f"{'='*60}\n")

    # ── Step 1: Fetch PDFs ────────────────────────────────────────────────
    print("Step 1: Fetching PDFs...")
    reports = gmail_fetch.fetch_reports(target_date)

    if not reports:
        alerter.record_issue("ALL", "gmail", "No reports fetched for any store")
        alerter.send_digest(target_date)
        return

    # ── Step 2 & 3: Extract + Write, per store ────────────────────────────
    for store in config.STORES:
        tab  = store["tab"]
        name = store["name"]

        store_reports = reports.get(tab)
        if not store_reports:
            alerter.record_issue(name, "all", "No PDFs found in email")
            continue

        print(f"\n-- {name} --")

        # Check required reports are present
        ddcr_path   = store_reports.get("ddcr")
        qcr_path    = store_reports.get("qcr_daily")
        ledger_path = store_reports.get("sales_ledger")

        if not ddcr_path:
            alerter.record_issue(name, "ddcr", "DDCR PDF not found")
        if not qcr_path:
            alerter.record_issue(name, "qcr_daily", "QCR Daily PDF not found")
        if not ledger_path:
            alerter.record_issue(name, "sales_ledger", "Sales Ledger PDF not found")

        if not ddcr_path:
            print(f"  Skipping {name} — no DDCR")
            continue

        # Extract
        try:
            ddcr_date_str = f"{target_date.day:02d}/{target_date.month:02d}/{target_date.year}"
            row_data = {}

            # DDCR (primary — required)
            ddcr_raw = pdf_extractor.extract_ddcr(ddcr_path, ddcr_date_str)
            row_data.update(pdf_extractor.ddcr_to_scorecard_row(ddcr_raw))

            # Sales Ledger (optional)
            if ledger_path:
                try:
                    ledger_data = pdf_extractor.extract_sales_ledger(
                        ledger_path, target_date.day
                    )
                    row_data.update(ledger_data)
                except Exception as e:
                    alerter.record_issue(name, "sales_ledger", str(e))

            # QCR Daily (optional)
            if qcr_path:
                try:
                    qcr_data = pdf_extractor.extract_qcr_daily(qcr_path)
                    row_data.update(qcr_data)
                except Exception as e:
                    alerter.record_issue(name, "qcr_daily", str(e))

        except Exception as e:
            alerter.record_issue(name, "ddcr", f"Extraction failed: {e}")
            print(f"  [ERROR] Extraction failed: {e}")
            continue

        # Write to scorecard
        try:
            action = sheets_writer.write_row(tab, target_date, row_data)
            print(f"  Scorecard: {action}")
        except Exception as e:
            alerter.record_issue(name, "sheets", f"Write failed: {e}")
            print(f"  [ERROR] Write failed: {e}")

        # Record this store's KPIs for the daily digest email
        alerter.record_store_result(name, row_data)

        # If this is a Sunday, also write a 'Week ending D/M/YY' summary row
        # containing the DDCR Week Total column + Sales Ledger Week Tot row
        if target_date.weekday() == 6:  # Monday=0 ... Sunday=6
            try:
                wt_row = {}
                wt_ddcr = pdf_extractor.extract_ddcr(ddcr_path, 'Week Total')
                wt_row.update(pdf_extractor.ddcr_to_scorecard_row(wt_ddcr))

                if ledger_path:
                    try:
                        wt_row.update(pdf_extractor.extract_sales_ledger(
                            ledger_path, target_date.day, week_total=True,
                        ))
                    except Exception as e:
                        alerter.record_issue(name, "sales_ledger_weekly", str(e))

                if qcr_path:
                    try:
                        wt_row.update(pdf_extractor.extract_qcr_daily(qcr_path))
                    except Exception as e:
                        alerter.record_issue(name, "qcr_daily_weekly", str(e))

                wt_action = sheets_writer.write_weekly_summary_row(tab, target_date, wt_row)
                print(f"  Weekly:    {wt_action}")
            except Exception as e:
                alerter.record_issue(name, "sheets_weekly", f"Weekly write failed: {e}")
                print(f"  [ERROR] Weekly write failed: {e}")

    # ── Step 4: Alert digest ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    alerter.send_digest(target_date)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            target = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid date format '{sys.argv[1]}' — use YYYY-MM-DD")
            sys.exit(1)
    else:
        target = None

    run(target)
