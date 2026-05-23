"""
alerter.py

Sends a daily digest email after every pipeline run containing:
  1. A KPI summary table — one row per store, one column per key metric
  2. A list of any issues (missing reports, extraction failures, etc.)

Console mode (default): prints the digest to stdout.
Email mode: activated when ALERT_EMAIL, SMTP_USER, and SMTP_PASS env vars are all set.
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

# Key KPI fields surfaced in the daily summary table.
# Each entry: (column header, field key in extracted dict, formatter function)
SUMMARY_FIELDS = [
    ("Projected Sales", "projected_sales", lambda v: f"${v:,.0f}"           if v is not None else ""),
    ("Actual Sales",    "actual_sales",    lambda v: f"${v:,.0f}"           if v is not None else ""),
    ("Sales Comp",      "sales_comp_pct",  lambda v: f"{v*100:.2f}%"        if v is not None else ""),
    ("Sales Proj Opp",  "sales_proj_opp",  lambda v: f"{v*100:.2f}%"        if v is not None else ""),
    ("GC Comp",         "gc_comp",         lambda v: f"{v*100:.2f}%"        if v is not None else ""),
    ("Cash +/-",        "cash_plus_minus", lambda v: f"${v:,.2f}"           if v is not None else ""),
    ("Waste",           "waste_combined",  lambda v: f"{v*100:.2f}%"        if v is not None else ""),
    ("Labour Proj",     "labour_proj",     lambda v: f"{v*100:.2f}%"        if v is not None else ""),
    ("SPCH",            "spch",            lambda v: f"${v:,.2f}"           if v is not None else ""),
    ("AHR",             "ahr",             lambda v: f"${v:,.2f}"           if v is not None else ""),
]

# Accumulated state for the current run — flushed by send_digest()
_issues: list[dict] = []
_store_results: list[dict] = []


def record_issue(store: str, report_type: str, error: str):
    """Record a problem. Call this anywhere in the pipeline."""
    _issues.append({
        "store":       store,
        "report_type": report_type,
        "error":       error,
    })
    print(f"  [ALERT] {store} | {report_type} | {error}")


def record_store_result(store: str, kpi_data: dict):
    """Record extracted KPI data for a store that processed successfully."""
    _store_results.append({"store": store, "data": kpi_data})


def _render_text_table(run_date: date) -> str:
    """Plain text rendering of the KPI summary + issues — used for stdout/fallback."""
    lines = [f"=== Daily Store Report — {run_date} ===", ""]

    if _store_results:
        headers = ["Store"] + [label for label, _, _ in SUMMARY_FIELDS]
        rows = [headers]
        for result in _store_results:
            row = [result["store"]]
            for _, key, fmt in SUMMARY_FIELDS:
                row.append(fmt(result["data"].get(key)))
            rows.append(row)
        # Compute column widths
        widths = [max(len(r[i]) for r in rows) for i in range(len(headers))]
        for r in rows:
            lines.append("  ".join(c.ljust(w) for c, w in zip(r, widths)))
        lines.append("")

    if _issues:
        lines.append(f"-- Issues ({len(_issues)}) --")
        for i in _issues:
            lines.append(f"  [{i['store']}] {i['report_type']}: {i['error']}")
    else:
        lines.append("-- No issues --")

    return "\n".join(lines)


def _render_html(run_date: date) -> str:
    """HTML email body — KPI table + issues."""
    parts = [
        '<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#222;">',
        f'<h2 style="margin:0 0 12px 0;">Daily Store Report — {run_date}</h2>',
    ]

    if _store_results:
        parts.append('<table cellspacing="0" cellpadding="6" '
                     'style="border-collapse:collapse;border:1px solid #ccc;">')
        # Header row
        parts.append('<thead><tr style="background:#f4f4f4;text-align:left;">')
        parts.append('<th style="border:1px solid #ccc;">Store</th>')
        for label, _, _ in SUMMARY_FIELDS:
            parts.append(f'<th style="border:1px solid #ccc;text-align:right;">{label}</th>')
        parts.append('</tr></thead><tbody>')
        # Data rows
        for result in _store_results:
            parts.append('<tr>')
            parts.append(f'<td style="border:1px solid #ccc;font-weight:bold;">{result["store"]}</td>')
            for _, key, fmt in SUMMARY_FIELDS:
                val = fmt(result["data"].get(key))
                parts.append(f'<td style="border:1px solid #ccc;text-align:right;">{val}</td>')
            parts.append('</tr>')
        parts.append('</tbody></table>')
    else:
        parts.append('<p><em>No store data extracted this run.</em></p>')

    # Issues section
    if _issues:
        parts.append(f'<h3 style="margin-top:24px;color:#b00;">Issues ({len(_issues)})</h3>')
        parts.append('<ul style="padding-left:20px;">')
        for i in _issues:
            parts.append(
                f'<li><b>{i["store"]}</b> — {i["report_type"]}: '
                f'<span style="color:#444;">{i["error"]}</span></li>'
            )
        parts.append('</ul>')
    else:
        parts.append('<p style="color:#080;margin-top:24px;">'
                     'No issues — all stores processed successfully.</p>')

    parts.append('</body></html>')
    return "".join(parts)


def send_digest(run_date: date = None):
    """
    Send (or print) the daily digest: KPI summary table + issues.
    Call once at the end of main.py.
    """
    if run_date is None:
        run_date = date.today()

    issue_count = len(_issues)
    store_count = len(_store_results)

    if issue_count == 0:
        subject = f"Daily Store Report — {run_date} ({store_count} stores OK)"
    else:
        subject = (f"Daily Store Report — {run_date} "
                   f"({store_count} OK, {issue_count} issue{'s' if issue_count != 1 else ''})")

    text_body = _render_text_table(run_date)

    if not USE_EMAIL:
        print(f"\n{'='*60}")
        print(f"DIGEST — {subject}")
        print("=" * 60)
        print(text_body)
        return

    html_body = _render_html(run_date)

    msg = MIMEMultipart("alternative")
    msg["From"]    = SMTP_USER
    msg["To"]      = ALERT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ALERT_EMAIL, msg.as_string())
        print(f"[DIGEST] Sent to {ALERT_EMAIL}")
    except Exception as e:
        print(f"[DIGEST] Failed to send email: {e}")
        print(text_body)


def clear():
    """Reset state (for tests)."""
    _issues.clear()
    _store_results.clear()


# ---------------------------------------------------------------------------
# Standalone test — fake data, prints to stdout
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import date as dt
    clear()
    record_store_result("William St", {
        "projected_sales": 13788.0, "actual_sales": 15168.7, "sales_comp_pct": 0.0754,
        "sales_proj_opp": 0.1001, "gc_comp": 0.062, "cash_plus_minus": 11.50,
        "waste_combined": 0.005, "labour_proj": 0.2443, "spch": 146.88, "ahr": 27.10,
    })
    record_store_result("Hay St", {
        "projected_sales": 10500.0, "actual_sales": 11200.0, "sales_comp_pct": 0.05,
        "sales_proj_opp": 0.067, "gc_comp": 0.03, "cash_plus_minus": -5.20,
        "waste_combined": 0.008, "labour_proj": 0.26, "spch": 130.0, "ahr": 28.0,
    })
    record_issue("Crown", "ddcr", "DDCR PDF not found in email")
    record_issue("Duncraig", "all", "No emails found for sender")
    send_digest(dt(2026, 4, 19))
