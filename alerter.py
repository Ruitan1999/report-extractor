"""
alerter.py

Sends alert emails when a store's PDFs are missing or extraction fails.
Never aborts the main pipeline — just records and notifies.

Console mode (default): prints alerts to stdout.
Email mode: activated when ALERT_EMAIL env var is set AND either
  GMAIL_OAUTH_CREDENTIALS (uses Gmail API) or SMTP_* vars are set.
"""

import os
import smtplib
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ALERT_EMAIL = os.environ.get("ALERT_EMAIL")
SMTP_HOST   = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER   = os.environ.get("SMTP_USER")
SMTP_PASS   = os.environ.get("SMTP_PASS")

USE_EMAIL = bool(ALERT_EMAIL and SMTP_USER and SMTP_PASS)

# Accumulated issues for the current run — sent as one digest at the end
_issues: list[dict] = []


def record_issue(store: str, report_type: str, error: str):
    """Record a problem. Call this anywhere in the pipeline."""
    _issues.append({
        "store":       store,
        "report_type": report_type,
        "error":       error,
    })
    print(f"  [ALERT] {store} | {report_type} | {error}")


def send_digest(run_date: date = None):
    """
    Send (or print) all accumulated issues as a single digest.
    Call once at the end of main.py.
    """
    if not _issues:
        print("[ALERT] No issues to report.")
        return

    if run_date is None:
        run_date = date.today()

    subject = f"Store Report Automation — {len(_issues)} issue(s) on {run_date}"
    lines = [f"Run date: {run_date}", f"Total issues: {len(_issues)}", ""]
    for i in _issues:
        lines.append(f"Store:  {i['store']}")
        lines.append(f"Report: {i['report_type']}")
        lines.append(f"Error:  {i['error']}")
        lines.append("")

    body = "\n".join(lines)

    if not USE_EMAIL:
        print(f"\n{'='*60}")
        print(f"ALERT DIGEST — {subject}")
        print("=" * 60)
        print(body)
        return

    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = ALERT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ALERT_EMAIL, msg.as_string())
        print(f"[ALERT] Digest sent to {ALERT_EMAIL}")
    except Exception as e:
        print(f"[ALERT] Failed to send email: {e}")
        print(body)


def clear():
    """Reset issue list (for tests)."""
    _issues.clear()
