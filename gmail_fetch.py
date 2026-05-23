"""
gmail_fetch.py

Fetches today's report PDFs from Gmail for each store.

Two modes:
  LOCAL (default): returns paths to PDF files in a local directory.
    Used for development without Gmail credentials.
  GOOGLE: uses Gmail API with OAuth2.
    Activated when GMAIL_OAUTH_CREDENTIALS env var is set.

Usage (standalone test):
    python gmail_fetch.py
"""

import os
import base64
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import config

# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

GMAIL_CREDENTIALS = os.environ.get("GMAIL_OAUTH_CREDENTIALS")
GMAIL_TOKEN       = os.environ.get("GMAIL_TOKEN")
USE_GMAIL = bool(GMAIL_CREDENTIALS and GMAIL_TOKEN)

if USE_GMAIL:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    _creds = Credentials.from_authorized_user_info(
        json.loads(GMAIL_TOKEN),
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    if _creds.expired and _creds.refresh_token:
        _creds.refresh(Request())

    _gmail = build("gmail", "v1", credentials=_creds)


# Local development: point at this folder for sample PDFs
LOCAL_SAMPLE_DIR = Path(__file__).parent / "Sample report"


# ---------------------------------------------------------------------------
# Report identification
# ---------------------------------------------------------------------------

def _identify_report_type(filename: str) -> str | None:
    """Return the report type key from config.REPORT_PATTERNS, or None."""
    name_lower = filename.lower()
    for report_type, pattern in config.REPORT_PATTERNS.items():
        if pattern.lower() in name_lower:
            return report_type
    return None


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------

def fetch_reports_local(sample_dir: Path = LOCAL_SAMPLE_DIR) -> dict:
    """
    Return a mapping of {store_tab: {report_type: pdf_path}} for all PDF
    files found in sample_dir. Used for local testing.

    Since sample PDFs are not organised by store, all PDFs are attributed
    to the first store (William St) for testing purposes.
    """
    if not sample_dir.exists():
        print(f"[WARN] Sample dir not found: {sample_dir}")
        return {}

    reports = {}
    test_store = config.STORES[0]["tab"]  # "William St"
    reports[test_store] = {}

    for pdf in sorted(sample_dir.glob("*.pdf")):
        report_type = _identify_report_type(pdf.name)
        if report_type:
            reports[test_store][report_type] = str(pdf)
            print(f"  [LOCAL] {pdf.name} -> {report_type}")
        else:
            print(f"  [LOCAL] {pdf.name} -> unrecognised (skipped)")

    return reports


# ---------------------------------------------------------------------------
# Gmail backend
# ---------------------------------------------------------------------------

def _search_messages(query: str) -> list:
    result = _gmail.users().messages().list(userId="me", q=query).execute()
    return result.get("messages", [])


def _download_attachments(message_id: str, dest_dir: Path) -> list[Path]:
    """Download all PDF attachments from a Gmail message. Returns saved paths."""
    msg = _gmail.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    saved = []
    parts = msg.get("payload", {}).get("parts", [])
    for part in parts:
        filename = part.get("filename", "")
        if not filename.lower().endswith(".pdf"):
            continue
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            continue
        att = _gmail.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        data = base64.urlsafe_b64decode(att["data"])
        dest = dest_dir / filename
        dest.write_bytes(data)
        saved.append(dest)
    return saved


def fetch_reports_gmail(target_date: date = None) -> dict:
    """
    For each store, search Gmail for emails from that store's sender
    received on or after target_date, download PDF attachments.

    Returns {store_tab: {report_type: pdf_path_str}}
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    after_epoch = int(target_date.strftime("%s")) if hasattr(target_date, "strftime") else 0
    after_str = target_date.strftime("%Y/%m/%d")

    reports = {}

    # NOTE: use mkdtemp (not TemporaryDirectory context manager) so the downloaded
    # PDFs persist for the rest of the pipeline run. The OS cleans up /var/folders
    # /tmp automatically.
    tmp_path = Path(tempfile.mkdtemp(prefix="report_extractor_"))

    for store in config.STORES:
        sender = store["sender"]
        tab    = store["tab"]

        query = f"from:{sender} after:{after_str} has:attachment filename:pdf"
        messages = _search_messages(query)

        if not messages:
            print(f"  [WARN] No emails found for {store['name']} ({sender})")
            continue

        store_reports = {}
        # Use the most recent matching message
        latest_msg = messages[0]
        pdfs = _download_attachments(latest_msg["id"], tmp_path)

        for pdf in pdfs:
            report_type = _identify_report_type(pdf.name)
            if report_type:
                store_reports[report_type] = str(pdf)

        if store_reports:
            reports[tab] = store_reports
            print(f"  [GMAIL] {store['name']}: {list(store_reports.keys())}")
        else:
            print(f"  [WARN] No recognised PDFs for {store['name']}")

    return reports


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def fetch_reports(target_date: date = None) -> dict:
    """
    Fetch reports for all stores. Returns {store_tab: {report_type: pdf_path}}.
    Uses Gmail if credentials present, otherwise local sample directory.
    """
    if USE_GMAIL:
        return fetch_reports_gmail(target_date)
    else:
        print("[LOCAL MODE] Using sample PDFs from:", LOCAL_SAMPLE_DIR)
        return fetch_reports_local()


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Backend: {'Gmail API' if USE_GMAIL else 'Local files'}")
    reports = fetch_reports()
    print("\nFetched reports:")
    for store_tab, store_reports in reports.items():
        print(f"  {store_tab}:")
        for rtype, path in store_reports.items():
            print(f"    {rtype:<20} {Path(path).name}")
